"""Field validation utilities for the Member CSV Cleaner.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Validate cleaned names, contacts, addresses, and signing dates.
Individual checks preserve record state. evaluate_record() refreshes issues
and eligibility and returns detached template-only values for included rows.
Original and editable working values remain intact. Batch duplicate review
and final export checks belong to the calling workflow. Local address checks
do not establish postal deliverability or geographic consistency.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import re
from datetime import date

from .address_data import USPS_DIRECTIONALS, USPS_STATE_CODES
from .address_parsing import (
    parse_unit_component,
    split_street_unit,
    street_suffix_index,
)
from .models import MemberRecord, NameContactResult, ReviewIssue


def is_date_signed_heading(name: str) -> bool:
    """Recognize the signing-date column without renaming its template key."""
    return name.strip().casefold() == "datesigned"


def is_valid_email(value: str) -> bool:

    """Check whether one address fits the application's email format rules.

    Args:
        value: One email address to check, supplied as text.

    Returns:
        True for a supported unquoted ASCII address with a dotted domain;
        otherwise False. Whitespace and comma typos are not repaired here.

    The local part is limited to 64 characters and the whole address to
    254. Domain labels contain 1-63 letters/digits/internal hyphens, and
    the final label must not be entirely numeric. Quoted addresses,
    Unicode forms, display names, and address literals require review.
    This checks structure only; no DNS or mailbox lookup is performed.
    """

    # Exactly one @ is required before splitting into two components.
    if len(value) > 254 or value.count("@") != 1:
        return False

    # .split() returns a list of two parts: local_part and domain.
    # For example, example@domain.com becomes ["example", "domain.com"].
    local_part, domain = value.split("@")

    # The local part is limited to 64 characters, and the domain must be present.
    if len(local_part) > 64:
        return False

    # RFC 5322 dot-atom characters allow plus tags and apostrophes.
    # This means the local part may contain letters, digits, and these symbols: !#$%&'*+/=?^_`{|}~-
    atom_pattern = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"

    # The local part may contain multiple dot-separated atoms, but cannot start or end with a dot, and cannot have consecutive dots.
    local_pattern = atom_pattern + r"(?:\." + atom_pattern + r")*"

    if re.fullmatch(local_pattern, local_part) is None:
        return False

    # Public-style domain names need multiple labels, such as example.com.
    labels = domain.split(".")

    # The final label must contain at least one letter, not just digits. [-1] is the last label.
    if len(labels) < 2 or labels[-1].isdigit():
        return False

    # A label starts/ends with a letter or digit; hyphens may occur inside.
    label_pattern = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"

    # Check each label against the pattern; return False if any label is invalid.
    for label in labels:
        if re.fullmatch(label_pattern, label) is None:
            return False

    return True


def is_valid_phone(value: str) -> bool:
    """Check the agreed canonical US phone format after cleanup.

    Args:
        value: Phone text to check, without performing normalization.

    Returns:
        True for exactly ten ASCII digits; otherwise False. Formatting,
        country-code removal, and whitespace trimming belong to cleanup.

    This checks the project's format/length rule, not whether a number is
    assigned, reachable, or actually a cell phone.
    """
    return re.fullmatch(r"[0-9]{10}", value) is not None


def get_phone_email_issues(record: MemberRecord) -> list[ReviewIssue]:
    """Collect current phone/email format issues without modifying a record.

    Args:
        record: A mapped member record whose automatic cleanup has run.

    Returns:
        A fresh list of field-specific issues. A malformed nonblank working
        value produces INVALID_PHONE or INVALID_EMAIL. A supplied original
        value that is blank after cleanup produces PHONE_CLEARED or
        EMAIL_CLEARED, unless the user deliberately removed that field.

    Missing contacts are optional individually and do not get missing-field
    issues here. Manual corrections still undergo format checks. Explicitly
    removing a value acknowledges its removal; it does not make the row
    eligible. Other helpers and evaluate_record handle the remaining checks.

    The caller combines these results with other issue groups during record
    evaluation. This function does not append to record.issues, set eligible,
    or prepare a record for export. Each call reflects current field values.
    """
    issues: list[ReviewIssue] = []

    # Functions can be stored in a table and called through a local variable.
    checks = (
        (
            "Primary Cell/Mobile Phone",
            is_valid_phone,
            "PHONE",
            "Use exactly ten digits for a US phone number, without formatting.",
        ),
        (
            "Email",
            is_valid_email,
            "EMAIL",
            "Use one supported email address, such as member@example.com, "
            "without spaces or multiple addresses.",
        ),
    )

    for field_name, check_format, code_prefix, format_message in checks:
        value = record.working_values.get(field_name, "")

        if value:
            # A manual override is preserved, but it is not exempt from checks.
            if not check_format(value):
                issues.append(
                    ReviewIssue(field_name, "INVALID_" + code_prefix, format_message)
                )
            continue

        # An explicit blank override means the user chose to remove this value.
        if field_name in record.manual_overrides:
            continue

        original = record.original_mapped_values.get(field_name, "")
        if original.strip():
            issues.append(
                ReviewIssue(
                    field_name,
                    code_prefix + "_CLEARED",
                    "A supplied value is blank after cleanup. Review the original "
                    "value, enter a correction, or explicitly leave the field blank.",
                )
            )

    return issues


def is_valid_zipcode(value: str) -> bool:
    """Require five ASCII digits; this does not confirm an assigned ZIP."""
    return re.fullmatch(r"[0-9]{5}", value) is not None


def is_valid_state(value: str) -> bool:
    """Require an uppercase state/region code from our postal reference data."""
    return value in USPS_STATE_CODES


def _is_place_text(value: str) -> bool:
    """Recognize conservative city/street-name characters, not actual places."""
    return (
        bool(value)
        and value == " ".join(value.split())
        and value[0].isalnum()
        and value[-1].isalnum()
        and any(char.isalpha() for char in value)
        and all(char.isalpha() or char in "0123456789 -'’" for char in value)
    )


def is_valid_city(value: str) -> bool:
    """Check cleaned city text, allowing compound names and accented letters.

    Numeric-only names, uncleaned punctuation, and combined city/state text
    need review. No city directory or ZIP-to-city lookup is consulted.
    """
    return _is_place_text(value)


def is_valid_street(value: str) -> bool:
    """Check a supported cleaned street or numbered PO-box structure.

    Ordinary streets require a supported house token, a name, a known suffix,
    and optionally a directional and one labelled unit. Missing suffixes,
    unsupported forms, and malformed units require review; none are invented.
    A valid shape does not establish an official address or delivery point.
    """
    if not value or value != " ".join(value.split()):
        return False
    if "." in value or "," in value:
        return False
    if re.fullmatch(r"PO Box [0-9]+", value) is not None:
        return True

    base, unit_text = split_street_unit(value)
    parts = base.split()
    suffix_index = street_suffix_index(parts)
    if suffix_index is None:
        return False

    name_start = 1
    if re.fullmatch(r"[0-9]+/[0-9]+", parts[name_start]) is not None:
        # A zero denominator is not a usable house-number fraction.
        if not parts[name_start].split("/")[1].strip("0"):
            return False
        name_start += 1
    if not _is_place_text(" ".join(parts[name_start:suffix_index])):
        return False

    return unit_text is None or parse_unit_component(unit_text) is not None


def _get_street_source_issues(record: MemberRecord) -> list[ReviewIssue]:
    """Check source-dependent unit conflicts and uncertain word boundaries.

    Called only for a currently supported Street shape. A deliberate Street
    edit confirms/replaces source interpretation, so only its current format
    needs checking afterward. Original snapshots are never rewritten.
    """
    if "Street" in record.manual_overrides:
        return []

    issues: list[ReviewIssue] = []
    original = record.original_mapped_values.get("Street", "")
    original_base, original_unit = split_street_unit(original)
    current_base, current_unit = split_street_unit(record.working_values["Street"])
    current_parts = (
        parse_unit_component(current_unit) if current_unit is not None else None
    )

    # Check both sources: automatic cleanup must not silently lose a unit.
    supplied_units = [record.original_unit_value, original_unit or ""]
    for supplied in supplied_units:
        if not supplied.strip():
            continue
        expected_parts = parse_unit_component(supplied)
        if expected_parts is None:
            code = "UNIT_REVIEW"
            message = "Review the original unit text; its format is unsupported."
        elif current_parts is None:
            code = "UNIT_MISSING"
            message = "A supplied unit is missing from Street. Review both originals."
        else:
            expected_code, expected_id = expected_parts
            current_code, current_id = current_parts
            types_agree = (
                expected_code == current_code or "#" in (expected_code, current_code)
            )
            if expected_id == current_id and types_agree:
                continue
            code = "UNIT_CONFLICT"
            message = "The working unit differs from supplied unit information."

        issue = ReviewIssue("Street", code, message)
        if issue not in issues:
            issues.append(issue)

    # Some unit words can also be literal words inside a street name.
    original_parts = original.replace(".", "").replace(",", "").split()
    if original_unit is not None and street_suffix_index(original_parts) is not None:
        issues.append(ReviewIssue(
            "Street", "UNIT_BOUNDARY_REVIEW",
            "Confirm whether the original unit wording belongs to the street name.",
        ))

    # Without a lookup, North Star can mean a literal name or N + Star.
    source_parts = original_base.replace(".", "").replace(",", "").split()
    suffix_index = street_suffix_index(source_parts)
    if suffix_index is not None:
        name_start = 1
        if re.fullmatch(r"[0-9]+/[0-9]+", source_parts[name_start]) is not None:
            name_start += 1
        first_word = source_parts[name_start].upper()
        direction = USPS_DIRECTIONALS.get(first_word)
        has_name_after = suffix_index - name_start > 1
        if direction is not None and first_word != direction and has_name_after:
            following = source_parts[name_start + 1]
            working_parts = current_base.split()
            if (following.upper() not in USPS_DIRECTIONALS
                    and any(char.isalpha() for char in following)
                    and working_parts[name_start].upper() == direction):
                issues.append(ReviewIssue(
                    "Street", "DIRECTION_REVIEW",
                    "Confirm the shortened leading direction against the original "
                    "street name; it may be a literal part of that name.",
                ))

    return issues


def get_address_issues(record: MemberRecord) -> list[ReviewIssue]:
    """Return fresh address review reasons without modifying record state.

    A completely absent address is optional. Once address information is
    supplied, Street, City, State, and Zipcode are required for MAILABLE.
    Blank Country is allowed; a supplied country must clean to USA.
    Preserved originals expose values lost during cleanup and unit conflicts.
    Manual corrections still undergo every current-value format check.
    Overall eligibility, issue storage, and CSV export belong to later steps.
    """
    checks = (
        ("Street", is_valid_street, "STREET",
         "Use a supported numbered street with a suffix, or a numbered PO Box."),
        ("City", is_valid_city, "CITY", "Enter a city name without state/ZIP text."),
        ("State", is_valid_state, "STATE", "Use a supported uppercase postal code."),
        ("Zipcode", is_valid_zipcode, "ZIPCODE", "Use exactly five ZIP digits."),
    )
    has_address = any(
        record.working_values.get(name, "")
        or (name not in record.manual_overrides
            and record.original_mapped_values.get(name, "").strip())
        for name, _, _, _ in checks
    )
    unreviewed_unit = (
        bool(record.original_unit_value.strip())
        and "Street" not in record.manual_overrides
    )
    if not has_address and not unreviewed_unit:
        return []

    issues: list[ReviewIssue] = []
    for name, check_format, prefix, message in checks:
        value = record.working_values.get(name, "")
        if value:
            if not check_format(value):
                issues.append(ReviewIssue(name, prefix + "_FORMAT", message))
            elif name == "Street":
                issues.extend(_get_street_source_issues(record))
        elif name == "Street" and unreviewed_unit:
            issues.append(ReviewIssue(
                name, "STREET_UNIT_REVIEW",
                "Street is blank although a separate unit was supplied. Review "
                "both original components and enter one complete Street value.",
            ))
        elif (name not in record.manual_overrides
              and record.original_mapped_values.get(name, "").strip()):
            issues.append(ReviewIssue(
                name, prefix + "_CLEARED",
                "A supplied address value is blank after cleanup. Review the "
                "original and correct it or deliberately remove the address.",
            ))
        else:
            issues.append(ReviewIssue(name, "MISSING_" + prefix, message))

    country = record.working_values.get("Country", "")
    if country and country != "USA":
        issues.append(ReviewIssue(
            "Country", "COUNTRY_REVIEW",
            "Review the country. Only US addresses qualify; use USA or leave "
            "an unspecified country blank.",
        ))
    elif (not country and "Country" not in record.manual_overrides
          and record.original_mapped_values.get("Country", "").strip()):
        issues.append(ReviewIssue(
            "Country", "COUNTRY_CLEARED",
            "A supplied country was cleared. Review it before using this address.",
        ))

    return issues


def get_address_status(record: MemberRecord) -> str:
    """Compute MAILABLE/BAD_ADDRESS without writing the template status field.

    MAILABLE means complete and acceptable under the project's local rules,
    with no unresolved address issue. It is not a delivery verification.
    A BAD_ADDRESS does not exclude a row that has another usable contact.
    """
    required = ("Street", "City", "State", "Zipcode")
    if all(record.working_values.get(name, "") for name in required):
        if not get_address_issues(record):
            return "MAILABLE"
    return "BAD_ADDRESS"


def has_usable_contact(record: MemberRecord) -> bool:
    """Check whether at least one current contact method qualifies.

    Use cleaned working values and recompute address status instead of
    trusting an imported or stale Address Contact Status field. An absent
    or unusable email does not disqualify a valid phone or MAILABLE address.
    Individual contact issues still need their own review/export checks.
    """
    return (
        is_valid_phone(record.working_values.get("Primary Cell/Mobile Phone", ""))
        or is_valid_email(record.working_values.get("Email", ""))
        or get_address_status(record) == "MAILABLE"
    )


def _has_full_name_part(value: str) -> bool:
    """Recognize a name part longer than one letter, rather than initials.

    Unicode letter groups preserve support for names such as Élise and Ng.
    Separators keep J. T., J-T, and J T from becoming one invented full name.
    This is the project's name-shape rule, not verification of an identity.
    """
    parts = re.findall(r"[^\W\d_]+", value)
    return any(len(part) > 1 and part.isalpha() for part in parts)


def has_usable_name(first_name: str, last_name: str) -> bool:
    """Check cleaned names against the agreed retention/substitution rules.

    A full first-name part is sufficient, even with no last name. A first
    initial can be retained with a full last-name part. Last-name-only,
    initials-only, lone-initial, and missing-name forms need the fallback.
    Compound names remain in their original fields. This does not format
    names, verify identities, or establish contact eligibility.
    """
    if _has_full_name_part(first_name):
        return True

    return (
        any(char.isalpha() for char in first_name)
        and _has_full_name_part(last_name)
    )


def get_name_contact_result(record: MemberRecord) -> NameContactResult:
    """Evaluate current names and contacts without changing record state.

    Args:
        record: A mapped member record after automatic cleanup or correction.

    Returns:
        Cleaned names or a proposed Anonymous/Donor pair, together with
        any name/contact exclusion reasons. Any one usable phone, email,
        or qualifying MAILABLE address is sufficient for the fallback.

    A record without usable contact fails regardless of its names. In that
    case, retain the names in the result for explanation instead of creating
    a placeholder for a record that currently cannot qualify.

    No working fields, overrides, issues, exclusions, duplicate decisions,
    or eligible flags are modified. Keep generated names in this result;
    do not write them back over the record's editable name inputs. The
    combined evaluator consumes this limited decision.
    """
    first_name = record.working_values.get("First Name", "")
    last_name = record.working_values.get("Last Name", "")

    if not has_usable_contact(record):
        return NameContactResult(
            first_name=first_name,
            last_name=last_name,
            used_anonymous_fallback=False,
            exclusion_reasons=("No usable phone, email, or MAILABLE address.",),
        )

    if has_usable_name(first_name, last_name):
        return NameContactResult(
            first_name=first_name,
            last_name=last_name,
            used_anonymous_fallback=False,
        )

    return NameContactResult(
        first_name="Anonymous",
        last_name="Donor",
        used_anonymous_fallback=True,
    )


def parse_date_signed(
    value: str, *, reference_date: date | None = None
) -> date | None:
    """Parse a supported US signing date using the first-version date policy.

    Args:
        value: Month/day/year text with a two- or four-digit year.
        reference_date: Latest permitted signing date. Defaults to the local
            computer's current date; callers/tests can supply one batch date.

    Returns:
        A calendar date, or None for missing, malformed, impossible, future,
        or unsupported-century input. Surrounding whitespace is permitted.

    Two-digit years explicitly mean 2000-2099. Four-digit years must also
    fall in that century so MM/DD/YY output can be read back consistently.
    Future dates and other centuries require review. This is a documented
    initial processing policy, not a century rule supplied by Rachel.
    No default strptime century cutoff, day/month swap, or date is guessed.
    """
    match = re.fullmatch(
        r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{2}|[0-9]{4})", value.strip()
    )
    if match is None:
        return None

    month_text, day_text, year_text = match.groups()
    year = int(year_text)
    if len(year_text) == 2:
        year += 2000
    if not 2000 <= year <= 2099:
        return None

    try:
        # date() checks real month lengths and Gregorian leap-year rules.
        parsed = date(year, int(month_text), int(day_text))
    except ValueError:
        return None

    if reference_date is None:
        reference_date = date.today()
    return parsed if parsed <= reference_date else None


def is_valid_date_signed(
    value: str, *, reference_date: date | None = None
) -> bool:
    """Require a usable canonical MM/DD/YY value without performing cleanup."""
    return (
        re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{2}", value) is not None
        and parse_date_signed(value, reference_date=reference_date) is not None
    )


def get_date_signed_issues(
    record: MemberRecord, *, reference_date: date | None = None
) -> list[ReviewIssue]:
    """Return current DateSigned review reasons without changing record state.

    A template without DateSigned is outside this field check. When the
    field exists, a missing date still requires review, including a manual
    blank. Supplied originals lost during cleanup remain distinguishable.
    A deliberate valid correction resolves source interpretation concerns.
    Date issues alone do not determine overall record/contact eligibility.
    """
    if reference_date is None:
        reference_date = date.today()
    return [
        issue
        for field in record.working_values
        if is_date_signed_heading(field)
        for issue in _check_signing_date(record, field, reference_date)
    ]


def _check_signing_date(record: MemberRecord, field: str, reference_date: date) -> list[ReviewIssue]:
    """Attach each date issue to its exact template key."""
    value = record.working_values[field]
    original = record.original_mapped_values.get(field, "")
    manually_reviewed = field in record.manual_overrides

    if not value:
        if original.strip() and not manually_reviewed:
            return [ReviewIssue(
                field, "DATE_SIGNED_CLEARED",
                "A supplied signing date could not be normalized. Review the "
                "original date; enter a real, nonfuture date in MM/DD/YY format.",
            )]
        return [ReviewIssue(
            field, "MISSING_DATE_SIGNED",
            "The signing date is missing. Review it; do not invent a date.",
        )]

    if not is_valid_date_signed(value, reference_date=reference_date):
        return [ReviewIssue(
            field, "DATE_SIGNED_FORMAT",
            "Use a real, nonfuture date in MM/DD/YY format. Two-digit years "
            "mean 2000-2099; other centuries need review.",
        )]

    if not manually_reviewed:
        original_date = parse_date_signed(original, reference_date=reference_date)
        current_date = parse_date_signed(value, reference_date=reference_date)
        if original_date is None:
            return [ReviewIssue(
                field, "DATE_SIGNED_SOURCE_REVIEW",
                "The original date was missing, unsupported, or unclear. Confirm the "
                "working date against the original before accepting it.",
            )]
        if current_date != original_date:
            return [ReviewIssue(
                field, "DATE_SIGNED_CONFLICT",
                "The working date differs from the supplied date. Confirm or "
                "correct it after reviewing the original.",
            )]

    return []


def evaluate_record(
    record: MemberRecord, *, reference_date: date | None = None
) -> dict[str, str] | None:
    """Refresh one cleaned record's evaluation and build candidate output values.

    Args:
        record: MemberRecord created before cleanup, with current cleaned or
            deliberately corrected working values. This does not run cleanup.
        reference_date: Processing date shared with date cleanup/validation;
            defaults to the local current date.

    Returns:
        A detached dictionary with exactly the record's template keys/order
        when locally included, or None when contact eligibility, manual
        exclusion, or a confirmed-duplicate decision prevents inclusion.

    This replaces automatic issues/reasons and sets eligible. It preserves
    original inputs, working values, manual overrides/exclusions, record ID,
    and confirmed_duplicate_of. Actual edits already invalidate evaluation
    through MemberRecord; reevaluation alone must not erase reviewer choices.

    Derived names, address status, and completed-record constants go only in
    the returned dictionary. Unusable phone/email values and unresolved dates
    are blank there while their editable inputs remain available for review.
    Address/date issues alone do not exclude a contact-qualified row.

    The caller must still complete batch duplicate confirmation and review
    before final export. A returned dictionary is not batch export approval.
    """
    if reference_date is None:
        reference_date = date.today()

    # Build fresh results first; do not accumulate flags from earlier passes.
    issues = get_phone_email_issues(record)
    issues.extend(get_address_issues(record))
    date_issues = get_date_signed_issues(record, reference_date=reference_date)
    issues.extend(date_issues)
    name_result = get_name_contact_result(record)
    address_status = get_address_status(record)

    if not name_result.passes_name_contact_rules:
        issues.append(ReviewIssue(
            None, "NO_USABLE_CONTACT",
            "At least one valid phone, email, or MAILABLE address is required.",
        ))

    # A separate copy prevents generated names from becoming later edit inputs.
    output_values = dict(record.working_values)
    derived_values = {
        "First Name": name_result.first_name,
        "Last Name": name_result.last_name,
        "Address Contact Status": address_status,
        "PhoneDisclaimeredYN": "Y",
        "Account Classification": "INDIVIDUAL",
    }
    for field_name, value in derived_values.items():
        # Partial templates remain exact: never add an absent output heading.
        if field_name in output_values:
            output_values[field_name] = value

    for field_name, check_format in (
        ("Primary Cell/Mobile Phone", is_valid_phone),
        ("Email", is_valid_email),
    ):
        if field_name in output_values and not check_format(output_values[field_name]):
            output_values[field_name] = ""

    # A valid-looking but unconfirmed source conflict must not export a guess.
    for issue in date_issues:
        output_values[issue.field_name] = ""

    # Commit this evaluation after computing the candidate values. Slice
    # assignment refreshes existing lists instead of appending stale entries.
    record.issues[:] = issues
    record.exclusion_reasons[:] = name_result.exclusion_reasons
    record.eligible = name_result.passes_name_contact_rules

    if not record.is_included:
        return None
    return output_values
