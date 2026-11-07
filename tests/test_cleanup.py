"""Field cleanup checks using fictional member data.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Verify field cleanup rules and original-value preservation after
column mapping. Run from the project root with unittest discovery.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import unittest
from datetime import date

from member_cleaner.cleanup import (
    clean_city,
    clean_country,
    clean_date_signed,
    clean_email,
    clean_name,
    clean_phone,
    clean_state,
    clean_street,
    clean_unit,
    clean_zipcode,
)
from member_cleaner.mapping import map_record


class CleanNameTests(unittest.TestCase):
    """Check formatting without applying record eligibility decisions."""

    def test_agreed_name_examples(self) -> None:
        """Cover spaces, capitalization, compound names, and initials."""
        cases = [
            ("", ""),
            (" \t\n ", ""),
            ("  jordan  ", "Jordan"),
            ("TAYLOR", "Taylor"),
            ("BRITTANY   SUE", "Brittany Sue"),
            ("nunez-lopez", "Nunez-Lopez"),
            ("nunez lopez", "Nunez Lopez"),
            ("  brittany\t  sue\n", "Brittany Sue"),
            ("McDonald", "McDonald"),
            ("mcdonald", "Mcdonald"),
            ("MCDONALD", "Mcdonald"),
            ("McDonald-lopez", "McDonald-Lopez"),
            ("o'neill", "O'Neill"),
            ("O’NEILL", "O’Neill"),
            ("O'Neill", "O'Neill"),
            ("J.", "J"),
            ("t.", "T"),
            ("J. T.", "J T"),
            ("j.-taylor", "J-Taylor"),
            ("st. john", "St. John"),
            ("élise", "Élise"),
            ("é.", "É"),
            ("1.", "1."),
            ("nunez--lopez", "Nunez--Lopez"),
        ]

        # Each subtest identifies its input if an example fails.
        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_name(original), expected)

    def test_repeated_cleanup_is_stable(self) -> None:
        """Rechecking edited records should not keep changing their names."""
        for original in [
            "  BRITTANY   SUE  ",
            "j.-taylor",
            "McDonald-lopez",
            "o'neill",
        ]:
            with self.subTest(original=original):
                cleaned = clean_name(original)
                self.assertEqual(clean_name(cleaned), cleaned)

    def test_cleanup_after_mapping(self) -> None:
        """Clean mapped names while preserving contact and source values."""
        source_headers = ["Given Name", "Surname", "Contact Email"]
        template_headers = ["First Name", "Last Name", "Email"]
        source_row = [
            "  BRITTANY   SUE  ",
            "nunez-lopez",
            "member@example.com",
        ]
        original_row = source_row.copy()
        mapping = {0: "First Name", 1: "Last Name", 2: "Email"}

        record = map_record(
            source_row, source_headers, template_headers, mapping
        )
        record["First Name"] = clean_name(record["First Name"])
        record["Last Name"] = clean_name(record["Last Name"])

        self.assertEqual(
            record,
            {
                "First Name": "Brittany Sue",
                "Last Name": "Nunez-Lopez",
                "Email": "member@example.com",
            },
        )
        self.assertEqual(source_row, original_row)


class CleanPhoneTests(unittest.TestCase):
    """Check the project's US phone formatting and length rules."""

    def test_phone_formatting_examples(self) -> None:
        """Cover formatting, country codes, invalid lengths, and ambiguity."""
        cases = [
            ("", ""),
            (" \t\n ", ""),
            ("3035550123", "3035550123"),
            (" (303) 555-0123 ", "3035550123"),
            ("303-555-0123", "3035550123"),
            ("303.555.0123", "3035550123"),
            ("303 555 0123", "3035550123"),
            ("1-303-555-0123", "3035550123"),
            ("13035550123", "3035550123"),
            ("+1 (303) 555-0123", "3035550123"),
            ("1234567890", "1234567890"),
            ("555-0123", ""),
            ("303555012", ""),
            ("30355501234", ""),
            ("23035550123", ""),
            ("+3035550123", ""),
            ("+1303555012", ""),
            ("+44 20 7946 0958", ""),
            ("3035550123 ext. 4", ""),
            ("303555012 x3", ""),
            ("CALL3035550123", ""),
            ("3035550123 / 7205550123", ""),
            ("303+5550123", ""),
            ("１２３４５６７８９０", ""),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_phone(original), expected)

    def test_repeated_cleanup_is_stable(self) -> None:
        """A second cleanup pass should preserve the first result."""
        for original in [
            "(303) 555-0123",
            "+1 (303) 555-0123",
            "1234567890",
            "3035550123 ext. 4",
        ]:
            with self.subTest(original=original):
                cleaned = clean_phone(original)
                self.assertEqual(clean_phone(cleaned), cleaned)

    def test_cleanup_after_mapping(self) -> None:
        """Clean names and a mapped cell phone while preserving the source."""
        source_headers = ["Given Name", "Surname", "Cell"]
        template_headers = [
            "First Name",
            "Last Name",
            "Primary Cell/Mobile Phone",
        ]
        source_row = [" j. ", "TAYLOR", "+1 (303) 555-0123"]
        original_row = source_row.copy()
        mapping = {
            0: "First Name",
            1: "Last Name",
            2: "Primary Cell/Mobile Phone",
        }

        record = map_record(
            source_row, source_headers, template_headers, mapping
        )
        record["First Name"] = clean_name(record["First Name"])
        record["Last Name"] = clean_name(record["Last Name"])
        record["Primary Cell/Mobile Phone"] = clean_phone(
            record["Primary Cell/Mobile Phone"]
        )

        self.assertEqual(
            record,
            {
                "First Name": "J",
                "Last Name": "Taylor",
                "Primary Cell/Mobile Phone": "3035550123",
            },
        )
        self.assertEqual(source_row, original_row)


class CleanZipcodeTests(unittest.TestCase):
    """Check ZIP formatting while preserving uncertain source values."""

    def test_zipcode_formatting_examples(self) -> None:
        """Cover leading zeros, ZIP+4, and inputs that require review."""
        cases = [
            ("", ""),
            (" \t\n ", ""),
            ("02108", "02108"),
            ("00501", "00501"),
            ("80203", "80203"),
            (" 02108 ", "02108"),
            ("02108-1234", "02108"),
            (" 00501-0001 ", "00501"),
            ("2108", ""),
            ("0210", ""),
            ("021081234", ""),
            ("02108-123", ""),
            ("02108-12345", ""),
            ("02108 1234", ""),
            ("02108 -1234", ""),
            ("02108- 1234", ""),
            ("02108.0", ""),
            ("ZIP 02108", ""),
            ("02108/80203", ""),
            ("０２１０８", ""),
            ("0210A", ""),
            ("02108\n1234", ""),
            ("02108-", ""),
            ("02108--1234", ""),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_zipcode(original), expected)

    def test_repeated_cleanup_is_stable(self) -> None:
        """A cleaned ZIP should remain stable on subsequent passes."""
        for original in ["02108", " 00501-0001 ", "2108", "02108.0"]:
            with self.subTest(original=original):
                cleaned = clean_zipcode(original)
                self.assertEqual(clean_zipcode(cleaned), cleaned)

    def test_cleanup_after_mapping(self) -> None:
        """Combine field cleanup while retaining the original mapped input."""
        source_headers = ["Given Name", "Surname", "Cell", "Postal Code"]
        template_headers = [
            "First Name",
            "Last Name",
            "Primary Cell/Mobile Phone",
            "Zipcode",
        ]
        source_row = ["  jordan  ", "taylor", "+1 (303) 555-0123", "02108-1234"]
        original_row = source_row.copy()
        mapping = {
            0: "First Name",
            1: "Last Name",
            2: "Primary Cell/Mobile Phone",
            3: "Zipcode",
        }

        record = map_record(
            source_row, source_headers, template_headers, mapping
        )
        original_record = record.copy()
        record["First Name"] = clean_name(record["First Name"])
        record["Last Name"] = clean_name(record["Last Name"])
        record["Primary Cell/Mobile Phone"] = clean_phone(
            record["Primary Cell/Mobile Phone"]
        )
        record["Zipcode"] = clean_zipcode(record["Zipcode"])

        self.assertEqual(
            record,
            {
                "First Name": "Jordan",
                "Last Name": "Taylor",
                "Primary Cell/Mobile Phone": "3035550123",
                "Zipcode": "02108",
            },
        )
        self.assertEqual(original_record["Zipcode"], "02108-1234")
        self.assertEqual(source_row, original_row)


class CleanEmailTests(unittest.TestCase):
    """Check conservative email repairs and reuse of format validation."""

    def test_email_cleanup_examples(self) -> None:
        """Cover trimming, permitted repairs, and values requiring review."""
        cases = [
            ("", ""),
            (" \t\n ", ""),
            ("member@example.com", "member@example.com"),
            ("  member@example.com  ", "member@example.com"),
            ("Member@EXAMPLE.COM", "Member@example.com"),
            ("First.Last+Updates@EXAMPLE.ORG", "First.Last+Updates@example.org"),
            ("o'neill@example.org", "o'neill@example.org"),
            ("member@example,com", "member@example.com"),
            ("member@example,org", "member@example.org"),
            ("member@example,net", "member@example.net"),
            (" Member@EXAMPLE,COM ", "Member@example.com"),
            ("member@example.info", "member@example.info"),
            ("member@example,info", ""),
            ("member@members.example,org", ""),
            ("member@example.com,org", ""),
            ("member@example,,com", ""),
            ("last,first@example.com", ""),
            ("member @ example.com", ""),
            ("member@example, com", ""),
            ("member@example.com;other@example.com", ""),
            ("member@example.com,other@example.com", ""),
            ("memberexample.com", ""),
            ("member@@example.com", ""),
            ('"first last"@example.com', ""),
            ("élise@example.com", ""),
            ("member@-example,com", ""),
            ("member..name@example,com", ""),
            ("member@example.com,", ""),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_email(original), expected)

    def test_repeated_cleanup_is_stable(self) -> None:
        """Rechecking a cleaned address should preserve the first result."""
        for original in [
            " member@example,com ",
            "Member@EXAMPLE.COM",
            "member @ example.com",
            "member@example.com,org",
        ]:
            with self.subTest(original=original):
                cleaned = clean_email(original)
                self.assertEqual(clean_email(cleaned), cleaned)

    def test_cleanup_after_mapping(self) -> None:
        """Clean mapped fields while retaining the original email and row."""
        source_headers = ["Given Name", "Surname", "Email", "Cell", "ZIP"]
        template_headers = [
            "First Name",
            "Last Name",
            "Email",
            "Primary Cell/Mobile Phone",
            "Zipcode",
        ]
        source_row = [
            "  jordan  ",
            "taylor",
            "  Jordan@example,com  ",
            "+1 (303) 555-0123",
            "02108-1234",
        ]
        original_row = source_row.copy()
        mapping = {
            0: "First Name",
            1: "Last Name",
            2: "Email",
            3: "Primary Cell/Mobile Phone",
            4: "Zipcode",
        }

        record = map_record(
            source_row, source_headers, template_headers, mapping
        )
        original_record = record.copy()
        record["First Name"] = clean_name(record["First Name"])
        record["Last Name"] = clean_name(record["Last Name"])
        record["Email"] = clean_email(record["Email"])
        record["Primary Cell/Mobile Phone"] = clean_phone(
            record["Primary Cell/Mobile Phone"]
        )
        record["Zipcode"] = clean_zipcode(record["Zipcode"])

        self.assertEqual(
            record,
            {
                "First Name": "Jordan",
                "Last Name": "Taylor",
                "Email": "Jordan@example.com",
                "Primary Cell/Mobile Phone": "3035550123",
                "Zipcode": "02108",
            },
        )
        self.assertEqual(original_record["Email"], "  Jordan@example,com  ")
        self.assertEqual(source_row, original_row)


class CleanCountryTests(unittest.TestCase):
    """Check explicit US aliases, blanks, and preservation of other entries."""

    def test_country_cleanup_examples(self) -> None:
        """Normalize known aliases without guessing from ambiguous values."""
        cases = [
            ("", ""),
            (" \t\n ", ""),
            ("US", "USA"),
            ("us", "USA"),
            ("USA", "USA"),
            (" usa ", "USA"),
            ("U.S", "USA"),
            ("U.S.", "USA"),
            ("U.S.A", "USA"),
            ("U.S.A.", "USA"),
            ("United States", "USA"),
            ("UNITED STATES OF AMERICA", "USA"),
            (" United   States ", "USA"),
            ("United\tStates\nof America", "USA"),
            (" Canada ", "Canada"),
            ("CANADA", "CANADA"),
            (" United   Kingdom ", "United   Kingdom"),
            ("MX", "MX"),
            ("America", "America"),
            (
                "United States Minor Outlying Islands",
                "United States Minor Outlying Islands",
            ),
            ("US/Canada", "US/Canada"),
            ("USA,", "USA,"),
            ("U S A", "U S A"),
            ("ＵＳＡ", "ＵＳＡ"),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_country(original), expected)

    def test_repeated_cleanup_is_stable(self) -> None:
        """Rechecking a country should preserve the first cleaned result."""
        for original in [" United   States ", "u.s.a.", " Canada ", "", "US/Canada"]:
            with self.subTest(original=original):
                cleaned = clean_country(original)
                self.assertEqual(clean_country(cleaned), cleaned)

    def test_cleanup_after_mapping(self) -> None:
        """Clean mapped countries without altering source or email values."""
        source_headers = ["Nation", "Contact Email"]
        template_headers = ["Country", "Email"]
        mapping = {0: "Country", 1: "Email"}

        for original, expected in [
            (" United   States ", "USA"),
            (" Canada ", "Canada"),
            ("", ""),
        ]:
            with self.subTest(country=original):
                source_row = [original, "member@example.com"]
                original_row = source_row.copy()
                record = map_record(
                    source_row, source_headers, template_headers, mapping
                )
                original_record = record.copy()
                record["Country"] = clean_country(record["Country"])

                self.assertEqual(
                    record,
                    {"Country": expected, "Email": "member@example.com"},
                )
                self.assertEqual(original_record["Country"], original)
                self.assertEqual(source_row, original_row)


class CleanStateTests(unittest.TestCase):
    """Check postal names/codes without inferring missing address details."""

    def test_state_cleanup_examples(self) -> None:
        """Cover names, codes, punctuation, postal regions, and unknowns."""
        cases = [
            ("", ""),
            (" \t\n ", ""),
            ("co", "CO"),
            (" CO ", "CO"),
            ("Colorado", "CO"),
            ("COLORADO", "CO"),
            ("New   York", "NY"),
            ("New\tYork", "NY"),
            ("N.Y.", "NY"),
            ("ca", "CA"),
            ("C.A.,", "CA"),
            ("District of Columbia", "DC"),
            ("D.C.", "DC"),
            ("Washington", "WA"),
            ("West Virginia", "WV"),
            ("Puerto Rico", "PR"),
            ("GU", "GU"),
            ("Armed Forces Pacific", "AP"),
            ("ae", "AE"),
            ("C A", ""),
            ("Calif.", ""),
            ("Ontario", ""),
            ("Denver, CO", ""),
            ("XX", ""),
            ("United States", ""),
            ("ＣＯ", ""),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_state(original), expected)

    def test_repeated_cleanup_is_stable(self) -> None:
        """Cleaned names/codes should remain stable on subsequent passes."""
        for original in [" Colorado ", "N.Y.", "District of Columbia", "XX"]:
            with self.subTest(original=original):
                cleaned = clean_state(original)
                self.assertEqual(clean_state(cleaned), cleaned)

    def test_cleanup_after_mapping(self) -> None:
        """Clean state/ZIP fields while preserving source and email values."""
        source_headers = ["Province", "Postal Code", "Contact Email"]
        template_headers = ["State", "Zipcode", "Email"]
        mapping = {0: "State", 1: "Zipcode", 2: "Email"}

        for state, zipcode, expected_state, expected_zip in [
            ("Colorado", "80203", "CO", "80203"),
            ("New York", "00501-1234", "NY", "00501"),
            ("Ontario", "00501", "", "00501"),
        ]:
            with self.subTest(state=state):
                source_row = [state, zipcode, "member@example.com"]
                original_row = source_row.copy()
                record = map_record(
                    source_row, source_headers, template_headers, mapping
                )
                original_record = record.copy()
                record["State"] = clean_state(record["State"])
                record["Zipcode"] = clean_zipcode(record["Zipcode"])

                self.assertEqual(
                    record,
                    {
                        "State": expected_state,
                        "Zipcode": expected_zip,
                        "Email": "member@example.com",
                    },
                )
                self.assertEqual(original_record["State"], state)
                self.assertEqual(original_record["Zipcode"], zipcode)
                self.assertEqual(source_row, original_row)


class CleanCityTests(unittest.TestCase):
    """Check city text formatting without asserting that a city is valid."""

    def test_city_cleanup_examples(self) -> None:
        """Cover punctuation, spacing, compound names, and conservative case."""
        cases = [
            ("", ""),
            (" \t\n ", ""),
            ("  denver  ", "Denver"),
            ("NEW   YORK", "New York"),
            ("ST. LOUIS,", "St Louis"),
            ("st. paul", "St Paul"),
            ("o'fallon", "O'Fallon"),
            ("WINSTON-SALEM", "Winston-Salem"),
            ("Winston-SALEM", "Winston-Salem"),
            ("McAllen", "McAllen"),
            ("mcallen", "Mcallen"),
            ("MCALLEN", "Mcallen"),
            ("LOS\tANGELES\n", "Los Angeles"),
            ("29 PALMS", "29 Palms"),
            ("Saint Louis", "Saint Louis"),
            ("Fort Worth", "Fort Worth"),
            ("  Salt   Lake City, ", "Salt Lake City"),
            ("san josé", "San José"),
            ("12345", "12345"),
            ("...,,,", ""),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_city(original), expected)

    def test_cleanup_after_mapping(self) -> None:
        """Format city/state fields while preserving blank cities and originals."""
        source_headers = ["Town", "Region", "Contact Email"]
        template_headers = ["City", "State", "Email"]
        mapping = {0: "City", 1: "State", 2: "Email"}

        for city, state, expected_city, expected_state in [
            (" st. louis, ", "mo", "St Louis", "MO"),
            ("WINSTON-SALEM", "nc", "Winston-Salem", "NC"),
            ("", "ny", "", "NY"),
        ]:
            with self.subTest(city=city):
                source_row = [city, state, "member@example.com"]
                original_row = source_row.copy()
                record = map_record(
                    source_row, source_headers, template_headers, mapping
                )
                original_record = record.copy()
                record["City"] = clean_city(record["City"])
                record["State"] = clean_state(record["State"])

                self.assertEqual(
                    record,
                    {
                        "City": expected_city,
                        "State": expected_state,
                        "Email": "member@example.com",
                    },
                )
                self.assertEqual(original_record["City"], city)
                self.assertEqual(original_record["State"], state)
                self.assertEqual(source_row, original_row)


class CleanStreetTests(unittest.TestCase):
    """Check PO-box handling and the initial ordinary-street formatter."""

    def test_po_box_addresses(self) -> None:
        """Recognize supported labels and preserve or reject number text."""
        cases = [
            ("PO Box 123", "PO Box 123"),
            (" p.o. box 123 ", "PO Box 123"),
            ("P.O.BOX123", "PO Box 123"),
            ("POBOX123", "PO Box 123"),
            ("P O BOX 123", "PO Box 123"),
            ("Post Office Box 00123", "PO Box 00123"),
            (" PO BOX #123, ", "PO Box 123"),
            ("PO Box 123.", "PO Box 123"),
            ("PO Box 123 ,", "PO Box 123"),
            ("PO Box", ""),
            ("P.O. Box", ""),
            ("Post Office Box", ""),
            ("PO Box...", ""),
            ("PO Box ABC", ""),
            ("PO Box 12,34", ""),
            ("PO Box 12.34", ""),
            ("PO Box 12 34", ""),
            ("PO Box 123-4", ""),
            ("PO Box 123ABC", ""),
            ("PO Box 123, PO Box 456", ""),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_street(original), expected)

    def test_basic_street_formatting(self) -> None:
        """Format supported base streets and recognized trailing units."""
        cases = [
            ("", ""),
            (" \t\n ", ""),
            (" 125 elm street., ", "125 Elm St"),
            ("125 north elm street", "125 N Elm St"),
            ("42 WINSTON-SALEM ROAD", "42 Winston-Salem Rd"),
            ("123 o'fallon lane", "123 O'Fallon Ln"),
            ("123 McDonald road", "123 McDonald Rd"),
            ("123 elm street apartment 4b", "123 Elm St Apt 4B"),
            ("123 elm street #4b", "123 Elm St # 4B"),
            ("123 1/2 oak avenue", "123 1/2 Oak Ave"),
            ("123 PO Boxwood Lane", "123 Po Boxwood Ln"),
            ("...,,,", ""),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_street(original), expected)

    def test_cleanup_after_mapping(self) -> None:
        """Keep Street values as strings and retain raw input for review."""
        source_headers = ["Mailing Address", "Contact Email"]
        template_headers = ["Street", "Email"]
        mapping = {0: "Street", 1: "Email"}

        for original, expected in [
            (" p.o. box 00123, ", "PO Box 00123"),
            ("PO Box", ""),
            ("PO Box 12,34", ""),
            ("123 elm street.,", "123 Elm St"),
            ("", ""),
        ]:
            with self.subTest(street=original):
                source_row = [original, "member@example.com"]
                original_row = source_row.copy()
                record = map_record(
                    source_row, source_headers, template_headers, mapping
                )
                original_record = record.copy()
                record["Street"] = clean_street(record["Street"])

                self.assertEqual(
                    record,
                    {"Street": expected, "Email": "member@example.com"},
                )
                self.assertIsInstance(record["Street"], str)
                self.assertEqual(original_record["Street"], original)
                self.assertEqual(source_row, original_row)


class CleanUnitTests(unittest.TestCase):
    """Check unit boundaries, identifier preservation, and review cases."""

    def test_unit_cleanup_examples(self) -> None:
        """Keep supported identifiers and reject missing or divided values."""
        cases = [
            ("", ""),
            (" \t\n ", ""),
            (" apartment 4b ", "Apt 4B"),
            ("APT. #004b", "Apt 004B"),
            ("Apartment4b", "Apt 4B"),
            ("Apt.4b", "Apt 4B"),
            ("Suite AB-03", "Ste AB-03"),
            ("Unit 02/03", "Unit 02/03"),
            ("Building 002", "Bldg 002"),
            ("Floor 3", "Fl 3"),
            ("Room a", "Rm A"),
            ("Hangar 2", "Hngr 2"),
            ("4b", "# 4B"),
            ("#4b", "# 4B"),
            ("# 004b, ", "# 004B"),
            ("Apt 4B.", "Apt 4B"),
            ("Basement", "Bsmt"),
            ("Rear", "Rear"),
            ("Office", "Ofc"),
            ("Penthouse", "Ph"),
            ("Apartment", ""),
            ("Apt.", ""),
            ("Suite", ""),
            ("Floor", ""),
            ("#", ""),
            ("Apt 4,5", ""),
            ("Apt 4.5", ""),
            ("Apt 4 B", ""),
            ("Apt 4&5", ""),
            ("Apt ##4", ""),
            ("Apt Suite", ""),
            ("Building 2 Apt 4B", ""),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_unit(original), expected)
                self.assertEqual(clean_unit(expected), expected)

    def test_units_in_street(self) -> None:
        """Separate units before punctuation cleanup and retain the full base."""
        cases = [
            ("125 Elm Street, Apartment 4B", "125 Elm St Apt 4B"),
            ("125 north elm street apt. #004b", "125 N Elm St Apt 004B"),
            ("125 Elm Street northwest Suite AB-03", "125 Elm St NW Ste AB-03"),
            ("125 Elm St#4b", "125 Elm St # 4B"),
            ("125 Elm Street Apartment4b", "125 Elm St Apt 4B"),
            ("125 Elm Street Apt.4b", "125 Elm St Apt 4B"),
            ("125 1/2 Elm Street Unit 02/03", "125 1/2 Elm St Unit 02/03"),
            ("125 Elm Street Building 002", "125 Elm St Bldg 002"),
            ("125 Elm Street Basement", "125 Elm St Bsmt"),
            ("125 Elm Street Rear", "125 Elm St Rear"),
            ("125 Elm Street Apt", ""),
            ("125 Elm Street Apt,", ""),
            ("125 Elm Street #", ""),
            ("125 Elm Street Apt 4,5", ""),
            ("125 Elm Street Apt 4.5", ""),
            ("125 Elm Street Apt 4 B", ""),
            ("125 Elm Street Bldg 2 Apt 4B", ""),
            ("125 Elm Street Apt 4B, Suite 2", ""),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_street(original), expected)
                self.assertEqual(clean_street(expected), expected)

    def test_unit_words_and_unrecognized_boundaries(self) -> None:
        """Protect name words and avoid inferring unlabelled or prefix units."""
        cases = [
            ("123 Suite Road", "123 Suite Rd"),
            ("123 Rear View Street", "123 Rear View St"),
            ("123 Apartment Road", "123 Apartment Rd"),
            ("123 Unit Circle", "123 Unit Cir"),
            ("123 Office Park Road", "123 Office Park Rd"),
            ("123 Elm Street 4B", "123 Elm Street 4B"),
            ("123 Elm Apt 4B", "123 Elm Apt 4B"),
            ("Apt 4B 123 Elm Street", "Apt 4B 123 Elm Street"),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_street(original), expected)

    def test_unit_cleanup_after_mapping(self) -> None:
        """Retain original unit text when working Street is changed or cleared."""
        source_headers = ["Mailing Address", "Contact Email"]
        template_headers = ["Street", "Email"]
        mapping = {0: "Street", 1: "Email"}

        for original, expected in [
            ("125 Elm Street, Apartment 004b", "125 Elm St Apt 004B"),
            ("125 Elm Street #4b", "125 Elm St # 4B"),
            ("125 Elm Street Basement", "125 Elm St Bsmt"),
            ("125 Elm Street Apt", ""),
            ("125 Elm Street Apt 4,5", ""),
        ]:
            with self.subTest(street=original):
                source_row = [original, "member@example.com"]
                original_row = source_row.copy()
                record = map_record(
                    source_row, source_headers, template_headers, mapping
                )
                original_record = record.copy()
                record["Street"] = clean_street(record["Street"])

                self.assertEqual(
                    record,
                    {"Street": expected, "Email": "member@example.com"},
                )
                self.assertIsInstance(record["Street"], str)
                self.assertEqual(clean_street(record["Street"]), expected)
                self.assertEqual(original_record["Street"], original)
                self.assertEqual(source_row, original_row)


class CleanStreetPostalTests(unittest.TestCase):
    """Check abbreviation positions and protection of street-name words."""

    def test_suffix_positions(self) -> None:
        """Shorten known endings without rewriting words inside the name."""
        cases = [
            ("125 Lake View Drive", "125 Lake View Dr"),
            ("125 Street Road", "125 Street Rd"),
            ("125 St John Street", "125 St John St"),
            ("125 Main Strt", "125 Main St"),
            ("125 Sunny Meadow", "125 Sunny Mdw"),
            ("125 Sunny MDW", "125 Sunny Mdw"),
            ("125 Sunny Meadows", "125 Sunny Mdws"),
            ("125 Oak Stravenue", "125 Oak Stra"),
            ("125 Oak Boulevard", "125 Oak Blvd"),
            ("125 Oak Parkway", "125 Oak Pkwy"),
            ("125 Broadway", "125 Broadway"),
            ("125 Lake", "125 Lake"),
            ("125 1/2 Lake", "125 1/2 Lake"),
            ("One Main Street", "One Main Street"),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_street(original), expected)

    def test_directional_positions(self) -> None:
        """Handle supported prefix/suffix directions and retain name words."""
        cases = [
            ("125 east elm street", "125 E Elm St"),
            ("125 northwest elm street", "125 NW Elm St"),
            ("125 n.e. elm street", "125 NE Elm St"),
            ("125 elm street west", "125 Elm St W"),
            ("125 elm street nw", "125 Elm St NW"),
            ("125 west elm street northeast", "125 W Elm St NE"),
            ("125 North Street", "125 North St"),
            ("125 NE Street", "125 NE St"),
            ("125 Elm North Street", "125 Elm North St"),
            ("125 East West Street", "125 East West St"),
            ("125 Avenue East", "125 Avenue East"),
            ("125 1/2 west elm street", "125 1/2 W Elm St"),
        ]

        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(clean_street(original), expected)

    def test_postal_cleanup_after_mapping(self) -> None:
        """Retain originals and ensure postal formatting remains stable."""
        source_headers = ["Mailing Address", "Contact Email"]
        template_headers = ["Street", "Email"]
        mapping = {0: "Street", 1: "Email"}

        for original, expected in [
            ("125 east elm street.,", "125 E Elm St"),
            ("125 Elm Street northwest", "125 Elm St NW"),
            ("125 North Street", "125 North St"),
            ("125 Sunny Meadow", "125 Sunny Mdw"),
        ]:
            with self.subTest(street=original):
                source_row = [original, "member@example.com"]
                original_row = source_row.copy()
                record = map_record(
                    source_row, source_headers, template_headers, mapping
                )
                original_record = record.copy()
                record["Street"] = clean_street(record["Street"])

                self.assertEqual(
                    record,
                    {"Street": expected, "Email": "member@example.com"},
                )
                self.assertEqual(clean_street(record["Street"]), expected)
                self.assertEqual(original_record["Street"], original)
                self.assertEqual(source_row, original_row)


class CleanDateSignedTests(unittest.TestCase):
    """Check US date formatting with a fixed, repeatable processing date."""

    reference_date = date(2026, 11, 6)

    def test_date_signed_cleanup_examples(self) -> None:
        """Format safe inputs and leave unsupported/unclear dates blank for review."""
        cases = [
            ("11/06/26", "11/06/26"), (" 3/7/26 ", "03/07/26"),
            ("3/7/2026", "03/07/26"), ("02/29/2024", "02/29/24"),
            ("02/29/00", "02/29/00"), ("01/01/2000", "01/01/00"),
            ("", ""), (" \t\n ", ""), ("02/29/2025", ""),
            ("04/31/26", ""), ("00/10/26", ""), ("11/00/26", ""),
            ("13/01/26", ""), ("11/07/26", ""), ("12/31/99", ""),
            ("11/06/1926", ""), ("12/31/1999", ""), ("01/01/2100", ""),
            ("2026-11-06", ""), ("11-06-26", ""), ("06/11/026", ""),
            ("31/12/25", ""), ("11 /06/26", ""), ("11/06/26 00:00", ""),
            ("45000", ""), ("１１/０６/２６", ""),
        ]
        for original, expected in cases:
            with self.subTest(original=original):
                self.assertEqual(
                    clean_date_signed(original, reference_date=self.reference_date),
                    expected,
                )

    def test_repeated_date_cleanup_is_stable(self) -> None:
        """A fixed batch reference date makes repeated cleanup deterministic."""
        for original in ["3/7/2026", "02/29/00", "11/06/26", "bad date", ""]:
            with self.subTest(original=original):
                first = clean_date_signed(original, reference_date=self.reference_date)
                self.assertEqual(
                    clean_date_signed(first, reference_date=self.reference_date), first
                )

    def test_date_cleanup_after_mapping_preserves_inputs(self) -> None:
        """Change only the mapped date while preserving exact fields and source text."""
        headers = ["Signed", "Postal", "Contact"]
        template = ["Email", "DateSigned", "Zipcode", "PROISSSUB "]
        mapping = {0: "DateSigned", 1: "Zipcode", 2: "Email"}
        for original in [" 3/7/2026 ", "02/29/25", ""]:
            with self.subTest(original=original):
                source = [original, "00501", "member@example.com"]
                before = source.copy()
                record = map_record(source, headers, template, mapping)
                mapped_before = record.copy()
                record["DateSigned"] = clean_date_signed(
                    record["DateSigned"], reference_date=self.reference_date
                )
                self.assertEqual(record["DateSigned"], "03/07/26" if original.strip() == "3/7/2026" else "")
                self.assertEqual(source, before)
                self.assertEqual(mapped_before["DateSigned"], original)
                self.assertEqual(list(record), template)
                self.assertEqual(record["Zipcode"], "00501")
                self.assertEqual(record["Email"], "member@example.com")
                self.assertEqual(record["PROISSSUB "], "")

