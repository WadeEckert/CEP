"""Exercise the GUI-to-workflow boundary with fictional CSV files.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Verify exact-header/index mapping, immutable loaded input, and
workflow integration without a display. Also exercise the actual widgets
when a graphical display is available; otherwise skip only widget tests.

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

from member_cleaner.gui import (
    CHOOSE, IGNORE, UNIT, FIRST_DESTINATION, MappingSession, MemberCleanerApp,
    build_mapping, mapping_choices, suggest_mapping_positions,
)


REFERENCE_DATE = date(2026, 11, 6)
TEMPLATE = [
    "First Name", "Last Name", "Street", "City", "State", "Zipcode",
    "Primary Cell/Mobile Phone", "Email", "DateSigned", "PROISSSUB ",
    "Address Contact Status", "PhoneDisclaimeredYN", "Account Classification",
]
SOURCE = ["Given", "Surname", "Address", "Unit", "City", "State", "ZIP", "Email", "Signed"]
ROWS = [[" jordan ", "TAYLOR", "125 Elm Street", "004b", "Denver", "Colorado", "80202",
         "jordan@example.com", "11/01/26"]]
SELECTIONS = [FIRST_DESTINATION + TEMPLATE.index(name) if name is not None else UNIT
              for name in ["First Name", "Last Name", "Street", None, "City", "State",
                           "Zipcode", "Email", "DateSigned"]]


def write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    """Create a temporary fictional fixture using real CSV quoting rules."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


class MappingSessionTests(unittest.TestCase):
    """Test the actual mapping boundary independently of Tk's display server."""

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "members.csv"
        self.template = Path(self.temp.name) / "template.csv"
        write_csv(self.source, SOURCE, ROWS)
        write_csv(self.template, TEMPLATE, [])

    def test_suggestions_skip_ambiguous_and_assigned_columns(self) -> None:
        source = (" DATEsigned", "Email", "Phone", "Name", " name ", "Other", "Unit", "Ignored")
        template = ("DateSigned ", "Email", "Phone", " phone ", "Name", "Unit", "Ignored")
        choices = (CHOOSE, CHOOSE, CHOOSE, CHOOSE, CHOOSE, FIRST_DESTINATION + 1, UNIT, IGNORE)
        suggestions = suggest_mapping_positions(source, template, choices)
        self.assertEqual(suggestions, {0: FIRST_DESTINATION})
        mapping, _ = build_mapping(source[:1], template, (suggestions[0],))
        self.assertEqual(mapping, {0: "DateSigned "})

    def test_repeated_source_headers_and_exact_destinations(self) -> None:
        """Keep source indexes and trailing destination spaces authoritative."""
        mapping, unit = build_mapping(
            ["Name", "Name", "Unit", "Street", "Other"],
            ["First Name", "PROISSSUB ", "Street"],
            [FIRST_DESTINATION, FIRST_DESTINATION + 1, UNIT, FIRST_DESTINATION + 2, IGNORE],
        )
        self.assertEqual(mapping, {0: "First Name", 1: "PROISSSUB ", 3: "Street", 4: None})
        self.assertEqual(unit, 2)
        self.assertNotIn(unit, mapping)

    def test_incomplete_and_conflicting_roles_are_rejected(self) -> None:
        """Do not silently ignore unchosen columns or overwrite destinations."""
        cases = [
            (["A"], [CHOOSE]), (["A", "B"], [FIRST_DESTINATION]),
            (["A", "B"], [FIRST_DESTINATION, FIRST_DESTINATION]),
            (["A", "B"], [UNIT, UNIT]), (["A", "B"], [UNIT, IGNORE]),
            (["A"], [IGNORE]), (["A"], [-1]), (["A"], [999]),
            (["A"], [True]), (["A"], ["3"]),
        ]
        for source, selections in cases:
            with self.subTest(selections=selections), self.assertRaises(ValueError):
                build_mapping(source, ["First Name", "Street"], selections)

    def test_display_labels_cannot_collide_with_roles_or_trim_headers(self) -> None:
        """A real heading named Ignore remains a separate mappable destination."""
        headings = ["Ignore this column", "Separate street unit", "PROISSSUB ", "PROISSSUB"]
        labels = mapping_choices(headings)
        self.assertEqual(len(labels), len(set(labels)))
        self.assertIn("'PROISSSUB '", labels[FIRST_DESTINATION + 2])
        for index, name in enumerate(headings):
            mapping, unit = build_mapping(["Data"], headings, [FIRST_DESTINATION + index])
            self.assertEqual(mapping, {0: name})
            self.assertIsNone(unit)

    def test_loaded_snapshot_survives_disk_changes_and_protects_paths(self) -> None:
        """Process the values shown to the user even if either file changes."""
        session = MappingSession.load(self.source, self.template)
        self.assertIsInstance(session.source_rows[0], tuple)
        with self.assertRaises(TypeError):
            session.source_rows[0][0] = "Changed"
        write_csv(self.source, ["Different"], [["Changed"]])
        self.template.unlink()
        batch = session.create_batch(SELECTIONS, reference_date=REFERENCE_DATE)
        record = batch.records[0]
        self.assertEqual(record.original_source_values, tuple(ROWS[0]))
        self.assertEqual(record.working_values["First Name"], "Jordan")
        with self.assertRaises(ValueError):
            batch.save_csv(self.template)
        self.assertEqual(self.source.read_text().splitlines()[0], "Different")

    def test_snapshot_mapping_reaches_cleaned_preview_without_writing_files(self) -> None:
        """Combine a separate unit and retain originals through real evaluation."""
        original = self.source.read_bytes()
        session = MappingSession.load(self.source, self.template)
        batch = session.create_batch(SELECTIONS, reference_date=REFERENCE_DATE)
        record = batch.records[0]
        preview = batch.get_preview(record.record_id)
        self.assertEqual(record.original_unit_value, "004b")
        self.assertEqual(record.original_mapped_values["Street"], "125 Elm Street")
        self.assertEqual(preview.output_values["Street"], "125 Elm St # 004B")
        self.assertEqual(preview.output_values["State"], "CO")
        self.assertEqual(preview.output_values["Address Contact Status"], "MAILABLE")
        self.assertEqual(preview.output_values["PhoneDisclaimeredYN"], "Y")
        self.assertEqual(list(preview.output_values), TEMPLATE)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(len(list(Path(self.temp.name).iterdir())), 2)

    def test_invalid_source_and_nonempty_template_fail_before_session_creation(self) -> None:
        """Use existing CSV validation instead of constructing a partial screen."""
        write_csv(self.source, SOURCE, [["Too few fields"]])
        with self.assertRaises(ValueError):
            MappingSession.load(self.source, self.template)
        write_csv(self.source, SOURCE, ROWS)
        write_csv(self.template, TEMPLATE, [["Data"]])
        with self.assertRaises(ValueError):
            MappingSession.load(self.source, self.template)

    def test_empty_file_still_requires_valid_mapping(self) -> None:
        """An empty input cannot conceal invalid or unchosen mapping roles."""
        write_csv(self.source, SOURCE, [])
        session = MappingSession.load(self.source, self.template)
        with self.assertRaises(ValueError):
            session.create_batch([CHOOSE] * len(SOURCE), reference_date=REFERENCE_DATE)
        self.assertEqual(session.create_batch(SELECTIONS, reference_date=REFERENCE_DATE).records, ())

    def test_new_batches_have_independent_models_and_duplicate_review_stays_pending(self) -> None:
        """Repreparing does not reuse edits or automatically delete likely matches."""
        write_csv(self.source, SOURCE, [ROWS[0], ROWS[0]])
        session = MappingSession.load(self.source, self.template)
        first = session.create_batch(SELECTIONS, reference_date=REFERENCE_DATE)
        second = session.create_batch(SELECTIONS, reference_date=REFERENCE_DATE)
        self.assertNotEqual(first.records[0].record_id, second.records[0].record_id)
        self.assertEqual(len(first.get_duplicate_candidates()), 1)
        self.assertEqual(sum(record.is_included for record in first.records), 2)
        with self.assertRaises(ValueError):
            first.prepare_export()


class GuiWidgetTests(unittest.TestCase):
    """Exercise real Tk controls when this environment has a graphical display."""

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
        write_csv(self.source, SOURCE, ROWS)
        write_csv(self.template, TEMPLATE, [])
        self.app = MemberCleanerApp(self.root)
        self.addCleanup(self.app.destroy)
        self.app._source_path.set(str(self.source))
        self.app._template_path.set(str(self.template))

    def load_and_select(self) -> None:
        """Exercise file loading, then select the fixture's dropdown roles."""
        self.app._load_files()
        for box, choice in zip(self.app._comboboxes, SELECTIONS):
            box.current(choice)

    def test_loading_builds_one_readonly_choice_per_source_index(self) -> None:
        """Startup is gated and loading shows samples without choosing mappings."""
        self.assertTrue(self.app._prepare_button.instate(["disabled"]))
        self.app._load_files()
        self.assertEqual(len(self.app._comboboxes), len(SOURCE))
        self.assertTrue(all(box.current() == CHOOSE for box in self.app._comboboxes))
        self.assertTrue(all(str(box["state"]) == "readonly" for box in self.app._comboboxes))
        self.assertFalse(self.app._prepare_button.instate(["disabled"]))

    def test_suggestions_mark_only_new_choices_and_wait_for_confirmation(self) -> None:
        self.app._load_files()
        city = SOURCE.index("City")
        email = SOURCE.index("Email")
        self.app._comboboxes[city].current(IGNORE)
        self.app._suggest_button.invoke()
        self.assertIsNone(self.app.batch)
        self.assertEqual(self.app._comboboxes[city].current(), IGNORE)
        self.assertEqual(self.app._comboboxes[email].current(), FIRST_DESTINATION + TEMPLATE.index("Email"))
        self.assertEqual(self.app._suggested_labels[email].cget("text"), "Suggested")
        self.assertEqual(self.app._comboboxes[0].current(), CHOOSE)
        self.assertIn("remaining source columns", self.app._status.get())

    def test_bad_mapping_is_recoverable_and_good_mapping_prepares_batch(self) -> None:
        """Show an actionable error and allow correction in the same window."""
        self.app._load_files()
        with patch("member_cleaner.gui.messagebox.showerror") as error:
            self.app._prepare_batch()
        error.assert_called_once()
        self.assertIsNone(self.app.batch)
        for box, choice in zip(self.app._comboboxes, SELECTIONS):
            box.current(choice)
        self.app._prepare_batch()
        self.assertIsNotNone(self.app.batch)
        self.assertIn("Source records: 1", self.app._summary.get())
        self.assertIn("Possible duplicate pairs: 0", self.app._summary.get())

    def test_mapping_change_and_file_choice_discard_stale_batch(self) -> None:
        """Cancel preserves state; real changes require a fresh batch/session."""
        self.load_and_select()
        self.app._prepare_batch()
        batch = self.app.batch
        with patch("member_cleaner.gui.filedialog.askopenfilename", return_value=""):
            self.app._select_file(self.app._source_path)
        self.assertIs(self.app.batch, batch)
        self.app._mapping_changed(None)
        self.assertIsNone(self.app.batch)
        self.assertEqual(self.app._summary.get(), "")
        self.app._prepare_batch()
        with patch("member_cleaner.gui.filedialog.askopenfilename", return_value=str(self.source)):
            self.app._select_file(self.app._source_path)
        self.assertIsNone(self.app.session)
        self.assertIsNone(self.app.batch)
        self.assertEqual(self.app._comboboxes, [])
        self.assertTrue(self.app._prepare_button.instate(["disabled"]))

    def test_failed_reload_clears_previous_mapping_and_shows_error(self) -> None:
        """A bad replacement file cannot leave a usable stale mapping screen."""
        self.load_and_select()
        self.source.unlink()
        with patch("member_cleaner.gui.messagebox.showerror") as error:
            self.app._load_files()
        error.assert_called_once()
        self.assertIsNone(self.app.session)
        self.assertEqual(self.app._comboboxes, [])
        self.assertTrue(self.app._prepare_button.instate(["disabled"]))

    def test_save_waits_for_duplicate_and_field_review(self) -> None:
        flagged = ROWS[0][:-1] + ["unknown"]
        write_csv(self.source, SOURCE, [flagged, flagged])
        self.load_and_select()
        self.app._prepare_batch()
        batch = self.app.batch
        self.assertTrue(self.app._save_button.instate(["disabled"]))
        self.assertIn("review 1 possible duplicate pair", self.app._status.get())
        batch.confirm_duplicate(batch.get_duplicate_candidates()[0], keep_record_id=batch.records[0].record_id)
        self.app._update_batch_summary()
        self.assertTrue(self.app._save_button.instate(["disabled"]))
        self.assertIn("review 1 flagged record", self.app._status.get())
        batch.acknowledge_record(batch.get_unreviewed_records()[0])
        self.app._update_batch_summary()
        self.assertFalse(self.app._save_button.instate(["disabled"]))
        self.assertIn("Save cleaned CSV (1 record ready)", self.app._status.get())
        with patch("member_cleaner.gui.messagebox.askyesno", return_value=True):
            self.app._mapping_changed(None)
        self.assertTrue(self.app._save_button.instate(["disabled"]))

    def test_save_dialog_cancel_protection_and_new_file(self) -> None:
        self.load_and_select()
        self.app._prepare_batch()
        output = self.source.with_name("new.csv")
        source_before = self.source.read_bytes()
        batch = self.app.batch
        batch.edit_field(batch.records[0].record_id, "First Name", "Jordyn")
        self.assertTrue(self.app._has_unsaved_work())
        with patch("member_cleaner.gui.filedialog.asksaveasfilename",
                   side_effect=["", str(self.source), str(output), str(output)]) as dialog, \
                patch("member_cleaner.gui.SaveConfirmation") as success, \
                patch("member_cleaner.gui.open_containing_folder") as open_folder, \
                patch("member_cleaner.gui.messagebox.showerror") as error:
            success.return_value.result = True
            self.app._save_button.invoke()
            self.assertFalse(output.exists())
            self.assertTrue(self.app._has_unsaved_work())
            self.app._save_button.invoke()
            self.assertEqual(self.source.read_bytes(), source_before)
            self.app._save_button.invoke()
            saved = output.read_bytes()
            self.assertFalse(self.app._has_unsaved_work())
            self.app._save_button.invoke()
            self.assertEqual(output.read_bytes(), saved)
        self.assertEqual(dialog.call_args.kwargs["initialfile"], "source_cleaned.csv")
        success.assert_called_once_with(self.root, output, 1)
        open_folder.assert_called_once_with(output)
        self.assertEqual(error.call_count, 2)
        with output.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames, TEMPLATE)
            row = next(reader)
            self.assertEqual(row["Street"], "125 Elm St # 004B")
            self.assertEqual(row["First Name"], "Jordyn")
        batch.edit_field(batch.records[0].record_id, "First Name", "Jordan")
        self.assertTrue(self.app._has_unsaved_work())

    def test_discard_prompt_preserves_dirty_batch_and_restores_mapping_on_no(self) -> None:
        self.load_and_select()
        self.app._prepare_batch()
        batch = self.app.batch
        batch.edit_field(batch.records[0].record_id, "First Name", "Jordyn")
        self.app._comboboxes[0].current(IGNORE)
        with patch("member_cleaner.gui.messagebox.askyesno", return_value=False) as confirm:
            self.app._mapping_changed(None)
            self.app._load_files()
            self.app._close_app()
        self.assertEqual(confirm.call_count, 3)
        self.assertIs(self.app.batch, batch)
        self.assertEqual(self.app._comboboxes[0].current(), SELECTIONS[0])
        self.assertEqual(batch.records[0].working_values["First Name"], "Jordyn")
        with patch("member_cleaner.gui.messagebox.askyesno", return_value=True) as confirm:
            self.app._load_files()
        confirm.assert_called_once()
        self.assertIsNone(self.app.batch)

    def test_save_rechecks_review_after_the_dialog_returns(self) -> None:
        self.load_and_select()
        self.app._prepare_batch()
        batch = self.app.batch
        output = self.source.with_name("new.csv")

        def choose_file(**_options) -> str:
            batch.edit_field(batch.records[0].record_id, "DateSigned", "unknown")
            return str(output)

        with patch("member_cleaner.gui.filedialog.asksaveasfilename", side_effect=choose_file), \
                patch("member_cleaner.gui.messagebox.showerror") as error:
            self.app._save_button.invoke()
        error.assert_called_once()
        self.assertFalse(output.exists())
        self.assertTrue(self.app._save_button.instate(["disabled"]))

    def test_batch_proisssub_requires_apply_before_save_and_clears_on_reload(self) -> None:
        self.load_and_select()
        self.app._prepare_batch()
        self.assertFalse(self.app._save_button.instate(["disabled"]))
        self.app._petition_entry.insert(0, " Group 24 ")
        self.assertEqual(self.app._petition_value.get(), " Group 24 ")
        self.assertTrue(self.app._save_button.instate(["disabled"]))
        self.assertIn("apply", self.app._status.get())
        self.app._apply_petition_button.invoke()
        self.assertFalse(self.app._save_button.instate(["disabled"]))
        self.assertEqual(self.app.batch.prepare_export()[0]["PROISSSUB "], "Group 24")
        with patch("member_cleaner.gui.messagebox.askyesno", return_value=True) as confirm:
            self.app._load_files()
        confirm.assert_called_once()
        self.assertEqual(self.app._petition_value.get(), "")
        self.assertFalse(self.app._petition_entry.instate(["disabled"]))

    def test_petition_entry_accepts_typing_before_prepare_with_alternate_heading(self) -> None:
        template = ["PROISSUB" if field == "PROISSSUB " else field for field in TEMPLATE]
        write_csv(self.template, template, [])
        self.load_and_select()
        self.assertIsNone(self.app.batch)
        self.assertFalse(self.app._petition_entry.instate(["disabled"]))
        self.app._petition_entry.insert(0, "Fictional Region A")
        self.app._prepare_batch()
        self.assertEqual(self.app.batch.prepare_export()[0]["PROISSUB"], "Fictional Region A")
        self.assertFalse(self.app._save_button.instate(["disabled"]))


if __name__ == "__main__":
    unittest.main()
