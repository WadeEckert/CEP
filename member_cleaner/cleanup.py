"""Field cleanup utilities for the Member CSV Cleaner.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Normalize member field formatting while keeping record
eligibility and review decisions separate from cleanup. Assemble supported
main-street and separate-unit components without discarding conflicts.
Normalize supported signing dates to MM/DD/YY while preserving originals
in the calling record workflow for later review.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import re
from datetime import date

from .validation import is_valid_email, parse_date_signed
from .address_data import (
    USPS_DIRECTIONALS,
    USPS_STATE_ABBREVIATIONS,
    USPS_STATE_CODES,
    USPS_STREET_SUFFIXES,
)
from .address_parsing import (
    parse_unit_component,
    split_street_unit,
    street_suffix_index,
    unit_label_parts,
)


def clean_name(value: str) -> str:

    """Clean one first-name or last-name field using conservative rules.

    Args:
        value: Original name text; use an empty string for a blank field.

    Returns:
        A new string with normalized whitespace, conservative title case,
        and periods removed from single-letter initials. Existing mixed
        case and other punctuation are preserved. Empty or whitespace-only
        text returns an empty string.

    Name parts are separated by whitespace or hyphens. Compound names
    remain in the supplied field. Eligibility and Anonymous Donor
    substitution are handled separately by validation.
    """

    # Create a new list for cleaned words, which may be hyphenated.
    cleaned_words: list[str] = []

    # .split() removes surrounding whitespace and skips repeated whitespace.
    for word in value.split():

        # Create a new list for cleaned parts of this word, which may be hyphenated
        cleaned_parts: list[str] = []

        # Rejoin these parts with hyphens so compound surnames stay intact.
        # .split("-") removes surrounding hyphens and skips repeated hyphens.
        # For example, "  smith-jones  " becomes ["smith", "jones"] and "o'neill" becomes ["o'neill"].
        for part in word.split("-"):
            # Remove a period only when this part is a single-letter initial.
            if len(part) == 2 and part[0].isalpha() and part[1] == ".":
                part = part[0]

            # Preserve existing mixed case, such as McDonald or O'Neill.
            # For example, "  o'neill  " becomes "O'Neill" and "mcDonald" becomes "McDonald".
            if part.islower() or part.isupper():
                part = part.title()

            cleaned_parts.append(part)

        # Join the cleaned parts with hyphens and add the result to the cleaned words list.
        # For example, ["smith", "jones"] becomes "Smith-Jones" and ["o'neill"] becomes "O'Neill".
        cleaned_words.append("-".join(cleaned_parts))

    # A single space separates words; joining an empty list returns "".
    return " ".join(cleaned_words)


def clean_phone(value: str) -> str:

    """Normalize one US phone field to ten ASCII digits or a blank string.

    Args:
        value: Original phone text; use an empty string for a blank field.

    Returns:
        Ten digits after removing common formatting and an optional US
        country code. Blank, unsupported, or incorrectly sized values
        return an empty string.

    Accepted formatting includes whitespace, parentheses, hyphens, and
    periods. A leading plus sign requires an eleven-digit number starting
    with 1. Letters, extensions, and multiple-number separators are rejected.
    This checks formatting and length, not service or mobile status.
    """

    text = value.strip()

    # Check the whole input before stripping punctuation or other characters.
    # The match pattern is a plus sign followed by digits, spaces, parentheses, hyphens, or periods.
    if re.fullmatch(r"\+?[0-9\s().-]+", text) is None:
        return ""

    # The preceding check ensures only permitted formatting is removed.
    digits = re.sub(r"[^0-9]", "", text)
    has_us_country_code = len(digits) == 11 and digits.startswith("1")

    # A plus sign must introduce a complete US country-code form.
    if text.startswith("+") and not has_us_country_code:
        return ""

    # Remove exactly one leading 1, only from an eleven-digit number.
    if has_us_country_code:
        digits = digits[1:]

    if len(digits) != 10:
        return ""

    return digits


def clean_zipcode(value: str) -> str:

    """Normalize a five-digit ZIP or hyphenated ZIP+4 to five digits.

    Args:
        value: Original ZIP text; use an empty string for a blank field.

    Returns:
        The five-digit base ZIP with leading zeros preserved. Blank,
        malformed, or unsupported values return an empty string.

    Only five digits or five digits followed by a hyphen and four digits
    are recognized. This checks structure, not whether a ZIP exists or
    matches an address. Original values must be retained for later review.
    """

    # Match the entire value so malformed text cannot be silently truncated.
    # The matched pattern is five digits, optionally followed by a hyphen and four digits.
    match = re.fullmatch(r"([0-9]{5})(?:-[0-9]{4})?", value.strip())

    if match is None:
        return ""

    # The first captured group is the base ZIP, still stored as text.
    return match.group(1)


def clean_email(value: str) -> str:

    """Trim one email field, repair a narrow typo, and validate the result.

    Args:
        value: Original email text; use an empty string for a blank field.

    Returns:
        A supported email address with surrounding whitespace removed and
        the domain lowercased. The part before @ is preserved. Blank,
        malformed, ambiguous, or unsupported values return an empty string.

    A single comma between one domain label and com/org/net/edu/gov/mil/us
    is treated as a mistyped period. Other comma patterns are not guessed.
    Internal whitespace and multiple addresses require review. Original
    values must be retained separately for that future review workflow.
    """

    # Remove surrounding whitespace and check for a single @ before splitting into local and domain parts.
    candidate = value.strip()

    # One address is required before considering any automatic correction.
    if candidate.count("@") != 1:
        return ""

    local_part, domain = candidate.split("@")

    # Match the whole domain so an existing dotted domain is not extended.
    comma_match = re.fullmatch(
        r"([A-Za-z0-9-]+),(com|org|net|edu|gov|mil|us)",
        domain,
        flags=re.IGNORECASE,
    )

    # If a single comma is found, replace it with a period and reassemble the address.
    if comma_match is not None:
        domain = comma_match.group(1) + "." + comma_match.group(2)
        candidate = local_part + "@" + domain

    # Validate before lowercasing so normalization does not admit unsupported characters.
    if not is_valid_email(candidate):
        return ""

    return local_part + "@" + domain.lower()


def clean_country(value: str) -> str:

    """Normalize explicit US country labels and preserve other entries.

    Args:
        value: Original country text; use an empty string for a blank field.

    Returns:
        "USA" for a recognized US alias, or an empty string for blank input.
        Other values retain their text with surrounding whitespace removed.

    Alias comparison ignores case and repeated whitespace. Unrecognized
    values are not assumed to mean the United States. Address status and
    review decisions are handled separately by validation.
    """

    text = value.strip()

    # A missing country must remain missing rather than defaulting to USA.
    if not text:
        return ""

    # Normalize a comparison key while retaining the text for other entries.
    # .join removes repeated whitespace, .casefold() ignores case for comparison, and .split() splits on whitespace.
    # For example, "  u.s.a.  " becomes "usa" and "United States of America" becomes "united states of america".
    comparison_key = " ".join(text.split()).casefold()
    us_aliases = {
        "us",
        "usa",
        "u.s",
        "u.s.",
        "u.s.a",
        "u.s.a.",
        "united states",
        "united states of america",
    }

    if comparison_key in us_aliases:
        return "USA"

    return text


def clean_state(value: str) -> str:

    """Normalize a recognized USPS state or postal-region entry.

    Args:
        value: Original state text; use an empty string for a blank field.

    Returns:
        An uppercase two-letter USPS code for a recognized name or code.
        Blank or unrecognized entries return an empty string.

    Periods and commas are removed, and comparison ignores case and extra
    whitespace. No state is inferred from a city or ZIP. Recognition does
    not determine country eligibility or postal deliverability; preserve
    original values separately for later validation and review.
    """

    # .replace removes periods and commas, .split() removes extra whitespace, and .upper() ignores case for comparison.
    # For example, "N.Y." becomes "NY" and "New York, NY" becomes "NEW YORK NY".
    text = value.replace(".", "").replace(",", "")
    comparison_key = " ".join(text.split()).upper()

    if comparison_key in USPS_STATE_CODES:
        return comparison_key

    # .get() finds a USPS code for a recognized full name, or returns "" for unrecognized names.
    # For example, "New York" becomes "NY" and "Narnia" becomes "".
    return USPS_STATE_ABBREVIATIONS.get(comparison_key, "")


def clean_city(value: str) -> str:

    """Format supplied city text without inferring missing address details.

    Args:
        value: Original city text; use an empty string for a blank field.

    Returns:
        City text with periods/commas removed, normalized whitespace, and
        conservative capitalization. Mixed case, hyphens, and apostrophes
        are preserved. Empty input, including text containing only periods,
        commas, or whitespace, returns an empty string.

    This reuses the name helper's text formatting only. It does not expand
    abbreviations, establish that a city exists, or determine address
    eligibility. Original values must be retained for later review.
    """

    # .replace() removes periods and commas.
    # For example, "St. Louis" becomes "St Louis" and "New York, NY" becomes "New York NY".
    text = value.replace(".", "").replace(",", "")

    # Pass the cleaned City text to the name helper for name formatting.
    # For example, "  new york  " becomes "New York" and "St. louis" becomes "St Louis".
    return clean_name(text)


def _clean_po_box(value: str) -> str | None:

    """Handle recognized PO-box input before general punctuation cleanup.

    Args:
        value: Original street text.

    Returns:
        A canonical "PO Box" label and numeric identifier when recognized.
        A blank string when the label is recognized but the number is
        missing or unsupported. None when no PO-box label is recognized.

    Accepts common PO/P.O./Post Office Box labels, an optional number
    marker #, and trailing periods/commas. Internal number punctuation,
    spaces, letters, or combined addresses require review.
    """
    # Remove repeated whitespace and check for a PO-box label at the start of the text.
    # For example, "  P.O. Box 123  " becomes "P.O. Box 123" and "Post Office Box #456 " becomes "Post Office Box #456".
    text = " ".join(value.split())

    # Use re.match to check for a PO-box label at the start of the text, ignoring case.
    label_match = re.match(
        r"(?:P\.?\s*O\.?\s*BOX|POST\s+OFFICE\s+BOX)"
        r"(?=\s|[0-9#.,]|$)", # Positive lookahead to ensure the label is followed by whitespace, a number, a #, a period, a comma, or the end of the string 
        text,
        flags=re.IGNORECASE,
    )

    if label_match is None:
        return None

    # Keep the number separate so removing punctuation cannot join digits.
    # .strip() removes surrounding whitespace, and .rstrip() removes trailing periods or commas.
    # For example, "P.O. Box 123." becomes "123" and "Post Office Box #456," becomes "#456".
    number_text = text[label_match.end():].strip().rstrip("., ")
    number_match = re.fullmatch(r"#?\s*([0-9]+)", number_text) # This regex matches an optional # followed by digits, ignoring whitespace between them

    if number_match is None:
        return ""

    # Keep the identifier as text, including any leading zeros.
    # .group(1) returns the first captured group, which is the numeric part of the PO-box identifier.
    # For example, "P.O. Box 00123" becomes "PO Box 00123" and "Post Office Box #0456" becomes "PO Box 0456".
    return "PO Box " + number_match.group(1)


def clean_unit(value: str) -> str:

    """Normalize one supported unit component without guessing its type.

    Args:
        value: Text explicitly identified as a unit component, not a whole
            street. A bare identifier is allowed only in this known role.

    Returns:
        A standard designator plus uppercase identifier, or a blank string
        for missing/unsupported input. Leading zeros, hyphens, and slashes
        in identifiers are retained. C2 locations such as Basement may
        stand alone; Apartment and most other designators need an identifier.

    A bare identifier becomes "# <identifier>", not an assumed apartment.
    Trailing periods/commas are formatting; internal punctuation and divided
    identifiers are not joined. Multiple unit levels require later review.
    Original values must be retained separately; this does not verify a unit.
    """

    parts = parse_unit_component(value)
    if parts is None:
        return ""

    # Recognition is shared with validation; this function handles display.
    code, identifier = parts
    return code.title() + " " + identifier if identifier else code.title()


def _abbreviate_street_parts(value: str, *, preserve_name: bool = False) -> str:

    """Apply positional suffix/directional rules to formatted street text.

    The supported shape is a numeric house token, an optional fraction,
    a street name, a known suffix, and an optional trailing directional.
    A leading directional is shortened only when another name follows.
    This is local parsing, not verification of the street's official name.
    The caller separates units first. Unusual forms require later review.
    """

    parts = value.split()

    suffix_index = street_suffix_index(parts)
    if suffix_index is None:
        return value

    name_start = 1

    if re.fullmatch(r"[0-9]+/[0-9]+", parts[name_start]) is not None:
        name_start += 1

    # The shared recognizer has already established the suffix's position.
    suffix = USPS_STREET_SUFFIXES[parts[suffix_index].upper()]
    parts[suffix_index] = suffix.title()

    if suffix_index < len(parts) - 1:
        parts[-1] = USPS_DIRECTIONALS[parts[-1].upper()]

    # A reviewer may be supplying a literal leading name such as North Star.
    if preserve_name:
        return " ".join(parts)

    predirection = USPS_DIRECTIONALS.get(parts[name_start].upper())

    if predirection is not None:
        already_abbreviated = parts[name_start].upper() == predirection
        has_name_after = suffix_index - name_start > 1

        if has_name_after:
            following_word = parts[name_start + 1]
            has_name_after = (
                following_word.upper() not in USPS_DIRECTIONALS
                and any(char.isalpha() for char in following_word)
            )

        if already_abbreviated or has_name_after:
            parts[name_start] = predirection

    return " ".join(parts)


def clean_street(value: str, *, preserve_name: bool = False) -> str:

    """Format PO boxes, supported base streets, and one trailing unit.

    Args:
        value: Original Street text; use an empty string for a blank field.
        preserve_name: Keep leading directional words and ambiguous street-name/unit
            boundaries literal when formatting a deliberate manual correction.

    Returns:
        A formatted numeric PO box, formatted street text, or a blank string.
        Recognized PO boxes or units with missing/unsupported identifiers
        return a blank; required unit information is never silently dropped.

    PO-box recognition runs before general punctuation cleanup. Other
    street text is split before punctuation removal so an invalid unit such
    as "Apt 4,5" cannot become "Apt 45". Base and unit are formatted
    separately and rejoined. Use assemble_street() for a separate source unit
    column. Ambiguous names and unsupported shapes need later review.
    This does not verify an official street name or set address status;
    originals must remain available for validation and review.
    """
    
    po_box = _clean_po_box(value)

    # An empty string is a handled PO-box result, so check None explicitly.
    if po_box is not None:
        return po_box

    base, unit_text = split_street_unit(value)
    if preserve_name and unit_text is not None:
        full_parts = value.replace(".", "").replace(",", "").split()
        if street_suffix_index(full_parts) is not None:
            base, unit_text = value, None
    unit = ""

    if unit_text is not None:
        unit = clean_unit(unit_text)
        if not unit:
            return ""

    text = base.replace(".", "").replace(",", "")
    street = _abbreviate_street_parts(clean_name(text), preserve_name=preserve_name)
    return street + " " + unit if unit else street


def assemble_street(street_value: str, unit_value: str = "") -> str:
    """Clean a mapped Street and an optional separate unit-column value.

    Args:
        street_value: Raw mapped Street text, possibly already containing a unit.
        unit_value: Raw text explicitly selected as the separate unit column.

    Returns:
        One formatted Street with a unit included once. A blank separate
        unit delegates to clean_street(). Missing/unsupported base streets,
        unsupported unit text, PO-box/unit combinations, and conflicting
        unit identifiers/types return a blank working Street for later review.

    Matching identifiers can combine a generic # with a known designator;
    the known type is retained. Two different known types are not guessed
    equivalent. Identifiers remain strings, including leading zeros.
    Callers retain both original components separately for review. This
    neither decides record eligibility nor establishes postal deliverability.
    """
    if not unit_value.strip():
        return clean_street(street_value)

    unit = clean_unit(unit_value)
    if not street_value.strip() or not unit:
        return ""

    # A separate unit attached to a PO box is outside the supported grammar.
    if _clean_po_box(street_value) is not None:
        return ""

    base, existing_text = split_street_unit(street_value)
    if existing_text is not None:
        existing_unit = clean_unit(existing_text)
        existing_parts = unit_label_parts(existing_unit)
        separate_parts = unit_label_parts(unit)
        if existing_parts is None or separate_parts is None:
            return ""

        existing_code, existing_identifier = existing_parts
        separate_code, separate_identifier = separate_parts
        if existing_identifier != separate_identifier:
            return ""

        # Agreement keeps one unit. A known type is more specific than #.
        if existing_code != separate_code:
            if separate_code == "#":
                unit = existing_unit
            elif existing_code != "#":
                return ""

    # Do not manufacture a usable main address from unit information alone.
    base_parts = base.replace(".", "").replace(",", "").split()
    if street_suffix_index(base_parts) is None:
        return ""

    return clean_street(base) + " " + unit


def clean_date_signed(
    value: str, *, reference_date: date | None = None
) -> str:
    """Normalize a supported signing date to MM/DD/YY, or return a blank.

    Args:
        value: Original date text in US month/day/two- or four-digit-year form.
        reference_date: Latest permitted date; defaults to the local current
            date. Use the same reference date throughout one processing batch.

    Missing, malformed, impossible, future, and unsupported-century inputs
    return a blank for review. Preserve the original in MemberRecord before
    cleanup. Validation supplies the review issue; this function only formats.
    """
    parsed = parse_date_signed(value, reference_date=reference_date)
    if parsed is None:
        return ""

    # Width 2 plus zero padding keeps each output component two digits long.
    return f"{parsed.month:02d}/{parsed.day:02d}/{parsed.year % 100:02d}"

