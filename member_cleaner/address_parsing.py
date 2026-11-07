"""Shared address-component recognition for the Member CSV Cleaner.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Locate supported suffix and unit boundaries without formatting
records, deciding eligibility, or verifying an address with an outside service.
Cleanup and later validation can reuse this module without importing each other.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import re

from .address_data import (
    USPS_DIRECTIONALS,
    USPS_STREET_SUFFIXES,
    USPS_UNIT_DESIGNATORS,
    USPS_UNIT_WITHOUT_RANGE,
)


# Longest labels come first; escaping keeps # and future punctuation literal.
# A label may be followed by whitespace, punctuation, or an attached number.
_UNIT_LABEL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(
        re.escape(label)
        for label in sorted(USPS_UNIT_DESIGNATORS, key=len, reverse=True)
    ) + r")\.?(?=\s|[0-9#.,]|$)",
    flags=re.IGNORECASE,
)


def street_suffix_index(parts: list[str]) -> int | None:

    """Locate a known suffix in the supported house/name/suffix shape.

    Args:
        parts: Street tokens with periods/commas already removed.

    Returns:
        The suffix's zero-based index, or None for an unsupported shape.
        An optional house-number fraction and final directional are allowed.

    This recognizes structure only; it does not prove the official street name.
    """

    if len(parts) < 3:
        return None

    if re.fullmatch(r"[0-9]+[A-Za-z]?(?:-[0-9]+[A-Za-z]?)?", parts[0]) is None:
        return None

    name_start = 1
    if re.fullmatch(r"[0-9]+/[0-9]+", parts[name_start]) is not None:
        name_start += 1

    suffix_index = len(parts) - 1
    if parts[-1].upper() in USPS_DIRECTIONALS:
        suffix_index -= 1

    street_name = " ".join(parts[name_start:suffix_index])
    if (parts[suffix_index].upper() not in USPS_STREET_SUFFIXES
            or not any(char.isalpha() for char in street_name)):
        return None

    return suffix_index


def unit_label_parts(value: str) -> tuple[str, str] | None:

    """Separate a leading recognized unit label from its identifier text.

    Args:
        value: Unit text, such as "Apartment 004b" or "#4B".

    Returns:
        An uppercase standard designator and the remaining text, or None
        when no label starts the value. Identifier punctuation is preserved.
    """

    text = " ".join(value.replace("#", " # ").split())
    match = _UNIT_LABEL_PATTERN.match(text)
    if match is None:
        return None

    code = USPS_UNIT_DESIGNATORS[match.group(1).upper()]
    return code, text[match.end():].strip()


def split_street_unit(value: str) -> tuple[str, str | None]:

    """Locate a trailing labelled unit after a recognizable base street.

    Args:
        value: Original combined Street text.

    Returns:
        Base street and unit text when a supported boundary is found.
        Otherwise, the original value and None. A missing unit identifier
        is left for cleanup to reject rather than being silently discarded.

    A unit word inside a street name is not enough: the preceding text must
    independently contain a supported house/name/suffix shape. Prefix units,
    unlabelled trailing identifiers, and unrecognized base streets are not
    inferred. Positional recognition still requires later review of ambiguity.
    """
    
    text = " ".join(value.replace("#", " # ").split())

    for match in _UNIT_LABEL_PATTERN.finditer(text):
        base = text[:match.start()].rstrip(" ,")
        base_parts = base.replace(".", "").replace(",", "").split()

        if street_suffix_index(base_parts) is not None:
            return base, text[match.start():]

    return value, None


def parse_unit_component(value: str) -> tuple[str, str] | None:

    """Recognize a supported unit and return its standard code and identifier.

    Args:
        value: Text already identified as a unit component. A bare identifier
            is permitted in this role and receives the generic # designator.

    Returns:
        Uppercase designator and identifier, or None for unusable input.
        An optional-range location such as Rear has an empty identifier.
        Leading zeros, hyphens, and slashes in identifiers remain intact.

    Cleanup renders these parts for display; validation compares their
    meaning. Keeping recognition here avoids an import cycle between those
    modules. Internal punctuation and multiple unit levels are not guessed.
    """
    
    text = " ".join(value.split())
    if not text:
        return None

    labelled = unit_label_parts(text)
    code, identifier = ("#", text) if labelled is None else labelled

    # Remove one redundant # after a known designator, never inside an ID.
    if code != "#" and identifier.startswith("#"):
        identifier = identifier[1:].strip()
    identifier = identifier.rstrip("., ")

    if not identifier:
        return (code, "") if code in USPS_UNIT_WITHOUT_RANGE else None

    if re.fullmatch(r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*", identifier) is None:
        return None
    if identifier.upper() in USPS_UNIT_DESIGNATORS:
        return None

    return code, identifier.upper()
