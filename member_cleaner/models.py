"""Record and review-issue models for the Member CSV Cleaner.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Preserve original CSV information while tracking working values,
manual corrections, review issues, and record-level inclusion decisions.
Represent evaluations, duplicate candidates, and review choices as immutable
results. Track input revisions so stale duplicate choices can be reopened.
Create each MemberRecord after mapping and before automatic cleanup.
Validation supplies eligibility and issues; the batch controller manages
duplicate relationships across records. CSV output receives a template-only
dictionary built from working values and validated derived values, keeping
review metadata outside the template fields.
AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

from collections.abc import Mapping, Sequence
from dataclasses import InitVar, dataclass, field
from types import MappingProxyType
from uuid import uuid4


def resolve_proissub_heading(headers: Sequence[str]) -> str | None:
    """Recognize the petition column, retaining its exact template spelling."""
    matches = [name for name in headers if name.strip().casefold() in {"proissub", "proisssub"}]
    if len(matches) > 1:
        raise ValueError("The template has more than one PROISSUB or PROISSSUB column. Keep just one.")
    return matches[0] if matches else None


@dataclass(frozen=True)
class ReviewIssue:
    """Describe one current issue without modifying the affected record.

    Attributes:
        field_name: Exact template heading, or None for a whole-record issue.
        code: Stable program-facing label, such as UNIT_CONFLICT.
        message: Plain-English explanation for the review screen.

    An issue is immutable. Validation replaces the current issue list after
    corrections instead of changing an existing issue's meaning in place.
    """

    field_name: str | None
    code: str
    message: str


@dataclass(frozen=True)
class NameContactResult:
    """Describe one name/contact decision without replacing editable names.

    Attributes:
        first_name: Cleaned first name, or the proposed Anonymous fallback.
        last_name: Cleaned last name, or the proposed Donor fallback.
        used_anonymous_fallback: Whether this evaluation substituted names.
        exclusion_reasons: Immutable reasons this part of evaluation failed.

    The future evaluator/review/export workflow consumes this result while
    MemberRecord retains the actual cleaned or manually corrected names.
    Generated placeholders must not become input to later name corrections.
    Passing these rules alone does not settle other review/export checks.
    """

    first_name: str
    last_name: str
    used_anonymous_fallback: bool
    exclusion_reasons: tuple[str, ...] = ()

    @property
    def passes_name_contact_rules(self) -> bool:
        """Report this limited decision, not the record's final inclusion state."""
        return not self.exclusion_reasons


@dataclass(frozen=True)
class DuplicateCandidate:
    """Describe one possible duplicate pair for later manual confirmation.

    Attributes:
        record_ids: Two stable record IDs in sorted order, not display indexes.
        matching_contacts: Evidence codes EMAIL, PHONE, and/or ADDRESS.
        petition_status: MATCHING for equal populated petitions, BOTH_BLANK
            when neither is supplied, or ONE_BLANK for a mixed pair.
        record_revisions: Input revisions aligned with the two record IDs.

    This is a snapshot of matching evidence, not a deletion decision. The
    review workflow uses the IDs to retrieve both records and their originals.
    Rebuild candidates after edits; do not treat old evidence as current.
    """

    record_ids: tuple[str, str]
    matching_contacts: tuple[str, ...]
    petition_status: str
    record_revisions: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class DuplicateDecision:
    """Save a reviewed candidate and the chosen keeper, or None for keep both.

    The candidate includes input revisions. A review controller must recheck
    it before applying this choice. Originals are retained for every outcome.
    """

    candidate: DuplicateCandidate
    kept_record_id: str | None = None

    def __post_init__(self) -> None:
        """Reject a keeper that is not one of the candidate's two records."""
        if (self.kept_record_id is not None
                and self.kept_record_id not in self.candidate.record_ids):
            raise ValueError("The keeper must be one of the candidate records.")

    @property
    def record_ids(self) -> tuple[str, str]:
        """Return the stable pair identifying this decision."""
        return self.candidate.record_ids

    @property
    def excluded_record_id(self) -> str | None:
        """Return the redundant record ID, or None when both are retained."""
        if self.kept_record_id is None:
            return None
        first, second = self.record_ids
        return second if self.kept_record_id == first else first


@dataclass
class MemberRecord:
    """Hold one member's source snapshots, working data, and review state.

    Args:
        source_values: Original source row, in source-column order.
        mapped_values: Raw mapped record containing exact template headings.
        unit_value: Raw separately selected unit text, or an empty string.

    The InitVar inputs are constructor-only arguments. __post_init__ copies
    them into protected snapshots and creates independent working values.
    Use apply_cleaned_values() and edit_field() to change working fields.
    Manual edits remain subject to validation and do not imply eligibility.
    """

    source_values: InitVar[Sequence[str]]
    mapped_values: InitVar[Mapping[str, str]]
    unit_value: InitVar[str] = ""

    # Factories run for each new record, so mutable state is never shared.
    issues: list[ReviewIssue] = field(default_factory=list, init=False)
    exclusion_reasons: list[str] = field(default_factory=list, init=False)
    eligible: bool | None = field(default=None, init=False)
    manual_exclusion_reason: str | None = field(default=None, init=False)
    confirmed_duplicate_of: str | None = field(default=None, init=False)

    _record_id: str = field(
        default_factory=lambda: uuid4().hex, init=False, repr=False
    )
    _revision: int = field(default=0, init=False, repr=False)
    _original_source_values: tuple[str, ...] = field(init=False, repr=False)
    _original_mapped_values: Mapping[str, str] = field(init=False, repr=False)
    _original_unit_value: str = field(init=False, repr=False)
    _working_values: dict[str, str] = field(
        default_factory=dict, init=False, repr=False
    )
    _manual_overrides: dict[str, str] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(
        self,
        source_values: Sequence[str],
        mapped_values: Mapping[str, str],
        unit_value: str,
    ) -> None:
        """Validate text containers and detach stored values from callers.

        Raises:
            TypeError: A source cell, mapped value, or unit is not text.
            ValueError: Mapped headings are absent, blank, or not strings.
        """
        if isinstance(source_values, (str, bytes)):
            raise TypeError("Supply a sequence of source cells, not one string.")

        source_snapshot = tuple(source_values)
        mapped_snapshot = dict(mapped_values)

        if any(not isinstance(value, str) for value in source_snapshot):
            raise TypeError("Source cells must contain text.")
        if not mapped_snapshot or any(
            not isinstance(name, str) or not name.strip()
            for name in mapped_snapshot
        ):
            raise ValueError("Mapped values require nonblank string headings.")
        if any(not isinstance(value, str) for value in mapped_snapshot.values()):
            raise TypeError("Mapped field values must contain text.")
        if not isinstance(unit_value, str):
            raise TypeError("The original unit value must contain text.")

        self._original_source_values = source_snapshot
        # Wrap a copy: a read-only view of the caller's dict would still
        # reflect later changes made by that caller.
        self._original_mapped_values = MappingProxyType(mapped_snapshot)
        self._original_unit_value = unit_value
        self._working_values.update(mapped_snapshot)

    @property
    def record_id(self) -> str:
        """Return the identifier assigned once when this record was created."""
        return self._record_id

    @property
    def revision(self) -> int:
        """Return the revision advanced by edits, changed cleanup, or invalidation."""
        return self._revision

    @property
    def original_source_values(self) -> tuple[str, ...]:
        """Return the original source cells as an immutable tuple."""
        return self._original_source_values

    @property
    def original_mapped_values(self) -> Mapping[str, str]:
        """Return the read-only raw mapped snapshot, including exact headings."""
        return self._original_mapped_values

    @property
    def original_unit_value(self) -> str:
        """Return the original separate-unit text without normalization."""
        return self._original_unit_value

    @property
    def working_values(self) -> Mapping[str, str]:
        """Return a read-only view; use the update methods to change fields."""
        return MappingProxyType(self._working_values)

    @property
    def manual_overrides(self) -> Mapping[str, str]:
        """Return deliberate field corrections preserved during cleanup."""
        return MappingProxyType(self._manual_overrides)

    @property
    def is_included(self) -> bool:
        """Report local eligibility and exclusion state, not batch export readiness.

        None means validation is pending. Issues alone do not exclude a
        record: a BAD_ADDRESS may coexist with a valid email or phone.
        The batch controller must still resolve possible duplicates and
        enforce the application's final export checks.
        """
        return (
            self.eligible is True
            and self.manual_exclusion_reason is None
            and self.confirmed_duplicate_of is None
        )

    def apply_cleaned_values(self, values: Mapping[str, str]) -> None:
        """Apply a complete cleaned record while retaining manual corrections.

        Args:
            values: All original template fields with string values.

        Raises:
            ValueError: The supplied fields differ from the template snapshot.
            TypeError: Any supplied value is not text.

        The caller's mapping is not changed. Actual value changes invalidate
        earlier evaluation; an identical repeat preserves existing decisions.
        """
        if set(values) != set(self._original_mapped_values):
            raise ValueError("Cleaned values must contain exactly the template fields.")
        if any(not isinstance(value, str) for value in values.values()):
            raise TypeError("Cleaned field values must contain text.")

        # Preserve template order even if the caller's dictionary is reordered.
        replacement = {name: values[name] for name in self._original_mapped_values}
        replacement.update(self._manual_overrides)

        if replacement != self._working_values:
            self._working_values.clear()
            self._working_values.update(replacement)
            self.invalidate_evaluation()

    def edit_field(self, field_name: str, value: str) -> None:
        """Store a deliberate user correction and request another evaluation.

        Args:
            field_name: An exact existing template heading.
            value: User-supplied replacement text, including an empty string.

        Raises:
            KeyError: The field is absent from the template snapshot.
            TypeError: The replacement is not text.

        The GUI controls which fields are editable. Validation still checks
        the correction and computes derived fields; an edit is not approval.
        """
        if field_name not in self._original_mapped_values:
            raise KeyError(field_name)
        if not isinstance(value, str):
            raise TypeError("A field correction must contain text.")

        self._manual_overrides[field_name] = value
        self._working_values[field_name] = value
        self.invalidate_evaluation()

    def invalidate_evaluation(self) -> None:
        """Clear stale evaluation after changes while retaining manual exclusions.

        A batch controller can call this when rules change. It must also
        invalidate duplicate decisions on other affected records, since
        this model can clear only its own kept-record association. Advancing
        revision also invalidates review snapshots involving this record.
        """
        self._revision += 1
        self.eligible = None
        self.issues.clear()
        self.exclusion_reasons.clear()
        self.confirmed_duplicate_of = None
