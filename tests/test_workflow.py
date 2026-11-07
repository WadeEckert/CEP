"""Batch correction and export checks using fictional member CSV data.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Exercise the real file/mapping/cleanup/review workflow, safe manual
corrections, immutable acknowledgments, duplicate reopening, and fresh guarded
CSV output. All files are temporary fictional fixtures.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import csv
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from datetime import date
from pathlib import Path

from member_cleaner.models import MemberRecord
from member_cleaner.workflow import MemberBatch, clean_record


REFERENCE_DATE = date(2026, 11, 6)
BASE_VALUES = {
    "First Name": " jordan ", "Last Name": " taylor ",
    "Primary Cell/Mobile Phone": "1 (202) 555-0147", "Email": "member@example.com",
    "Street": "125 elm street", "City": " boston ",
    "State": "Massachusetts", "Zipcode": "02108-1234", "Country": "",
    "DateSigned": "3/7/2026", "PROISSSUB ": "",
    "Address Contact Status": "", "PhoneDisclaimeredYN": "",
    "Account Classification": "", "Other  Field ": " Keep As Entered ",
    "Birth Date": "July 4 1990", "Name Prefix": "mr",
}
TEMPLATE = tuple(BASE_VALUES)
NO_ADDRESS = {"Street": "", "City": "", "State": "", "Zipcode": ""}


def raw_record(changes: dict[str, str] | None = None, *, unit: str = "") -> MemberRecord:
    """Create raw mapped data before the batch applies any cleanup."""
    mapped = {**BASE_VALUES, **(changes or {})}
    return MemberRecord(list(mapped.values()) + [unit], mapped, unit)


def make_batch(changes: dict[str, str] | None = None) -> MemberBatch:
    """Build a one-record fixture with a deterministic processing date."""
    return MemberBatch([raw_record(changes)], TEMPLATE, reference_date=REFERENCE_DATE)


class MemberBatchTests(unittest.TestCase):
    """Check correction/review/export behavior through the public batch API."""

    def test_review_state_tracks_decisions_acknowledgments_and_overrides(self) -> None:
        batch = MemberBatch([raw_record({"DateSigned": "unknown"}), raw_record()],
                            TEMPLATE, reference_date=REFERENCE_DATE)
        initial = batch.review_state()
        pair, = batch.get_duplicate_candidates()
        decision = batch.keep_both(pair)
        decided = batch.review_state()
        self.assertNotEqual(decided, initial)
        self.assertEqual(decided.decisions, (decision,))
        preview, = batch.get_unreviewed_records()
        batch.acknowledge_record(preview)
        acknowledged = batch.review_state()
        self.assertNotEqual(acknowledged, decided)
        batch.edit_field(preview.record_id, "DateSigned", "11/6/2026")
        edited = batch.review_state()
        self.assertNotEqual(edited, acknowledged)
        self.assertEqual(edited.acknowledged, frozenset())
        self.assertEqual(edited.decisions, ())
        self.assertEqual(batch.review_state(), edited)

    def test_batch_proisssub_applies_to_excluded_records_and_preserves_originals(self) -> None:
        field = "PROISSSUB "
        first, second = raw_record({field: "Old group"}), raw_record({field: "Other group"})
        batch = MemberBatch([first, second], TEMPLATE, reference_date=REFERENCE_DATE)
        self.assertEqual(batch.get_duplicate_candidates(), ())
        batch.exclude_record(second.record_id, "Review later")
        batch.set_batch_proisssub("  Petition 24  ")
        self.assertEqual(batch.batch_proisssub, "Petition 24")
        self.assertEqual(batch.prepare_export()[0][field], "Petition 24")
        self.assertEqual(second.working_values[field], "Petition 24")
        self.assertEqual(second.original_mapped_values[field], "Other group")
        self.assertNotIn(field, batch.editable_fields)
        with self.assertRaisesRegex(ValueError, "main screen"):
            batch.edit_field(first.record_id, field, "Different petition")
        batch.restore_record(second.record_id)
        pair, = batch.get_duplicate_candidates()
        self.assertEqual(pair.petition_status, "MATCHING")
        batch.keep_both(pair)
        self.assertEqual([row[field] for row in batch.prepare_export()], ["Petition 24", "Petition 24"])

    def test_batch_proisssub_reopens_changed_pair_decisions_but_not_unchanged_ones(self) -> None:
        batch = MemberBatch([raw_record(), raw_record()], TEMPLATE, reference_date=REFERENCE_DATE)
        pair, = batch.get_duplicate_candidates()
        batch.keep_both(pair)
        batch.set_batch_proisssub("Group 24")
        new_pair, = batch.get_duplicate_candidates()
        self.assertEqual(new_pair.petition_status, "MATCHING")
        self.assertEqual(batch.get_duplicate_decisions(), ())
        decision = batch.keep_both(new_pair)
        batch.set_batch_proisssub(" Group 24 ")
        self.assertEqual(batch.get_duplicate_candidates(), ())
        self.assertEqual(batch.get_duplicate_decisions(), (decision,))

    def test_batch_petition_heading_variants_preserve_export_keys_and_match_logic(self) -> None:
        for field in ("PROISSUB", "PROISSSUB", "  proissub "):
            with self.subTest(field=field):
                values = {key: value for key, value in BASE_VALUES.items() if key != "PROISSSUB "}
                first = MemberRecord((), {**values, field: "First group"})
                second = MemberRecord((), {**values, field: "Second group"})
                headers = (*values, field)
                batch = MemberBatch([first, second], headers, reference_date=REFERENCE_DATE)
                self.assertTrue(batch.supports_batch_proisssub)
                self.assertEqual(batch.get_duplicate_candidates(), ())
                batch.set_batch_proisssub("Campaign 24, Region A")
                pair, = batch.get_duplicate_candidates()
                self.assertEqual(pair.petition_status, "MATCHING")
                batch.keep_both(pair)
                with tempfile.TemporaryDirectory() as directory:
                    output = batch.save_csv(Path(directory) / "groups.csv")
                    with output.open(encoding="utf-8", newline="") as stream:
                        reader = csv.DictReader(stream)
                        self.assertEqual(tuple(reader.fieldnames), headers)
                        self.assertEqual([row[field] for row in reader], ["Campaign 24, Region A"] * 2)

    def test_manual_signing_date_uses_cleanup_and_validation_on_header_variants(self) -> None:
        for field in ("DateSigned", "DateSigned ", "  datesigned  "):
            with self.subTest(field=field):
                values = {key: value for key, value in BASE_VALUES.items() if key != "DateSigned"}
                values[field] = "unknown"
                record = MemberRecord((), values)
                batch = MemberBatch([record], tuple(values), reference_date=REFERENCE_DATE)
                self.assertTrue(batch.get_unreviewed_records())
                batch.edit_field(record.record_id, field, "11/6/2026")
                self.assertEqual(batch.get_unreviewed_records(), ())
                self.assertEqual(record.working_values[field], "11/06/26")
                with tempfile.TemporaryDirectory() as directory:
                    output = batch.save_csv(Path(directory) / "date.csv")
                    with output.open(encoding="utf-8", newline="") as stream:
                        reader = csv.DictReader(stream)
                        self.assertEqual(tuple(reader.fieldnames), tuple(values))
                        self.assertEqual(next(reader)[field], "11/06/26")
                batch.edit_field(record.record_id, field, "02/30/2026")
                preview, = batch.get_unreviewed_records()
                self.assertEqual(preview.output_values[field], "")
                self.assertTrue(any(issue.field_name == field for issue in preview.issues))

    def test_file_mapping_review_and_export_preserve_sources_and_template(self) -> None:
        """Export named/anonymous rows and omit a contactless row through real CSV IO."""
        headers = ["Given", "Family", "Cell", "Mailing", "Unit", "Contact",
                   "Town", "Region", "Postal", "Signed", "Note"]
        rows = [
            [" jordan ", "taylor", "1 (202) 555-0147", "125 elm street,",
             "Apartment 004b", "member@example.com", "boston", "Massachusetts",
             "02108-1234", "3/7/2026", " Keep As Entered "],
            ["", "Taylor", "2025550147", "", "", "bad email", "", "", "", "", ""],
            ["Jordan", "Taylor", "", "", "", "", "", "", "", "3/7/26", ""],
        ]
        mapping = {0: "First Name", 1: "Last Name", 2: "Primary Cell/Mobile Phone",
                   3: "Street", 5: "Email", 6: "City", 7: "State", 8: "Zipcode",
                   9: "DateSigned", 10: "Other  Field "}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, template, output = root / "source.csv", root / "template.csv", root / "out.csv"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(headers)
                writer.writerows(rows)
            with template.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream).writerow(TEMPLATE)
            before = (source.read_bytes(), template.read_bytes())
            batch = MemberBatch.from_csv(source, template, mapping, unit_source_index=4,
                                         reference_date=REFERENCE_DATE)
            self.assertEqual(batch.get_duplicate_candidates(), ())
            self.assertEqual(len(batch.get_unreviewed_records()), 1)
            batch.acknowledge_record(batch.get_unreviewed_records()[0])
            batch.save_csv(output)
            with output.open("r", encoding="utf-8", newline="") as stream:
                exported = list(csv.reader(stream))
            self.assertEqual(exported[0], list(TEMPLATE))
            self.assertEqual(len(exported), 3)
            first, second = [dict(zip(TEMPLATE, row)) for row in exported[1:]]
            self.assertEqual(first["Street"], "125 Elm St Apt 004B")
            self.assertEqual(first["Zipcode"], "02108")
            self.assertEqual(first["DateSigned"], "03/07/26")
            self.assertEqual(first["Other  Field "], " Keep As Entered ")
            self.assertEqual((second["First Name"], second["Last Name"]), ("Anonymous", "Donor"))
            self.assertEqual(second["Email"], "")
            self.assertEqual(second["DateSigned"], "")
            self.assertEqual(second["Address Contact Status"], "BAD_ADDRESS")
            for values in [first, second]:
                self.assertEqual(values["PROISSSUB "], "")
                self.assertEqual(values["PhoneDisclaimeredYN"], "Y")
                self.assertEqual(values["Account Classification"], "INDIVIDUAL")
            self.assertEqual((source.read_bytes(), template.read_bytes()), before)
            self.assertEqual([record.original_source_values for record in batch.records],
                             [tuple(row) for row in rows])
            self.assertIsNone(batch.get_preview(batch.records[2].record_id).output_values)

    def test_cleanup_is_repeatable_and_originals_are_preserved(self) -> None:
        record = raw_record(unit="Apartment 004b")
        original = (record.original_source_values, dict(record.original_mapped_values))
        batch = MemberBatch([record], TEMPLATE, reference_date=REFERENCE_DATE)
        revision = record.revision
        clean_record(record, reference_date=REFERENCE_DATE)
        self.assertEqual(record.revision, revision)
        self.assertEqual((record.original_source_values, dict(record.original_mapped_values)), original)
        self.assertEqual(batch.prepare_export()[0]["Street"], "125 Elm St Apt 004B")

    def test_unreviewed_flags_block_export_before_any_file_is_created(self) -> None:
        batch = make_batch({"Email": "bad email"})
        with self.assertRaises(ValueError):
            batch.prepare_export()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "blocked.csv"
            with self.assertRaises(ValueError):
                batch.save_csv(output)
            self.assertFalse(output.exists())

    def test_acknowledgment_accepts_safe_blanks_without_making_address_mailable(self) -> None:
        batch = make_batch({"Street": "125 Elm", "Email": "bad email", "DateSigned": ""})
        preview = batch.get_unreviewed_records()[0]
        self.assertEqual(preview.output_values["Email"], "")
        self.assertEqual(preview.output_values["DateSigned"], "")
        self.assertEqual(preview.output_values["Address Contact Status"], "BAD_ADDRESS")
        batch.acknowledge_record(preview)
        self.assertEqual(batch.get_unreviewed_records(), ())
        self.assertTrue(batch.records[0].issues)
        self.assertEqual(batch.prepare_export()[0]["Address Contact Status"], "BAD_ADDRESS")

    def test_valid_corrections_are_normalized_before_becoming_overrides(self) -> None:
        batch = make_batch({"Email": "bad email"})
        record = batch.records[0]
        for name, value, expected in [
            ("Email", " member@example,com ", "member@example.com"),
            ("First Name", " BRITTANY  SUE ", "Brittany Sue"),
            ("Last Name", "NUNEZ-LOPEZ", "Nunez-Lopez"),
            ("Primary Cell/Mobile Phone", "1 (202) 555-0147", "2025550147"),
            ("State", "Massachusetts", "MA"),
            ("Zipcode", "02108-1234", "02108"),
            ("DateSigned", "3/7/2026", "03/07/26"),
        ]:
            with self.subTest(name=name):
                batch.edit_field(record.record_id, name, value)
                self.assertEqual(record.manual_overrides[name], expected)
        self.assertEqual(batch.get_unreviewed_records(), ())
        self.assertEqual(batch.prepare_export()[0]["First Name"], "Brittany Sue")

    def test_failed_nonblank_corrections_remain_visible_and_flagged(self) -> None:
        for name, value in [
            ("Primary Cell/Mobile Phone", "202-555-014"), ("Email", "member @example.com"),
            ("State", "Unknown"), ("Zipcode", "2108"),
            ("DateSigned", "02/29/25"), ("Street", "125 Elm St Apt 4,5"),
        ]:
            with self.subTest(name=name):
                batch = make_batch()
                record = batch.records[0]
                batch.edit_field(record.record_id, name, value)
                preview = batch.get_preview(record.record_id)
                self.assertEqual(record.working_values[name], value)
                self.assertEqual(record.manual_overrides[name], value)
                self.assertTrue(any(issue.field_name == name for issue in preview.issues))
                self.assertEqual(preview.output_values[name], "")
                with self.assertRaises(ValueError):
                    batch.prepare_export()

    def test_intentional_removal_differs_from_failed_cleanup(self) -> None:
        batch = make_batch({"Email": "bad email", "Primary Cell/Mobile Phone": "bad phone"})
        record = batch.records[0]
        batch.edit_field(record.record_id, "Email", "")
        batch.edit_field(record.record_id, "Primary Cell/Mobile Phone", "")
        self.assertFalse(any(issue.field_name in ("Email", "Primary Cell/Mobile Phone")
                             for issue in batch.get_preview(record.record_id).issues))
        batch.edit_field(record.record_id, "DateSigned", "")
        preview = batch.get_preview(record.record_id)
        self.assertIn("MISSING_DATE_SIGNED", [issue.code for issue in preview.issues])
        batch.acknowledge_record(preview)
        self.assertEqual(batch.prepare_export()[0]["DateSigned"], "")

    def test_previews_are_immutable_and_stale_acknowledgments_are_rejected(self) -> None:
        batch = make_batch({"Email": "bad email"})
        preview = batch.get_unreviewed_records()[0]
        with self.assertRaises(TypeError):
            preview.output_values["Email"] = "changed@example.com"
        with self.assertRaises(FrozenInstanceError):
            preview.revision = 99
        batch.records[0].edit_field("Other  Field ", "Changed")
        with self.assertRaises(ValueError):
            batch.acknowledge_record(preview)
        batch.acknowledge_record(batch.get_preview(preview.record_id))
        self.assertEqual(batch.prepare_export()[0]["Other  Field "], "Changed")

    def test_edit_invalidates_acknowledgment_even_if_issue_codes_are_unchanged(self) -> None:
        batch = make_batch({"Email": "bad email"})
        old = batch.get_unreviewed_records()[0]
        batch.acknowledge_record(old)
        batch.edit_field(old.record_id, "Other  Field ", "New note")
        current = batch.get_unreviewed_records()[0]
        self.assertEqual(old.issues, current.issues)
        self.assertNotEqual(old.revision, current.revision)
        with self.assertRaises(ValueError):
            batch.prepare_export()

    def test_manual_street_corrections_preserve_literal_names_and_normalize_units(self) -> None:
        for entered, expected in [
            ("125 north star street", "125 North Star St"),
            ("125 elm street rear road", "125 Elm Street Rear Rd"),
            ("125 north star street west", "125 North Star St W"),
            ("125 elm street apartment 004b", "125 Elm St Apt 004B"),
            ("p.o. box #00123", "PO Box 00123"),
        ]:
            with self.subTest(entered=entered):
                batch = make_batch({"Street": "125 North Star Street"})
                record = batch.records[0]
                batch.edit_field(record.record_id, "Street", entered)
                self.assertEqual(record.working_values["Street"], expected)
                clean_record(record, reference_date=REFERENCE_DATE)
                preview = batch.get_preview(record.record_id)
                self.assertEqual(preview.output_values["Street"], expected)
                self.assertEqual(preview.output_values["Address Contact Status"], "MAILABLE")

    def test_derived_and_invalid_edits_are_rejected_before_input_changes(self) -> None:
        batch = make_batch()
        record = batch.records[0]
        before = (record.revision, dict(record.working_values), dict(record.manual_overrides))
        for name in ["PhoneDisclaimeredYN", "Account Classification", "Address Contact Status"]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    batch.edit_field(record.record_id, name, "Changed")
        with self.assertRaises(KeyError):
            batch.edit_field(record.record_id, "Unknown", "value")
        with self.assertRaises(TypeError):
            batch.edit_field(record.record_id, "Email", 123)
        with self.assertRaises(ValueError):
            batch.exclude_record(record.record_id, " ")
        self.assertEqual(before, (record.revision, dict(record.working_values),
                                  dict(record.manual_overrides)))

    def test_duplicate_gate_blocks_corrections_acknowledgments_and_export(self) -> None:
        batch = MemberBatch([raw_record(), raw_record()], TEMPLATE, reference_date=REFERENCE_DATE)
        candidate = batch.get_duplicate_candidates()[0]
        record = batch.records[0]
        with self.assertRaises(ValueError):
            batch.get_correction_records()
        with self.assertRaises(ValueError):
            batch.edit_field(record.record_id, "Email", "other@example.com")
        with self.assertRaises(ValueError):
            batch.acknowledge_record(batch.get_preview(record.record_id))
        with self.assertRaises(ValueError):
            batch.prepare_export()
        batch.keep_both(candidate)
        self.assertEqual(len(batch.get_correction_records()), 2)
        self.assertEqual(len(batch.prepare_export()), 2)

    def test_keeper_edits_reopen_duplicates_and_undo_restores_rows(self) -> None:
        batch = MemberBatch([raw_record(), raw_record()], TEMPLATE, reference_date=REFERENCE_DATE)
        keeper = batch.records[0]
        decision = batch.confirm_duplicate(batch.get_duplicate_candidates()[0],
                                            keep_record_id=keeper.record_id)
        self.assertEqual(batch.get_duplicate_decisions(), (decision,))
        self.assertEqual(len(batch.prepare_export()), 1)
        batch.undo_duplicate_decision(decision.record_ids)
        self.assertEqual(len(batch.get_duplicate_candidates()), 1)
        batch.confirm_duplicate(batch.get_duplicate_candidates()[0], keep_record_id=keeper.record_id)
        batch.edit_field(keeper.record_id, "Email", "new@example.com")
        self.assertEqual(len(batch.get_duplicate_candidates()), 1)
        with self.assertRaises(ValueError):
            batch.prepare_export()
        batch.keep_both(batch.get_duplicate_candidates()[0])
        self.assertEqual(len(batch.prepare_export()), 2)

    def test_excluding_both_leaves_no_fallback_and_either_can_be_restored(self) -> None:
        batch = MemberBatch([raw_record(), raw_record()], TEMPLATE, reference_date=REFERENCE_DATE)
        pair, = batch.get_duplicate_candidates()
        first, second = batch.records
        originals = tuple(record.original_source_values for record in batch.records)
        batch.exclude_both(pair, "  Both out of scope  ")
        self.assertEqual(batch.get_duplicate_candidates(), ())
        self.assertEqual(batch.get_correction_records(), ())
        for record in batch.records:
            preview = batch.get_preview(record.record_id)
            self.assertEqual(preview.manual_exclusion_reason, "Both out of scope")
            self.assertIsNone(preview.confirmed_duplicate_of)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "empty.csv"
            with self.assertRaisesRegex(ValueError, "No included records"):
                batch.save_csv(output)
            self.assertFalse(output.exists())
        batch.restore_record(second.record_id)
        self.assertEqual(batch.get_correction_records(), (second,))
        batch.restore_record(first.record_id)
        self.assertEqual(len(batch.get_duplicate_candidates()), 1)
        self.assertEqual(tuple(record.original_source_values for record in batch.records), originals)

    def test_excluding_both_rejects_blank_reason_and_stale_pair(self) -> None:
        batch = MemberBatch([raw_record(), raw_record()], TEMPLATE, reference_date=REFERENCE_DATE)
        pair, = batch.get_duplicate_candidates()
        with self.assertRaisesRegex(ValueError, "reason"):
            batch.exclude_both(pair, " ")
        self.assertEqual(batch.get_duplicate_candidates(), (pair,))
        batch.keep_both(pair)
        with self.assertRaisesRegex(ValueError, "pair changed"):
            batch.exclude_both(pair, "Out of scope")
        self.assertEqual(len(batch.get_correction_records()), 2)
        self.assertTrue(all(record.manual_exclusion_reason is None for record in batch.records))

    def test_exclude_both_decision_keeps_reason_and_undo_reopens_pair(self) -> None:
        batch = MemberBatch([raw_record(), raw_record()], TEMPLATE, reference_date=REFERENCE_DATE)
        pair, = batch.get_duplicate_candidates()
        batch.exclude_both(pair, "  Both out of scope  ")
        decision, = batch.get_duplicate_decisions()
        self.assertEqual(decision.record_ids, pair.record_ids)
        self.assertEqual(decision.reason, "Both out of scope")
        self.assertEqual(decision.excluded_record_ids, pair.record_ids)
        left, right = pair.record_ids
        batch.undo_duplicate_decision((right, left))
        self.assertEqual(batch.get_duplicate_decisions(), ())
        self.assertEqual(batch.get_duplicate_candidates(), (pair,))
        self.assertTrue(all(record.manual_exclusion_reason is None for record in batch.records))

    def test_undo_pair_exclusion_preserves_later_individual_exclusion(self) -> None:
        batch = MemberBatch([raw_record(), raw_record()], TEMPLATE, reference_date=REFERENCE_DATE)
        pair, = batch.get_duplicate_candidates()
        first, second = batch.records
        batch.exclude_both(pair, "Out of scope")
        batch.restore_record(first.record_id)
        # Reusing the same reason must not make this newer decision part of the pair.
        batch.exclude_record(first.record_id, "Out of scope")
        decision, = batch.get_duplicate_decisions()
        self.assertEqual(decision.excluded_record_ids, (second.record_id,))
        batch.undo_duplicate_decision(pair.record_ids)
        self.assertEqual(batch.get_duplicate_decisions(), ())
        self.assertEqual(batch.get_correction_records(), (second,))
        self.assertEqual(first.manual_exclusion_reason, "Out of scope")

    def test_manual_exclusion_and_restoration_require_current_review(self) -> None:
        batch = make_batch({"Email": "bad email"})
        preview = batch.get_unreviewed_records()[0]
        batch.acknowledge_record(preview)
        batch.exclude_record(preview.record_id, "  Reviewer choice  ")
        excluded = batch.get_preview(preview.record_id)
        self.assertIsNone(excluded.output_values)
        self.assertEqual(excluded.manual_exclusion_reason, "Reviewer choice")
        self.assertEqual(batch.prepare_export(), [])
        with self.assertRaises(ValueError):
            batch.acknowledge_record(excluded)
        batch.restore_record(preview.record_id)
        self.assertEqual(len(batch.get_unreviewed_records()), 1)
        with self.assertRaises(ValueError):
            batch.prepare_export()

    def test_contact_correction_can_restore_an_ineligible_anonymous_row(self) -> None:
        batch = make_batch({**NO_ADDRESS, "First Name": "", "Last Name": "Taylor",
                            "Email": "", "Primary Cell/Mobile Phone": ""})
        record = batch.records[0]
        self.assertIsNone(batch.get_preview(record.record_id).output_values)
        self.assertEqual(batch.get_correction_records(), ())
        batch.edit_field(record.record_id, "Primary Cell/Mobile Phone", "1 (202) 555-0147")
        values = batch.prepare_export()[0]
        self.assertEqual((values["First Name"], values["Last Name"]), ("Anonymous", "Donor"))
        self.assertEqual(record.original_mapped_values["Primary Cell/Mobile Phone"], "")

    def test_unchanged_refresh_preserves_acknowledgments_and_detaches_export_values(self) -> None:
        batch = make_batch({"DateSigned": ""})
        preview = batch.get_unreviewed_records()[0]
        batch.acknowledge_record(preview)
        revision = batch.records[0].revision
        values = batch.prepare_export()
        values[0]["First Name"] = "Changed outside batch"
        self.assertEqual(batch.get_preview(preview.record_id), preview)
        self.assertEqual(batch.get_unreviewed_records(), ())
        self.assertEqual(batch.prepare_export()[0]["First Name"], "Jordan")
        self.assertEqual(batch.records[0].revision, revision)

    def test_input_paths_and_existing_files_are_protected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, template = root / "source.csv", root / "template.csv"
            source.write_text("original source")
            template.write_text("original template")
            batch = MemberBatch([raw_record()], TEMPLATE, reference_date=REFERENCE_DATE,
                                 protected_paths=(source, template))
            for path in [source, template]:
                with self.assertRaises(ValueError):
                    batch.save_csv(path)
            existing = root / "existing.csv"
            existing.write_text("keep existing")
            with self.assertRaises(FileExistsError):
                batch.save_csv(existing)
            self.assertEqual(existing.read_text(), "keep existing")
            source.unlink()
            with self.assertRaises(ValueError):
                batch.save_csv(source)
            self.assertFalse(source.exists())
            self.assertEqual(template.read_text(), "original template")

    def test_schema_and_empty_file_mapping_errors_are_caught(self) -> None:
        record = raw_record()
        before = record.revision
        for headers in [[], ["Email", "Email"], [" "], ["Email"]]:
            with self.subTest(headers=headers):
                with self.assertRaises(ValueError):
                    MemberBatch([record], headers, reference_date=REFERENCE_DATE)
        with self.assertRaises(ValueError):
            MemberBatch([record, record], TEMPLATE, reference_date=REFERENCE_DATE)
        self.assertEqual(record.revision, before)
        with tempfile.TemporaryDirectory() as directory:
            source, template = Path(directory) / "source.csv", Path(directory) / "template.csv"
            source.write_text("Contact\n")
            template.write_text("Email\n")
            with self.assertRaises(ValueError):
                MemberBatch.from_csv(source, template, {}, reference_date=REFERENCE_DATE)
            empty = MemberBatch.from_csv(source, template, {0: "Email"}, reference_date=REFERENCE_DATE)
            self.assertEqual(empty.prepare_export(), [])

    def test_save_builds_fresh_values_after_corrections(self) -> None:
        batch = make_batch()
        cached = batch.prepare_export()
        cached[0]["First Name"] = "Wrong cached value"
        batch.edit_field(batch.records[0].record_id, "First Name", "Casey")
        with tempfile.TemporaryDirectory() as directory:
            path = batch.save_csv(Path(directory) / "fresh.csv")
            with path.open("r", encoding="utf-8", newline="") as stream:
                values = list(csv.DictReader(stream))
            self.assertEqual(values[0]["First Name"], "Casey")
            self.assertEqual(batch.records[0].original_mapped_values["First Name"], " jordan ")

    def test_other_fields_are_copied_exactly_and_template_order_is_authoritative(self) -> None:
        record = raw_record()
        headers = tuple(reversed(TEMPLATE))
        batch = MemberBatch([record], headers, reference_date=REFERENCE_DATE)
        batch.edit_field(record.record_id, "Birth Date", "  jan 2 1991  ")
        values = batch.prepare_export()[0]
        self.assertEqual(list(values), list(headers))
        self.assertEqual(values["Birth Date"], "  jan 2 1991  ")
        self.assertEqual(values["Name Prefix"], "mr")
        self.assertEqual(values["Country"], "")
        self.assertEqual(values["PROISSSUB "], "")
