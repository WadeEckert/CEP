"""Separate-column address mapping checks using fictional member data.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Verify explicit unit-column roles, preservation of original values,
safe street/unit assembly, and the resulting CSV workflow. Run from the
project root with python -m unittest discover -s tests -v.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from member_cleaner.cleanup import assemble_street, clean_street, clean_zipcode
from member_cleaner.csv_io import read_source_csv, write_output_csv
from member_cleaner.mapping import (
    map_record,
    map_record_with_unit,
    validate_mapping,
)


class UnitMappingTests(unittest.TestCase):
    """Check that each source column has one explicit, nonconflicting role."""

    def test_unit_role_preserves_raw_values(self) -> None:
        """Use index zero and repeated headings without altering input or schema."""
        source_headers = ["Address", "Address", "Contact"]
        template_headers = ["Email", "Street", "PROISSSUB "]
        source_row = [
            "  apartment 004b ",
            " 125 Elm Street, ",
            "member@example.com",
        ]
        mapping = {1: "Street", 2: "Email"}
        original_row = source_row.copy()
        original_mapping = mapping.copy()

        record, unit_value = map_record_with_unit(
            source_row,
            source_headers,
            template_headers,
            mapping,
            unit_source_index=0,
        )

        self.assertEqual(
            record,
            {
                "Email": "member@example.com",
                "Street": " 125 Elm Street, ",
                "PROISSSUB ": "",
            },
        )
        self.assertEqual(unit_value, "  apartment 004b ")
        self.assertEqual(list(record), template_headers)

        # Keep a mapped snapshot before applying automatic address cleanup.
        original_record = record.copy()
        record["Street"] = assemble_street(record["Street"], unit_value)

        self.assertEqual(record["Street"], "125 Elm St Apt 004B")
        self.assertEqual(record["Email"], "member@example.com")
        self.assertEqual(original_record["Street"], " 125 Elm Street, ")
        self.assertEqual(source_row, original_row)
        self.assertEqual(mapping, original_mapping)

    def test_mapping_without_a_unit_role(self) -> None:
        """Retain ordinary mapping behavior, even without a Street heading."""
        source_headers = ["Contact", "Postal", "Unused"]
        template_headers = ["Zipcode", "Email"]
        source_row = [" member@example.com ", "00501", "keep source only"]
        mapping = {0: "Email", 1: "Zipcode", 2: None}

        record, unit_value = map_record_with_unit(
            source_row, source_headers, template_headers, mapping
        )

        self.assertEqual(
            record, map_record(source_row, source_headers, template_headers, mapping)
        )
        self.assertEqual(unit_value, "")
        self.assertEqual(record["Email"], " member@example.com ")
        self.assertEqual(list(record), template_headers)

    def test_invalid_unit_roles_and_mapping_conflicts(self) -> None:
        """Reject missing choices, role overlaps, bad indexes, and overwrites."""
        source_headers = ["Mailing", "Apartment", "Contact"]
        template_headers = ["Street", "Email"]
        cases = [
            ({0: "Street", 2: "Email"}, True),
            ({0: "Street", 2: "Email"}, "1"),
            ({0: "Street", 2: "Email"}, -1),
            ({0: "Street", 2: "Email"}, 3),
            ({0: "Street", 1: None, 2: "Email"}, 1),
            ({0: "Street", 1: "Email", 2: None}, 1),
            ({0: None, 2: "Email"}, 1),
            ({0: "Street"}, 1),
            ({0: "Street", 2: "Email"}, None),
            ({0: "Street", 2: "Street"}, 1),
            ({0: "Street", 2: "Unknown"}, 1),
            ({False: "Street", 2: "Email"}, 1),
        ]

        for mapping, unit_index in cases:
            with self.subTest(mapping=mapping, unit_index=unit_index):
                with self.assertRaises(ValueError):
                    validate_mapping(
                        source_headers,
                        template_headers,
                        mapping,
                        unit_source_index=unit_index,
                    )

        # Width validation must happen before reading the selected unit cell.
        with self.assertRaises(ValueError):
            map_record_with_unit(
                ["125 Elm Street"],
                source_headers,
                template_headers,
                {0: "Street", 2: "Email"},
                unit_source_index=1,
            )

    def test_csv_workflow_with_a_separate_unit_column(self) -> None:
        """Read, map, assemble, and export while preserving the source CSV."""
        source_headers = ["Apartment", "Postal", "Mailing", "Contact", "Petition"]
        template_headers = ["Email", "Street", "Zipcode", "PROISSSUB "]
        source_rows = [
            ["004b", "00501", "125 elm street,", "one@example.com", "PET-1"],
            ["Suite AB-03", "02108-1234", "125 elm street nw", "two@example.com", "PET-2"],
            ["004B", "00501", "125 Elm St Apt 004B", "three@example.com", "PET-3"],
        ]
        mapping = {1: "Zipcode", 2: "Street", 3: "Email", 4: "PROISSSUB "}

        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "fictional_source.csv"
            output_path = Path(directory) / "fictional_cleaned.csv"
            with source_path.open("w", encoding="utf-8", newline="") as source:
                writer = csv.writer(source)
                writer.writerow(source_headers)
                writer.writerows(source_rows)

            original_bytes = source_path.read_bytes()
            headers, rows = read_source_csv(source_path)
            records = []
            for row in rows:
                record, unit_value = map_record_with_unit(
                    row,
                    headers,
                    template_headers,
                    mapping,
                    unit_source_index=0,
                )
                record["Street"] = assemble_street(record["Street"], unit_value)
                record["Zipcode"] = clean_zipcode(record["Zipcode"])
                records.append(record)

            write_output_csv(output_path, template_headers, records)
            with output_path.open("r", encoding="utf-8", newline="") as output:
                exported = list(csv.reader(output))

            self.assertEqual(
                exported,
                [
                    template_headers,
                    ["one@example.com", "125 Elm St # 004B", "00501", "PET-1"],
                    ["two@example.com", "125 Elm St NW Ste AB-03", "02108", "PET-2"],
                    ["three@example.com", "125 Elm St Apt 004B", "00501", "PET-3"],
                ],
            )
            self.assertEqual(source_path.read_bytes(), original_bytes)
            self.assertEqual(rows, source_rows)


class AssembleStreetTests(unittest.TestCase):
    """Check supported address assembly and conservative review outcomes."""

    def test_separate_unit_examples(self) -> None:
        """Format supplied components without inventing a base or unit value."""
        cases = [
            ("", "", ""),
            ("", "Apt 4B", ""),
            (" \t ", "4B", ""),
            ("125 elm street", "", "125 Elm St"),
            ("PO Box 00123", " ", "PO Box 00123"),
            ("125 north elm street", "Apartment 4b", "125 N Elm St Apt 4B"),
            ("125 Elm Street,", "004b", "125 Elm St # 004B"),
            ("125 Elm Street", "Suite AB-03", "125 Elm St Ste AB-03"),
            ("125 Elm Street", "Unit 02/03", "125 Elm St Unit 02/03"),
            ("125 Elm Street", "Basement", "125 Elm St Bsmt"),
            ("125 Elm Street", "Apartment", ""),
            ("125 Elm Street", "Apt 4,5", ""),
            ("125 Elm", "Apt 4B", ""),
            ("One Main Street", "Apt 4B", ""),
            ("PO Box 123", "Apt 4B", ""),
            ("125 Elm Street", "Bldg 2 Apt 4B", ""),
        ]

        for street, unit, expected in cases:
            with self.subTest(street=street, unit=unit):
                self.assertEqual(assemble_street(street, unit), expected)

    def test_existing_unit_agreement_and_conflicts(self) -> None:
        """Keep an agreeing unit once and preserve conflicts for later review."""
        cases = [
            ("125 Elm Street Apt 4B", "Apartment 4b", "125 Elm St Apt 4B"),
            ("125 Elm Street Apt 004B", "004b", "125 Elm St Apt 004B"),
            ("125 Elm Street #004b", "Apartment 004B", "125 Elm St Apt 004B"),
            ("125 Elm Street #4B", "#4b", "125 Elm St # 4B"),
            ("125 Elm Street Floor 3", "3", "125 Elm St Fl 3"),
            ("125 Elm Street Rear", "Rear", "125 Elm St Rear"),
            ("125 Elm Street Apt 4B", "Apt 5B", ""),
            ("125 Elm Street Apt 004B", "4B", ""),
            ("125 Elm Street Apt 4B", "Suite 4B", ""),
            ("125 Elm Street Rear", "Basement", ""),
            ("125 Elm Street Apt", "4B", ""),
            ("125 Elm Street Bldg 2 Apt 4B", "4B", ""),
        ]

        for street, unit, expected in cases:
            with self.subTest(street=street, unit=unit):
                self.assertEqual(assemble_street(street, unit), expected)

    def test_repeated_assembly_is_stable(self) -> None:
        """Rechecking must neither append the unit again nor change its type."""
        cases = [
            ("125 Elm Street", "Apartment 004b"),
            ("125 Elm Street", "Suite AB-03"),
            ("125 Elm Street", "4b"),
            ("125 Elm Street Apt 4B", "4b"),
            ("125 Elm Street #4B", "Apartment 4b"),
            ("125 Elm Street", "Basement"),
            ("125 Elm Street Apt 4B", "Apt 5B"),
        ]

        for street, unit in cases:
            with self.subTest(street=street, unit=unit):
                cleaned = assemble_street(street, unit)
                self.assertEqual(assemble_street(cleaned, unit), cleaned)
                self.assertEqual(clean_street(cleaned), cleaned)
