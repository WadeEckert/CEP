"""Review flags, correct fields, and accept prepared CSV values.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Show original, working, and prepared values without mixing them.
Send corrections and review decisions through MemberBatch so validation,
duplicate checks, and export approval all use the same record state.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

from collections.abc import Callable
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from .gui_style import PRIMARY_BUTTON, SURFACE, style_text
from .models import MemberRecord
from .workflow import MemberBatch, RecordPreview


NEEDS_REVIEW = "Needs field review"
INCLUDED = "All included records"
EXCLUDED = "Excluded records"
FLAGGED_FIELDS = "Flagged fields"
ALL_FIELDS = "All fields"


def correction_groups(batch: MemberBatch) -> dict[str, tuple[MemberRecord, ...]]:
    """Build source-ordered lists after the duplicate gate is satisfied.

    Contact-ineligible and manually excluded records can be recovered here.
    Confirmed duplicates must be restored through duplicate review instead.
    """
    included = batch.get_correction_records()
    unreviewed = {preview.record_id for preview in batch.get_unreviewed_records()}
    return {
        NEEDS_REVIEW: tuple(record for record in included if record.record_id in unreviewed),
        INCLUDED: included,
        EXCLUDED: tuple(record for record in batch.records
                        if not record.is_included and record.confirmed_duplicate_of is None),
    }


def _display(value: str) -> str:
    """Make blanks and significant whitespace visible without changing data."""
    if not value:
        return "(blank)"
    return repr(value) if not value.isprintable() or value != value.strip() else value


class FieldEditDialog(simpledialog.Dialog):
    """Edit one literal field, allowing multiline values and intentional blanks."""

    def __init__(self, parent: tk.Misc, heading: str, value: str, *,
                 from_original: bool = False) -> None:
        self._heading = heading
        self._value = value
        self._from_original = from_original
        super().__init__(parent, title="Edit selected field")

    def body(self, master: tk.Misc) -> tk.Text:
        self.configure(background=SURFACE)
        master.configure(background=SURFACE)
        ttk.Label(master, text=self._heading.rstrip(), style="Heading.TLabel").pack(
            anchor="w", padx=10, pady=(8, 4)
        )
        if self._from_original:
            ttk.Label(
                master,
                text="Cleanup left this field blank. The original value is shown so you can edit it.",
                wraplength=360,
                style="Muted.TLabel",
            ).pack(anchor="w", padx=10, pady=(0, 6))
        self._input = tk.Text(master, width=55, height=5, wrap="word")
        style_text(self._input)
        self._input.pack(padx=10, pady=(0, 8))
        self._input.insert("1.0", self._value)
        self._input.mark_set("insert", "end-1c")
        return self._input

    def apply(self) -> None:
        # Exclude Tk's automatic final newline; keep the user's actual text.
        self.result = self._input.get("1.0", "end-1c")

    def buttonbox(self) -> None:
        buttons = ttk.Frame(self, padding=(14, 0, 14, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right")
        ttk.Button(buttons, text="Apply correction", command=self.ok, style=PRIMARY_BUTTON).pack(
            side="right", padx=(0, 8)
        )
        # Enter adds a line in the editor. Escape cancels as in other dialogs.
        self.bind("<Escape>", self.cancel)


class CorrectionReviewWindow(tk.Toplevel):
    """Review the same prepared batch without creating an output file."""

    DEFAULT_SIZE = (1010, 640)

    def __init__(self, parent: tk.Misc, batch: MemberBatch, *, on_change: Callable[[], None],
                 on_return_to_save: Callable[[], None]) -> None:
        super().__init__(parent)
        self.title("Review and correct records")
        self.minsize(760, 575)
        self.transient(parent.winfo_toplevel())
        self._batch = batch
        self._on_change = on_change
        self._on_return_to_save = on_return_to_save
        self._editable = frozenset(batch.editable_fields)
        self._numbers = {record.record_id: i for i, record in enumerate(batch.records, start=1)}
        self._record: MemberRecord | None = None
        self._preview: RecordPreview | None = None
        self._field_keys: tuple[str, ...] = ()
        self._complete = False
        self._build_widgets()
        self.refresh()

    def _build_widgets(self) -> None:
        self._body = body = ttk.Frame(self, padding=16, style="Page.TFrame")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        self._progress = progress = ttk.Frame(body, padding=(16, 12), style="Info.TFrame")
        progress.grid(row=0, column=0, sticky="ew")
        self._summary = ttk.Label(progress, style="Info.Heading.TLabel")
        self._summary.pack(anchor="w")
        self._completion_message = ttk.Label(progress, style="Success.TLabel", wraplength=660)
        self._completion_actions = ttk.Frame(progress, style="Success.TFrame")
        self._return_button = ttk.Button(self._completion_actions, text="Return to save",
                                         command=self._on_return_to_save, style=PRIMARY_BUTTON)
        self._browse_button = ttk.Button(self._completion_actions, text="Browse records",
                                         command=self._toggle_browse)

        self._record_view = records = ttk.Frame(body, style="Page.TFrame")
        records.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        records.columnconfigure(0, weight=1)
        records.rowconfigure(3, weight=1)
        selectors = ttk.Frame(records, style="Page.TFrame")
        selectors.grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(selectors, text="Records:", style="Subtitle.TLabel").pack(side="left")
        self._group_box = ttk.Combobox(selectors, values=(NEEDS_REVIEW, INCLUDED, EXCLUDED),
                                       state="readonly", width=20)
        self._group_box.pack(side="left", padx=(5, 12))
        self._group_box.current(0)
        self._group_box.bind("<<ComboboxSelected>>", self._populate_records)
        ttk.Label(selectors, text="Source record:", style="Subtitle.TLabel").pack(side="left")
        self._record_box = ttk.Combobox(selectors, state="readonly", width=34)
        self._record_box.pack(side="left", padx=5)
        self._record_box.bind("<<ComboboxSelected>>", self._show_record)
        self._next_flagged_button = ttk.Button(selectors, text="Next flagged record", command=self._next_flagged)
        self._next_flagged_button.pack(side="left", padx=(6, 0))

        field_controls = ttk.Frame(records, style="Page.TFrame")
        field_controls.grid(row=1, column=0, sticky="w")
        ttk.Label(field_controls, text="Fields:", style="Subtitle.TLabel").pack(side="left")
        self._field_mode = ttk.Combobox(field_controls, values=(FLAGGED_FIELDS, ALL_FIELDS),
                                        state="readonly", width=17)
        self._field_mode.pack(side="left", padx=5)
        self._field_mode.set(ALL_FIELDS)
        self._field_mode.bind("<<ComboboxSelected>>", self._render_fields)
        self._field_notice = ttk.Label(records, style="Notice.TLabel", wraplength=690)
        self._field_notice.grid(row=2, column=0, sticky="w", pady=(6, 8))

        table = ttk.Frame(records)
        table.grid(row=3, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self._fields = ttk.Treeview(table, columns=("field", "original", "working", "prepared"),
                                    show="headings", selectmode="browse", height=8)
        for key, title in (("field", "Field"), ("original", "Original mapped"),
                           ("working", "Current value"), ("prepared", "Prepared for CSV")):
            self._fields.heading(key, text=title)
            self._fields.column(key, width=190, minwidth=130)
        self._fields.tag_configure("flagged", background="#fff0c7", foreground="#563a0a",
                                   font=ttk.Style(self).lookup("Strong.TLabel", "font"))
        self._fields.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self._fields.yview)
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self._fields.xview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self._fields.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self._fields.bind("<<TreeviewSelect>>", self._show_field)

        self._details = ScrolledText(records, height=6, width=1, wrap="word", state="disabled")
        style_text(self._details)
        self._details.grid(row=4, column=0, sticky="ew", pady=8)
        actions = ttk.Frame(records, style="Page.TFrame")
        actions.grid(row=5, column=0, sticky="ew")
        self._edit_button = ttk.Button(actions, text="Edit selected field...", command=self._edit)
        self._accept_button = ttk.Button(actions, text="Accept prepared values...", command=self._accept)
        self._exclude_button = ttk.Button(actions, text="Exclude record...", command=self._exclude)
        self._restore_button = ttk.Button(actions, text="Restore record", command=self._restore)
        for button in (self._edit_button, self._accept_button, self._exclude_button, self._restore_button):
            button.pack(side="left", padx=(0, 6))
        ttk.Button(body, text="Close review", command=self.destroy).grid(
            row=2, column=0, sticky="e", pady=(10, 0)
        )

    def refresh(self) -> None:
        """Rebuild the lists without retaining a stale review preview."""
        self._editable = frozenset(self._batch.editable_fields)
        previous = self._record.record_id if self._record is not None else None
        was_complete = self._complete
        if self._batch.get_duplicate_candidates():
            self._groups = {key: () for key in (NEEDS_REVIEW, INCLUDED, EXCLUDED)}
            self._complete = False
            self._summary.configure(text="Resolve possible duplicates before continuing corrections.")
        else:
            self._groups = correction_groups(self._batch)
            waiting = len(self._groups[NEEDS_REVIEW])
            self._complete = not waiting and bool(self._groups[INCLUDED])
            if self._complete:
                self._summary.configure(text="Field review complete")
                if not was_complete:
                    self._group_box.set(NEEDS_REVIEW)
            else:
                self._summary.configure(text=(f"Records awaiting field review: {waiting}" if waiting
                                              else "No included records to save"))
        group = self._group_box.get()
        if not self._complete and not self._groups[group]:
            self._group_box.set(next((key for key, records in self._groups.items() if records), group))
        self._populate_records(preferred_id=previous)

    def _toggle_browse(self) -> None:
        """Let the reviewer inspect records without leaving the completed batch."""
        if not self._complete:
            return
        if self._group_box.get() == NEEDS_REVIEW:
            self._group_box.set(INCLUDED)
            self._populate_records()
            self._group_box.focus_set()
        else:
            self._group_box.set(NEEDS_REVIEW)
            self._populate_records()
            self._return_button.focus_set()

    def _render_completion(self) -> None:
        """Show a finish state instead of an empty table when the queue is clear."""
        tone = "Success" if self._complete else "Info"
        self._progress.configure(style=f"{tone}.TFrame")
        self._summary.configure(style=f"{tone}.Heading.TLabel")
        if self._complete:
            count = len(self._groups[INCLUDED])
            self._completion_message.configure(text=(
                "No included records are waiting for review.\n"
                f"{count} {'record is' if count == 1 else 'records are'} included in this batch. "
                "Return to the main window to save the CSV."
            ))
            self._completion_message.pack(anchor="w", pady=(4, 10))
            self._completion_actions.pack(anchor="w")
            self._return_button.pack(side="left")
            self._browse_button.pack(side="left", padx=(8, 0))
        else:
            self._completion_message.pack_forget()
            self._completion_actions.pack_forget()
            self._return_button.pack_forget()
            self._browse_button.pack_forget()
        completion_only = self._complete and self._group_box.get() == NEEDS_REVIEW
        self._body.rowconfigure(0, weight=int(completion_only))
        self._body.rowconfigure(1, weight=int(not completion_only))
        self._progress.configure(padding=(24, 22) if completion_only else (16, 12))
        self._progress.grid_configure(padx=32 if completion_only else 0)
        if completion_only:
            self._record_view.grid_remove()
            self._browse_button.configure(text="Browse records")
        else:
            self._record_view.grid()
            self._browse_button.configure(text="Back to completion")

    def _populate_records(self, _event: tk.Event | None = None, *, preferred_id: str | None = None) -> None:
        self._records = self._groups[self._group_box.get()]
        self._record_box.configure(values=[self._record_label(row) for row in self._records])
        if self._records:
            index = next((i for i, row in enumerate(self._records) if row.record_id == preferred_id), 0)
            self._record_box.state(["!disabled"])
            self._record_box.current(index)
        else:
            self._record_box.set("")
            self._record_box.state(["disabled"])
        self._show_record()
        self._render_completion()
        if _event is not None and self._complete and not self._records:
            self._return_button.focus_set()

    def _record_label(self, record: MemberRecord) -> str:
        name = " ".join(" ".join(record.working_values.get(field, "").split())
                        for field in ("First Name", "Last Name")).strip()
        name = (name[:23] + "…") if len(name) > 24 else name
        count = len(record.issues)
        return f"Record {self._numbers[record.record_id]} — {name or 'No name'} — {count} flag{'s' if count != 1 else ''}"

    def _next_flagged(self) -> None:
        """Move through the unreviewed records in source order, wrapping at the end."""
        pending = self._groups[NEEDS_REVIEW]
        if not pending:
            return
        current = self._numbers[self._record.record_id] if self._record is not None else 0
        next_record = next((row for row in pending if self._numbers[row.record_id] > current), pending[0])
        self._group_box.set(NEEDS_REVIEW)
        self._populate_records(preferred_id=next_record.record_id)

    def _show_record(self, _event: tk.Event | None = None) -> None:
        previous = self._record
        had_field_flags = bool(self._flagged_fields())
        preferred_field = self._selected_field()
        index = self._record_box.current()
        self._record = self._records[index] if 0 <= index < len(self._records) else None
        self._preview = self._batch.get_preview(self._record.record_id) if self._record is not None else None
        has_field_flags = bool(self._flagged_fields())
        if self._record is not previous or has_field_flags != had_field_flags:
            self._field_mode.set(FLAGGED_FIELDS if has_field_flags else ALL_FIELDS)
        self._field_mode.state(["!disabled"] if has_field_flags else ["disabled"])
        others_waiting = any(row is not self._record for row in self._groups[NEEDS_REVIEW])
        self._next_flagged_button.state(["!disabled"] if others_waiting else ["disabled"])
        self._render_fields(preferred_field=preferred_field if self._record is previous else None)

    def _flagged_fields(self) -> tuple[str, ...]:
        """Keep a distinct, ordered list of exact headings with field issues."""
        if self._preview is None:
            return ()
        return tuple(dict.fromkeys(issue.field_name for issue in self._preview.issues
                                   if issue.field_name is not None))

    def _render_fields(self, _event: tk.Event | None = None, *, preferred_field: str | None = None) -> None:
        if _event is not None:
            preferred_field = self._selected_field()
        self._field_keys = ()
        for item in self._fields.get_children():
            self._fields.delete(item)
        record, preview = self._record, self._preview
        flagged = self._flagged_fields()
        notice = "No records in this view."
        if record is not None and preview is not None:
            accepted = preview.is_included and record not in self._groups[NEEDS_REVIEW]
            # Keep flagged fields prominent while preserving exact keys for editing.
            self._field_keys = (flagged if self._field_mode.get() == FLAGGED_FIELDS
                                else tuple(sorted(record.working_values, key=lambda field: field not in flagged)))
            if flagged:
                labels = ", ".join(field.rstrip() for field in flagged)
                kind = "Accepted flags" if accepted else "Flagged fields"
                notice = f"{kind} ({len(flagged)}): {labels}"
            elif preview.issues or preview.exclusion_reasons:
                notice = "This record has a record-level issue. See the details below."
            else:
                notice = "No fields are flagged for this record."
            for i, field in enumerate(self._field_keys):
                prepared = "(excluded)" if preview.output_values is None else _display(preview.output_values[field])
                marker = ("Accepted: " if accepted else "Review: ") if field in flagged else ""
                self._fields.insert("", "end", iid=str(i), values=(
                    marker + field.rstrip(), _display(record.original_mapped_values[field]),
                    _display(record.working_values[field]), prepared,
                ), tags=("flagged",) if field in flagged else ())
            if self._field_keys:
                selected = str(self._field_keys.index(preferred_field)) if preferred_field in self._field_keys else "0"
                self._fields.selection_set(selected)
                self._fields.see(selected)
        self._field_notice.configure(text=notice)
        self._show_field()

    def _selected_field(self) -> str | None:
        selected = self._fields.selection()
        return self._field_keys[int(selected[0])] if selected else None

    def _show_field(self, _event: tk.Event | None = None) -> None:
        record, preview, field = self._record, self._preview, self._selected_field()
        lines: list[str] = []
        waiting = record is not None and any(row.record_id == record.record_id for row in self._groups[NEEDS_REVIEW])
        if record is not None and preview is not None:
            if preview.manual_exclusion_reason:
                lines.append(f"Manually excluded: {preview.manual_exclusion_reason}")
            if preview.exclusion_reasons:
                lines.extend(preview.exclusion_reasons)
            if preview.is_included and preview.issues and not waiting:
                lines.append("Prepared values accepted for the current flags.")
            for issue in preview.issues:
                if issue.field_name is not None and issue.field_name != field:
                    continue
                label = issue.field_name.rstrip() if issue.field_name is not None else "Record"
                lines.append(f"{label}: {issue.message}")
            if field is not None:
                lines.extend((
                    "", f"{field.rstrip()}:",
                    f"Original: {_display(record.original_mapped_values[field])}",
                    f"Current: {_display(record.working_values[field])}",
                    "Prepared: " + ("(excluded)" if preview.output_values is None
                                    else _display(preview.output_values[field])),
                ))
                if field == "Street" and record.original_unit_value:
                    lines.append(f"Original separate unit: {_display(record.original_unit_value)}")
                if field == self._batch.proissub_heading and field not in self._editable:
                    lines.append("Set for every record. To change it, use Batch petition group on the main screen.")
        self._details.configure(state="normal")
        self._details.delete("1.0", "end")
        self._details.insert("1.0", "\n".join(lines) or "No records in this view.")
        self._details.yview_moveto(0)
        self._details.configure(state="disabled")
        for button, enabled in (
            (self._edit_button, record is not None and field in self._editable),
            (self._accept_button, waiting),
            (self._exclude_button, preview is not None and preview.is_included),
            (self._restore_button, preview is not None and preview.manual_exclusion_reason is not None),
        ):
            button.state(["!disabled"] if enabled else ["disabled"])

    def _apply(self, action: Callable[[], None]) -> None:
        """Apply one backend decision, then refresh even if it was rejected."""
        try:
            action()
        except ValueError as error:
            messagebox.showerror("Could not update record", str(error), parent=self)
        self.refresh()
        self._on_change()
        if self.winfo_exists() and self._complete and self._group_box.get() == NEEDS_REVIEW:
            self._return_button.focus_set()

    def _edit(self) -> None:
        record, field = self._record, self._selected_field()
        if record is None or field not in self._editable:
            return
        current = record.working_values[field]
        original = record.original_mapped_values[field]
        # Automatic cleanup may clear a value that the reviewer can repair.
        # A deliberate blank correction should stay blank when reopened.
        from_original = not current and field not in record.manual_overrides and bool(original.strip())
        value = FieldEditDialog(self, field, original if from_original else current,
                                from_original=from_original).result
        # Submitting a blank or the same value is still a deliberate decision.
        if value is not None:
            self._apply(lambda: self._batch.edit_field(record.record_id, field, value))

    def _accept(self) -> None:
        preview = self._preview
        if preview is not None and preview.is_included and messagebox.askyesno(
            "Accept prepared values",
            "Use the prepared CSV values shown for this record? Any blanks and remaining flags will stay as shown.",
            parent=self,
        ):
            self._apply(lambda: self._batch.acknowledge_record(preview))

    def _exclude(self) -> None:
        preview = self._preview
        if preview is None or not preview.is_included:
            return
        reason = simpledialog.askstring("Exclude record", "Why should this record be excluded?", parent=self)
        if reason is not None:
            self._apply(lambda: self._batch.exclude_record(preview.record_id, reason))

    def _restore(self) -> None:
        preview = self._preview
        if preview is not None and preview.manual_exclusion_reason is not None:
            self._apply(lambda: self._batch.restore_record(preview.record_id))
