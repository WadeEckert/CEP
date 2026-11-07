"""File selection, mapping, review, and Save As for the Member CSV Cleaner.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Preview incoming columns, collect explicit mapping choices, and
prepare a MemberBatch using the same raw rows shown to the user. Open its
review windows, refresh the summary after choices, and collect an output
path for the backend to validate and save.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import csv
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .correction_review_gui import CorrectionReviewWindow
from .csv_io import load_template, read_source_csv
from .duplicate_review_gui import DuplicateReviewWindow
from .gui_style import PRIMARY_BUTTON, SURFACE, configure_theme
from .mapping import map_record_with_unit, validate_mapping
from .models import MemberRecord, resolve_proissub_heading
from .workflow import MemberBatch, ReviewState


# Combobox positions are roles, not exported field names. A real template
# heading named "Ignore this column" must still be available as a destination.
CHOOSE = 0
IGNORE = 1
UNIT = 2
FIRST_DESTINATION = 3


def mapping_choices(template_headers: Sequence[str]) -> tuple[str, ...]:
    """Make distinct display labels without changing any destination heading.

    repr() exposes trailing spaces and escaped whitespace in the labels.
    Numeric positions distinguish destinations from the three special roles.
    These labels are presentation only; they never become CSV field names.
    """
    return (
        "Choose a destination...", "Ignore this column", "Separate street unit",
        *(f"{index}. {heading!r}"
          for index, heading in enumerate(template_headers, start=1)),
    )


def suggest_mapping_positions(
    source_headers: Sequence[str], template_headers: Sequence[str], choices: Sequence[int],
) -> dict[int, int]:
    """Suggest only unique unused heading matches; preserve exact destination keys."""
    source_keys = [" ".join(heading.split()).casefold() for heading in source_headers]
    template_keys = [" ".join(heading.split()).casefold() for heading in template_headers]
    source_counts, destination_counts = Counter(source_keys), Counter(template_keys)
    destinations = {key: i for i, key in enumerate(template_keys, start=FIRST_DESTINATION)}
    used = set(choices)
    return {
        index: destinations[key]
        for index, (key, choice) in enumerate(zip(source_keys, choices, strict=True))
        if choice == CHOOSE and key and source_counts[key] == destination_counts[key] == 1
        and destinations[key] not in used
    }


def build_mapping(
    source_headers: Sequence[str], template_headers: Sequence[str],
    choice_indexes: Sequence[int],
) -> tuple[dict[int, str | None], int | None]:
    """Translate GUI positions to the mapping API and validate every role.

    Require one deliberate choice per source column. Keep a separate unit
    index outside the ordinary mapping, exactly as map_record_with_unit
    expects. Existing mapping validation rejects reused destinations and a
    unit role without a mapped main Street field.
    """
    if len(choice_indexes) != len(source_headers):
        raise ValueError("Choose a role for every source column.")
    mapping: dict[int, str | None] = {}
    unit_index = None
    for source_index, choice in enumerate(choice_indexes):
        if type(choice) is not int or not 0 <= choice < FIRST_DESTINATION + len(template_headers):
            raise ValueError(f"Column {source_index + 1} has an invalid choice.")
        if choice == CHOOSE:
            raise ValueError(
                f"Column {source_index + 1}: choose a destination, Ignore, or a separate unit."
            )
        if choice == UNIT:
            if unit_index is not None:
                raise ValueError("Select only one separate street unit column.")
            unit_index = source_index
        elif choice == IGNORE:
            mapping[source_index] = None
        else:
            mapping[source_index] = template_headers[choice - FIRST_DESTINATION]
    validate_mapping(
        list(source_headers), list(template_headers), mapping,
        unit_source_index=unit_index,
    )
    return mapping, unit_index


@dataclass(frozen=True)
class MappingSession:
    """Hold a read-only snapshot of the files behind the mapping screen.

    Paths identify protected inputs. Nested tuples retain the exact loaded
    headings and rows, including repeated source headings and leading zeros.
    Preparing a batch does not reread files that may have changed on disk.
    """

    source_path: Path
    template_path: Path
    source_headers: tuple[str, ...]
    template_headers: tuple[str, ...]
    source_rows: tuple[tuple[str, ...], ...]

    @property
    def proissub_heading(self) -> str | None:
        """Return the exact petition destination in the loaded template."""
        return resolve_proissub_heading(self.template_headers)

    @classmethod
    def load(cls, source_path: str | Path, template_path: str | Path) -> "MappingSession":
        """Read and validate both files before displaying a new session."""
        source = Path(source_path).resolve()
        template = Path(template_path).resolve()
        destinations = load_template(template)
        resolve_proissub_heading(destinations)
        headers, rows = read_source_csv(source)
        return cls(source, template, tuple(headers), tuple(destinations),
                   tuple(tuple(row) for row in rows))

    def create_batch(
        self, choice_indexes: Sequence[int], *, reference_date: date | None = None,
    ) -> MemberBatch:
        """Map the displayed snapshot into fresh models and the tested workflow."""
        mapping, unit_index = build_mapping(
            self.source_headers, self.template_headers, choice_indexes
        )
        records = []
        for row in self.source_rows:
            mapped, unit = map_record_with_unit(
                list(row), list(self.source_headers), list(self.template_headers),
                mapping, unit_source_index=unit_index,
            )
            records.append(MemberRecord(row, mapped, unit))
        return MemberBatch(
            records, self.template_headers, reference_date=reference_date,
            protected_paths=(self.source_path, self.template_path),
        )


def open_containing_folder(path: Path) -> None:
    """Open the saved file's folder in the system file manager."""
    folder = str(path.resolve().parent)
    if os.name == "nt":
        os.startfile(folder)
    else:
        launcher = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([launcher, folder])


class SaveConfirmation(simpledialog.Dialog):
    """Show what was saved and let the user choose to open its folder."""

    def __init__(self, parent: tk.Misc, path: Path, count: int) -> None:
        self._path = path
        self._count = count
        super().__init__(parent, title="Cleaned CSV saved")

    def body(self, master: tk.Misc) -> None:
        self.configure(background=SURFACE)
        master.configure(background=SURFACE)
        ttk.Label(master, text=f"Saved {self._count} record{'s' if self._count != 1 else ''}",
                  style="Heading.TLabel").pack(anchor="w", padx=14, pady=(12, 6))
        ttk.Label(master, text=str(self._path), wraplength=525).pack(anchor="w", padx=14, pady=(0, 10))

    def buttonbox(self) -> None:
        buttons = ttk.Frame(self, padding=(14, 0, 14, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Close", command=self.cancel).pack(side="right")
        ttk.Button(buttons, text="Open containing folder", command=self.ok,
                   style=PRIMARY_BUTTON).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", self.cancel)

    def apply(self) -> None:
        self.result = True


class MemberCleanerApp(ttk.Frame):
    """Collect files and mapping choices without implementing business rules.

    self.batch is shared with duplicate review. Changes to the source,
    template, or mapping discard that batch and close its review window.
    """

    def __init__(self, root: tk.Tk) -> None:
        """Create the initial controls and an empty mapping session."""
        configure_theme(root)
        super().__init__(root, padding=16, style="Page.TFrame")
        root.title("Member CSV Cleaner")
        root.geometry("1100x760")
        root.minsize(900, 620)
        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        self.session: MappingSession | None = None
        self.batch: MemberBatch | None = None
        self._duplicate_window: DuplicateReviewWindow | None = None
        self._correction_window: CorrectionReviewWindow | None = None
        self._comboboxes: list[ttk.Combobox] = []
        self._suggested_labels: list[ttk.Label] = []
        self._source_path = tk.StringVar(master=root)
        self._template_path = tk.StringVar(master=root)
        self._status = tk.StringVar(master=root, value="Choose both files, then load their columns.")
        self._summary = tk.StringVar(master=root)
        self._petition_value = tk.StringVar(master=root)
        self._petition_help = tk.StringVar(master=root)
        self._review_ready = False
        self._review_status = ""
        self._review_action: ttk.Button | None = None
        self._saved_review_state: ReviewState | None = None
        self._prepared_choices: tuple[int, ...] = ()
        self._build_widgets()
        root.protocol("WM_DELETE_WINDOW", self._close_app)
        self._petition_value.trace_add("write", self._refresh_petition_controls)
        self._refresh_petition_controls()

    def _build_widgets(self) -> None:
        """Arrange file controls, a scrollable mapping area, and batch feedback."""
        heading = ttk.Frame(self, style="Page.TFrame")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(heading, text="Prepare a member CSV", style="Title.TLabel").pack(anchor="w")
        ttk.Label(heading, text="Choose your files, review the batch, and save a cleaned copy.",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))
        files = ttk.LabelFrame(self, text="1. Choose files", padding=8)
        files.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        files.columnconfigure(1, weight=1)
        for row, (label, variable) in enumerate((
            ("Source CSV", self._source_path), ("Header-only template", self._template_path),
        )):
            ttk.Label(files, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=2)
            ttk.Entry(files, textvariable=variable, state="readonly").grid(
                row=row, column=1, sticky="ew", pady=2
            )
            # A default argument captures this loop's variable for each button.
            ttk.Button(files, text="Browse...", command=lambda value=variable: self._select_file(value)).grid(
                row=row, column=2, padx=(10, 0), pady=2
            )
        load_actions = ttk.Frame(files)
        load_actions.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._load_button = ttk.Button(load_actions, text="Load columns", command=self._load_files,
                                      style=PRIMARY_BUTTON)
        self._load_button.pack(side="left")
        self._primary_action: ttk.Button | None = self._load_button
        self._suggest_button = ttk.Button(load_actions, text="Suggest column matches",
                                         command=self._suggest_mappings, state="disabled")
        self._suggest_button.pack(side="left", padx=(8, 0))

        mapping_frame = ttk.LabelFrame(self, text="2. Map every source column", padding=8)
        mapping_frame.grid(row=3, column=0, sticky="nsew")
        mapping_frame.rowconfigure(1, weight=1)
        mapping_frame.columnconfigure(0, weight=1)
        ttk.Label(
            mapping_frame,
            text="Choose a template field, Ignore, or one separate unit column. Quotes reveal header spacing.",
            wraplength=820, style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self._canvas = tk.Canvas(mapping_frame, background=SURFACE, highlightthickness=0, height=200)
        vertical = ttk.Scrollbar(mapping_frame, orient="vertical", command=self._canvas.yview)
        horizontal = ttk.Scrollbar(mapping_frame, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self._canvas.grid(row=1, column=0, sticky="nsew")
        vertical.grid(row=1, column=1, sticky="ns")
        horizontal.grid(row=2, column=0, sticky="ew")
        self._mapping_body = ttk.Frame(self._canvas, padding=4)
        self._canvas_window = self._canvas.create_window((0, 0), window=self._mapping_body, anchor="nw")
        self._mapping_body.bind("<Configure>", self._update_scroll_region)
        self._canvas.bind("<Configure>", self._resize_mapping)

        petition = ttk.LabelFrame(self, text="3. Batch petition group", padding=8)
        petition.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self._petition_entry = ttk.Entry(petition, textvariable=self._petition_value, width=23)
        self._petition_entry.pack(side="left")
        self._apply_petition_button = ttk.Button(petition, text="Apply to all records",
                                                command=self._apply_batch_petition)
        self._apply_petition_button.pack(side="left", padx=8)
        ttk.Label(petition, textvariable=self._petition_help, wraplength=510).pack(side="left", anchor="w")

        actions = ttk.Frame(self, style="Page.TFrame")
        actions.grid(row=5, column=0, sticky="w", pady=10)
        self._prepare_button = ttk.Button(actions, text="Prepare batch", command=self._prepare_batch,
                                          state="disabled")
        self._prepare_button.pack(side="left")
        self._review_button = ttk.Button(actions, text="Review duplicates...", command=self._review_duplicates,
                                         state="disabled")
        self._review_button.pack(side="left", padx=(10, 0))
        self._correction_button = ttk.Button(
            actions, text="Review and correct records...", command=self._review_corrections, state="disabled"
        )
        self._correction_button.pack(side="left", padx=(10, 0))
        self._save_button = ttk.Button(actions, text="Save cleaned CSV...", command=self._save_csv,
                                       state="disabled")
        self._save_button.pack(side="left", padx=(10, 0))
        status = ttk.Frame(self, padding=(12, 8), style="Info.TFrame")
        status.grid(row=6, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(status, textvariable=self._status, style="Info.TLabel", wraplength=810).pack(anchor="w")
        summary = ttk.LabelFrame(self, text="Batch summary", padding=10)
        summary.grid(row=7, column=0, sticky="ew")
        ttk.Label(summary, textvariable=self._summary, wraplength=850).pack(anchor="w")

    def _emphasize(self, action: ttk.Button | None) -> None:
        """Use one primary button for the next step described in the status."""
        if self._primary_action is not None:
            self._primary_action.configure(style="TButton")
        self._primary_action = action
        if action is not None:
            action.configure(style=PRIMARY_BUTTON)

    def _update_scroll_region(self, _event: tk.Event) -> None:
        """Make both scrollbars cover the current mapping contents."""
        self._canvas.itemconfigure(
            self._canvas_window,
            width=max(self._canvas.winfo_width(), self._mapping_body.winfo_reqwidth()),
        )
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _resize_mapping(self, event: tk.Event) -> None:
        """Use available width while allowing horizontal scrolling when needed."""
        self._canvas.itemconfigure(
            self._canvas_window, width=max(event.width, self._mapping_body.winfo_reqwidth())
        )

    def _clear_session(self) -> None:
        """Discard mappings and batches belonging to a previously loaded file."""
        self.session = None
        self._discard_batch()
        self._petition_value.set("")
        self._comboboxes.clear()
        self._suggested_labels.clear()
        for widget in self._mapping_body.winfo_children():
            widget.destroy()
        self._prepare_button.state(["disabled"])
        self._suggest_button.state(["disabled"])
        self._status.set("Choose both files, then load their columns.")
        self._emphasize(self._load_button)
        self._canvas.yview_moveto(0)
        self._canvas.xview_moveto(0)

    def _select_file(self, variable: tk.StringVar) -> None:
        """Open a native file picker; cancel leaves the current session intact."""
        title = "Choose the source CSV" if variable is self._source_path else "Choose the header-only template"
        filename = filedialog.askopenfilename(
            parent=self.winfo_toplevel(), title=title,
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if filename and self._confirm_discard():
            variable.set(filename)
            self._clear_session()

    def _load_files(self) -> None:
        """Load one complete snapshot or show a recoverable file error."""
        if not self._confirm_discard():
            return
        self._clear_session()
        if not self._source_path.get() or not self._template_path.get():
            messagebox.showerror("Choose both files", "Select a source CSV and a header-only template.",
                                 parent=self.winfo_toplevel())
            return
        try:
            session = MappingSession.load(self._source_path.get(), self._template_path.get())
        except (OSError, UnicodeError, csv.Error, ValueError) as error:
            messagebox.showerror("Could not load CSV files", str(error), parent=self.winfo_toplevel())
            return
        self.session = session
        choices = mapping_choices(session.template_headers)
        for column, title in enumerate(("Source column", "Sample values", "Destination column")):
            ttk.Label(self._mapping_body, text=title, style="Strong.TLabel").grid(
                row=0, column=column, sticky="w", padx=6, pady=(0, 8)
            )
        for index, heading in enumerate(session.source_headers):
            # The numeric index is the identity even if headings are repeated.
            ttk.Label(self._mapping_body, text=f"{index + 1}. {heading!r}", wraplength=230).grid(
                row=index + 1, column=0, sticky="w", padx=6, pady=3
            )
            samples = []
            for row in session.source_rows:
                value = row[index]
                if value.strip() and value not in samples:
                    samples.append(value)
                if len(samples) == 3:
                    break
            display = " | ".join(repr(value[:80]) + ("..." if len(value) > 80 else "") for value in samples)
            ttk.Label(self._mapping_body, text=display or "(No nonblank samples)", wraplength=300).grid(
                row=index + 1, column=1, sticky="w", padx=6, pady=3
            )
            box = ttk.Combobox(self._mapping_body, values=choices, state="readonly", width=40)
            box.current(CHOOSE)
            box.grid(row=index + 1, column=2, sticky="ew", padx=6, pady=3)
            box.bind("<<ComboboxSelected>>", self._mapping_changed)
            self._comboboxes.append(box)
            suggested = ttk.Label(self._mapping_body, style="Muted.TLabel")
            suggested.grid(row=index + 1, column=3, sticky="w", padx=6)
            self._suggested_labels.append(suggested)
        self._prepare_button.state(["!disabled"])
        self._suggest_button.state(["!disabled"])
        self._emphasize(self._suggest_button)
        self._refresh_petition_controls()
        self._status.set(
            f"Loaded {len(session.source_rows)} records and {len(session.source_headers)} source columns. "
            "Next: choose destinations or try Suggest column matches."
        )

    def _suggest_mappings(self) -> None:
        """Fill unassigned dropdowns only, leaving confirmation to Prepare batch."""
        if self.session is None or self.batch is not None:
            return
        suggestions = suggest_mapping_positions(
            self.session.source_headers, self.session.template_headers,
            [box.current() for box in self._comboboxes],
        )
        for source_index, destination in suggestions.items():
            self._comboboxes[source_index].current(destination)
            self._suggested_labels[source_index].configure(text="Suggested")
        remaining = sum(box.current() == CHOOSE for box in self._comboboxes)
        if suggestions:
            message = f"Suggested {len(suggestions)} column match{'es' if len(suggestions) != 1 else ''}. "
        else:
            message = "No additional unambiguous matches. " if remaining else ""
        self._status.set(message + self._mapping_next_step(remaining))
        self._emphasize(None if remaining else self._prepare_button)

    @staticmethod
    def _mapping_next_step(remaining: int) -> str:
        if remaining:
            return f"Next: choose a destination or role for {remaining} remaining source column{'s' if remaining != 1 else ''}."
        return "Next: review the choices, then select Prepare batch."

    def _mapping_changed(self, event: tk.Event | None) -> None:
        """A changed mapping requires a freshly prepared batch and summary."""
        if self.batch is not None:
            choices = tuple(box.current() for box in self._comboboxes)
            if event is not None and choices == self._prepared_choices:
                return
            if not self._confirm_discard():
                # Tk has already changed the dropdown; put the old choice back.
                for box, choice in zip(self._comboboxes, self._prepared_choices, strict=True):
                    box.current(choice)
                return
        self._discard_batch()
        if self.session is not None:
            self._prepare_button.state(["!disabled"])
            self._suggest_button.state(["!disabled"])
        if event is not None and event.widget in self._comboboxes:
            self._suggested_labels[self._comboboxes.index(event.widget)].configure(text="")
        remaining = sum(box.current() == CHOOSE for box in self._comboboxes)
        self._status.set(self._mapping_next_step(remaining))
        self._emphasize(None if remaining else self._prepare_button)

    def _prepare_batch(self) -> None:
        """Validate dropdowns and hand the displayed snapshot to MemberBatch."""
        if self.batch is not None and not self._confirm_discard():
            return
        self._discard_batch()
        self._status.set("Check every column choice before preparing the batch.")
        if self.session is None:
            return
        try:
            choices = tuple(box.current() for box in self._comboboxes)
            batch = self.session.create_batch(choices)
            prepared_state = batch.review_state()
            petition = self._petition_value.get().strip()
            if petition and batch.supports_batch_proisssub:
                batch.set_batch_proisssub(petition)
        except ValueError as error:
            messagebox.showerror("Check column mapping", str(error), parent=self.winfo_toplevel())
            return
        self.batch = batch
        self._saved_review_state = prepared_state
        self._prepared_choices = choices
        self._petition_value.set(batch.batch_proisssub or "")
        self._prepare_button.state(["disabled"])
        self._suggest_button.state(["disabled"])
        self._review_button.state(["!disabled"])
        self._update_batch_summary()

    def _discard_batch(self) -> None:
        """Close any review window before discarding the batch it belongs to."""
        self._close_corrections()
        if self._duplicate_window is not None and self._duplicate_window.winfo_exists():
            self._duplicate_window.destroy()
        self._duplicate_window = None
        self.batch = None
        self._saved_review_state = None
        self._prepared_choices = ()
        self._review_ready = False
        self._review_button.state(["disabled"])
        self._correction_button.state(["disabled"])
        self._refresh_petition_controls()
        self._summary.set("")

    def _has_unsaved_work(self) -> bool:
        if self.batch is None:
            return bool(self._petition_value.get().strip())
        return self._petition_pending() or self.batch.review_state() != self._saved_review_state

    def _confirm_discard(self) -> bool:
        """Ask only before actions that would discard unsaved batch work."""
        return not self._has_unsaved_work() or messagebox.askyesno(
            "Discard unsaved work?",
            "This batch has unsaved review work. Discard it?",
            default="no", parent=self.winfo_toplevel(),
        )

    def _close_app(self) -> None:
        if self._confirm_discard():
            self.winfo_toplevel().destroy()

    def _petition_pending(self) -> bool:
        batch = self.batch
        return (batch is not None and batch.supports_batch_proisssub
                and self._petition_value.get().strip() != (batch.batch_proisssub or ""))

    def _refresh_petition_controls(self, *_trace_args: str) -> None:
        """Prevent saving an older value when a new code has been typed."""
        batch = self.batch
        heading = self.session.proissub_heading if self.session is not None else None
        available = heading is not None
        pending = self._petition_pending()
        self._petition_entry.state(["!disabled"] if available else ["disabled"])
        self._apply_petition_button.state(["!disabled"] if pending else ["disabled"])
        self._save_button.state(["!disabled"] if self._review_ready and not pending else ["disabled"])
        if self.session is None:
            help_text = "Load the template to enter a petition group."
        elif not available:
            help_text = "The template needs a PROISSUB or PROISSSUB column."
        elif batch is None:
            help_text = f"Enter the group for {heading.strip()}. Prepare batch applies it to all records."
        elif pending:
            help_text = "Select Apply to all records before saving."
        elif batch.batch_proisssub is not None:
            help_text = "Applied to all records." if batch.batch_proisssub else "Set to blank for all records."
        else:
            help_text = "Optional. Enter the code shared by this file, ideally before duplicate review."
        self._petition_help.set(help_text)
        if batch is not None:
            self._status.set("Next: apply the new petition group." if pending else self._review_status)
            self._emphasize(self._apply_petition_button if pending else self._review_action)

    def _apply_batch_petition(self) -> None:
        """Set one value and refresh review from the changed batch."""
        batch = self.batch
        if batch is None or not self._petition_pending():
            return
        batch.set_batch_proisssub(self._petition_value.get())
        self._petition_value.set(batch.batch_proisssub or "")
        pending_pairs = self._update_batch_summary()
        if self._correction_window is not None and self._correction_window.winfo_exists():
            if pending_pairs:
                self._review_duplicates()
            else:
                self._correction_window.refresh()
        elif self._duplicate_window is not None and self._duplicate_window.winfo_exists():
            self._duplicate_window.refresh()

    def _review_duplicates(self) -> None:
        """Open or raise one duplicate review window for the current batch."""
        if self.batch is None or self.session is None:
            return
        self._close_corrections()
        if self._duplicate_window is None or not self._duplicate_window.winfo_exists():
            self._duplicate_window = DuplicateReviewWindow(
                self, self.batch, self.session.source_headers,
                on_change=self._update_batch_summary,
                on_continue=self._review_corrections,
            )
            self._position_review_window(self._duplicate_window, DuplicateReviewWindow.DEFAULT_SIZE)
        else:
            self._duplicate_window.refresh()
        self._duplicate_window.lift()
        self._duplicate_window.focus_set()

    def _close_corrections(self) -> None:
        if self._correction_window is not None and self._correction_window.winfo_exists():
            self._correction_window.destroy()
        self._correction_window = None

    def _review_corrections(self) -> None:
        """Open corrections after duplicate review, using the same batch."""
        batch = self.batch
        if batch is None:
            return
        if batch.get_duplicate_candidates():
            self._update_batch_summary()
            self._review_duplicates()
            return
        if self._duplicate_window is not None and self._duplicate_window.winfo_exists():
            self._duplicate_window.destroy()
        self._duplicate_window = None
        if self._correction_window is None or not self._correction_window.winfo_exists():
            self._correction_window = CorrectionReviewWindow(
                self, batch, on_change=self._corrections_changed, on_return_to_save=self._return_to_save,
            )
            self._position_review_window(self._correction_window, CorrectionReviewWindow.DEFAULT_SIZE)
        else:
            self._correction_window.refresh()
        self._correction_window.lift()
        self._correction_window.focus_set()

    def _return_to_save(self) -> None:
        self._close_corrections()
        self._update_batch_summary()
        self.winfo_toplevel().lift()
        if self._save_button.instate(["!disabled"]):
            self._save_button.focus_set()
        elif self._petition_pending():
            self._apply_petition_button.focus_set()

    def _position_review_window(self, window: tk.Toplevel, size: tuple[int, int]) -> None:
        """Position a newly opened review window over the main window."""
        root = self.winfo_toplevel()
        width, height = size
        if not root.winfo_ismapped():
            window.geometry(f"{width}x{height}")
            return
        # Use the parent's on-screen position so moving the main window moves
        # the starting position of subsequent review windows as well.
        x = root.winfo_rootx() + (root.winfo_width() - width) // 2
        y = root.winfo_rooty() + (root.winfo_height() - height) // 2
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _corrections_changed(self) -> None:
        """Route edits that reopen duplicate review back to that screen."""
        if self._update_batch_summary():
            self._status.set("A correction reopened duplicate review. Resolve the pairs to continue.")
            self._review_duplicates()

    def _update_batch_summary(self) -> bool:
        """Show current counts after preparing, deciding a pair, or undoing."""
        batch = self.batch
        if batch is None:
            return False
        # This call refreshes eligibility, issues, and duplicate exclusions.
        pairs = batch.get_duplicate_candidates()
        self._correction_button.state(["disabled"] if pairs else ["!disabled"])
        included = sum(record.is_included for record in batch.records)
        if pairs:
            review_count = sum(record.is_included and bool(record.issues) for record in batch.records)
            review_label = "Included records with field flags"
        else:
            review_count = len(batch.get_unreviewed_records())
            review_label = "Included records awaiting field review"
        self._review_ready = not pairs and review_count == 0 and included > 0
        redundant = sum(record.confirmed_duplicate_of is not None for record in batch.records)
        self._summary.set(
            f"Source records: {len(batch.records)}    |    "
            f"Currently included records: {included}    |    "
            f"Excluded records: {len(batch.records) - included} (confirmed duplicates: {redundant})\n"
            f"{review_label}: {review_count}    |    Possible duplicate pairs: {len(pairs)}"
        )
        if pairs:
            self._review_action = self._review_button
            count = len(pairs)
            status = f"Next: review {count} possible duplicate pair{'s' if count != 1 else ''} before saving."
        elif not included:
            self._review_action = self._correction_button if batch.records else None
            status = ("No records to save. Open Review and correct records to inspect exclusions."
                      if batch.records else "The source CSV has no data rows. Choose another file.")
        elif review_count:
            self._review_action = self._correction_button
            status = f"Next: review {review_count} flagged record{'s' if review_count != 1 else ''} before saving."
        else:
            self._review_action = self._save_button
            status = f"Next: Save cleaned CSV ({included} record{'s' if included != 1 else ''} ready)."
        self._review_status = status
        self._refresh_petition_controls()
        return bool(pairs)

    def _save_csv(self) -> None:
        """Choose an output path, then recheck and save through the batch."""
        batch, session = self.batch, self.session
        if batch is None or session is None:
            return
        parent = self.winfo_toplevel()
        try:
            if self._petition_pending():
                raise ValueError("Apply the petition group before saving.")
            if not batch.prepare_export():
                raise ValueError("No included records are available to save.")
        except ValueError as error:
            self._update_batch_summary()
            messagebox.showerror("Cannot save CSV", str(error), parent=parent)
            return

        filename = filedialog.asksaveasfilename(
            parent=parent, title="Save cleaned CSV", initialdir=str(session.source_path.parent),
            initialfile=f"{session.source_path.stem}_cleaned.csv", defaultextension=".csv",
            filetypes=(("CSV files", "*.csv"),), confirmoverwrite=False,
        )
        if not filename or self.batch is not batch:
            return
        try:
            if self._petition_pending():
                raise ValueError("Apply the petition group before saving.")
            saved_path = batch.save_csv(filename)
        except FileExistsError:
            messagebox.showerror("File already exists", "Choose a new filename. Existing files are not overwritten.",
                                 parent=parent)
        except (OSError, ValueError, csv.Error) as error:
            self._update_batch_summary()
            messagebox.showerror("Could not save CSV", str(error), parent=parent)
        else:
            self._saved_review_state = batch.review_state()
            count = sum(record.is_included for record in batch.records)
            self._status.set(f"Saved {count} record{'s' if count != 1 else ''} to {saved_path}")
            self._emphasize(None)
            if SaveConfirmation(parent, saved_path, count).result:
                try:
                    open_containing_folder(saved_path)
                except OSError as error:
                    messagebox.showerror("Could not open folder", f"The CSV was saved.\n{error}", parent=parent)
