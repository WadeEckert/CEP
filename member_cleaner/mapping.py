"""Column mapping utilities for the Member CSV Cleaner.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Validate column selections and copy source values into records
that contain every destination heading from the CRM template.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""


def validate_mapping(
    source_headers: list[str],
    template_headers: list[str],
    mapping: dict[int, str | None],
    *,
    unit_source_index: int | None = None,
) -> None:
    
    """Check ordinary destinations and an optional separate-unit role.

    Args:
        source_headers: Incoming headings in their original column order.
        template_headers: Exact output headings in their required order.
        mapping: Ordinary source indexes mapped to template headings or
            None for Ignore. Omit the separately selected unit index.
        unit_source_index: Index of the source column holding unit text,
            or None when no separate unit column is selected.

    Returns:
        None when the mapping is valid.

    Raises:
        ValueError: Template headings are empty, blank, or repeated; a
            source index or destination is invalid; a destination is reused;
            a source column lacks a choice; every source column is ignored;
            or the unit role conflicts with another choice or lacks Street.
    """

    # A dictionary record requires distinct, nonblank destination headings.
    if not template_headers or any(not header.strip() for header in template_headers):
        raise ValueError("Template headings must be present and nonblank.")

    # A set of valid destinations allows quick membership testing.
    valid_destinations = set(template_headers)

    # Ensure that template headings are unique.
    if len(valid_destinations) != len(template_headers):
        raise ValueError("Template headings must be unique.")

    if unit_source_index is not None:
        # A unit is an explicit input role, not an extra template heading.
        if type(unit_source_index) is not int:
            raise ValueError("The unit source column index must be an integer.")

        if not 0 <= unit_source_index < len(source_headers):
            raise ValueError("The unit source column index is out of range.")

        if unit_source_index in mapping:
            raise ValueError(
                "The unit source column cannot also have a destination or Ignore. "
                "Omit that index from the ordinary mapping."
            )

    used_destinations: set[str] = set()

    for source_index, destination in mapping.items():
        # Reject booleans and strings as source indexes.
        if type(source_index) is not int:
            raise ValueError("Source column indexes must be integers.")

        if not 0 <= source_index < len(source_headers):
            raise ValueError(f"Source column index {source_index} is out of range.")

        if destination is None:
            continue

        if not isinstance(destination, str) or destination not in valid_destinations:
            raise ValueError(f"Unknown template destination: {destination!r}.")

        # Ordinary destinations still cannot overwrite one another.
        if destination in used_destinations:
            raise ValueError(
                f"More than one source column maps to {destination!r}. "
                "Choose a different destination or Ignore."
            )

        used_destinations.add(destination)

    # Every source column has exactly one role.
    selected_count = len(mapping) + (1 if unit_source_index is not None else 0)

    if selected_count != len(source_headers):
        raise ValueError(
            "Choose a destination, Ignore, or the separate unit role "
            "for every source column."
        )

    if unit_source_index is not None and "Street" not in used_destinations:
        raise ValueError("Map a main Street column before selecting a unit column.")

    if not used_destinations:
        raise ValueError("Map at least one source column to a template heading.")


def map_record(source_row: list[str], source_headers: list[str], template_headers: list[str], mapping: dict[int, str | None]) -> dict[str, str]:
    
    """Copy one source row into a new record using a validated mapping.

    Args:
        source_row: Original field values for one member, in source order.
        source_headers: Headings associated with this source row.
        template_headers: Exact output headings in their required order.
        mapping: Source indexes mapped to template headings; None means Ignore.

    Returns:
        A new dictionary containing every template heading. Unmapped fields
        contain empty strings. Copied values retain their original text.

    Raises:
        ValueError: The mapping is invalid or the row width differs from
            the number of source headings.
    """

    # Validate the mapping before copying any values, to avoid partial records.
    validate_mapping(source_headers, template_headers, mapping)

    # Check that the source row has the same number of fields as the source headings.
    if len(source_row) != len(source_headers):
        raise ValueError(
            f"Expected {len(source_headers)} fields in the source row; "
            f"found {len(source_row)}."
        )

    # Create a new record with every template heading, initialized to empty strings.
    record = {header: "" for header in template_headers}

    # Copy each source value into the record at its mapped destination, if any.
    for source_index, destination in mapping.items():
        if destination is not None: # Only copy if the source column is not ignored.
            record[destination] = source_row[source_index]

    return record


def map_record_with_unit(
    source_row: list[str],
    source_headers: list[str],
    template_headers: list[str],
    mapping: dict[int, str | None],
    *,
    unit_source_index: int | None = None,
) -> tuple[dict[str, str], str]:
    
    """Map one record and return separate unit text without cleaning it.

    Args:
        source_row: Original values for one member, in source order.
        source_headers: Headings associated with the source row.
        template_headers: Exact output headings in their required order.
        mapping: Ordinary destinations or Ignore; omit the selected unit index.
        unit_source_index: Separate unit column index, or None if absent.

    Returns:
        A tuple containing the ordinary mapped record and raw unit text.
        No selected unit column produces an empty unit string. Only template
        headings appear in the record; input values and mapping are unchanged.

    Raises:
        ValueError: The mapping/roles are invalid or the row width is wrong.

    The caller passes the record's Street and returned unit text to
    cleanup.assemble_street(). Keeping this step separate preserves the
    distinction between source mapping and automatic normalization.
    """

    validate_mapping(
        source_headers,
        template_headers,
        mapping,
        unit_source_index=unit_source_index,
    )

    # Use a private copy so the caller's mapping remains unchanged.
    # The existing copier skips this column; its text is returned separately.
    field_mapping = mapping.copy()

    if unit_source_index is not None:
        field_mapping[unit_source_index] = None

    record = map_record(
        source_row, source_headers, template_headers, field_mapping
    )

    unit_value = "" if unit_source_index is None else source_row[unit_source_index]

    return record, unit_value