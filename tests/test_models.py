"""Record-state checks using fictional member data.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Verify independent snapshots, stable identity, manual corrections,
evaluation invalidation, and separation of review metadata from CSV fields.
Check revision changes that protect duplicate decisions from stale inputs.
Run from the project root with python -m unittest discover -s tests -v.
AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import csv
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from member_cleaner.cleanup import assemble_street, clean_street
from member_cleaner.csv_io import write_output_csv
from member_cleaner.mapping import map_record_with_unit
from member_cleaner.models import MemberRecord, ReviewIssue


def make_record(first_name: str = "Jordan") -> MemberRecord:
    """Create a small all-string record without applying business rules."""
    source = [first_name, "125 elm street", "member@example.com", "00501", "PET-1"]
    mapped = {
        "First Name": first_name,
        "Street": "125 elm street",
        "Email": "member@example.com",
        "Zipcode": "00501",
        "PROISSSUB ": "PET-1",
    }
    return MemberRecord(source, mapped)


class MemberRecordTests(unittest.TestCase):
    """Check state transitions needed by later validation and review code."""

    def test_original_snapshots_are_detached_and_read_only(self) -> None:
        """Caller mutations and later edits must not rewrite source evidence."""
        source = ["125 Elm Street Apt 4B", " Apt 5B ", "member@example.com"]
        mapped = {
            "Street": "125 Elm Street Apt 4B",
            "Email": "member@example.com",
            "Zipcode": "00501",
            "PROISSSUB ": "PET-1",
        }
        expected_source = tuple(source)
        expected_mapped = mapped.copy()
        member = MemberRecord(source, mapped, source[1])

        source[0] = "changed in caller"
        mapped["Street"] = "changed in caller"
        member.edit_field("Street", "125 Elm St Apt 5B")

        self.assertEqual(member.original_source_values, expected_source)
        self.assertEqual(dict(member.original_mapped_values), expected_mapped)
        self.assertEqual(member.original_unit_value, " Apt 5B ")
        self.assertEqual(member.working_values["Zipcode"], "00501")

        with self.assertRaises(TypeError):
            member.original_mapped_values["Street"] = "overwrite"
        with self.assertRaises(TypeError):
            member.working_values["Street"] = "bypass update methods"
        with self.assertRaises(AttributeError):
            member.original_source_values = ()
        with self.assertRaises(AttributeError):
            member.original_unit_value = "overwrite"

    def test_records_do_not_share_mutable_state(self) -> None:
        """One record's values, corrections, issues, and reasons stay local."""
        first = make_record()
        second = make_record()
        issue = ReviewIssue("Street", "ADDRESS_REVIEW", "Check this address.")

        first.edit_field("Email", "changed@example.com")
        first.issues.append(issue)
        first.exclusion_reasons.append("An example evaluation reason.")

        self.assertEqual(second.working_values["Email"], "member@example.com")
        self.assertEqual(dict(second.manual_overrides), {})
        self.assertEqual(second.issues, [])
        self.assertEqual(second.exclusion_reasons, [])
        self.assertEqual(first.manual_overrides["Email"], "changed@example.com")

        with self.assertRaises(FrozenInstanceError):
            issue.message = "Change the meaning after attaching the issue."
        with self.assertRaises(TypeError):
            first.manual_overrides["Email"] = "bypass edit_field"

    def test_identity_survives_cleanup_edits_and_sorting(self) -> None:
        """Sorting a display and correcting data must not generate new IDs."""
        records = [make_record("Jordan"), make_record("Alex")]
        original_ids = {id(member): member.record_id for member in records}
        self.assertEqual(len(set(original_ids.values())), 2)

        candidate = dict(records[0].working_values)
        candidate["Street"] = clean_street(candidate["Street"])
        records[0].apply_cleaned_values(candidate)
        records[0].edit_field("First Name", "Zoe")
        records.sort(key=lambda member: member.working_values["First Name"])

        self.assertEqual(
            [member.working_values["First Name"] for member in records],
            ["Alex", "Zoe"],
        )
        for member in records:
            self.assertEqual(member.record_id, original_ids[id(member)])
        with self.assertRaises(AttributeError):
            records[0].record_id = "replacement-id"

    def test_manual_corrections_survive_later_cleanup(self) -> None:
        """A later formatting pass must preserve a confirmed literal name."""
        member = MemberRecord(
            ["125 north star street", "member@example.com"],
            {"Street": "125 north star street", "Email": "member@example.com"},
        )
        candidate = dict(member.working_values)
        candidate["Street"] = clean_street(candidate["Street"])
        member.apply_cleaned_values(candidate)
        self.assertEqual(member.working_values["Street"], "125 N Star St")

        member.edit_field("Street", "125 North Star St")
        self.assertIsNone(member.eligible)
        later_pass = dict(member.working_values)
        later_pass["Street"] = clean_street(later_pass["Street"])
        member.apply_cleaned_values(later_pass)

        self.assertEqual(member.working_values["Street"], "125 North Star St")
        self.assertEqual(later_pass["Street"], "125 N Star St")
        self.assertEqual(member.original_mapped_values["Street"], "125 north star street")

        # A correction is preserved even when it still needs validation.
        member.edit_field("Email", "not-an-email")
        self.assertIsNone(member.eligible)
        self.assertFalse(member.is_included)

    def test_changes_invalidate_old_evaluation(self) -> None:
        """Changed data clears stale checks but retains deliberate exclusions."""
        for action in ("edit", "cleanup"):
            with self.subTest(action=action):
                member = make_record()
                member.eligible = True
                member.issues.append(ReviewIssue("Street", "OLD_ISSUE", "Old result."))
                member.exclusion_reasons.append("Old evaluation reason.")
                member.confirmed_duplicate_of = "previous-kept-record"
                member.manual_exclusion_reason = "User chose to exclude this row."

                if action == "edit":
                    member.edit_field("Email", "updated@example.com")
                else:
                    candidate = dict(member.working_values)
                    candidate["Street"] = clean_street(candidate["Street"])
                    member.apply_cleaned_values(candidate)

                self.assertIsNone(member.eligible)
                self.assertEqual(member.issues, [])
                self.assertEqual(member.exclusion_reasons, [])
                self.assertIsNone(member.confirmed_duplicate_of)
                self.assertEqual(
                    member.manual_exclusion_reason,
                    "User chose to exclude this row.",
                )

    def test_unchanged_cleanup_preserves_existing_decisions(self) -> None:
        """An identical pass must not repeatedly reopen duplicate decisions."""
        member = make_record()
        member.eligible = True
        issue = ReviewIssue("Street", "ADDRESS_REVIEW", "A current review issue.")
        member.issues.append(issue)
        member.confirmed_duplicate_of = "kept-record"
        same_values = {
            name: member.working_values[name]
            for name in reversed(list(member.working_values))
        }

        member.apply_cleaned_values(same_values)

        self.assertTrue(member.eligible)
        self.assertEqual(member.issues, [issue])
        self.assertEqual(member.confirmed_duplicate_of, "kept-record")
        self.assertEqual(list(member.working_values), list(member.original_mapped_values))

        # Rule changes can explicitly request evaluation without a data change.
        member.invalidate_evaluation()
        self.assertIsNone(member.eligible)
        self.assertIsNone(member.confirmed_duplicate_of)

    def test_inclusion_uses_evaluation_and_exclusion_state(self) -> None:
        """Pending checks exclude; an issue alone need not exclude an eligible row."""
        member = make_record()
        self.assertIsNone(member.eligible)
        self.assertFalse(member.is_included)

        # Simulate the result of a future validator finding a usable email.
        member.eligible = True
        member.issues.append(ReviewIssue("Street", "BAD_ADDRESS", "Address needs review."))
        self.assertTrue(member.is_included)

        member.manual_exclusion_reason = "User excluded this row."
        self.assertFalse(member.is_included)
        member.manual_exclusion_reason = None
        self.assertTrue(member.is_included)
        member.confirmed_duplicate_of = "kept-record"
        self.assertFalse(member.is_included)
        member.confirmed_duplicate_of = None
        member.eligible = False
        member.exclusion_reasons.append("No usable contact information.")
        self.assertFalse(member.is_included)

    def test_invalid_updates_leave_state_unchanged(self) -> None:
        """Reject schema/type errors before modifying values or evaluation."""
        member = make_record()
        member.eligible = True
        issue = ReviewIssue(None, "EXAMPLE", "Keep this result after a failed update.")
        member.issues.append(issue)
        before = dict(member.working_values)
        cases = [
            (KeyError, lambda: member.edit_field("Unknown", "value")),
            (TypeError, lambda: member.edit_field("Zipcode", 501)),
            (ValueError, lambda: member.apply_cleaned_values({"Email": "only@example.com"})),
            (ValueError, lambda: member.apply_cleaned_values({**before, "record_id": "extra"})),
            (TypeError, lambda: member.apply_cleaned_values({**before, "Zipcode": 501})),
        ]

        for expected_error, update in cases:
            with self.subTest(expected_error=expected_error):
                with self.assertRaises(expected_error):
                    update()
                self.assertEqual(dict(member.working_values), before)
                self.assertEqual(dict(member.manual_overrides), {})
                self.assertTrue(member.eligible)
                self.assertEqual(member.issues, [issue])

    def test_mapping_cleanup_and_export_preserve_originals(self) -> None:
        """Keep conflicting source components and export only template values."""
        source_headers = ["Mailing", "Unit", "Contact", "Postal"]
        source_row = ["125 Elm Street Apt 4B", "Apt 5B", "member@example.com", "00501"]
        template_headers = ["Email", "Street", "Zipcode", "PROISSSUB "]
        mapped, unit_value = map_record_with_unit(
            source_row,
            source_headers,
            template_headers,
            {0: "Street", 2: "Email", 3: "Zipcode"},
            unit_source_index=1,
        )
        member = MemberRecord(source_row, mapped, unit_value)
        candidate = dict(member.working_values)
        candidate["Street"] = assemble_street(
            candidate["Street"], member.original_unit_value
        )
        member.apply_cleaned_values(candidate)
        member.issues.append(
            ReviewIssue("Street", "UNIT_CONFLICT", "Street and unit column disagree.")
        )
        # Simulate later validation; this model does not evaluate contacts.
        member.eligible = True

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "fictional_output.csv"
            write_output_csv(
                output_path, template_headers, [dict(member.working_values)]
            )
            with output_path.open("r", encoding="utf-8", newline="") as output:
                exported = list(csv.reader(output))

        self.assertEqual(
            exported,
            [template_headers, ["member@example.com", "", "00501", ""]],
        )
        self.assertEqual(member.original_source_values, tuple(source_row))
        self.assertEqual(member.original_mapped_values["Street"], "125 Elm Street Apt 4B")
        self.assertEqual(member.original_unit_value, "Apt 5B")
        self.assertEqual(member.issues[0].code, "UNIT_CONFLICT")
        self.assertTrue(member.is_included)


class RecordRevisionTests(unittest.TestCase):
    """Check input revision changes independently of evaluation metadata."""

    def test_revision_is_read_only_and_identity_stays_stable(self) -> None:
        """Start at zero; deliberate edits advance revisions while preserving the ID."""
        record = make_record()
        original_id = record.record_id
        self.assertEqual(record.revision, 0)
        with self.assertRaises(AttributeError):
            record.revision = 99
        record.edit_field("First Name", record.working_values["First Name"])
        self.assertEqual(record.revision, 1)
        self.assertEqual(record.record_id, original_id)
        record.invalidate_evaluation()
        self.assertEqual(record.revision, 2)

    def test_only_changed_cleanup_advances_revision(self) -> None:
        """Identical/invalid updates leave revision unchanged; changed values advance it."""
        record = make_record()
        original_revision = record.revision
        record.apply_cleaned_values(dict(record.working_values))
        self.assertEqual(record.revision, original_revision)
        changed = dict(record.working_values)
        changed["First Name"] = "Casey"
        record.apply_cleaned_values(changed)
        self.assertEqual(record.revision, original_revision + 1)
        record.apply_cleaned_values(dict(reversed(list(changed.items()))))
        self.assertEqual(record.revision, original_revision + 1)
        with self.assertRaises(ValueError):
            record.apply_cleaned_values({"Unknown": "value"})
        with self.assertRaises(KeyError):
            record.edit_field("Unknown", "value")
        self.assertEqual(record.revision, original_revision + 1)

    def test_evaluation_metadata_does_not_advance_input_revision(self) -> None:
        """Changing evaluation/exclusion metadata alone must not look like an input edit."""
        record = make_record()
        before = record.revision
        record.eligible = True
        record.issues.append(ReviewIssue(None, "EXAMPLE", "Evaluation metadata."))
        record.manual_exclusion_reason = "Reviewer choice"
        record.confirmed_duplicate_of = "fictional-keeper"
        self.assertEqual(record.revision, before)

