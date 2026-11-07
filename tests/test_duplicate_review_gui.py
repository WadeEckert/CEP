"""Test duplicate comparison and review controls with fictional records.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Verify that the displayed comparison preserves source order and
raw evidence, and that the Tk controls apply reversible batch decisions.
Only the widget tests require an available desktop display.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
import unittest
from unittest.mock import patch
from uuid import UUID

from member_cleaner.duplicate_review_gui import build_pair_comparison
from member_cleaner.gui import FIRST_DESTINATION, IGNORE, MappingSession, MemberCleanerApp


SOURCE = ("Given", "Surname", "Email", "Email", "Cell", "Petition", "Signed")
TEMPLATE = ("First Name", "Last Name", "Email", "Primary Cell/Mobile Phone", "PROISSSUB ", "DateSigned")
ROWS = (
    (" jordan ", "TAYLOR", "jordan@example.com", "first source note", "303-555-0140", "", "01/10/24"),
    ("Jordan", "Taylor", "jordan@example.com", "second source note", "3035550140", "Forest", "01/12/24"),
    ("Jordan", "Taylor", "jordan@example.com", "third source note", "3035550140", "Forest", "01/13/24"),
)
SELECTIONS = (FIRST_DESTINATION, FIRST_DESTINATION + 1, FIRST_DESTINATION + 2, IGNORE,
              FIRST_DESTINATION + 3, FIRST_DESTINATION + 4, FIRST_DESTINATION + 5)


def make_batch(rows=ROWS[:2]):
    """Prepare real models from a loaded snapshot without writing files."""
    session = MappingSession(Path("members.csv"), Path("template.csv"), SOURCE, TEMPLATE, rows)
    # Force sorted IDs to run opposite the source order in these comparisons.
    ids = [UUID(int=number) for number in range(len(rows), 0, -1)]
    with patch("member_cleaner.models.uuid4", side_effect=ids):
        return session.create_batch(SELECTIONS)


class PairComparisonTests(unittest.TestCase):
    """Check the data shown in the comparison without opening a window."""

    def test_comparison_preserves_originals_and_uses_source_order(self) -> None:
        batch = make_batch()
        pair, = batch.get_duplicate_candidates()
        self.assertEqual(pair.record_ids[0], batch.records[1].record_id)
        comparison = build_pair_comparison(batch, SOURCE, pair)
        self.assertEqual(comparison.record_ids, tuple(record.record_id for record in batch.records))
        self.assertEqual(comparison.record_numbers, (1, 2))
        self.assertIn("email, phone", comparison.evidence)
        self.assertIn("One PROISSSUB value is blank", comparison.evidence)
        self.assertIn(("First Name", "Jordan", "Jordan"), comparison.prepared_rows)
        self.assertIn(("PROISSSUB ", "", "Forest"), comparison.prepared_rows)
        self.assertIn(("1. 'Given'", " jordan ", "Jordan"), comparison.original_rows)
        self.assertIn(("3. 'Email'", "jordan@example.com", "jordan@example.com"), comparison.original_rows)
        self.assertIn(("4. 'Email'", "first source note", "second source note"), comparison.original_rows)
        self.assertEqual(tuple(record.original_source_values for record in batch.records), ROWS[:2])
        self.assertEqual(batch.get_duplicate_decisions(), ())

    def test_comparison_displays_effective_anonymous_name_beside_originals(self) -> None:
        rows = tuple(("", "Taylor", *row[2:]) for row in ROWS[:2])
        batch = make_batch(rows)
        pair, = batch.get_duplicate_candidates()
        comparison = build_pair_comparison(batch, SOURCE, pair)
        self.assertIn(("First Name", "Anonymous", "Anonymous"), comparison.prepared_rows)
        self.assertIn(("Last Name", "Donor", "Donor"), comparison.prepared_rows)
        self.assertIn(("2. 'Surname'", "Taylor", "Taylor"), comparison.original_rows)

    def test_comparison_rejects_changed_record_revisions(self) -> None:
        batch = make_batch()
        pair, = batch.get_duplicate_candidates()
        batch.records[0].edit_field("DateSigned", "01/11/24")
        with self.assertRaisesRegex(ValueError, "records changed"):
            build_pair_comparison(batch, SOURCE, pair)


class DuplicateReviewWidgetTests(unittest.TestCase):
    """Exercise real widget callbacks against the mapping and batch workflow."""

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
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source.csv"
        self.template = Path(self.temp.name) / "template.csv"
        with self.template.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerow(TEMPLATE)
        self.app = MemberCleanerApp(self.root)
        self.addCleanup(self.app.destroy)
        self.app._source_path.set(str(self.source))
        self.app._template_path.set(str(self.template))

    def open_review(self, rows=ROWS[:2]):
        """Load fictional CSV files, prepare a batch, and open its review window."""
        with self.source.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows((SOURCE, *rows))
        self.app._load_files()
        for box, choice in zip(self.app._comboboxes, SELECTIONS, strict=True):
            box.current(choice)
        ids = [UUID(int=number) for number in range(len(rows), 0, -1)]
        with patch("member_cleaner.models.uuid4", side_effect=ids):
            self.app._prepare_button.invoke()
        self.app._review_button.invoke()
        return self.app._duplicate_window

    def test_keep_right_updates_summary_and_undo_restores_row(self) -> None:
        self.assertTrue(self.app._review_button.instate(["disabled"]))
        review = self.open_review()
        self.assertIn("Matching contact: email, phone", review._evidence.cget("text"))
        self.assertIn("second source note", review._originals[1][1].get("1.0", "end-1c"))
        self.assertEqual(review._keep_right.cget("text"), "Keep record 2 only")
        first, second = self.app.batch.records
        with self.assertRaisesRegex(ValueError, "Resolve duplicate candidates"):
            self.app.batch.get_correction_records()
        review._keep_right.invoke()
        self.assertEqual(first.confirmed_duplicate_of, second.record_id)
        self.assertEqual(self.app.batch.get_correction_records(), (second,))
        self.assertIn("confirmed duplicates: 1", self.app._summary.get())
        self.assertEqual(review._progress.cget("text"), "Duplicate review complete")
        history_item, = review._history.get_children()
        review._history.selection_set(history_item)
        review._update_undo_button()
        review._undo_button.invoke()
        self.assertTrue(all(record.is_included for record in self.app.batch.records))
        self.assertEqual(review._pair_box.get(), "Records 1 and 2")
        self.assertIn("Possible duplicate pairs: 1", self.app._summary.get())

    def test_keep_both_decision_survives_closing_and_reopening(self) -> None:
        review = self.open_review()
        review._keep_both.invoke()
        self.assertEqual(self.app.batch.get_correction_records(), self.app.batch.records)
        self.app._review_button.invoke()
        self.assertIs(self.app._duplicate_window, review)
        review.destroy()
        self.app._review_button.invoke()
        reopened = self.app._duplicate_window
        self.assertIsNot(reopened, review)
        item, = reopened._history.get_children()
        self.assertEqual(reopened._history.item(item, "values"), ("Records 1 and 2", "Keep both"))

    def test_exclude_both_cancels_or_records_a_reason_and_supports_undo(self) -> None:
        review = self.open_review()
        with patch("member_cleaner.duplicate_review_gui.simpledialog.askstring", return_value=None):
            review._exclude_both_button.invoke()
        self.assertEqual(len(self.app.batch.get_duplicate_candidates()), 1)
        with patch("member_cleaner.duplicate_review_gui.simpledialog.askstring", return_value="Out of scope"):
            review._exclude_both_button.invoke()
        self.assertEqual(self.app.batch.get_correction_records(), ())
        self.assertIn("Excluded records: 2 (confirmed duplicates: 0)", self.app._summary.get())
        self.assertTrue(review._exclude_both_button.instate(["disabled"]))
        self.assertTrue(self.app._save_button.instate(["disabled"]))
        self.assertEqual(review._continue_button.cget("text"), "Review excluded records")
        self.assertEqual(review._pair_box.winfo_manager(), "")
        review._continue_button.invoke()
        self.assertEqual(self.app._correction_window._group_box.get(), "Excluded records")
        self.app._review_button.invoke()
        review = self.app._duplicate_window
        item, = review._history.get_children()
        self.assertEqual(review._history.item(item, "values"),
                         ("Records 1 and 2", "Both records excluded — Out of scope"))
        review._history.selection_set(item)
        review._update_undo_button()
        self.assertEqual(review._history_reason.get("1.0", "end-1c"), "Reason: Out of scope")
        review._undo_button.invoke()
        self.assertEqual(review._history.get_children(), ())
        self.assertEqual(len(self.app.batch.get_duplicate_candidates()), 1)
        self.assertTrue(all(record.manual_exclusion_reason is None for record in self.app.batch.records))
        self.assertEqual(review._completion.winfo_manager(), "")
        self.assertEqual(review._pair_box.winfo_manager(), "grid")

    def test_completion_handoff_opens_field_review_on_same_batch(self) -> None:
        review = self.open_review()
        review._keep_both.invoke()
        batch = self.app.batch
        self.assertEqual(review._continue_button.cget("text"), "Continue to field review")
        self.assertEqual(review._pair_box.winfo_manager(), "")
        review._continue_button.invoke()
        self.assertFalse(review.winfo_exists())
        self.assertIs(self.app._correction_window._batch, batch)

    def test_alternate_pair_uses_the_selected_records(self) -> None:
        review = self.open_review(ROWS)
        self.assertEqual(tuple(review._pair_box["values"]),
                         ("Records 1 and 2", "Records 1 and 3", "Records 2 and 3"))
        review._pair_box.current(2)
        review._show_selected_pair()
        review._keep_left.invoke()
        self.assertEqual(self.app.batch.records[2].confirmed_duplicate_of,
                         self.app.batch.records[1].record_id)
        self.assertEqual(review._pair_box.get(), "Records 1 and 2")

    def test_stale_choice_is_rejected_and_display_refreshes(self) -> None:
        review = self.open_review()
        self.app.batch.records[0].edit_field("DateSigned", "01/11/24")
        with patch("member_cleaner.duplicate_review_gui.messagebox.showerror") as error:
            review._keep_right.invoke()
        error.assert_called_once()
        self.assertEqual(self.app.batch.get_duplicate_decisions(), ())
        self.assertIn("01/11/24", review._prepared[0][1].get("1.0", "end-1c"))

    def test_remapping_closes_review_and_invalidates_old_batch(self) -> None:
        review = self.open_review()
        self.app._mapping_changed(None)
        self.assertFalse(review.winfo_exists())
        self.assertIsNone(self.app.batch)
        self.assertTrue(self.app._review_button.instate(["disabled"]))
        self.assertFalse(self.app._prepare_button.instate(["disabled"]))

    def test_no_candidates_disables_choices_and_shows_ready_count(self) -> None:
        review = self.open_review(ROWS[:1])
        self.assertEqual(review._progress.cget("text"), "Duplicate review complete")
        self.assertIn("Records ready for correction review: 1", review._evidence.cget("text"))
        for button in (review._keep_both, review._keep_left, review._keep_right, review._undo_button):
            self.assertTrue(button.instate(["disabled"]))


if __name__ == "__main__":
    unittest.main()
