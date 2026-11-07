"""Field-format and review-issue checks using fictional member data.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Verify contact/address formats, name/contact decisions, and review issues
plus combined evaluation and template-only CSV output. Preserve original
values and independent review decisions. Run from
the project root with unittest discovery.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import csv
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

from member_cleaner.cleanup import (
    assemble_street, 
    clean_city, 
    clean_country, 
    clean_email, 
    clean_phone,
    clean_date_signed, 
    clean_name, 
    clean_state, 
    clean_zipcode,
)
from member_cleaner.mapping import map_record_with_unit
from member_cleaner.csv_io import read_source_csv, write_output_csv
from member_cleaner.models import MemberRecord, ReviewIssue
from member_cleaner.validation import (
    evaluate_record,
    get_address_issues,
    get_address_status,
    get_date_signed_issues,
    get_name_contact_result,
    get_phone_email_issues,
    has_usable_contact,
    has_usable_name,
    is_valid_email,
    is_valid_phone,
    is_valid_city,
    is_valid_state,
    is_valid_street,
    is_valid_zipcode,
    is_valid_date_signed,
    parse_date_signed,
)


class EmailValidationTests(unittest.TestCase):
    """Check the application's supported email format without network access."""

    def test_supported_email_formats(self) -> None:
        """Accept ordinary addresses and supported local/domain variations."""
        addresses = [
            "member@example.com",
            "first.last@example.org",
            "first+updates@example.org",
            "o'neill@example.org",
            "Member@EXAMPLE.COM",
            "member@members.example.org",
            "member@group-name.example",
            "a@b.co",
            "member_1@example.org",
            "member@xn--bcher-kva.example",
            "first!last@example.com",
            "first/last@example.com",
            "first=last@example.com",
        ]

        for address in addresses:
            with self.subTest(address=address):
                self.assertTrue(is_valid_email(address))

    def test_rejected_or_unsupported_formats(self) -> None:
        """Reject malformed, divided, multiple, or unsupported addresses."""
        addresses = [
            "",
            " \t\n ",
            "memberexample.com",
            "member@@example.com",
            "@example.com",
            "member@",
            "member@example",
            "member@.example.com",
            "member@example.com.",
            "member@example..com",
            ".member@example.com",
            "member.@example.com",
            "first..last@example.com",
            "member @example.com",
            "member@ example.com",
            " member@example.com",
            "member@example.com ",
            "member@example,com",
            "member@example_com",
            "member@-example.com",
            "member@example-.com",
            "member@example.123",
            "member@example.com;other@example.com",
            "member@example.com,other@example.com",
            "Member Name <member@example.com>",
            '"first last"@example.com',
            "élise@example.com",
            "member@exámple.com",
        ]

        for address in addresses:
            with self.subTest(address=address):
                self.assertFalse(is_valid_email(address))

    def test_length_boundaries(self) -> None:
        """Check both sides of local-part, domain-label, and total limits."""
        domain_prefix = "b" * 63 + "." + "c" * 63 + "."
        longest_address = "a" * 64 + "@" + domain_prefix + "d" * 57 + ".com"
        longer_address = "a" * 64 + "@" + domain_prefix + "d" * 58 + ".com"

        cases = [
            ("a" * 64 + "@example.com", True),
            ("a" * 65 + "@example.com", False),
            ("member@" + "b" * 63 + ".com", True),
            ("member@" + "b" * 64 + ".com", False),
            (longest_address, True),
            (longer_address, False),
        ]

        for address, expected in cases:
            with self.subTest(length=len(address), address=address):
                self.assertEqual(is_valid_email(address), expected)


def make_contact_record(phone: str, email: str) -> MemberRecord:
    """Preserve raw contacts, then apply the existing cleanup functions."""
    record = MemberRecord(
        [phone, email],
        {"Primary Cell/Mobile Phone": phone, "Email": email, "Street": ""},
    )
    cleaned = dict(record.working_values)
    cleaned["Primary Cell/Mobile Phone"] = clean_phone(phone)
    cleaned["Email"] = clean_email(email)
    record.apply_cleaned_values(cleaned)
    return record


class PhoneValidationTests(unittest.TestCase):
    """Check canonical phone values without doing cleanup or network lookups."""

    def test_canonical_phone_format(self) -> None:
        """Require ten ASCII digits and keep normalization a separate step."""
        cases = [
            ("2025550147", True),
            ("0123456789", True),
            ("0000000000", True),
            ("", False),
            ("202555014", False),
            ("12025550147", False),
            ("+12025550147", False),
            ("202-555-0147", False),
            ("(202) 555-0147", False),
            (" 2025550147", False),
            ("2025550147 ", False),
            ("2025550147x12", False),
            ("２０２５５５０１４７", False),
            ("٢٠٢٥٥٥٠١٤٧", False),
        ]

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(is_valid_phone(value), expected)


class PhoneEmailIssueTests(unittest.TestCase):
    """Check review reasons against current values and preserved originals."""

    def test_cleaned_usable_contacts_do_not_need_review(self) -> None:
        """Accept safe repairs instead of flagging every formatting change."""
        cases = [
            ("1 (202) 555-0147", " member@example,com "),
            ("202.555.0147", "Member@EXAMPLE.COM"),
            ("0123456789", "first+updates@example.org"),
        ]

        for phone, email in cases:
            with self.subTest(phone=phone, email=email):
                record = make_contact_record(phone, email)
                self.assertEqual(get_phone_email_issues(record), [])
                self.assertEqual(record.original_mapped_values["Email"], email)
                self.assertEqual(
                    record.original_mapped_values["Primary Cell/Mobile Phone"], phone
                )
                self.assertIsNone(record.eligible)

    def test_values_cleared_by_cleanup_produce_field_issues(self) -> None:
        """A blank working value must not hide supplied contact information."""
        cases = [
            ("202-555-014", "member@example.com", ["PHONE_CLEARED"]),
            ("2025550147", "member @example.com", ["EMAIL_CLEARED"]),
            (
                "2025550147 ext 2",
                "one@example.com;two@example.com",
                ["PHONE_CLEARED", "EMAIL_CLEARED"],
            ),
        ]

        for phone, email, expected_codes in cases:
            with self.subTest(phone=phone, email=email):
                record = make_contact_record(phone, email)
                issues = get_phone_email_issues(record)

                self.assertEqual([issue.code for issue in issues], expected_codes)
                self.assertTrue(all(issue.message for issue in issues))
                for issue in issues:
                    expected_field = (
                        "Primary Cell/Mobile Phone"
                        if issue.code == "PHONE_CLEARED" else "Email"
                    )
                    self.assertEqual(issue.field_name, expected_field)
                self.assertEqual(record.original_source_values, (phone, email))
                self.assertEqual(record.issues, [])

    def test_manual_corrections_and_intentional_removals(self) -> None:
        """Validate corrections and let explicit removal resolve a cleared flag."""
        record = make_contact_record("bad phone", "not-an-email")
        self.assertEqual(len(get_phone_email_issues(record)), 2)

        record.edit_field("Primary Cell/Mobile Phone", "2025550147")
        record.edit_field("Email", "corrected@example.com")
        self.assertEqual(get_phone_email_issues(record), [])

        # A preserved manual override still needs to meet the format contract.
        record.edit_field("Primary Cell/Mobile Phone", "202-555-0147")
        record.edit_field("Email", "member @example.com")
        self.assertEqual(
            [issue.code for issue in get_phone_email_issues(record)],
            ["INVALID_PHONE", "INVALID_EMAIL"],
        )

        record.edit_field("Primary Cell/Mobile Phone", "")
        record.edit_field("Email", "")
        self.assertEqual(get_phone_email_issues(record), [])
        self.assertIsNone(record.eligible)
        self.assertFalse(record.is_included)
        self.assertEqual(record.original_source_values, ("bad phone", "not-an-email"))

    def test_optional_and_unmapped_contacts_do_not_get_missing_flags(self) -> None:
        """Do not require both contacts or assume every template contains them."""
        for phone, email in [("", ""), (" \t ", "\n"), ("", "member@example.com")]:
            with self.subTest(phone=phone, email=email):
                record = make_contact_record(phone, email)
                self.assertEqual(get_phone_email_issues(record), [])

        for mapped in [{"First Name": "Jordan"}, {"Email": ""}]:
            with self.subTest(mapped=mapped):
                record = MemberRecord(list(mapped.values()), mapped)
                self.assertEqual(get_phone_email_issues(record), [])
                self.assertIsNone(record.eligible)

    def test_issue_collection_is_repeatable_and_side_effect_free(self) -> None:
        """Repeated checks return fresh lists without changing other review state."""
        record = make_contact_record("bad phone", "not-an-email")
        address_issue = ReviewIssue("Street", "ADDRESS_REVIEW", "Review the address.")
        record.issues.append(address_issue)
        record.manual_exclusion_reason = "Reviewer excluded this row."
        values_before = dict(record.working_values)
        original_id = record.record_id

        first = get_phone_email_issues(record)
        second = get_phone_email_issues(record)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        first.append(ReviewIssue(None, "EXAMPLE", "Only the returned list changes."))

        self.assertEqual(len(second), 2)
        self.assertEqual(record.issues, [address_issue])
        self.assertEqual(dict(record.working_values), values_before)
        self.assertEqual(record.record_id, original_id)
        self.assertEqual(record.manual_exclusion_reason, "Reviewer excluded this row.")
        self.assertIsNone(record.eligible)


def make_address_record(
    street: str = "125 Elm Street",
    city: str = "Denver",
    state: str = "Colorado",
    zipcode: str = "80203",
    country: str = "",
    unit: str = "",
) -> MemberRecord:
    """Capture fictional raw fields before running the real address cleaners."""
    mapped = {
        "Street": street, "City": city, "State": state,
        "Zipcode": zipcode, "Country": country, "Address Contact Status": "",
    }
    record = MemberRecord([street, city, state, zipcode, country, unit], mapped, unit)
    apply_address_cleanup(record)
    return record


def apply_address_cleanup(record: MemberRecord) -> None:
    """Apply the address workflow without changing the record's exact schema."""
    cleaned = dict(record.working_values)
    cleaned["Street"] = assemble_street(cleaned["Street"], record.original_unit_value)
    for name, cleaner in (
        ("City", clean_city), ("State", clean_state),
        ("Zipcode", clean_zipcode), ("Country", clean_country),
    ):
        if name in cleaned:
            cleaned[name] = cleaner(cleaned[name])
    record.apply_cleaned_values(cleaned)


class AddressFormatTests(unittest.TestCase):
    """Check supported formats without inventing geographic knowledge."""

    def test_city_state_and_zip_formats(self) -> None:
        """Check compound/Unicode names, postal regions, and five ASCII digits."""
        groups = (
            (is_valid_city, ["Denver", "29 Palms", "San José", "O'Fallon",
                             "Winston-Salem", "Coeur d’Alene"],
             ["", "123", "Denver, CO", "Denver  ", "New  York", "@Denver", "---"]),
            (is_valid_state, ["CO", "DC", "PR", "AA"],
             ["", "Colorado", "co", "ZZ", " CO", "CO "]),
            (is_valid_zipcode, ["80203", "00501", "00000"],
             ["", "501", "80203-1234", "802030000", " 80203", "８０２０３"]),
        )
        for check_format, accepted, rejected in groups:
            for value in accepted + rejected:
                with self.subTest(check=check_format.__name__, value=value):
                    self.assertEqual(check_format(value), value in accepted)

    def test_supported_and_unsupported_street_shapes(self) -> None:
        """Accept supported houses/units/PO boxes; do not invent missing suffixes."""
        accepted = [
            "125 Elm St", "125A Elm St NW", "12-14 Elm St", "125 1/2 Elm St",
            "125 N Elm St Apt 004B", "125 Elm St # 004B", "125 Elm St Rear",
            "125 Elm St Fl 3", "125 Elm St Ste AB-03", "125 Elm St Unit 02/03",
            "125 O'Neil St", "125 San José St", "PO Box 00123",
        ]
        rejected = [
            "", "125 Elm", "Elm St", "One Elm St", "125 Elm St,",
            "125 Elm St.", "125  Elm St", "125 Elm St\n", "125 El@m St",
            "125 Elm St Apt", "125 Elm St Apt 4,5", "125 Elm St Apt 4 5",
            "125 Elm St Bldg 2 Apt 4", "125 Elm St 4B", "125 1/0 Elm St",
            "PO Box", "PO Box AB12", "PO Box 123 Apt 4", "Apt 4 125 Elm St",
        ]
        for value in accepted + rejected:
            with self.subTest(value=value):
                self.assertEqual(is_valid_street(value), value in accepted)


class AddressIssueTests(unittest.TestCase):
    """Check completeness, source preservation, corrections, and computed status."""

    def test_complete_addresses_and_numbered_po_boxes(self) -> None:
        """A complete supported address needs no flag or source-value changes."""
        for street, unit in [
            (" 125 elm street, ", ""), ("P.O. Box #00123", ""),
            ("125 Elm Street", "Apartment 004b"), ("125 Elm St Rear", ""),
        ]:
            with self.subTest(street=street, unit=unit):
                record = make_address_record(street=street, unit=unit)
                self.assertEqual(get_address_issues(record), [])
                self.assertEqual(get_address_status(record), "MAILABLE")
                self.assertEqual(record.original_mapped_values["Street"], street)
                self.assertEqual(record.original_unit_value, unit)
                self.assertEqual(record.working_values["Address Contact Status"], "")
                self.assertIsNone(record.eligible)

    def test_absent_and_partial_addresses(self) -> None:
        """Do not flag absent addresses; require every component of partial ones."""
        absent = make_address_record("", "", "", "", "USA")
        self.assertEqual(get_address_issues(absent), [])
        self.assertEqual(get_address_status(absent), "BAD_ADDRESS")
        phone_only = MemberRecord(["2025550147"], {"Primary Cell/Mobile Phone": "2025550147"})
        self.assertEqual(get_address_issues(phone_only), [])
        self.assertEqual(get_address_status(phone_only), "BAD_ADDRESS")

        partial = make_address_record(city="", state="", zipcode="")
        self.assertEqual([issue.code for issue in get_address_issues(partial)],
                         ["MISSING_CITY", "MISSING_STATE", "MISSING_ZIPCODE"])
        self.assertEqual(get_address_status(partial), "BAD_ADDRESS")
        self.assertEqual(partial.working_values["City"], "")

    def test_cleanup_cannot_hide_supplied_address_values(self) -> None:
        """Flag cleared fields and separate-unit conflicts using raw snapshots."""
        record = make_address_record(state="Unknown", zipcode="8020")
        self.assertEqual([issue.code for issue in get_address_issues(record)],
                         ["STATE_CLEARED", "ZIPCODE_CLEARED"])
        record = make_address_record(street="PO Box")
        self.assertEqual(get_address_issues(record)[0].code, "STREET_CLEARED")

        for street, unit in [("125 Elm St Apt 4", "Apt 5"),
                             ("125 Elm St", "Apt 4,5"), ("", "Apt 4")]:
            with self.subTest(street=street, unit=unit):
                record = make_address_record(street=street, unit=unit)
                self.assertEqual(record.working_values["Street"], "")
                self.assertEqual(get_address_issues(record)[0].code, "STREET_UNIT_REVIEW")
                self.assertEqual(get_address_status(record), "BAD_ADDRESS")
                self.assertEqual(record.original_unit_value, unit)

    def test_country_rules_and_unexpected_clearing(self) -> None:
        """Allow blank/cleaned USA; do not silently erase a supplied country."""
        for country in ["", "United States", "US", "USA"]:
            with self.subTest(country=country):
                self.assertEqual(get_address_status(make_address_record(country=country)),
                                 "MAILABLE")
        record = make_address_record(country="Canada")
        self.assertEqual(get_address_issues(record)[0].code, "COUNTRY_REVIEW")
        self.assertEqual(get_address_status(record), "BAD_ADDRESS")
        changed = dict(record.working_values)
        changed["Country"] = ""
        record.apply_cleaned_values(changed)
        self.assertEqual(get_address_issues(record)[0].code, "COUNTRY_CLEARED")
        record.edit_field("Country", "USA")
        self.assertEqual(get_address_status(record), "MAILABLE")

    def test_missing_changed_and_agreeing_original_units(self) -> None:
        """Require supplied units without conflating identifiers or known types."""
        record = make_address_record(unit="Apartment 004B")
        for street, expected in [
            ("125 Elm St", "UNIT_MISSING"), ("125 Elm St Apt 4B", "UNIT_CONFLICT"),
            ("125 Elm St Ste 004B", "UNIT_CONFLICT"), ("125 Elm St # 004B", None),
        ]:
            with self.subTest(street=street):
                changed = dict(record.working_values)
                changed["Street"] = street
                record.apply_cleaned_values(changed)
                self.assertEqual([issue.code for issue in get_address_issues(record)],
                                 [] if expected is None else [expected])

        embedded = make_address_record(street="125 Elm St Apt 004B")
        changed = dict(embedded.working_values)
        changed["Street"] = "125 Elm St"
        embedded.apply_cleaned_values(changed)
        self.assertEqual(get_address_issues(embedded)[0].code, "UNIT_MISSING")
        invalid_raw = make_address_record(unit="Apt 4,5")
        changed = dict(invalid_raw.working_values)
        changed["Street"] = "125 Elm St Apt 45"
        invalid_raw.apply_cleaned_values(changed)
        self.assertEqual(get_address_issues(invalid_raw)[0].code, "UNIT_REVIEW")

    def test_uncertain_direction_and_unit_word_boundaries(self) -> None:
        """Require human confirmation for possible changes to literal names."""
        for street, expected in [
            ("125 North Star Street", "DIRECTION_REVIEW"),
            ("125 Elm Street Rear Road", "UNIT_BOUNDARY_REVIEW"),
        ]:
            with self.subTest(street=street):
                record = make_address_record(street=street)
                self.assertIn(expected, [issue.code for issue in get_address_issues(record)])
                self.assertEqual(get_address_status(record), "BAD_ADDRESS")
                # Accepting the same text is a deliberate confirmation, not cleanup.
                record.edit_field("Street", record.working_values["Street"])
                self.assertEqual(get_address_issues(record), [])
                self.assertEqual(get_address_status(record), "MAILABLE")
        for street in ["125 North Street", "125 N Star Street", "125 North East Street"]:
            with self.subTest(street=street):
                self.assertEqual(get_address_issues(make_address_record(street=street)), [])

    def test_manual_corrections_removals_and_format_checks(self) -> None:
        """Corrections resolve issues only while meeting current format rules."""
        record = make_address_record(street="125 Elm St Apt 4", unit="Apt 5")
        record.edit_field("Street", "125 Elm St Apt 5")
        self.assertEqual(get_address_status(record), "MAILABLE")
        record.edit_field("Street", "125 Elm")
        record.edit_field("City", "Denver, CO")
        record.edit_field("State", "Colorado")
        record.edit_field("Zipcode", "8020")
        self.assertEqual([issue.code for issue in get_address_issues(record)],
                         ["STREET_FORMAT", "CITY_FORMAT", "STATE_FORMAT", "ZIPCODE_FORMAT"])
        for name in ["Street", "City", "State", "Zipcode"]:
            record.edit_field(name, "")
        self.assertEqual(get_address_issues(record), [])
        self.assertEqual(get_address_status(record), "BAD_ADDRESS")
        self.assertEqual(record.original_unit_value, "Apt 5")

        # Whitespace-only manual entries are invalid values, not an absent address.
        for name in ["Street", "City", "State", "Zipcode"]:
            record.edit_field(name, " ")
        self.assertEqual(len(get_address_issues(record)), 4)
        self.assertEqual(get_address_status(record), "BAD_ADDRESS")

    def test_issue_collection_and_status_are_repeatable_and_pure(self) -> None:
        """Do not accumulate issues or change unrelated evaluation/duplicate state."""
        record = make_address_record(zipcode="bad ZIP")
        unrelated = ReviewIssue("Email", "EMAIL_REVIEW", "Review supplied email.")
        record.issues.append(unrelated)
        record.eligible = True
        record.manual_exclusion_reason = "Reviewer choice"
        record.confirmed_duplicate_of = "fictional-survivor"
        before = (record.record_id, dict(record.working_values),
                  dict(record.manual_overrides), list(record.exclusion_reasons))
        first = get_address_issues(record)
        second = get_address_issues(record)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        first.clear()
        self.assertEqual(len(second), 1)
        self.assertEqual(get_address_status(record), "BAD_ADDRESS")
        self.assertEqual(record.issues, [unrelated])
        self.assertTrue(record.eligible)
        self.assertEqual(record.manual_exclusion_reason, "Reviewer choice")
        self.assertEqual(record.confirmed_duplicate_of, "fictional-survivor")
        self.assertEqual(before, (record.record_id, dict(record.working_values),
                                 dict(record.manual_overrides), list(record.exclusion_reasons)))

    def test_mapping_cleanup_and_validation_preserve_source_and_schema(self) -> None:
        """Use the actual mapper and cleaners before evaluating a combined address."""
        headers = ["Unit", "Mailing", "Town", "Region", "Postal"]
        template = ["Street", "City", "State", "Zipcode", "PROISSSUB "]
        source = ["004b", "125 elm street,", " boston ", "Massachusetts", "02108-1234"]
        mapped, unit = map_record_with_unit(
            source, headers, template,
            {1: "Street", 2: "City", 3: "State", 4: "Zipcode"}, unit_source_index=0,
        )
        record = MemberRecord(source, mapped, unit)
        apply_address_cleanup(record)
        self.assertEqual(get_address_issues(record), [])
        self.assertEqual(get_address_status(record), "MAILABLE")
        self.assertEqual(record.working_values["Street"], "125 Elm St # 004B")
        self.assertEqual(record.working_values["Zipcode"], "02108")
        self.assertEqual(record.working_values["PROISSSUB "], "")
        self.assertEqual(list(record.working_values), template)
        self.assertEqual(record.original_source_values, tuple(source))
        self.assertEqual(record.original_mapped_values, mapped)
        apply_address_cleanup(record)
        self.assertEqual(get_address_issues(record), [])
        self.assertEqual(get_address_status(record), "MAILABLE")


def make_name_contact_record(
    first_name: str,
    last_name: str,
    phone: str = "",
    email: str = "",
    *,
    address_fields: dict[str, str] | None = None,
    unit: str = "",
) -> MemberRecord:
    """Preserve fictional inputs, then run the real field-cleanup workflow."""
    mapped = {
        "First Name": first_name, "Last Name": last_name,
        "Primary Cell/Mobile Phone": phone, "Email": email,
        "Street": "", "City": "", "State": "", "Zipcode": "", "Country": "",
        "Address Contact Status": "",
    }
    mapped.update(address_fields or {})
    record = MemberRecord(list(mapped.values()) + [unit], mapped, unit)
    cleaned = dict(record.working_values)
    cleaned["First Name"] = clean_name(first_name)
    cleaned["Last Name"] = clean_name(last_name)
    cleaned["Primary Cell/Mobile Phone"] = clean_phone(phone)
    cleaned["Email"] = clean_email(email)
    record.apply_cleaned_values(cleaned)
    apply_address_cleanup(record)
    return record


class NameContactTests(unittest.TestCase):
    """Check retained names, Anonymous Donor proposals, and usable contacts."""

    def test_usable_and_fallback_name_shapes(self) -> None:
        """Distinguish full parts from absent names, lone initials, and initials-only."""
        cases = [
            ("Jordan", "Taylor", True), ("Jordan", "", True),
            ("J", "Taylor", True), ("Jordan", "T", True),
            ("Brittany Sue", "Nunez-Lopez", True), ("Brittany Sue", "Nunez Lopez", True),
            ("Li", "Ng", True), ("Élise", "O'Neill", True),
            ("J R", "Taylor", True), ("Jean-Luc", "", True),
            ("", "Taylor", False), ("", "T", False),
            ("J", "", False), ("J", "T", False), ("J R", "T S", False),
            ("J.T.", "", False), ("J-T", "", False),
            ("", "", False), ("   ", "---", False), ("123", "???", False),
        ]
        for first_name, last_name, expected in cases:
            with self.subTest(first_name=first_name, last_name=last_name):
                self.assertEqual(has_usable_name(first_name, last_name), expected)

    def test_retained_names_use_existing_cleanup_rules(self) -> None:
        """Keep compound names, initials, and first-name-only forms without a flag."""
        cases = [
            (" jordan ", " taylor ", "Jordan", "Taylor"),
            ("J.", "Taylor", "J", "Taylor"),
            ("Jordan", "T.", "Jordan", "T"),
            ("BRITTANY SUE", "nunez-lopez", "Brittany Sue", "Nunez-Lopez"),
            ("BRITTANY SUE", "nunez lopez", "Brittany Sue", "Nunez Lopez"),
            ("McDonald", "O'Neill", "McDonald", "O'Neill"),
            (" jordan ", "", "Jordan", ""),
        ]
        for first, last, expected_first, expected_last in cases:
            with self.subTest(first=first, last=last):
                record = make_name_contact_record(first, last, phone="1 (202) 555-0147")
                result = get_name_contact_result(record)
                self.assertEqual((result.first_name, result.last_name),
                                 (expected_first, expected_last))
                self.assertTrue(result.passes_name_contact_rules)
                self.assertFalse(result.used_anonymous_fallback)
                self.assertEqual(result.exclusion_reasons, ())
                self.assertEqual(record.issues, [])
                self.assertEqual(record.original_mapped_values["First Name"], first)
                self.assertEqual(record.original_mapped_values["Last Name"], last)

    def test_anonymous_substitution_for_agreed_name_cases(self) -> None:
        """Propose Anonymous Donor for unusable names with one qualifying contact."""
        for first, last in [("", "Taylor"), ("J.", "T."), ("J.", ""),
                            ("", "T"), ("", ""), ("J R", "T S")]:
            with self.subTest(first=first, last=last):
                record = make_name_contact_record(first, last, email=" member@example,com ")
                result = get_name_contact_result(record)
                self.assertEqual((result.first_name, result.last_name), ("Anonymous", "Donor"))
                self.assertTrue(result.used_anonymous_fallback)
                self.assertTrue(result.passes_name_contact_rules)
                self.assertEqual(result.exclusion_reasons, ())
                self.assertEqual(get_phone_email_issues(record), [])

    def test_any_one_usable_contact_can_support_anonymous_donor(self) -> None:
        """Accept email, phone without email, a street address, or a numbered PO box."""
        address = {"Street": "125 Elm Street", "City": "Denver",
                   "State": "Colorado", "Zipcode": "80203"}
        cases = [
            {"phone": "202-555-0147"},
            {"email": "member@example.com"},
            {"address_fields": address},
            {"address_fields": {**address, "Street": "P.O. Box 00123"}},
        ]
        for supplied in cases:
            with self.subTest(supplied=supplied):
                record = make_name_contact_record("", "", **supplied)
                self.assertTrue(has_usable_contact(record))
                result = get_name_contact_result(record)
                self.assertTrue(result.passes_name_contact_rules)
                self.assertTrue(result.used_anonymous_fallback)
                self.assertEqual((result.first_name, result.last_name), ("Anonymous", "Donor"))

    def test_missing_or_unusable_contacts_fail_for_any_name(self) -> None:
        """No name can replace the requirement for one usable contact method."""
        bad_address = {"Street": "125 Elm", "City": "Denver", "State": "CO",
                       "Zipcode": "80203", "Address Contact Status": "MAILABLE"}
        for first, last in [("Jordan", "Taylor"), ("", "Taylor"),
                            ("J.", "T."), ("", ""), ("Anonymous", "Donor")]:
            with self.subTest(first=first, last=last):
                record = make_name_contact_record(
                    first, last, phone="bad phone", email="not-an-email",
                    address_fields=bad_address,
                )
                self.assertFalse(has_usable_contact(record))
                result = get_name_contact_result(record)
                self.assertFalse(result.passes_name_contact_rules)
                self.assertTrue(result.exclusion_reasons)
                self.assertFalse(result.used_anonymous_fallback)
                self.assertEqual((result.first_name, result.last_name),
                                 (clean_name(first), clean_name(last)))
                self.assertIsNone(record.eligible)

        absent = make_name_contact_record("Jordan", "Taylor")
        self.assertFalse(get_name_contact_result(absent).passes_name_contact_rules)

    def test_other_issues_do_not_erase_an_independently_usable_contact(self) -> None:
        """Separate contact eligibility from unresolved field review requirements."""
        record = make_name_contact_record(
            "", "Taylor", phone="2025550147", email="bad email",
            address_fields={"Street": "125 Elm", "Country": "Canada"},
        )
        result = get_name_contact_result(record)
        self.assertTrue(result.passes_name_contact_rules)
        self.assertTrue(result.used_anonymous_fallback)
        self.assertEqual(get_address_status(record), "BAD_ADDRESS")
        self.assertEqual([issue.code for issue in get_phone_email_issues(record)],
                         ["EMAIL_CLEARED"])
        self.assertTrue(get_address_issues(record))

        # Source-dependent address concerns must prevent address-only eligibility.
        for address, unit in [
            ({"Street": "125 North Star Street"}, ""),
            ({"Street": "125 Elm Street", "Country": "Canada"}, ""),
            ({"Street": "125 Elm Street Apt 4"}, "Apt 5"),
        ]:
            with self.subTest(address=address, unit=unit):
                record = make_name_contact_record(
                    "", "", address_fields={"City": "Denver", "State": "CO",
                                            "Zipcode": "80203", **address}, unit=unit,
                )
                self.assertFalse(has_usable_contact(record))
                self.assertFalse(get_name_contact_result(record).passes_name_contact_rules)

    def test_manual_name_and_contact_corrections_are_re_evaluated(self) -> None:
        """Use current edits; neither valid old values nor a prior result can linger."""
        record = make_name_contact_record("", "Taylor", phone="2025550147")
        self.assertTrue(get_name_contact_result(record).used_anonymous_fallback)
        record.edit_field("First Name", "Jordan")
        result = get_name_contact_result(record)
        self.assertEqual((result.first_name, result.last_name), ("Jordan", "Taylor"))
        self.assertFalse(result.used_anonymous_fallback)

        record.edit_field("Primary Cell/Mobile Phone", "202-555-0147")
        self.assertFalse(get_name_contact_result(record).passes_name_contact_rules)
        record.edit_field("Email", "corrected@example.com")
        self.assertTrue(get_name_contact_result(record).passes_name_contact_rules)
        record.edit_field("Primary Cell/Mobile Phone", "")
        record.edit_field("Email", "")
        self.assertFalse(get_name_contact_result(record).passes_name_contact_rules)

    def test_generated_names_never_become_later_edit_inputs(self) -> None:
        """A later first-name-only correction must not inherit the generated Donor."""
        record = make_name_contact_record("", "", phone="2025550147")
        proposed = get_name_contact_result(record)
        self.assertEqual((proposed.first_name, proposed.last_name), ("Anonymous", "Donor"))
        self.assertEqual(record.working_values["First Name"], "")
        self.assertEqual(record.working_values["Last Name"], "")

        record.edit_field("First Name", "Jordan")
        corrected = get_name_contact_result(record)
        self.assertEqual((corrected.first_name, corrected.last_name), ("Jordan", ""))
        self.assertFalse(corrected.used_anonymous_fallback)
        self.assertEqual(record.original_mapped_values["First Name"], "")
        self.assertEqual(record.original_mapped_values["Last Name"], "")

    def test_results_are_immutable_and_evaluation_is_side_effect_free(self) -> None:
        """Return independent results while preserving every unrelated review decision."""
        record = make_name_contact_record("J.", "T.", phone="2025550147")
        issue = ReviewIssue("Email", "EXAMPLE", "Existing review information.")
        record.issues.append(issue)
        record.exclusion_reasons.append("Existing evaluation reason.")
        record.eligible = False
        record.manual_exclusion_reason = "Reviewer choice"
        record.confirmed_duplicate_of = "fictional-survivor"
        before = (record.record_id, record.original_source_values,
                  dict(record.original_mapped_values), dict(record.working_values),
                  dict(record.manual_overrides), list(record.issues),
                  list(record.exclusion_reasons), record.eligible,
                  record.manual_exclusion_reason, record.confirmed_duplicate_of)
        first = get_name_contact_result(record)
        second = get_name_contact_result(record)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertTrue(first.passes_name_contact_rules)
        with self.assertRaises(FrozenInstanceError):
            first.first_name = "Changed"
        with self.assertRaises(FrozenInstanceError):
            first.exclusion_reasons = ("Changed",)
        self.assertEqual(before, (record.record_id, record.original_source_values,
                                 dict(record.original_mapped_values), dict(record.working_values),
                                 dict(record.manual_overrides), list(record.issues),
                                 list(record.exclusion_reasons), record.eligible,
                                 record.manual_exclusion_reason, record.confirmed_duplicate_of))

    def test_mapping_cleanup_and_name_decision_preserve_exact_fields(self) -> None:
        """Keep expected blank petition/date text while evaluating a mapped first name."""
        headers = ["Surname", "Given", "Cell", "Petition", "Signed"]
        template = ["First Name", "Last Name", "Primary Cell/Mobile Phone",
                    "PROISSSUB ", "DateSigned"]
        source = ["", " jordan ", "1 (202) 555-0147", "", "11/06/26"]
        mapped, unit = map_record_with_unit(
            source, headers, template,
            {0: "Last Name", 1: "First Name", 2: "Primary Cell/Mobile Phone",
             3: "PROISSSUB ", 4: "DateSigned"},
        )
        record = MemberRecord(source, mapped, unit)
        cleaned = dict(record.working_values)
        cleaned["First Name"] = clean_name(cleaned["First Name"])
        cleaned["Last Name"] = clean_name(cleaned["Last Name"])
        cleaned["Primary Cell/Mobile Phone"] = clean_phone(cleaned["Primary Cell/Mobile Phone"])
        record.apply_cleaned_values(cleaned)
        result = get_name_contact_result(record)
        self.assertEqual((result.first_name, result.last_name), ("Jordan", ""))
        self.assertTrue(result.passes_name_contact_rules)
        self.assertEqual(record.original_source_values, tuple(source))
        self.assertEqual(record.original_mapped_values, mapped)
        self.assertEqual(list(record.working_values), template)
        self.assertEqual(record.working_values["PROISSSUB "], "")
        self.assertEqual(record.working_values["DateSigned"], "11/06/26")


def make_date_signed_record(value: str, reference_date: date) -> MemberRecord:
    """Preserve the raw signing date before applying the real date cleaner."""
    mapped = {"DateSigned": value, "First Name": "Jordan", "Last Name": "",
              "Primary Cell/Mobile Phone": "2025550147"}
    record = MemberRecord(list(mapped.values()), mapped)
    cleaned = dict(record.working_values)
    cleaned["DateSigned"] = clean_date_signed(value, reference_date=reference_date)
    record.apply_cleaned_values(cleaned)
    return record


class DateSignedValidationTests(unittest.TestCase):
    """Check date interpretation, provenance, corrections, and read-only issues."""

    reference_date = date(2026, 11, 6)

    def test_calendar_century_and_reference_date_boundaries(self) -> None:
        """Check real dates and explicit century/future limits without a hidden pivot."""
        cases = [
            ("3/7/26", date(2026, 3, 7)), ("11/06/2026", self.reference_date),
            ("02/29/00", date(2000, 2, 29)), ("02/29/24", date(2024, 2, 29)),
            ("02/29/25", None), ("04/31/26", None), ("11/07/26", None),
            ("12/31/99", None), ("12/31/1999", None), ("11/06/1926", None),
            ("01/01/2100", None), ("", None), ("11/06/026", None),
            ("2026-11-06", None), ("31/12/25", None),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    parse_date_signed(value, reference_date=self.reference_date), expected
                )
        self.assertEqual(
            parse_date_signed("12/31/99", reference_date=date(2099, 12, 31)),
            date(2099, 12, 31),
        )
        self.assertIsNone(
            parse_date_signed("01/01/2100", reference_date=date(2100, 1, 1))
        )

    def test_canonical_date_validation_does_not_clean_input(self) -> None:
        """Require MM/DD/YY even when a different raw form could be cleaned."""
        for value, expected in [
            ("03/07/26", True), ("11/06/26", True), ("02/29/00", True),
            ("3/7/26", False), ("03/07/2026", False), (" 03/07/26", False),
            ("03/07/26 ", False), ("02/29/25", False), ("11/07/26", False),
            ("12/31/99", False), ("", False),
        ]:
            with self.subTest(value=value):
                self.assertEqual(
                    is_valid_date_signed(value, reference_date=self.reference_date), expected
                )

    def test_cleaned_missing_cleared_and_unmapped_date_issues(self) -> None:
        """Flag absent/unclear dates without making a contact-qualified row ineligible."""
        cases = [
            (" 3/7/2026 ", []), ("11/06/26", []), ("02/29/00", []),
            ("", ["MISSING_DATE_SIGNED"]), (" \t ", ["MISSING_DATE_SIGNED"]),
            ("02/29/25", ["DATE_SIGNED_CLEARED"]),
            ("11/07/26", ["DATE_SIGNED_CLEARED"]),
            ("11/06/1926", ["DATE_SIGNED_CLEARED"]),
            ("11/06/26;11/05/26", ["DATE_SIGNED_CLEARED"]),
        ]
        for raw, codes in cases:
            with self.subTest(raw=raw):
                record = make_date_signed_record(raw, self.reference_date)
                issues = get_date_signed_issues(record, reference_date=self.reference_date)
                self.assertEqual([issue.code for issue in issues], codes)
                self.assertTrue(all(issue.field_name == "DateSigned" and issue.message
                                    for issue in issues))
                self.assertEqual(record.original_mapped_values["DateSigned"], raw)
                self.assertTrue(get_name_contact_result(record).passes_name_contact_rules)
                self.assertIsNone(record.eligible)
                self.assertEqual(record.issues, [])
        no_date_field = MemberRecord(["Jordan"], {"First Name": "Jordan"})
        self.assertEqual(get_date_signed_issues(no_date_field), [])

    def test_source_dates_cannot_be_silently_replaced_or_invented(self) -> None:
        """Expose lost centuries, changed dates, and automatic filling of a blank."""
        for original, expected_code in [
            ("11/06/1926", "DATE_SIGNED_SOURCE_REVIEW"),
            ("11/05/2026", "DATE_SIGNED_CONFLICT"),
            ("", "DATE_SIGNED_SOURCE_REVIEW"),
        ]:
            with self.subTest(original=original):
                record = make_date_signed_record(original, self.reference_date)
                changed = dict(record.working_values)
                changed["DateSigned"] = "11/06/26"
                record.apply_cleaned_values(changed)
                self.assertEqual(
                    [issue.code for issue in get_date_signed_issues(
                        record, reference_date=self.reference_date
                    )], [expected_code]
                )
                record.edit_field("DateSigned", "11/06/26")
                self.assertEqual(
                    get_date_signed_issues(record, reference_date=self.reference_date), []
                )
                self.assertEqual(record.original_mapped_values["DateSigned"], original)

    def test_manual_corrections_and_missing_dates_still_need_valid_values(self) -> None:
        """Validate corrections and retain the missing-date flag after explicit removal."""
        record = make_date_signed_record("bad date", self.reference_date)
        for replacement, expected_codes in [
            ("11/06/26", []), ("02/29/25", ["DATE_SIGNED_FORMAT"]),
            ("11/07/26", ["DATE_SIGNED_FORMAT"]), (" ", ["DATE_SIGNED_FORMAT"]),
            ("11/06/2026", ["DATE_SIGNED_FORMAT"]), ("", ["MISSING_DATE_SIGNED"]),
            ("03/07/26", []),
        ]:
            with self.subTest(replacement=replacement):
                record.edit_field("DateSigned", replacement)
                self.assertEqual(
                    [issue.code for issue in get_date_signed_issues(
                        record, reference_date=self.reference_date
                    )], expected_codes
                )
        self.assertEqual(record.original_mapped_values["DateSigned"], "bad date")

    def test_date_issue_collection_is_repeatable_and_side_effect_free(self) -> None:
        """Return fresh issue lists without changing values, IDs, or review decisions."""
        record = make_date_signed_record("02/29/25", self.reference_date)
        unrelated = ReviewIssue("Email", "EXAMPLE", "Existing review information.")
        record.issues.append(unrelated)
        record.exclusion_reasons.append("Existing reason.")
        record.eligible = True
        record.manual_exclusion_reason = "Reviewer choice"
        record.confirmed_duplicate_of = "fictional-survivor"
        before = (record.record_id, record.original_source_values,
                  dict(record.original_mapped_values), dict(record.working_values),
                  dict(record.manual_overrides), list(record.issues),
                  list(record.exclusion_reasons), record.eligible,
                  record.manual_exclusion_reason, record.confirmed_duplicate_of)
        first = get_date_signed_issues(record, reference_date=self.reference_date)
        second = get_date_signed_issues(record, reference_date=self.reference_date)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        first.clear()
        self.assertEqual(len(second), 1)
        self.assertEqual(before, (record.record_id, record.original_source_values,
                                 dict(record.original_mapped_values), dict(record.working_values),
                                 dict(record.manual_overrides), list(record.issues),
                                 list(record.exclusion_reasons), record.eligible,
                                 record.manual_exclusion_reason, record.confirmed_duplicate_of))


def apply_evaluation_cleanup(record: MemberRecord, reference_date: date) -> None:
    """Run the real cleanup steps used by the combined-evaluation fixtures."""
    cleaned = dict(record.working_values)
    for name, cleaner in (
        ("First Name", clean_name), ("Last Name", clean_name),
        ("Primary Cell/Mobile Phone", clean_phone), ("Email", clean_email),
    ):
        if name in cleaned:
            cleaned[name] = cleaner(cleaned[name])
    if "DateSigned" in cleaned:
        cleaned["DateSigned"] = clean_date_signed(
            cleaned["DateSigned"], reference_date=reference_date
        )
    record.apply_cleaned_values(cleaned)
    if "Street" in cleaned:
        apply_address_cleanup(record)


def make_evaluation_record(
    changes: dict[str, str] | None = None, *, unit: str = ""
) -> MemberRecord:
    """Preserve a fictional raw record before running actual field cleanup."""
    mapped = {
        "First Name": " jordan ", "Last Name": " taylor ",
        "Street": "125 elm street", "City": " boston ",
        "State": "Massachusetts", "Zipcode": "02108-1234", "Country": "",
        "Primary Cell/Mobile Phone": "1 (202) 555-0147",
        "Email": "member@example.com", "DateSigned": "3/7/2026",
        "PROISSSUB ": "", "Address Contact Status": "IMPORTED",
        "PhoneDisclaimeredYN": "N", "Account Classification": "ORGANIZATION",
        "Other  Field ": " Keep As Entered ",
    }
    mapped.update(changes or {})
    record = MemberRecord(list(mapped.values()) + [unit], mapped, unit)
    apply_evaluation_cleanup(record, date(2026, 11, 6))
    return record


class RecordEvaluationTests(unittest.TestCase):
    """Check combined decisions and detached output through the CSV workflow."""

    reference_date = date(2026, 11, 6)
    no_address = {"Street": "", "City": "", "State": "", "Zipcode": ""}

    def test_complete_record_gets_derived_output_without_changing_inputs(self) -> None:
        """Compute names/status/constants while preserving the editable values."""
        record = make_evaluation_record()
        working_before = dict(record.working_values)
        output = evaluate_record(record, reference_date=self.reference_date)
        self.assertIsNotNone(output)
        self.assertEqual(output["First Name"], "Jordan")
        self.assertEqual(output["Last Name"], "Taylor")
        self.assertEqual(output["Street"], "125 Elm St")
        self.assertEqual(output["Zipcode"], "02108")
        self.assertEqual(output["DateSigned"], "03/07/26")
        self.assertEqual(output["Address Contact Status"], "MAILABLE")
        self.assertEqual(output["PhoneDisclaimeredYN"], "Y")
        self.assertEqual(output["Account Classification"], "INDIVIDUAL")
        self.assertEqual(output["PROISSSUB "], "")
        self.assertEqual(output["Other  Field "], " Keep As Entered ")
        self.assertTrue(record.eligible)
        self.assertTrue(record.is_included)
        self.assertEqual(record.issues, [])
        self.assertEqual(record.exclusion_reasons, [])
        self.assertEqual(dict(record.working_values), working_before)

    def test_anonymous_donor_can_use_each_independent_contact_route(self) -> None:
        """Do not restore an email-only requirement while combining the checks."""
        for supplied in [
            {**self.no_address, "Primary Cell/Mobile Phone": "2025550147"},
            {**self.no_address, "Email": "member@example.com"},
            {},
            {"Street": "P.O. Box 00123"},
        ]:
            with self.subTest(supplied=supplied):
                record = make_evaluation_record({
                    "First Name": "", "Last Name": "",
                    "Primary Cell/Mobile Phone": "", "Email": "", **supplied,
                })
                output = evaluate_record(record, reference_date=self.reference_date)
                self.assertIsNotNone(output)
                self.assertEqual((output["First Name"], output["Last Name"]),
                                 ("Anonymous", "Donor"))
                self.assertTrue(record.eligible)
                self.assertEqual(record.working_values["First Name"], "")
                self.assertEqual(record.working_values["Last Name"], "")

    def test_retained_initial_compound_and_first_only_names(self) -> None:
        """Use the name result without inventing a surname or a missing-name flag."""
        for first, last, expected in [
            ("Jordan", "", ("Jordan", "")),
            ("J.", "Taylor", ("J", "Taylor")),
            ("Jordan", "T.", ("Jordan", "T")),
            ("BRITTANY SUE", "nunez-lopez", ("Brittany Sue", "Nunez-Lopez")),
            ("BRITTANY SUE", "nunez lopez", ("Brittany Sue", "Nunez Lopez")),
        ]:
            with self.subTest(first=first, last=last):
                record = make_evaluation_record({"First Name": first, "Last Name": last})
                output = evaluate_record(record, reference_date=self.reference_date)
                self.assertEqual((output["First Name"], output["Last Name"]), expected)
                self.assertEqual(record.issues, [])

    def test_no_usable_contact_excludes_with_a_whole_record_reason(self) -> None:
        """Names and an imported status cannot compensate for no usable contact."""
        record = make_evaluation_record({
            **self.no_address, "Primary Cell/Mobile Phone": "", "Email": "",
            "Address Contact Status": "MAILABLE",
        })
        self.assertIsNone(evaluate_record(record, reference_date=self.reference_date))
        self.assertFalse(record.eligible)
        self.assertFalse(record.is_included)
        self.assertTrue(record.exclusion_reasons)
        self.assertTrue(any(issue.code == "NO_USABLE_CONTACT" and issue.field_name is None
                            for issue in record.issues))

    def test_partial_or_uncertain_address_can_coexist_with_usable_contact(self) -> None:
        """Keep contact-qualified rows while deriving BAD_ADDRESS and current flags."""
        for changed, expected_code in [
            ({"Zipcode": ""}, "MISSING_ZIPCODE"),
            ({"Street": "125 Elm"}, "STREET_FORMAT"),
            ({"Street": "125 North Star Street"}, "DIRECTION_REVIEW"),
        ]:
            with self.subTest(changed=changed):
                record = make_evaluation_record(changed)
                output = evaluate_record(record, reference_date=self.reference_date)
                self.assertIsNotNone(output)
                self.assertEqual(output["Address Contact Status"], "BAD_ADDRESS")
                self.assertTrue(record.eligible)
                self.assertIn(expected_code, [issue.code for issue in record.issues])
                self.assertEqual(output["Street"], record.working_values["Street"])

    def test_invalid_manual_contacts_are_blank_only_in_output(self) -> None:
        """Preserve corrections for review while keeping malformed contacts out of CSV."""
        for field_name, replacement, code in [
            ("Primary Cell/Mobile Phone", "202-555-0147", "INVALID_PHONE"),
            ("Email", "one@example.com;two@example.com", "INVALID_EMAIL"),
        ]:
            with self.subTest(field_name=field_name):
                record = make_evaluation_record()
                record.edit_field(field_name, replacement)
                output = evaluate_record(record, reference_date=self.reference_date)
                self.assertIsNotNone(output)
                self.assertEqual(output[field_name], "")
                self.assertEqual(record.working_values[field_name], replacement)
                self.assertEqual(record.manual_overrides[field_name], replacement)
                self.assertIn(code, [issue.code for issue in record.issues])

    def test_unresolved_dates_are_blank_without_excluding_qualified_rows(self) -> None:
        """Do not export a missing, invalid, invented, or conflicting signing date."""
        for raw, expected in [
            ("", "MISSING_DATE_SIGNED"), ("02/29/25", "DATE_SIGNED_CLEARED"),
            ("11/07/26", "DATE_SIGNED_CLEARED"),
        ]:
            with self.subTest(raw=raw):
                record = make_evaluation_record({"DateSigned": raw})
                output = evaluate_record(record, reference_date=self.reference_date)
                self.assertIsNotNone(output)
                self.assertEqual(output["DateSigned"], "")
                self.assertTrue(record.eligible)
                self.assertIn(expected, [issue.code for issue in record.issues])

        for raw, expected in [
            ("11/05/2026", "DATE_SIGNED_CONFLICT"),
            ("", "DATE_SIGNED_SOURCE_REVIEW"),
        ]:
            with self.subTest(original=raw):
                record = make_evaluation_record({"DateSigned": raw})
                changed = dict(record.working_values)
                changed["DateSigned"] = "11/06/26"
                record.apply_cleaned_values(changed)
                output = evaluate_record(record, reference_date=self.reference_date)
                self.assertEqual(output["DateSigned"], "")
                self.assertEqual(record.working_values["DateSigned"], "11/06/26")
                self.assertIn(expected, [issue.code for issue in record.issues])
                record.edit_field("DateSigned", "11/06/26")
                self.assertEqual(
                    evaluate_record(record, reference_date=self.reference_date)["DateSigned"],
                    "11/06/26",
                )

    def test_manual_and_confirmed_duplicate_exclusions_survive_evaluation(self) -> None:
        """Refreshing automatic checks must not undo deliberate reviewer decisions."""
        for decision in ["manual", "duplicate"]:
            with self.subTest(decision=decision):
                record = make_evaluation_record()
                if decision == "manual":
                    record.manual_exclusion_reason = "Reviewer excluded this row."
                else:
                    record.confirmed_duplicate_of = "fictional-survivor"
                before = (record.manual_exclusion_reason, record.confirmed_duplicate_of)
                for _ in range(2):
                    self.assertIsNone(evaluate_record(record, reference_date=self.reference_date))
                    self.assertTrue(record.eligible)
                    self.assertFalse(record.is_included)
                    self.assertEqual(
                        (record.manual_exclusion_reason, record.confirmed_duplicate_of), before
                    )

    def test_repeated_evaluation_replaces_stale_flags_and_reasons(self) -> None:
        """A new pass replaces old automatic state without accumulating duplicates."""
        record = make_evaluation_record({"Email": "bad email", "DateSigned": "bad date"})
        record.issues.append(ReviewIssue(None, "STALE", "Old result."))
        record.exclusion_reasons.append("Old exclusion.")
        record.eligible = False
        first = evaluate_record(record, reference_date=self.reference_date)
        first_issues = list(record.issues)
        second = evaluate_record(record, reference_date=self.reference_date)
        self.assertEqual(first, second)
        self.assertEqual(record.issues, first_issues)
        self.assertNotIn("STALE", [issue.code for issue in record.issues])
        self.assertEqual(record.exclusion_reasons, [])
        self.assertTrue(record.eligible)

    def test_edits_can_restore_and_remove_eligibility_without_generated_name_leaks(self) -> None:
        """Recheck corrected contact/name inputs after an earlier exclusion."""
        record = make_evaluation_record({
            **self.no_address, "First Name": "", "Last Name": "",
            "Primary Cell/Mobile Phone": "", "Email": "",
        })
        self.assertIsNone(evaluate_record(record, reference_date=self.reference_date))
        record.edit_field("Primary Cell/Mobile Phone", "2025550147")
        output = evaluate_record(record, reference_date=self.reference_date)
        self.assertEqual((output["First Name"], output["Last Name"]), ("Anonymous", "Donor"))
        self.assertEqual(record.exclusion_reasons, [])
        record.edit_field("First Name", "Jordan")
        output = evaluate_record(record, reference_date=self.reference_date)
        self.assertEqual((output["First Name"], output["Last Name"]), ("Jordan", ""))
        record.edit_field("Primary Cell/Mobile Phone", "")
        self.assertIsNone(evaluate_record(record, reference_date=self.reference_date))
        self.assertFalse(record.eligible)
        self.assertTrue(record.exclusion_reasons)
        self.assertEqual(record.working_values["Last Name"], "")

    def test_derived_field_overrides_cannot_replace_computed_rules(self) -> None:
        """Compute required constants/status while preserving other literal edits."""
        record = make_evaluation_record({"Zipcode": ""})
        record.edit_field("Address Contact Status", "MAILABLE")
        record.edit_field("PhoneDisclaimeredYN", "N")
        record.edit_field("Account Classification", "ORGANIZATION")
        record.edit_field("Other  Field ", "  Reviewer entered this  ")
        output = evaluate_record(record, reference_date=self.reference_date)
        self.assertEqual(output["Address Contact Status"], "BAD_ADDRESS")
        self.assertEqual(output["PhoneDisclaimeredYN"], "Y")
        self.assertEqual(output["Account Classification"], "INDIVIDUAL")
        self.assertEqual(output["Other  Field "], "  Reviewer entered this  ")
        self.assertEqual(record.manual_overrides["Address Contact Status"], "MAILABLE")
        self.assertEqual(record.manual_overrides["PhoneDisclaimeredYN"], "N")

    def test_output_is_detached_and_original_identity_evidence_remains_intact(self) -> None:
        """Changing a returned dictionary must not alter record inputs or later output."""
        record = make_evaluation_record(unit="Apartment 004b")
        before = (record.record_id, record.original_source_values,
                  dict(record.original_mapped_values), record.original_unit_value,
                  dict(record.working_values), dict(record.manual_overrides))
        output = evaluate_record(record, reference_date=self.reference_date)
        self.assertEqual(output["Street"], "125 Elm St Apt 004B")
        self.assertEqual(list(output), list(record.working_values))
        self.assertTrue(all(isinstance(value, str) for value in output.values()))
        output["First Name"] = "Changed outside record"
        output["_debug"] = "Must never enter later output"
        refreshed = evaluate_record(record, reference_date=self.reference_date)
        self.assertEqual(refreshed["First Name"], "Jordan")
        self.assertNotIn("_debug", refreshed)
        self.assertEqual(before, (record.record_id, record.original_source_values,
                                 dict(record.original_mapped_values), record.original_unit_value,
                                 dict(record.working_values), dict(record.manual_overrides)))

    def test_partial_template_does_not_gain_extra_output_headings(self) -> None:
        """Retain the generic exact-schema contract when optional headings are absent."""
        record = MemberRecord(["2025550147"], {"Primary Cell/Mobile Phone": "2025550147"})
        self.assertEqual(
            evaluate_record(record, reference_date=self.reference_date),
            {"Primary Cell/Mobile Phone": "2025550147"},
        )
        self.assertTrue(record.eligible)
        self.assertEqual(record.issues, [])

    def test_csv_mapping_cleanup_evaluation_and_output_preserve_source(self) -> None:
        """Exercise real CSV transport, raw-unit mapping, inclusion, and derived output."""
        headers = ["Given", "Family", "Phone", "Email Address", "Mailing",
                   "Town", "Region", "Postal", "Signed", "Unit"]
        template = [
            "Email", "Last Name", "First Name", "Street", "City", "State", "Zipcode",
            "Primary Cell/Mobile Phone", "DateSigned", "PROISSSUB ",
            "PhoneDisclaimeredYN", "Account Classification", "Address Contact Status",
        ]
        rows = [
            [" jordan ", " taylor ", "1 (202) 555-0147", "member@example.com",
             "125 elm street", "boston", "Massachusetts", "02108-1234",
             "3/7/2026", "Apartment 004b"],
            ["", "Taylor", "2025550147", "bad email", "", "", "", "", "", ""],
            ["Jordan", "Taylor", "", "", "", "", "", "", "3/7/26", ""],
        ]
        mapping = {0: "First Name", 1: "Last Name", 2: "Primary Cell/Mobile Phone",
                   3: "Email", 4: "Street", 5: "City", 6: "State",
                   7: "Zipcode", 8: "DateSigned"}
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "fictional_source.csv"
            output_path = Path(directory) / "fictional_cleaned.csv"
            with source_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(headers)
                writer.writerows(rows)
            original_bytes = source_path.read_bytes()
            actual_headers, actual_rows = read_source_csv(source_path)
            members = []
            included = []
            for source_row in actual_rows:
                mapped, unit = map_record_with_unit(
                    source_row, actual_headers, template, mapping, unit_source_index=9
                )
                record = MemberRecord(source_row, mapped, unit)
                apply_evaluation_cleanup(record, self.reference_date)
                members.append(record)
                values = evaluate_record(record, reference_date=self.reference_date)
                if values is not None:
                    included.append(values)

            write_output_csv(output_path, template, included)
            with output_path.open("r", encoding="utf-8", newline="") as stream:
                exported = list(csv.reader(stream))
            self.assertEqual(exported[0], template)
            self.assertEqual(len(exported), 3)
            first, second = [dict(zip(template, row)) for row in exported[1:]]
            self.assertEqual(first["Street"], "125 Elm St Apt 004B")
            self.assertEqual(first["Zipcode"], "02108")
            self.assertEqual(first["DateSigned"], "03/07/26")
            self.assertEqual(first["Address Contact Status"], "MAILABLE")
            self.assertEqual((second["First Name"], second["Last Name"]), ("Anonymous", "Donor"))
            self.assertEqual(second["Email"], "")
            self.assertEqual(second["DateSigned"], "")
            self.assertEqual(second["Address Contact Status"], "BAD_ADDRESS")
            for output in [first, second]:
                self.assertEqual(output["PROISSSUB "], "")
                self.assertEqual(output["PhoneDisclaimeredYN"], "Y")
                self.assertEqual(output["Account Classification"], "INDIVIDUAL")
            self.assertFalse(members[2].eligible)
            self.assertEqual(members[1].working_values["First Name"], "")
            self.assertEqual(members[1].working_values["Last Name"], "Taylor")
            self.assertEqual([member.original_source_values for member in members],
                             [tuple(row) for row in rows])
            self.assertEqual(source_path.read_bytes(), original_bytes)


