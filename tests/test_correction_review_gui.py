"""Test correction review and exact template headings with fictional data.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Verify the review lists, safe prepared values, and the connection
between Tk corrections, duplicate review, and existing export gates.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import csv
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
import unittest
from unittest.mock import patch

from member_cleaner.correction_review_gui import (
    ALL_FIELDS, EXCLUDED, FLAGGED_FIELDS, INCLUDED, NEEDS_REVIEW, correction_groups,
)
from member_cleaner.gui import FIRST_DESTINATION, MemberCleanerApp
from member_cleaner.models import MemberRecord
from member_cleaner.workflow import MemberBatch


HEADERS = ("First Name", "Last Name", "Email", "DateSigned ", "PROISSSUB ", "Account Classification")
ROWS = (
    (" Jordan ", "TAYLOR", "jordan@example.com", "unknown", "", ""),
    ("Jordan", "Taylor", "jordan@example.com", "01/12/24", "", ""),
    ("Morgan", "Reed", "", "", "", ""),
)


def make_batch(*rows: tuple[str, ...]) -> MemberBatch:
    """Prepare fictional values with the exact signing-date heading."""
    records = [MemberRecord(row, dict(zip(HEADERS, row, strict=True))) for row in rows]
    return MemberBatch(records, HEADERS, reference_date=date(2026, 11, 6))


class CorrectionGroupTests(unittest.TestCase):
    def test_exact_date_heading_cleans_flags_and_exports_without_renaming(self) -> None:
        batch = make_batch(ROWS[0])
        record, = batch.records
        preview = batch.get_preview(record.record_id)
        self.assertEqual(preview.output_values["DateSigned "], "")
        self.assertEqual([issue.field_name for issue in preview.issues], ["DateSigned "])
        with self.assertRaisesRegex(ValueError, "flagged records"):
            batch.prepare_export()
        batch.edit_field(record.record_id, "DateSigned ", "1/10/2024")
        self.assertEqual(correction_groups(batch)[NEEDS_REVIEW], ())
        self.assertEqual(record.original_mapped_values["DateSigned "], "unknown")
        with TemporaryDirectory() as directory:
            output = batch.save_csv(Path(directory) / "cleaned.csv")
            with output.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                row = next(reader)
                self.assertEqual(tuple(reader.fieldnames), HEADERS)
                self.assertEqual(row["DateSigned "], "01/10/24")
                self.assertNotIn("DateSigned", row)

    def test_acknowledgment_updates_queue_without_hiding_flags(self) -> None:
        batch = make_batch(ROWS[0])
        record, = batch.records
        self.assertEqual(correction_groups(batch)[NEEDS_REVIEW], (record,))
        batch.acknowledge_record(batch.get_preview(record.record_id))
        groups = correction_groups(batch)
        self.assertEqual(groups[NEEDS_REVIEW], ())
        self.assertEqual(groups[INCLUDED], (record,))
        self.assertTrue(batch.get_preview(record.record_id).issues)
        batch.edit_field(record.record_id, "DateSigned ", "still unknown")
        self.assertEqual(correction_groups(batch)[NEEDS_REVIEW], (record,))

    def test_recoverable_exclusions_stay_separate_from_confirmed_duplicates(self) -> None:
        batch = make_batch(*ROWS)
        first, second, third = batch.records
        with self.assertRaisesRegex(ValueError, "Resolve duplicate candidates"):
            correction_groups(batch)
        pair, = batch.get_duplicate_candidates()
        batch.confirm_duplicate(pair, keep_record_id=second.record_id)
        self.assertEqual(correction_groups(batch)[INCLUDED], (second,))
        self.assertEqual(correction_groups(batch)[EXCLUDED], (third,))
        self.assertNotIn(first, correction_groups(batch)[EXCLUDED])
        batch.edit_field(third.record_id, "Email", "morgan@example.com")
        self.assertEqual(correction_groups(batch)[INCLUDED], (second, third))
        self.assertEqual(correction_groups(batch)[NEEDS_REVIEW], (third,))


class CorrectionReviewWidgetTests(unittest.TestCase):
    """Exercise actual Tk buttons when a desktop is available."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"A graphical display is required: {error}") from error
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.root.destroy()

    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.source = Path(directory.name) / "source.csv"
        self.template = Path(directory.name) / "template.csv"
        self.app = MemberCleanerApp(self.root)
        self.addCleanup(self.app.destroy)
        self.app._source_path.set(str(self.source))
        self.app._template_path.set(str(self.template))

    def prepare(self, *rows: tuple[str, ...]) -> None:
        with self.template.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerow(HEADERS)
        with self.source.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows((HEADERS, *rows))
        self.app._load_files()
        for index, box in enumerate(self.app._comboboxes):
            box.current(FIRST_DESTINATION + index)
        self.app._prepare_button.invoke()

    def test_acknowledge_then_edit_exact_date_key(self) -> None:
        self.prepare(ROWS[0])
        self.app._correction_button.invoke()
        review = self.app._correction_window
        self.assertEqual(review._selected_field(), "DateSigned ")
        self.assertEqual(review._return_button.winfo_manager(), "")
        self.assertIn("unknown", review._details.get("1.0", "end-1c"))
        with patch("member_cleaner.correction_review_gui.messagebox.askyesno", return_value=True):
            review._accept_button.invoke()
        self.assertIn("awaiting field review: 0", self.app._summary.get())
        self.assertEqual(review._summary.cget("text"), "Field review complete")
        self.assertIn("1 record is included", review._completion_message.cget("text"))
        self.assertEqual(review._record_view.winfo_manager(), "")
        self.assertEqual(review._return_button.winfo_manager(), "pack")
        review._browse_button.invoke()
        self.assertEqual(review._record_view.winfo_manager(), "grid")
        self.assertEqual(review._selected_field(), "DateSigned ")
        self.assertIn("Accepted flags", review._field_notice.cget("text"))
        with patch("member_cleaner.correction_review_gui.FieldEditDialog") as dialog:
            dialog.return_value.result = "01/10/24"
            review._edit_button.invoke()
            dialog.assert_called_once_with(review, "DateSigned ", "unknown", from_original=True)
        self.assertEqual(self.app.batch.prepare_export()[0]["DateSigned "], "01/10/24")
        self.assertEqual(review._summary.cget("text"), "Field review complete")
        self.assertEqual(review._return_button.winfo_manager(), "pack")
        batch = self.app.batch
        review._return_button.invoke()
        self.assertIsNone(self.app._correction_window)
        self.assertIs(self.app.batch, batch)
        self.assertFalse(self.app._save_button.instate(["disabled"]))

    def test_flagged_view_focus_and_next_record_navigation(self) -> None:
        self.prepare(ROWS[0], ("Morgan", "Reed", "morgan@example.com", "", "", ""))
        self.app._correction_button.invoke()
        review = self.app._correction_window
        self.assertIn("Record 1 — Jordan Taylor — 1 flag", review._record_box.get())
        self.assertEqual(review._field_mode.get(), FLAGGED_FIELDS)
        self.assertEqual(review._field_keys, ("DateSigned ",))
        self.assertIn("Flagged fields (1): DateSigned", review._field_notice.cget("text"))
        review._field_mode.set(ALL_FIELDS)
        review._render_fields()
        self.assertIn("Email", review._field_keys)
        review._next_flagged_button.invoke()
        self.assertIn("Record 2 — Morgan Reed — 1 flag", review._record_box.get())
        self.assertEqual(review._field_keys, ("DateSigned ",))
        self.assertEqual(review._field_mode.get(), FLAGGED_FIELDS)
        review._next_flagged_button.invoke()
        self.assertIn("Record 1", review._record_box.get())

    def test_edit_after_keep_both_returns_to_reopened_duplicate_review(self) -> None:
        self.prepare(*ROWS[:2])
        self.assertTrue(self.app._correction_button.instate(["disabled"]))
        self.app._review_button.invoke()
        self.app._duplicate_window._keep_both.invoke()
        self.app._correction_button.invoke()
        review = self.app._correction_window
        with patch("member_cleaner.correction_review_gui.FieldEditDialog") as dialog:
            dialog.return_value.result = "01/10/24"
            review._edit_button.invoke()
        self.assertFalse(review.winfo_exists())
        self.assertTrue(self.app._duplicate_window.winfo_exists())
        self.assertTrue(self.app._correction_button.instate(["disabled"]))
        self.assertEqual(len(self.app.batch.get_duplicate_candidates()), 1)

    def test_exclude_and_restore_keep_reason_separate_from_fields(self) -> None:
        self.prepare(ROWS[1])
        self.app._correction_button.invoke()
        review = self.app._correction_window
        review._browse_button.invoke()
        with patch("member_cleaner.correction_review_gui.simpledialog.askstring", return_value="Training example"):
            review._exclude_button.invoke()
        self.assertEqual(review._group_box.get(), EXCLUDED)
        self.assertEqual(review._return_button.winfo_manager(), "")
        self.assertEqual(review._record_view.winfo_manager(), "grid")
        self.assertIn("Training example", review._details.get("1.0", "end-1c"))
        self.assertTrue(review._accept_button.instate(["disabled"]))
        review._restore_button.invoke()
        self.assertEqual(review._summary.cget("text"), "Field review complete")
        self.assertEqual(review._record_view.winfo_manager(), "")
        review._browse_button.invoke()
        self.assertEqual(review._group_box.get(), INCLUDED)
        self.assertEqual(len(self.app.batch.get_correction_records()), 1)

    def test_remapping_closes_correction_window(self) -> None:
        self.prepare(ROWS[0])
        self.app._correction_button.invoke()
        review = self.app._correction_window
        self.app._mapping_changed(None)
        self.assertFalse(review.winfo_exists())
        self.assertIsNone(self.app.batch)
        self.assertTrue(self.app._correction_button.instate(["disabled"]))


if __name__ == "__main__":
    unittest.main()
