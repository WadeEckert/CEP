"""Batch correction, review acknowledgment, and CSV export coordination.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Connect mapping, cleanup, duplicate confirmation, corrections,
immutable output previews, and final review gates for one source file.
Preserve originals and write only freshly evaluated template-only values.
The GUI supplies file paths, mappings, edits, and explicit review choices.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from types import MappingProxyType

from .cleanup import (
    assemble_street, clean_city, clean_country, clean_date_signed, clean_email,
    clean_name, clean_phone, clean_state, clean_street, clean_zipcode,
)
from .csv_io import load_template, read_source_csv, write_output_csv
from .duplicates import DuplicateReview
from .mapping import map_record_with_unit, validate_mapping
from .models import DuplicateCandidate, DuplicateDecision, MemberRecord, ReviewIssue, resolve_proissub_heading
from .validation import evaluate_record, is_date_signed_heading


_FIELD_CLEANERS = {
    "First Name": clean_name, "Last Name": clean_name,
    "Primary Cell/Mobile Phone": clean_phone, "Email": clean_email,
    "City": clean_city, "State": clean_state,
    "Zipcode": clean_zipcode, "Country": clean_country,
}
_DERIVED_FIELDS = frozenset({
    "Address Contact Status", "PhoneDisclaimeredYN", "Account Classification",
})


def _format_value(
    name: str, value: str, reference_date: date, *, manual_street: bool = False
) -> str:
    """Format known fields; copy all other mapped values exactly as supplied."""
    if name == "Street":
        return clean_street(value, preserve_name=manual_street)
    if is_date_signed_heading(name):
        return clean_date_signed(value, reference_date=reference_date)
    cleaner = _FIELD_CLEANERS.get(name)
    return cleaner(value) if cleaner is not None else value


def clean_record(record: MemberRecord, *, reference_date: date) -> None:
    """Apply automatic cleanup after originals have been captured by the model."""
    cleaned = {
        name: _format_value(name, value, reference_date)
        for name, value in record.working_values.items()
    }
    if "Street" in cleaned:
        cleaned["Street"] = assemble_street(
            record.working_values["Street"], record.original_unit_value
        )
    record.apply_cleaned_values(cleaned)


@dataclass(frozen=True)
class RecordPreview:
    """Capture exactly which output and issues the reviewer was shown.

    output_values is None for an excluded record. Acknowledgment accepts a
    current included preview, including safe blanks/BAD_ADDRESS when issues
    remain. It does not make invalid information usable or change field flags.
    """

    record_id: str
    revision: int
    output_values: Mapping[str, str] | None
    issues: tuple[ReviewIssue, ...]
    exclusion_reasons: tuple[str, ...]
    manual_exclusion_reason: str | None
    confirmed_duplicate_of: str | None

    def __post_init__(self) -> None:
        """Detach the output snapshot and prevent later caller mutation."""
        if self.output_values is not None:
            object.__setattr__(
                self, "output_values", MappingProxyType(dict(self.output_values))
            )

    @property
    def is_included(self) -> bool:
        """Report inclusion in this snapshot, not permanent export approval."""
        return self.output_values is not None


@dataclass(frozen=True)
class ExcludeBothDecision:
    """A pair decision and the manual exclusions it still owns."""

    record_ids: tuple[str, str]
    reason: str
    excluded_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReviewState:
    """Capture review work so the GUI can tell what would be lost."""

    records: tuple[tuple[int, str | None], ...]
    decisions: tuple[DuplicateDecision | ExcludeBothDecision, ...]
    acknowledged: frozenset[str]
    petition_group: str | None


class MemberBatch:
    """Coordinate one mapped batch before the GUI requests a final CSV.

    Create this before duplicate choices are assigned. Inputs are raw mapped
    MemberRecords with preserved source snapshots. The constructor cleans and
    evaluates them; one shared reference date applies for the entire batch.
    """

    def __init__(
        self, records: Sequence[MemberRecord], template_headers: Sequence[str], *,
        reference_date: date | None = None,
        protected_paths: Sequence[str | Path] = (),
    ) -> None:
        """Validate schema/identity, clean inputs, and start duplicate review.

        protected_paths lists source/template filenames that Save As must
        not reuse, even if the original file later disappears. from_csv()
        registers both automatically. All records must use the template's
        exact field names; output order follows template_headers.
        """
        if reference_date is not None and type(reference_date) is not date:
            raise TypeError("reference_date must be a datetime.date value.")
        headers = tuple(template_headers)
        if (not headers or any(not isinstance(name, str) or not name.strip() for name in headers)
                or len(set(headers)) != len(headers)):
            raise ValueError("Template headings must be present, nonblank, and unique.")
        members = tuple(records)
        if len({record.record_id for record in members}) != len(members):
            raise ValueError("Each batch record must have a unique stable ID.")
        if any(set(record.working_values) != set(headers) for record in members):
            raise ValueError("Every record must contain exactly the template fields.")
        if any(record.confirmed_duplicate_of is not None for record in members):
            raise ValueError("Create the batch before assigning duplicate exclusions.")

        self._headers = headers
        self._records = members
        self._by_id = {record.record_id: record for record in members}
        self._reference_date = reference_date if reference_date is not None else date.today()
        self._protected_paths = frozenset(Path(path).resolve() for path in protected_paths)
        self._acknowledged: dict[str, RecordPreview] = {}
        self._previews: dict[str, RecordPreview] = {}
        self._pair_exclusions: dict[tuple[str, str], ExcludeBothDecision] = {}
        self._proissub_heading = resolve_proissub_heading(self._headers)
        self._batch_proisssub: str | None = None
        for record in members:
            clean_record(record, reference_date=self._reference_date)
        self._duplicates = DuplicateReview(members, reference_date=self._reference_date)
        self._sync()

    @classmethod
    def from_csv(
        cls, source_path: str | Path, template_path: str | Path,
        mapping: dict[int, str | None], *, unit_source_index: int | None = None,
        reference_date: date | None = None,
    ) -> "MemberBatch":
        """Read/map a file, preserving raw records and protecting both input paths."""
        template = load_template(template_path)
        headers, rows = read_source_csv(source_path)
        validate_mapping(headers, template, mapping, unit_source_index=unit_source_index)
        records = []
        for row in rows:
            mapped, unit = map_record_with_unit(
                row, headers, template, mapping, unit_source_index=unit_source_index
            )
            records.append(MemberRecord(row, mapped, unit))
        return cls(records, template, reference_date=reference_date,
                   protected_paths=(source_path, template_path))

    @property
    def records(self) -> tuple[MemberRecord, ...]:
        """Expose fixed batch membership for source/exclusion inspection."""
        return self._records

    def _sync(self) -> tuple[DuplicateCandidate, ...]:
        """Revalidate the batch and discard acknowledgments whose previews changed."""
        pending = self._duplicates.refresh()
        previews = {}
        for record in self._records:
            values = evaluate_record(record, reference_date=self._reference_date)
            if values is not None:
                # Keep canonical output formatting separate from literal edit inputs.
                values = {
                    name: _format_value(name, values[name], self._reference_date,
                                        manual_street=True)
                    for name in self._headers
                }
            previews[record.record_id] = RecordPreview(
                record.record_id, record.revision, values, tuple(record.issues),
                tuple(record.exclusion_reasons), record.manual_exclusion_reason,
                record.confirmed_duplicate_of,
            )
        self._previews = previews
        self._acknowledged = {
            record_id: saved for record_id, saved in self._acknowledged.items()
            if previews[record_id].is_included and previews[record_id] == saved
        }
        return pending

    def get_duplicate_candidates(self) -> tuple[DuplicateCandidate, ...]:
        """Return current pairs before entry or return to correction review."""
        return self._sync()

    def get_duplicate_decisions(self) -> tuple[DuplicateDecision | ExcludeBothDecision, ...]:
        """Expose current choices for the GUI's decision list and Undo controls."""
        self._sync()
        return (*self._duplicates.get_decisions(), *self._pair_exclusions.values())

    def review_state(self) -> ReviewState:
        """Snapshot current edits and choices, even while review is incomplete."""
        decisions = self.get_duplicate_decisions()
        return ReviewState(
            tuple((record.revision, record.manual_exclusion_reason) for record in self._records),
            decisions, frozenset(self._acknowledged), self._batch_proisssub,
        )

    def keep_both(self, candidate: DuplicateCandidate) -> DuplicateDecision:
        """Apply an explicit distinct-record choice through the duplicate controller."""
        decision = self._duplicates.keep_both(candidate)
        self._sync()
        return decision

    def confirm_duplicate(
        self, candidate: DuplicateCandidate, *, keep_record_id: str
    ) -> DuplicateDecision:
        """Apply an explicit keeper choice and refresh included previews."""
        decision = self._duplicates.confirm_duplicate(candidate, keep_record_id=keep_record_id)
        self._sync()
        return decision

    def exclude_both(self, candidate: DuplicateCandidate, reason: str) -> None:
        """Manually exclude both members of a currently pending pair."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Enter a reason for excluding both records.")
        if candidate not in self._sync():
            raise ValueError("This pair changed. Review the current duplicate candidates.")

        reason = reason.strip()
        decision = ExcludeBothDecision(candidate.record_ids, reason, candidate.record_ids)
        # Mark both before refreshing so neither can become the other's fallback.
        for record_id in candidate.record_ids:
            self._by_id[record_id].manual_exclusion_reason = reason
        self._pair_exclusions[decision.record_ids] = decision
        self._sync()

    def undo_duplicate_decision(self, record_ids: tuple[str, str]) -> None:
        """Reopen one duplicate choice before further corrections or export."""
        left, right = sorted(record_ids)
        pair_exclusion = self._pair_exclusions.pop((left, right), None)
        if pair_exclusion is None:
            self._duplicates.undo_decision(record_ids)
        else:
            for record_id in pair_exclusion.excluded_record_ids:
                self._by_id[record_id].manual_exclusion_reason = None
        self._sync()

    def _detach_pair_exclusion(self, record_id: str) -> None:
        """Give an individual decision precedence over an older pair exclusion."""
        for pair, decision in tuple(self._pair_exclusions.items()):
            if record_id not in decision.excluded_record_ids:
                continue
            remaining = tuple(other for other in decision.excluded_record_ids if other != record_id)
            if remaining:
                self._pair_exclusions[pair] = replace(decision, excluded_record_ids=remaining)
            else:
                del self._pair_exclusions[pair]
            return

    def _require_duplicate_review(self) -> None:
        if self._sync():
            raise ValueError("Resolve duplicate candidates before corrections or export.")

    @property
    def editable_fields(self) -> tuple[str, ...]:
        """Return exact headings for fields the reviewer can correct."""
        return tuple(field for field in self._headers if field not in _DERIVED_FIELDS
                     and not (field == self._proissub_heading and self._batch_proisssub is not None))

    @property
    def proissub_heading(self) -> str | None:
        """Return the exact destination key for the petition group."""
        return self._proissub_heading

    @property
    def supports_batch_proisssub(self) -> bool:
        """Check for the exact petition heading without changing the template."""
        return self._proissub_heading is not None

    @property
    def batch_proisssub(self) -> str | None:
        """Return the last applied value; None means there is no batch override."""
        return self._batch_proisssub

    def set_batch_proisssub(self, value: str) -> None:
        """Apply one petition value to every record, including excluded rows."""
        heading = self._proissub_heading
        if heading is None:
            raise ValueError("The template needs a PROISSUB or PROISSSUB column.")
        if not isinstance(value, str):
            raise TypeError("Enter the PROISSSUB value as text.")
        value = value.strip()
        self._batch_proisssub = value
        for record in self._records:
            # Changed petition values may reopen prior duplicate decisions.
            if record.working_values[heading] != value:
                record.edit_field(heading, value)
        self._sync()

    def get_correction_records(self) -> tuple[MemberRecord, ...]:
        """Return included rows after the duplicate-confirmation gate is satisfied."""
        self._require_duplicate_review()
        return tuple(record for record in self._records if record.is_included)

    def get_preview(self, record_id: str) -> RecordPreview:
        """Return a fresh immutable snapshot; excluded rows remain inspectable."""
        self._sync()
        return self._previews[record_id]

    def edit_field(self, record_id: str, field_name: str, value: str) -> None:
        """Normalize a correction, preserve failed nonblank input, and revalidate.

        A failed cleanup must not become an intentional empty override. Keep
        that entered text for a format flag and safe blank output instead.
        Street corrections preserve literal directional/name wording.
        """
        self._require_duplicate_review()
        record = self._by_id[record_id]
        if field_name not in record.working_values:
            raise KeyError(field_name)
        if field_name in _DERIVED_FIELDS:
            raise ValueError("This field is calculated by the program.")
        if field_name == self._proissub_heading and self._batch_proisssub is not None:
            raise ValueError("Change the batch petition group on the main screen.")
        if not isinstance(value, str):
            raise TypeError("A field correction must contain text.")
        normalized = _format_value(field_name, value, self._reference_date, manual_street=True)
        replacement = value if value.strip() and not normalized else normalized
        record.edit_field(field_name, replacement)
        self._sync()

    def exclude_record(self, record_id: str, reason: str) -> None:
        """Preserve an explicit exclusion reason and recheck dependent choices."""
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Enter a reason for excluding the record.")
        self._detach_pair_exclusion(record_id)
        self._by_id[record_id].manual_exclusion_reason = reason.strip()
        self._sync()

    def restore_record(self, record_id: str) -> None:
        """Clear a manual exclusion; contact and duplicate requirements still apply."""
        self._detach_pair_exclusion(record_id)
        self._by_id[record_id].manual_exclusion_reason = None
        self._sync()

    def acknowledge_record(self, preview: RecordPreview) -> None:
        """Accept the exact current safe output shown for an included flagged row."""
        self._require_duplicate_review()
        current = self._previews[preview.record_id]
        if preview != current:
            raise ValueError("This preview changed. Review the current record again.")
        if not current.is_included:
            raise ValueError("Excluded records cannot be acknowledged for export.")
        self._acknowledged[preview.record_id] = current

    def get_unreviewed_records(self) -> tuple[RecordPreview, ...]:
        """Return included flagged previews without a current acknowledgment."""
        self._require_duplicate_review()
        return tuple(
            preview for record_id, preview in self._previews.items()
            if preview.is_included and preview.issues and record_id not in self._acknowledged
        )

    def prepare_export(self) -> list[dict[str, str]]:
        """Build fresh exact-template rows after duplicate and field-review gates."""
        if self.get_unreviewed_records():
            raise ValueError("Review or correct the remaining flagged records before export.")
        return [dict(preview.output_values) for preview in self._previews.values()
                if preview.output_values is not None]

    def save_csv(self, output_path: str | Path) -> Path:
        """Write reviewed, nonempty output to a new file, protecting input paths."""
        path = Path(output_path)
        if path.resolve() in self._protected_paths:
            raise ValueError("Choose an output path different from the source and template.")
        values = self.prepare_export()
        if not values:
            raise ValueError("No included records are available to save.")
        return write_output_csv(path, list(self._headers), values)
