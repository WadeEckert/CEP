"""Compare possible duplicate records and collect explicit review decisions.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Show matching evidence, prepared values, and original CSV values
for each candidate pair. Route keeper, keep-both, exclude-both, and undo
choices through MemberBatch, preserving the original source data.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from .gui_style import PRIMARY_BUTTON, style_text
from .models import DuplicateCandidate
from .validation import is_date_signed_heading
from .workflow import ExcludeBothDecision, MemberBatch


_CONTACT_LABELS = {"EMAIL": "email", "PHONE": "phone", "ADDRESS": "complete mailing address"}
_PETITION_LABELS = {
    "MATCHING": "{heading} values match.",
    "BOTH_BLANK": "Both {heading} values are blank.",
    "ONE_BLANK": "One {heading} value is blank.",
}
_KEY_FIELDS = (
    "First Name", "Last Name", "Email", "Primary Cell/Mobile Phone",
    "Street", "City", "State", "Zipcode", "Country",
)


@dataclass(frozen=True)
class PairComparison:
    """Capture display values in source order, keeping each stable record ID."""

    record_ids: tuple[str, str]
    record_numbers: tuple[int, int]
    evidence: str
    prepared_rows: tuple[tuple[str, str, str], ...]
    original_rows: tuple[tuple[str, str, str], ...]


def build_pair_comparison(
    batch: MemberBatch, source_headers: Sequence[str], candidate: DuplicateCandidate,
) -> PairComparison:
    """Build two aligned comparisons without applying any duplicate choice.

    Source record numbers are one-based positions among the data records,
    independent of the ID order used for backend matching. Show effective
    names and other prepared values, but preserve all original column text,
    including repeated headings and columns ignored during mapping.
    """
    by_id = {record.record_id: (number, record)
             for number, record in enumerate(batch.records, start=1)}
    left_id, right_id = sorted(candidate.record_ids, key=lambda key: by_id[key][0])
    left_number, left_record = by_id[left_id]
    right_number, right_record = by_id[right_id]
    revisions = dict(zip(candidate.record_ids, candidate.record_revisions, strict=True))
    left_preview, right_preview = batch.get_preview(left_id), batch.get_preview(right_id)
    if (left_preview.output_values is None or right_preview.output_values is None
            or left_preview.revision != revisions[left_id]
            or right_preview.revision != revisions[right_id]):
        raise ValueError("These records changed. Review the current pair again.")

    left, right = left_preview.output_values, right_preview.output_values
    # Put the likely evidence first; also show populated values elsewhere in
    # the template so the reviewer can compare other information worth keeping.
    key_fields = (*_KEY_FIELDS, *(field for field in left if is_date_signed_heading(field)))
    if batch.proissub_heading is not None:
        key_fields += (batch.proissub_heading,)
    headings = tuple(dict.fromkeys((*key_fields, *left)))
    prepared = tuple(
        (heading, left[heading], right[heading])
        for heading in headings
        if heading in left and (heading in key_fields or left[heading] or right[heading])
    )
    originals = tuple(
        (f"{index}. {heading!r}", left_value, right_value)
        for index, (heading, left_value, right_value) in enumerate(
            zip(source_headers, left_record.original_source_values,
                right_record.original_source_values, strict=True),
            start=1,
        )
    )
    contacts = ", ".join(_CONTACT_LABELS[code] for code in candidate.matching_contacts)
    petition = _PETITION_LABELS[candidate.petition_status].format(
        heading=(batch.proissub_heading or "PROISSSUB").strip(),
    )
    return PairComparison(
        (left_id, right_id), (left_number, right_number),
        f"Names match. Matching contact: {contacts}. {petition}",
        prepared, originals,
    )


class DuplicateReviewWindow(tk.Toplevel):
    """Review one prepared batch in a window owned by the mapping screen."""

    DEFAULT_SIZE = (980, 720)

    def __init__(
        self, parent: tk.Misc, batch: MemberBatch, source_headers: Sequence[str], *,
        on_change: Callable[[], None], on_continue: Callable[[], None],
    ) -> None:
        """Create the comparison and decision controls for the existing batch."""
        super().__init__(parent)
        self.title("Review possible duplicates")
        self.minsize(740, 585)
        self.transient(parent.winfo_toplevel())
        self._batch = batch
        self._source_headers = tuple(source_headers)
        self._on_change = on_change
        self._on_continue = on_continue
        self._record_numbers = {record.record_id: number
                                for number, record in enumerate(batch.records, start=1)}
        self._candidate: DuplicateCandidate | None = None
        self._comparison: PairComparison | None = None
        self._build_widgets()
        self.refresh()

    def _build_widgets(self) -> None:
        """Build the pair selector, comparison tabs, and reversible actions."""
        body = ttk.Frame(self, padding=16, style="Page.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(4, weight=1)
        self._banner = ttk.Frame(body, padding=(16, 12), style="Info.TFrame")
        self._banner.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._progress = ttk.Label(self._banner, style="Info.Heading.TLabel")
        self._progress.pack(anchor="w")
        hint = ttk.Label(body, text="Record numbers follow the order of data records in the source file.",
                         style="Subtitle.TLabel")
        hint.grid(row=1, column=0, sticky="w", pady=(3, 6))
        self._pair_box = ttk.Combobox(body, state="readonly", width=34)
        self._pair_box.grid(row=2, column=0, sticky="w")
        self._pair_box.bind("<<ComboboxSelected>>", self._show_selected_pair)
        self._evidence = ttk.Label(body, wraplength=680, style="Notice.TLabel")
        self._evidence.grid(row=3, column=0, sticky="w", pady=8)

        tabs = ttk.Notebook(body)
        tabs.grid(row=4, column=0, sticky="nsew")
        self._prepared = self._add_comparison_tab(tabs, "Prepared values")
        self._originals = self._add_comparison_tab(tabs, "Original CSV values")

        actions = ttk.Frame(body, style="Page.TFrame")
        actions.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self._keep_both = ttk.Button(actions, text="Keep both", command=lambda: self._decide(None))
        self._keep_left = ttk.Button(actions, command=lambda: self._decide(0))
        self._keep_right = ttk.Button(actions, command=lambda: self._decide(1))
        self._exclude_both_button = ttk.Button(actions, text="Exclude both...", command=self._exclude_both)
        for button in (self._keep_both, self._keep_left, self._keep_right, self._exclude_both_button):
            button.pack(side="left", padx=(0, 8))
        help_label = ttk.Label(
            body, text="Keeping one excludes the other. To reverse a pair decision, select it below and choose Undo.",
            wraplength=680, style="Subtitle.TLabel",
        )
        help_label.grid(row=6, column=0, sticky="w", pady=(4, 8))
        self._pair_widgets = (hint, self._pair_box, tabs, actions, help_label)

        self._completion = ttk.LabelFrame(body, text="Next step", padding=16)
        self._completion.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        self._completion_message = ttk.Label(self._completion, wraplength=650)
        self._completion_message.pack(anchor="w")
        self._continue_button = ttk.Button(self._completion, command=self._on_continue, style=PRIMARY_BUTTON)
        self._continue_button.pack(anchor="w", pady=(10, 0))

        history = ttk.LabelFrame(body, text="Decisions for this batch", padding=8)
        history.grid(row=7, column=0, sticky="ew")
        history.columnconfigure(0, weight=1)
        self._history = ttk.Treeview(history, columns=("pair", "choice"),
                                     show="headings", selectmode="browse", height=3)
        self._history.heading("pair", text="Records compared")
        self._history.heading("choice", text="Decision")
        self._history.column("pair", width=190, stretch=False)
        self._history.column("choice", width=340)
        self._history.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(history, orient="vertical", command=self._history.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._history.configure(yscrollcommand=scroll.set)
        self._history.bind("<<TreeviewSelect>>", self._update_undo_button)
        self._undo_button = ttk.Button(history, text="Undo selected decision", command=self._undo)
        self._undo_button.grid(row=0, column=2, sticky="n", padx=(8, 0))
        self._history_reason = ScrolledText(history, width=1, height=2, wrap="word", state="disabled")
        style_text(self._history_reason)
        self._history_reason.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self._history_reason.grid_remove()
        ttk.Button(body, text="Close review", command=self.destroy).grid(
            row=8, column=0, sticky="e", pady=(10, 0)
        )

    @staticmethod
    def _add_comparison_tab(
        notebook: ttk.Notebook, title: str,
    ) -> tuple[tuple[ttk.Label, ScrolledText], tuple[ttk.Label, ScrolledText]]:
        """Give each record its own scrollable, read-only comparison pane."""
        page = ttk.Frame(notebook, padding=8)
        notebook.add(page, text=title)
        page.rowconfigure(1, weight=1)
        panes = []
        for column in range(2):
            page.columnconfigure(column, weight=1, uniform="records")
            label = ttk.Label(page, style="Strong.TLabel")
            label.grid(row=0, column=column, sticky="w", padx=4, pady=(0, 5))
            text = ScrolledText(page, width=1, height=6, wrap="word", state="disabled")
            style_text(text)
            text.tag_configure("heading", font=ttk.Style(page).lookup("Strong.TLabel", "font"))
            text.grid(row=1, column=column, sticky="nsew", padx=4)
            panes.append((label, text))
        return panes[0], panes[1]

    def _source_pair(self, record_ids: tuple[str, str]) -> tuple[int, int]:
        """Use source order for labels rather than the backend's ID order."""
        left, right = (self._record_numbers[record_id] for record_id in record_ids)
        return min(left, right), max(left, right)

    def _pair_label(self, record_ids: tuple[str, str]) -> str:
        left, right = self._source_pair(record_ids)
        return f"Records {left} and {right}"

    def refresh(self, *, preferred_pair: tuple[str, str] | None = None) -> None:
        """Refresh the pending queue and decision history from the workflow."""
        if preferred_pair is None and self._candidate is not None:
            preferred_pair = self._candidate.record_ids
        self._candidates = sorted(self._batch.get_duplicate_candidates(),
                                  key=lambda candidate: self._source_pair(candidate.record_ids))
        self._pair_box.configure(values=[self._pair_label(pair.record_ids) for pair in self._candidates])
        if self._candidates:
            self._banner.configure(style="Info.TFrame")
            self._progress.configure(style="Info.Heading.TLabel")
            self._completion.grid_remove()
            for widget in self._pair_widgets:
                widget.grid()
            index = next((i for i, pair in enumerate(self._candidates)
                          if pair.record_ids == preferred_pair), 0)
            self._pair_box.state(["!disabled"])
            self._pair_box.current(index)
            self._progress.configure(text=f"Possible duplicate pairs remaining: {len(self._candidates)}")
        else:
            self._banner.configure(style="Success.TFrame")
            self._progress.configure(style="Success.Heading.TLabel")
            for widget in self._pair_widgets:
                widget.grid_remove()
            self._completion.grid()
            self._pair_box.set("")
            self._pair_box.state(["disabled"])
            count = len(self._batch.get_correction_records())
            self._progress.configure(text="Duplicate review complete")
            self._evidence.configure(text=f"Records ready for correction review: {count}.")
            self._show_completion(count)
        self._show_selected_pair()

        self._decisions = sorted(self._batch.get_duplicate_decisions(),
                                 key=lambda decision: self._source_pair(decision.record_ids))
        for item in self._history.get_children():
            self._history.delete(item)
        for index, decision in enumerate(self._decisions):
            if isinstance(decision, ExcludeBothDecision):
                if len(decision.excluded_record_ids) == 2:
                    choice = "Both records excluded"
                else:
                    remaining = self._record_numbers[decision.excluded_record_ids[0]]
                    choice = f"Pair exclusion remains on record {remaining}"
                choice += f" — {' '.join(decision.reason.split())}"
            elif decision.excluded_record_id is None:
                choice = "Keep both"
            else:
                kept = self._record_numbers[decision.kept_record_id]
                excluded = self._record_numbers[decision.excluded_record_id]
                choice = f"Keep record {kept}; exclude record {excluded}"
            self._history.insert("", "end", iid=str(index),
                                 values=(self._pair_label(decision.record_ids), choice))
        self._update_undo_button()

    def _show_completion(self, included_count: int) -> None:
        """Offer a useful handoff even when there are no included records."""
        if included_count:
            text = "All duplicate pairs are resolved. Check any flagged fields or inspect the included records."
            button = "Continue to field review"
        elif any(record.confirmed_duplicate_of is None for record in self._batch.records):
            text = "No records are included. Review excluded records to see why or restore a record."
            button = "Review excluded records"
        else:
            text = "There are no records to review. Close this window and choose another source file."
            button = ""
        self._completion_message.configure(text=text)
        if button:
            self._continue_button.configure(text=button)
            self._continue_button.pack(anchor="w", pady=(10, 0))
        else:
            self._continue_button.pack_forget()

    def _show_selected_pair(self, _event: tk.Event | None = None) -> None:
        """Show both sides of the current candidate and label their actions."""
        index = self._pair_box.current()
        self._candidate = None
        self._comparison = None
        if 0 <= index < len(self._candidates):
            candidate = self._candidates[index]
            try:
                self._comparison = build_pair_comparison(self._batch, self._source_headers, candidate)
            except ValueError as error:
                self._evidence.configure(text=str(error))
            else:
                self._candidate = candidate
                self._evidence.configure(text=self._comparison.evidence)

        for panes, original in ((self._prepared, False), (self._originals, True)):
            for side, (label, text) in enumerate(panes):
                text.configure(state="normal")
                text.delete("1.0", "end")
                if self._comparison is None:
                    label.configure(text="")
                else:
                    label.configure(text=f"Record {self._comparison.record_numbers[side]}")
                    rows = self._comparison.original_rows if original else self._comparison.prepared_rows
                    for heading, left, right in rows:
                        value = (left, right)[side]
                        if not value:
                            display = "(blank)"
                        elif original or not value.isprintable():
                            display = repr(value)
                        else:
                            display = value
                        text.insert("end", f"{heading}: ", "heading")
                        text.insert("end", f"{display}\n")
                text.configure(state="disabled")
                text.yview_moveto(0)

        for side, button in enumerate((self._keep_left, self._keep_right)):
            if self._comparison is None:
                button.configure(text=f"Keep {'left' if side == 0 else 'right'} record only")
            else:
                button.configure(text=f"Keep record {self._comparison.record_numbers[side]} only")
        for button in (self._keep_both, self._keep_left, self._keep_right, self._exclude_both_button):
            button.state(["!disabled"] if self._candidate is not None else ["disabled"])

    def _decide(self, side: int | None) -> None:
        """Apply the displayed candidate and chosen ID, never a row position."""
        candidate, comparison = self._candidate, self._comparison
        if candidate is None or comparison is None:
            return
        try:
            if side is None:
                self._batch.keep_both(candidate)
            else:
                self._batch.confirm_duplicate(candidate, keep_record_id=comparison.record_ids[side])
        except ValueError as error:
            messagebox.showerror("Could not apply decision", str(error), parent=self)
        self.refresh()
        self._on_change()

    def _exclude_both(self) -> None:
        """Require an explicit reason before excluding both displayed rows."""
        candidate = self._candidate
        if candidate is None:
            return
        reason = simpledialog.askstring(
            "Exclude both records",
            f"Exclude {self._pair_label(candidate.record_ids).lower()} from the CSV. Enter a reason:",
            parent=self,
        )
        if reason is None:
            return
        try:
            self._batch.exclude_both(candidate, reason)
        except ValueError as error:
            messagebox.showerror("Could not exclude both records", str(error), parent=self)
        self.refresh()
        self._on_change()

    def _update_undo_button(self, _event: tk.Event | None = None) -> None:
        selection = self._history.selection()
        decision = self._decisions[int(selection[0])] if selection else None
        self._undo_button.state(["!disabled"] if decision is not None else ["disabled"])
        if isinstance(decision, ExcludeBothDecision):
            # The compact history column may clip a long reason.
            self._history_reason.configure(state="normal")
            self._history_reason.delete("1.0", "end")
            self._history_reason.insert("1.0", f"Reason: {decision.reason}")
            self._history_reason.configure(state="disabled")
            self._history_reason.grid()
        else:
            self._history_reason.grid_remove()

    def _undo(self) -> None:
        """Undo exactly the selected history item and return to its pair."""
        selection = self._history.selection()
        if not selection:
            return
        pair = self._decisions[int(selection[0])].record_ids
        try:
            self._batch.undo_duplicate_decision(pair)
        except ValueError as error:
            messagebox.showerror("Could not undo decision", str(error), parent=self)
        self.refresh(preferred_pair=pair)
        self._on_change()
