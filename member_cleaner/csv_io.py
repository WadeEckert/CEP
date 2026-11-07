"""CSV input and output utilities for the Member CSV Cleaner.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Read the CRM template and incoming member CSV files while
preserving column headings, field values, and their original order.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import csv
from pathlib import Path


def load_template(template_path: str | Path) -> list[str]:

    """Read and validate a header-only, comma-separated CRM template.

    Args:
        template_path: Path to a UTF-8 CSV file, with or without a BOM.

    Returns:
        Column headings in their original order, with spacing preserved.

    Raises:
        OSError: The file cannot be opened or read, including a missing file.
        UnicodeDecodeError: The file is not valid UTF-8 text.
        csv.Error: The CSV parser detects malformed CSV syntax.
        ValueError: Headings are missing, blank, or repeated exactly, or
            the template contains a nonblank row after its headings.
    """

    # Create a Path object to handle the template file location.
    path = Path(template_path)

    # Handle an optional UTF-8 BOM and let the CSV parser manage newlines.
    with path.open("r", encoding="utf-8-sig", newline="") as template_file:
        reader = csv.reader(template_file, strict=True)
        headers = next(reader, None)

        # An empty file or blank first row cannot define output columns.
        if not headers:
            raise ValueError("The template must begin with a header row.")

        # Initialize a set to track seen headings and check for duplicates or blanks.
        seen_headers: set[str] = set()

        # Check each heading for nonblank content and uniqueness, without altering the original text.
        # start=1 ensures that column numbers reported to the user are 1-based, matching spreadsheet conventions.
        for column_number, header in enumerate(headers, start=1):
            
            # Check a stripped copy without changing the actual heading.
            if not header.strip():
                raise ValueError(
                    f"Template column {column_number} has a blank heading."
                )

            # Repeated dictionary keys would collapse separate output fields.
            if header in seen_headers:
                raise ValueError(
                    f"Duplicate template heading {header!r} "
                    f"at column {column_number}."
                )

            seen_headers.add(header)

        # Allow empty trailing rows, but reject records in the template.
        for row in reader:
            if any(value.strip() for value in row):
                raise ValueError(
                    "The template must contain only column headings. "
                    "Remove the nonblank rows beneath them."
                )

    return headers


def read_source_csv(source_path: str | Path, encoding: str = "utf-8-sig") -> tuple[list[str], list[list[str]]]:
    
    """Read a comma-separated member file without cleaning its values.

    Args:
        source_path: Path to the incoming CSV file.
        encoding: Text encoding to use; defaults to UTF-8 with an optional BOM.

    Returns:
        A tuple containing the source headings and a list of member rows.
        Each row is a list of strings in the original column order.
        Duplicate and individually blank headings are preserved by position.
        A header-only file returns an empty list of member rows.

    Raises:
        OSError: The file cannot be opened or read, including a missing file.
        LookupError: The requested encoding name is unknown.
        UnicodeDecodeError: The file does not match the requested encoding.
        csv.Error: The CSV parser detects malformed CSV syntax.
        ValueError: No usable header row exists, or a member row has a
            different number of fields than the header row.
    """

    path = Path(source_path)

    with path.open("r", encoding=encoding, newline="") as source_file:
        reader = csv.reader(source_file, strict=True)
        headers = next(reader, None)

        # At least one heading is needed to identify the source columns.
        if not headers or not any(header.strip() for header in headers):
            raise ValueError(
                "The source CSV must begin with at least one nonblank heading."
            )

        # Check for missing or extra fields in each row, which can occur with unquoted commas.
        expected_columns = len(headers)
        rows: list[list[str]] = []

        for row in reader:
            # Skip any empty trailing rows, which can occur with a final newline.
            if not row:
                continue

            # Check for missing or extra fields, which can occur with unquoted commas.
            if len(row) != expected_columns:
                raise ValueError(
                    f"Expected {expected_columns} fields in the source CSV "
                    f"record ending on line {reader.line_num}; found {len(row)}. "
                    "Check for missing or extra commas and quote fields "
                    "that contain commas."
                )

            # Keep original strings, including spaces and leading zeros.
            rows.append(row)

    return headers, rows


def write_output_csv(output_path: str | Path, template_headers: list[str], records: list[dict[str, str]]) -> Path:
    
    """Write records to a new UTF-8 CSV using the exact template layout.

    Args:
        output_path: New file location inside an existing directory.
        template_headers: Exact output headings in their required order.
        records: Records containing every template field with string values.

    Returns:
        The output location as a Path, after the file has been closed.

    Raises:
        ValueError: Template headings are missing, blank, or repeated; a
            record's fields differ from the template; or a value is not text.
        FileExistsError: A file already occupies the requested output path.
        OSError: The output file cannot be created, written, or closed.
        UnicodeEncodeError: A value cannot be encoded as UTF-8.
        csv.Error: The CSV writer cannot serialize the supplied data.
    """

    # Create a Path object to handle the output file location.
    path = Path(output_path)

    # Validate the template headings and ensure they are unique, nonblank, and present.
    if not template_headers or any(not header.strip() for header in template_headers):
        raise ValueError("Template headings must be present and nonblank.")

    expected_fields = set(template_headers)

    # Validate that the template headings are unique, since duplicate keys would collapse separate output fields.
    if len(expected_fields) != len(template_headers):
        raise ValueError("Template headings must be unique.")

    # Check every record for the correct fields and string values.
    for record_number, record in enumerate(records, start=1):
        if set(record) != expected_fields: # Check for missing or extra fields
            raise ValueError(
                f"Record {record_number} must contain exactly the template fields."
            )

        # Check that every value is a string, including empty strings for blanks.
        for field, value in record.items():
            if not isinstance(value, str):
                raise ValueError(
                    f"Record {record_number}, field {field!r}, must contain text. "
                    "Use an empty string for a blank value."
                )

    # Exclusive creation protects existing files, including the source CSV.
    with path.open("x", encoding="utf-8", newline="") as output_file:
        # The CSV writer will raise an error if a record is missing a field.
        writer = csv.DictWriter(output_file, fieldnames=template_headers, extrasaction="raise")
        writer.writeheader()
        writer.writerows(records)

    return path