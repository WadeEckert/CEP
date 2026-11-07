"""Within-file duplicate candidate detection for the Member CSV Cleaner.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Compare cleaned, evaluated records and return immutable candidate
pairs with matching contact evidence and petition context. Preserve all record
values, review state, exclusions, and source data during detection.
DuplicateReview applies explicit choices, reopens stale decisions, and gates
entry to correction review. Final export review belongs to the caller.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

from collections.abc import Sequence
from datetime import date
from itertools import combinations

from .models import DuplicateCandidate, DuplicateDecision, MemberRecord, resolve_proissub_heading
from .validation import (
    evaluate_record,
    get_address_status,
    get_name_contact_result,
    is_valid_email,
    is_valid_phone,
)


def _comparison_text(value: str) -> str:
    """Create a case/whitespace comparison key without changing stored text."""
    return " ".join(value.split()).casefold()


def _petition_key(record: MemberRecord) -> str:
    """Compare petition values using the same heading accepted by batch entry."""
    heading = resolve_proissub_heading(tuple(record.working_values))
    return _comparison_text(record.working_values[heading]) if heading is not None else ""


def _matching_contacts(
    left: MemberRecord, right: MemberRecord
) -> tuple[str, ...]:
    """Return every matching usable contact method, in a stable evidence order."""
    matches: list[str] = []
    for field_name, check_format, evidence_code in (
        ("Email", is_valid_email, "EMAIL"),
        ("Primary Cell/Mobile Phone", is_valid_phone, "PHONE"),
    ):
        left_value = left.working_values.get(field_name, "")
        right_value = right.working_values.get(field_name, "")
        if (check_format(left_value) and check_format(right_value)
                and _comparison_text(left_value) == _comparison_text(right_value)):
            matches.append(evidence_code)

    # Compare all required components, including any unit within Street.
    # A supplied status label or matching Street/ZIP alone is insufficient.
    if (get_address_status(left) == "MAILABLE"
            and get_address_status(right) == "MAILABLE"):
        fields = ("Street", "City", "State", "Zipcode")
        left_address = tuple(_comparison_text(left.working_values[name]) for name in fields)
        right_address = tuple(_comparison_text(right.working_values[name]) for name in fields)
        if left_address == right_address:
            matches.append("ADDRESS")

    return tuple(matches)


def find_possible_duplicates(
    records: Sequence[MemberRecord],
) -> list[DuplicateCandidate]:
    """Find matching pairs among locally included records without modifying them.

    Args:
        records: Records from one file after cleanup and evaluate_record().
            Reevaluate edited records before calling this function again.

    Returns:
        One candidate per matching pair, ordered by sorted stable record IDs.
        Effective first/last names must match, along with at least one usable
        email, phone, or complete MAILABLE address. First-name-only pairs use
        the same exact-name rule; a blank last name is not a wildcard.

    Raises:
        ValueError: A stable record ID is repeated, or evaluation is pending.

    Different populated petitions retain both records. Blank petitions are
    expected and do not prevent candidacy. Comparisons ignore case and extra
    whitespace, preserving other punctuation and meaningful unit differences.
    Shared Anonymous Donor names still require usable matching contact evidence.

    This does not merge pairs into transitive groups, exclude records, append
    issues, select a survivor, or change prior decisions. The calling workflow
    must obtain manual confirmation before excluding a redundant record.
    """
    seen_ids: set[str] = set()
    active: list[MemberRecord] = []
    name_keys: dict[str, tuple[str, str]] = {}
    petition_keys: dict[str, str] = {}

    for record in records:
        if record.record_id in seen_ids:
            raise ValueError("Each input record must have a unique stable ID.")
        seen_ids.add(record.record_id)
        if record.eligible is None:
            raise ValueError("Evaluate every record before finding duplicate candidates.")
        if not record.is_included:
            continue

        names = get_name_contact_result(record)
        if not names.passes_name_contact_rules:
            continue
        active.append(record)
        petition_keys[record.record_id] = _petition_key(record)
        name_keys[record.record_id] = (
            _comparison_text(names.first_name), _comparison_text(names.last_name)
        )

    # sorted() creates a new list, preserving source/display order in records.
    active = sorted(active, key=lambda record: record.record_id)
    candidates: list[DuplicateCandidate] = []

    for left, right in combinations(active, 2):
        if name_keys[left.record_id] != name_keys[right.record_id]:
            continue

        left_petition = petition_keys[left.record_id]
        right_petition = petition_keys[right.record_id]
        if left_petition and right_petition and left_petition != right_petition:
            continue

        evidence = _matching_contacts(left, right)
        if not evidence:
            continue

        if left_petition and right_petition:
            petition_status = "MATCHING"
        elif left_petition or right_petition:
            petition_status = "ONE_BLANK"
        else:
            petition_status = "BOTH_BLANK"

        candidates.append(DuplicateCandidate(
            record_ids=(left.record_id, right.record_id),
            matching_contacts=evidence,
            petition_status=petition_status,
            record_revisions=(left.revision, right.revision),
        ))

    return candidates


class DuplicateReview:
    """Manage explicit duplicate choices for one already-cleaned source batch.

    Create this before assigning duplicate exclusions. refresh() reevaluates
    records, retains decisions only for unchanged current evidence/revisions,
    and reapplies verified exclusions. Editing either endpoint reopens that
    pair; editing a keeper also reopens its dependent decisions.

    Records remain the caller's editable MemberRecord objects. Batch membership
    is fixed, and its original order is retained for correction review.
    """

    def __init__(
        self, records: Sequence[MemberRecord], *, reference_date: date | None = None
    ) -> None:
        """Validate batch identity before taking ownership of duplicate choices."""
        if reference_date is not None and type(reference_date) is not date:
            raise TypeError("reference_date must be a datetime.date value.")
        members = tuple(records)
        if len({record.record_id for record in members}) != len(members):
            raise ValueError("Each batch record must have a unique stable ID.")
        if any(record.confirmed_duplicate_of is not None for record in members):
            raise ValueError("Start duplicate review before assigning duplicate exclusions.")
        self._records = {record.record_id: record for record in members}
        self._reference_date = reference_date if reference_date is not None else date.today()
        self._decisions: dict[tuple[str, str], DuplicateDecision] = {}
        self.refresh()

    def refresh(self) -> tuple[DuplicateCandidate, ...]:
        """Recheck decisions and return currently unresolved active candidates.

        Temporarily clear only controller-owned duplicate links to reconsider
        their original pairs. No intermediate output values are exposed.
        Manual exclusions and input values remain intact throughout.
        """
        owned_links = {
            decision.excluded_record_id: decision.kept_record_id
            for decision in self._decisions.values()
            if decision.excluded_record_id is not None
        }
        for record in self._records.values():
            link = record.confirmed_duplicate_of
            if link is not None and link != owned_links.get(record.record_id):
                raise ValueError("Change duplicate choices through this review controller.")

        for record in self._records.values():
            record.confirmed_duplicate_of = None
            evaluate_record(record, reference_date=self._reference_date)
        current = {
            candidate.record_ids: candidate
            for candidate in find_possible_duplicates(tuple(self._records.values()))
        }
        self._decisions = {
            pair: decision for pair, decision in self._decisions.items()
            if current.get(pair) == decision.candidate
        }
        for decision in self._decisions.values():
            excluded = decision.excluded_record_id
            if excluded is not None:
                self._records[excluded].confirmed_duplicate_of = decision.kept_record_id

        return tuple(
            candidate for pair, candidate in current.items()
            if pair not in self._decisions
            and all(self._records[record_id].is_included for record_id in pair)
        )

    def get_pending_candidates(self) -> tuple[DuplicateCandidate, ...]:
        """Refresh the batch and return pairs still requiring a reviewer choice."""
        return self.refresh()

    def get_decisions(self) -> tuple[DuplicateDecision, ...]:
        """Return current immutable decisions in stable pair order."""
        self.refresh()
        return tuple(self._decisions[pair] for pair in sorted(self._decisions))

    def keep_both(self, candidate: DuplicateCandidate) -> DuplicateDecision:
        """Record that both rows should remain distinct for this candidate pair."""
        return self._decide(candidate, keep_record_id=None)

    def confirm_duplicate(
        self, candidate: DuplicateCandidate, *, keep_record_id: str
    ) -> DuplicateDecision:
        """Keep the selected row and exclude its directly confirmed redundant row."""
        if keep_record_id is None:
            raise ValueError("Select a candidate record to keep, or use keep_both().")
        return self._decide(candidate, keep_record_id=keep_record_id)

    def _decide(
        self, candidate: DuplicateCandidate, *, keep_record_id: str | None
    ) -> DuplicateDecision:
        """Validate current evidence and choice consistency before storing a decision."""
        pending = {item.record_ids: item for item in self.refresh()}
        if pending.get(candidate.record_ids) != candidate:
            raise ValueError("This candidate is stale or no longer awaiting a decision.")
        decision = DuplicateDecision(candidate, keep_record_id)
        if decision.excluded_record_id is not None:
            self._check_keeper_choice(decision)
        self._decisions[decision.record_ids] = decision
        self.refresh()
        return decision

    def _check_keeper_choice(self, proposed: DuplicateDecision) -> None:
        """Prevent exclusion chains and conflicts with petitions or keep-both choices."""
        keeper = proposed.kept_record_id
        excluded = proposed.excluded_record_id
        for decision in self._decisions.values():
            if decision.kept_record_id == excluded and decision.excluded_record_id is not None:
                raise ValueError("Undo dependent decisions before excluding their keeper.")

        # Each excluded row must refer directly to the actual retained keeper.
        family = {keeper, excluded}
        family.update(
            decision.excluded_record_id for decision in self._decisions.values()
            if decision.kept_record_id == keeper and decision.excluded_record_id is not None
        )
        petitions = {
            _petition_key(self._records[record_id])
            for record_id in family
        }
        petitions.discard("")
        if len(petitions) > 1:
            raise ValueError("Different populated petitions must retain separate records.")
        for decision in self._decisions.values():
            if decision.kept_record_id is None and set(decision.record_ids).issubset(family):
                raise ValueError("This choice conflicts with a keep-both decision; undo it first.")

    def undo_decision(self, record_ids: tuple[str, str]) -> None:
        """Remove one current decision and restore any row it alone excluded."""
        self.refresh()
        pair = tuple(sorted(record_ids))
        if pair not in self._decisions:
            raise ValueError("There is no current decision for this pair.")
        decision = self._decisions.pop(pair)
        excluded = decision.excluded_record_id
        if excluded is not None:
            self._records[excluded].confirmed_duplicate_of = None
        self.refresh()

    def get_correction_records(self) -> tuple[MemberRecord, ...]:
        """Return included rows in source order after all active pairs are resolved.

        The calling GUI must return to duplicate confirmation if later edits
        create or reopen candidates. Field review and final export checks are
        later workflow steps; this gate covers duplicate confirmation only.
        """
        if self.refresh():
            raise ValueError("Resolve duplicate candidates before correction review.")
        return tuple(record for record in self._records.values() if record.is_included)
