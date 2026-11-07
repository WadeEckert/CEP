"""Duplicate candidate checks using fictional member records.

Wade Eckert
Bellevue University
Bachelor of Science in Software Development and Mathematics

Purpose: Verify matching names and usable contacts, petition distinctions,
pairwise evidence, evaluation prerequisites, and preservation of source/review
state. Use real cleanup and record evaluation before candidate detection.
Exercise explicit review choices, stale-evidence rejection, undo, and the
gate between duplicate confirmation and correction review.
Run from the project root with python -m unittest discover -s tests -v.

AI disclosure: This code and documentation were generated with
OpenAI ChatGPT for developer review and adaptation.
"""

import unittest
from dataclasses import FrozenInstanceError
from datetime import date

from member_cleaner.cleanup import (
    assemble_street, clean_city, clean_country, clean_date_signed, clean_email,
    clean_name, clean_phone, clean_state, clean_zipcode,
)
from member_cleaner.duplicates import DuplicateReview, find_possible_duplicates
from member_cleaner.models import MemberRecord
from member_cleaner.validation import evaluate_record


REFERENCE_DATE = date(2026, 11, 6)
FULL_ADDRESS = {"Street": "125 Elm Street", "City": "Boston",
                "State": "Massachusetts", "Zipcode": "02108-1234"}


def make_duplicate_record(changes: dict[str, str] | None = None, *, unit: str = "", evaluate: bool = True) -> MemberRecord:
    """Preserve raw fixture values, clean fields, and normally evaluate the row."""
    mapped = {
        "First Name": " jordan ", "Last Name": " taylor ",
        "Email": "member@example.com", "Primary Cell/Mobile Phone": "2025550147",
        "Street": "", "City": "", "State": "", "Zipcode": "", "Country": "",
        "DateSigned": "3/7/2026", "PROISSSUB ": "",
        "Address Contact Status": "", "PhoneDisclaimeredYN": "",
        "Account Classification": "",
    }
    mapped.update(changes or {})
    record = MemberRecord(list(mapped.values()) + [unit], mapped, unit)
    cleaned = dict(record.working_values)
    for name, cleaner in (
        ("First Name", clean_name), ("Last Name", clean_name),
        ("Email", clean_email), ("Primary Cell/Mobile Phone", clean_phone),
        ("City", clean_city), ("State", clean_state),
        ("Zipcode", clean_zipcode), ("Country", clean_country),
    ):
        cleaned[name] = cleaner(cleaned[name])
    cleaned["Street"] = assemble_street(cleaned["Street"], unit)
    cleaned["DateSigned"] = clean_date_signed(
        cleaned["DateSigned"], reference_date=REFERENCE_DATE
    )
    record.apply_cleaned_values(cleaned)
    if evaluate:
        evaluate_record(record, reference_date=REFERENCE_DATE)
    return record


def record_snapshot(record: MemberRecord) -> tuple:
    """Capture all source, working, and review state relevant to pure detection."""
    return (
        record.record_id, record.original_source_values,
        dict(record.original_mapped_values), record.original_unit_value,
        dict(record.working_values), dict(record.manual_overrides),
        list(record.issues), list(record.exclusion_reasons), record.eligible,
        record.manual_exclusion_reason, record.confirmed_duplicate_of,
    )


class DuplicateCandidateTests(unittest.TestCase):
    """Check exact cleaned comparisons and immutable pairwise evidence."""

    def test_matching_email_and_names_ignore_case(self) -> None:
        """A usable matching email qualifies despite a conflicting phone."""
        left = make_duplicate_record({"Email": " Member@Example.COM ",
                                      "Primary Cell/Mobile Phone": "2025550101"})
        right = make_duplicate_record({"First Name": "jOrDaN", "Last Name": "TAYLOR",
                                       "Email": "member@example.com",
                                       "Primary Cell/Mobile Phone": "2025550102"})
        result = find_possible_duplicates([left, right])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].matching_contacts, ("EMAIL",))
        self.assertEqual(result[0].petition_status, "BOTH_BLANK")

    def test_matching_cleaned_phone_qualifies_with_different_emails(self) -> None:
        """Use the actual phone cleaner before comparing ten-digit values."""
        left = make_duplicate_record({"Email": "one@example.com",
                                      "Primary Cell/Mobile Phone": "1 (202) 555-0147"})
        right = make_duplicate_record({"Email": "two@example.com",
                                       "Primary Cell/Mobile Phone": "202.555.0147"})
        result = find_possible_duplicates([left, right])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].matching_contacts, ("PHONE",))

    def test_matching_complete_address_includes_unit_and_all_components(self) -> None:
        """Normalize supplied aliases while requiring a complete usable address."""
        left = make_duplicate_record({**FULL_ADDRESS, "Country": "US",
                                      "Email": "one@example.com",
                                      "Primary Cell/Mobile Phone": "2025550101"},
                                     unit="Apartment 004b")
        right = make_duplicate_record({**FULL_ADDRESS, "Street": "125 elm st apt 004B",
                                       "City": "BOSTON", "State": "MA", "Zipcode": "02108",
                                       "Email": "two@example.com",
                                       "Primary Cell/Mobile Phone": "2025550102"})
        result = find_possible_duplicates([left, right])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].matching_contacts, ("ADDRESS",))
        self.assertEqual(left.original_unit_value, "Apartment 004b")

    def test_names_and_contact_both_have_to_match(self) -> None:
        """Neither a shared name alone nor a shared contact alone establishes a pair."""
        left = make_duplicate_record({"Email": "one@example.com",
                                      "Primary Cell/Mobile Phone": "2025550101"})
        for changes in [
            {"Email": "two@example.com", "Primary Cell/Mobile Phone": "2025550102"},
            {"First Name": "Casey", "Email": "one@example.com"},
            {"Last Name": "Morgan", "Email": "one@example.com"},
            {"Last Name": "Taylor-Jones", "Email": "one@example.com"},
        ]:
            with self.subTest(changes=changes):
                self.assertEqual(find_possible_duplicates([left, make_duplicate_record(changes)]), [])

    def test_blank_or_invalid_contacts_cannot_supply_evidence(self) -> None:
        """Matching unusable values remain review data rather than duplicate evidence."""
        for email in ["", "bad email", "one@example.com;two@example.com"]:
            with self.subTest(email=email):
                left = make_duplicate_record({"Email": email,
                                              "Primary Cell/Mobile Phone": "2025550101"})
                right = make_duplicate_record({"Email": email,
                                               "Primary Cell/Mobile Phone": "2025550102"})
                self.assertEqual(find_possible_duplicates([left, right]), [])
        left = make_duplicate_record({"Email": "one@example.com",
                                      "Primary Cell/Mobile Phone": "bad phone"})
        right = make_duplicate_record({"Email": "two@example.com",
                                       "Primary Cell/Mobile Phone": "bad phone"})
        self.assertEqual(find_possible_duplicates([left, right]), [])

    def test_address_differences_and_unresolved_fields_prevent_address_match(self) -> None:
        """Do not reduce a full-address match to Street and ZIP or trust status labels."""
        left = make_duplicate_record({**FULL_ADDRESS, "Email": "one@example.com",
                                      "Primary Cell/Mobile Phone": "2025550101"}, unit="Apt 004B")
        for changes in [
            {"City": "Denver"}, {"State": "CO"}, {"Zipcode": "02109"},
            {"Zipcode": "", "Address Contact Status": "MAILABLE"},
            {"Country": "Canada"}, {"Street": "125 Elm"},
            {"Street": "125 Elm St Apt 005B"},
            {"Street": "125 Elm St Apt 4B"},
            {"Street": "125 Elm St Ste 004B"},
        ]:
            with self.subTest(changes=changes):
                right = make_duplicate_record({
                    **FULL_ADDRESS, "Street": "125 Elm St Apt 004B",
                    "Email": "two@example.com", "Primary Cell/Mobile Phone": "2025550102",
                    **changes,
                })
                self.assertEqual(find_possible_duplicates([left, right]), [])

    def test_petition_values_distinguish_matching_blank_and_different_pairs(self) -> None:
        """Expected blanks allow review; different populated petitions retain both rows."""
        for left_value, right_value, expected in [
            ("PET-1", "PET-1", "MATCHING"), (" pet-1 ", "PET-1", "MATCHING"),
            ("", "", "BOTH_BLANK"), (" \t ", "", "BOTH_BLANK"),
            ("", "PET-1", "ONE_BLANK"), ("PET-1", "", "ONE_BLANK"),
            ("PET-1", "PET-2", None),
        ]:
            with self.subTest(left=left_value, right=right_value):
                left = make_duplicate_record({"PROISSSUB ": left_value})
                right = make_duplicate_record({"PROISSSUB ": right_value})
                result = find_possible_duplicates([left, right])
                self.assertEqual(len(result), 0 if expected is None else 1)
                if expected is not None:
                    self.assertEqual(result[0].petition_status, expected)
                self.assertEqual(left.working_values["PROISSSUB "], left_value)
                self.assertEqual(right.working_values["PROISSSUB "], right_value)

    def test_first_name_only_pairs_do_not_use_a_blank_last_name_as_wildcard(self) -> None:
        """Match equal first-only names while distinguishing populated surnames."""
        left = make_duplicate_record({"First Name": "Jordan", "Last Name": ""})
        same = make_duplicate_record({"First Name": "JORDAN", "Last Name": ""})
        self.assertEqual(len(find_possible_duplicates([left, same])), 1)
        for first, last in [("Jordan", "Taylor"), ("Casey", "")]:
            with self.subTest(first=first, last=last):
                other = make_duplicate_record({"First Name": first, "Last Name": last})
                self.assertEqual(find_possible_duplicates([left, other]), [])

    def test_anonymous_names_require_matching_usable_contact(self) -> None:
        """Shared generated names alone are insufficient; actual contact can flag review."""
        left = make_duplicate_record({"First Name": "", "Last Name": "Taylor", "Email": ""})
        right = make_duplicate_record({"First Name": "J.", "Last Name": "T.", "Email": ""})
        result = find_possible_duplicates([left, right])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].matching_contacts, ("PHONE",))
        different_contact = make_duplicate_record({
            "First Name": "", "Last Name": "", "Email": "",
            "Primary Cell/Mobile Phone": "2025550102",
        })
        self.assertEqual(find_possible_duplicates([left, different_contact]), [])
        self.assertEqual(left.working_values["First Name"], "")
        self.assertEqual(left.working_values["Last Name"], "Taylor")

    def test_excluded_and_ineligible_records_do_not_enter_candidates(self) -> None:
        """Consider locally included records and preserve all existing exclusion state."""
        left, right = make_duplicate_record(), make_duplicate_record()
        ineligible = make_duplicate_record({"Email": "", "Primary Cell/Mobile Phone": ""})
        manual = make_duplicate_record()
        manual.manual_exclusion_reason = "Reviewer choice"
        confirmed = make_duplicate_record()
        confirmed.confirmed_duplicate_of = left.record_id
        records = [left, manual, right, ineligible, confirmed]
        before = [record_snapshot(record) for record in records]
        result = find_possible_duplicates(records)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].record_ids, tuple(sorted((left.record_id, right.record_id))))
        self.assertEqual([record_snapshot(record) for record in records], before)

    def test_all_matching_methods_produce_one_immutable_candidate(self) -> None:
        """Return one pair with all evidence rather than repeating it for each contact."""
        left, right = make_duplicate_record(FULL_ADDRESS), make_duplicate_record(FULL_ADDRESS)
        result = find_possible_duplicates([right, left])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].matching_contacts, ("EMAIL", "PHONE", "ADDRESS"))
        self.assertEqual(result[0].record_ids, tuple(sorted((left.record_id, right.record_id))))
        with self.assertRaises(FrozenInstanceError):
            result[0].petition_status = "Changed"
        with self.assertRaises(TypeError):
            result[0].matching_contacts[0] = "Changed"

    def test_matching_is_pairwise_and_does_not_infer_transitive_duplicates(self) -> None:
        """A-B matching email and B-C matching phone must not manufacture A-C."""
        first = make_duplicate_record({"Email": "one@example.com",
                                       "Primary Cell/Mobile Phone": "2025550101"})
        middle = make_duplicate_record({"Email": "one@example.com",
                                        "Primary Cell/Mobile Phone": "2025550102"})
        last = make_duplicate_record({"Email": "three@example.com",
                                      "Primary Cell/Mobile Phone": "2025550102"})
        result = find_possible_duplicates([first, middle, last])
        evidence = {frozenset(item.record_ids): item.matching_contacts for item in result}
        self.assertEqual(evidence, {
            frozenset((first.record_id, middle.record_id)): ("EMAIL",),
            frozenset((middle.record_id, last.record_id)): ("PHONE",),
        })
        self.assertTrue(all(record.confirmed_duplicate_of is None
                            for record in [first, middle, last]))

    def test_edits_require_reevaluation_and_candidates_are_rebuilt(self) -> None:
        """Discard old evidence after edits while retaining each record's stable ID."""
        left = make_duplicate_record({"Primary Cell/Mobile Phone": "2025550101"})
        right = make_duplicate_record({"Primary Cell/Mobile Phone": "2025550102"})
        old = find_possible_duplicates([left, right])
        self.assertEqual(old[0].matching_contacts, ("EMAIL",))
        original_id = right.record_id
        right.edit_field("Email", "other@example.com")
        with self.assertRaises(ValueError):
            find_possible_duplicates([left, right])
        evaluate_record(right, reference_date=REFERENCE_DATE)
        self.assertEqual(find_possible_duplicates([left, right]), [])
        right.edit_field("Primary Cell/Mobile Phone", "2025550101")
        evaluate_record(right, reference_date=REFERENCE_DATE)
        new = find_possible_duplicates([left, right])
        self.assertEqual(new[0].matching_contacts, ("PHONE",))
        self.assertEqual(right.record_id, original_id)
        self.assertEqual(old[0].matching_contacts, ("EMAIL",))

    def test_results_are_repeatable_order_independent_and_side_effect_free(self) -> None:
        """Sorting/display order and repeated calls must not change evidence or state."""
        records = [make_duplicate_record({"DateSigned": "bad date"}),
                   make_duplicate_record(), make_duplicate_record()]
        records[1].edit_field("First Name", "Jordan")
        evaluate_record(records[1], reference_date=REFERENCE_DATE)
        before = [record_snapshot(record) for record in records]
        order_before = [record.record_id for record in records]
        first = find_possible_duplicates(records)
        second = find_possible_duplicates(list(reversed(records)))
        self.assertEqual(len(first), 3)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertEqual([record.record_id for record in records], order_before)
        self.assertEqual([record_snapshot(record) for record in records], before)

    def test_empty_single_pending_and_repeated_id_inputs(self) -> None:
        """Reject ambiguous input identity or pending evaluation before comparison."""
        self.assertEqual(find_possible_duplicates([]), [])
        ready = make_duplicate_record()
        self.assertEqual(find_possible_duplicates((ready,)), [])
        with self.assertRaises(ValueError):
            find_possible_duplicates([ready, ready])
        pending = make_duplicate_record(evaluate=False)
        with self.assertRaises(ValueError):
            find_possible_duplicates([ready, pending])


def pending_pair(review: DuplicateReview, first: MemberRecord, second: MemberRecord):
    """Find the current displayed candidate for two stable record IDs."""
    pair = tuple(sorted((first.record_id, second.record_id)))
    return next(item for item in review.get_pending_candidates() if item.record_ids == pair)


class DuplicateReviewTests(unittest.TestCase):
    """Check explicit decisions and revalidation across the entire source batch."""

    def test_initial_evaluation_and_gate_require_a_choice(self) -> None:
        """Evaluate cleaned pending rows and block correction review until resolved."""
        records = [make_duplicate_record(evaluate=False), make_duplicate_record(evaluate=False)]
        revisions = [record.revision for record in records]
        review = DuplicateReview(records, reference_date=REFERENCE_DATE)
        self.assertEqual(len(review.get_pending_candidates()), 1)
        self.assertEqual(review.get_decisions(), ())
        with self.assertRaises(ValueError):
            review.get_correction_records()
        self.assertTrue(all(record.eligible for record in records))
        self.assertEqual([record.revision for record in records], revisions)

    def test_either_record_can_be_the_explicit_keeper(self) -> None:
        """Exclude only the selected redundant row and retain its original data."""
        for keep_index in [0, 1]:
            with self.subTest(keep_index=keep_index):
                records = [make_duplicate_record(), make_duplicate_record()]
                review = DuplicateReview(records, reference_date=REFERENCE_DATE)
                keeper, excluded = records[keep_index], records[1 - keep_index]
                originals = excluded.original_source_values
                decision = review.confirm_duplicate(
                    review.get_pending_candidates()[0], keep_record_id=keeper.record_id
                )
                self.assertEqual(decision.kept_record_id, keeper.record_id)
                self.assertEqual(decision.excluded_record_id, excluded.record_id)
                self.assertEqual(excluded.confirmed_duplicate_of, keeper.record_id)
                self.assertEqual(review.get_pending_candidates(), ())
                self.assertEqual(review.get_correction_records(), (keeper,))
                self.assertIsNone(evaluate_record(excluded, reference_date=REFERENCE_DATE))
                self.assertEqual(excluded.original_source_values, originals)
                self.assertEqual(len(review.get_decisions()), 1)

    def test_keep_both_survives_unchanged_cleanup_and_reevaluation(self) -> None:
        """A resolved keep-both choice stays resolved until input evidence changes."""
        left, right = make_duplicate_record(), make_duplicate_record()
        review = DuplicateReview([right, left], reference_date=REFERENCE_DATE)
        decision = review.keep_both(review.get_pending_candidates()[0])
        for record in [left, right]:
            record.apply_cleaned_values(dict(record.working_values))
            evaluate_record(record, reference_date=REFERENCE_DATE)
        self.assertEqual(review.get_pending_candidates(), ())
        self.assertEqual(review.get_correction_records(), (right, left))
        self.assertEqual(review.get_decisions(), (decision,))
        self.assertIsNone(decision.excluded_record_id)
        with self.assertRaises(FrozenInstanceError):
            decision.kept_record_id = left.record_id

    def test_undo_reopens_both_keep_both_and_confirmed_choices(self) -> None:
        """Undo restores the excluded row and presents the actual pair again."""
        for confirm in [False, True]:
            with self.subTest(confirm=confirm):
                left, right = make_duplicate_record(), make_duplicate_record()
                review = DuplicateReview([left, right], reference_date=REFERENCE_DATE)
                candidate = review.get_pending_candidates()[0]
                if confirm:
                    review.confirm_duplicate(candidate, keep_record_id=left.record_id)
                else:
                    review.keep_both(candidate)
                review.undo_decision(tuple(reversed(candidate.record_ids)))
                self.assertEqual(review.get_decisions(), ())
                self.assertEqual(len(review.get_pending_candidates()), 1)
                self.assertIsNone(right.confirmed_duplicate_of)
                self.assertTrue(left.is_included and right.is_included)

    def test_stale_displayed_candidate_is_rejected_even_when_methods_still_match(self) -> None:
        """A changed shared email must invalidate the old displayed evidence."""
        left, right = make_duplicate_record(), make_duplicate_record()
        review = DuplicateReview([left, right], reference_date=REFERENCE_DATE)
        old = review.get_pending_candidates()[0]
        left.edit_field("Email", "new@example.com")
        right.edit_field("Email", "new@example.com")
        with self.assertRaises(ValueError):
            review.confirm_duplicate(old, keep_record_id=left.record_id)
        current = review.get_pending_candidates()[0]
        self.assertEqual(old.record_ids, current.record_ids)
        self.assertEqual(old.matching_contacts, current.matching_contacts)
        self.assertNotEqual(old.record_revisions, current.record_revisions)
        self.assertIsNone(right.confirmed_duplicate_of)
        review.confirm_duplicate(current, keep_record_id=left.record_id)
        self.assertEqual(review.get_correction_records(), (left,))

    def test_editing_keeper_reopens_every_dependent_decision(self) -> None:
        """Recheck other rows that still point to an edited keeper."""
        keeper, first, second = [make_duplicate_record() for _ in range(3)]
        review = DuplicateReview([keeper, first, second], reference_date=REFERENCE_DATE)
        review.confirm_duplicate(pending_pair(review, keeper, first),
                                 keep_record_id=keeper.record_id)
        review.confirm_duplicate(pending_pair(review, keeper, second),
                                 keep_record_id=keeper.record_id)
        self.assertEqual(review.get_correction_records(), (keeper,))
        keeper.edit_field("Email", "changed@example.com")
        self.assertEqual(len(review.get_pending_candidates()), 3)
        self.assertEqual(review.get_decisions(), ())
        self.assertTrue(all(record.confirmed_duplicate_of is None
                            for record in [keeper, first, second]))
        with self.assertRaises(ValueError):
            review.get_correction_records()

    def test_editing_excluded_row_preserves_unrelated_decisions(self) -> None:
        """Reopen only affected pairs while retaining another independent choice."""
        first, redundant = make_duplicate_record(), make_duplicate_record()
        other = make_duplicate_record({"First Name": "Casey"})
        other_redundant = make_duplicate_record({"First Name": "Casey"})
        review = DuplicateReview([first, redundant, other, other_redundant],
                                 reference_date=REFERENCE_DATE)
        review.confirm_duplicate(pending_pair(review, first, redundant),
                                 keep_record_id=first.record_id)
        kept = review.confirm_duplicate(pending_pair(review, other, other_redundant),
                                        keep_record_id=other.record_id)
        redundant.edit_field("DateSigned", "03/08/26")
        self.assertEqual(len(review.get_pending_candidates()), 1)
        self.assertEqual(review.get_decisions(), (kept,))
        self.assertIsNone(redundant.confirmed_duplicate_of)
        self.assertEqual(other_redundant.confirmed_duplicate_of, other.record_id)

    def test_ineligible_keeper_releases_its_redundant_row(self) -> None:
        """Losing the keeper's usable contacts must not leave another row hidden."""
        keeper, redundant = make_duplicate_record(), make_duplicate_record()
        review = DuplicateReview([keeper, redundant], reference_date=REFERENCE_DATE)
        review.confirm_duplicate(review.get_pending_candidates()[0],
                                 keep_record_id=keeper.record_id)
        keeper.edit_field("Email", "")
        keeper.edit_field("Primary Cell/Mobile Phone", "")
        self.assertEqual(review.get_correction_records(), (redundant,))
        self.assertFalse(keeper.eligible)
        self.assertIsNone(redundant.confirmed_duplicate_of)
        self.assertEqual(review.get_decisions(), ())

    def test_manual_exclusion_of_keeper_releases_dependent_row(self) -> None:
        """Preserve the manual exclusion while reopening its former duplicate choice."""
        keeper, redundant = make_duplicate_record(), make_duplicate_record()
        review = DuplicateReview([keeper, redundant], reference_date=REFERENCE_DATE)
        review.confirm_duplicate(review.get_pending_candidates()[0],
                                 keep_record_id=keeper.record_id)
        keeper.manual_exclusion_reason = "Reviewer excluded the keeper."
        self.assertEqual(review.get_correction_records(), (redundant,))
        self.assertEqual(keeper.manual_exclusion_reason, "Reviewer excluded the keeper.")
        self.assertIsNone(redundant.confirmed_duplicate_of)
        self.assertEqual(review.get_decisions(), ())

    def test_invalid_choices_leave_current_decisions_and_inputs_unchanged(self) -> None:
        """Require a real pending candidate and an explicitly selected pair member."""
        left, right = make_duplicate_record(), make_duplicate_record()
        review = DuplicateReview([left, right], reference_date=REFERENCE_DATE)
        candidate = review.get_pending_candidates()[0]
        before = [record_snapshot(record) for record in [left, right]]
        for invalid_keeper in ["unknown-id", None]:
            with self.subTest(invalid_keeper=invalid_keeper):
                with self.assertRaises(ValueError):
                    review.confirm_duplicate(candidate, keep_record_id=invalid_keeper)
        foreign = find_possible_duplicates([make_duplicate_record(), make_duplicate_record()])[0]
        with self.assertRaises(ValueError):
            review.keep_both(foreign)
        self.assertEqual(review.get_decisions(), ())
        self.assertEqual([record_snapshot(record) for record in [left, right]], before)

    def test_constructor_rejects_repeated_ids_existing_links_and_bad_date_type(self) -> None:
        """Reject ownership/configuration errors before changing a batch."""
        record = make_duplicate_record()
        before = record_snapshot(record)
        with self.assertRaises(ValueError):
            DuplicateReview([record, record], reference_date=REFERENCE_DATE)
        with self.assertRaises(TypeError):
            DuplicateReview([record], reference_date="11/06/26")
        self.assertEqual(record_snapshot(record), before)
        record.confirmed_duplicate_of = "unowned-link"
        with self.assertRaises(ValueError):
            DuplicateReview([record], reference_date=REFERENCE_DATE)
        self.assertEqual(record.confirmed_duplicate_of, "unowned-link")

    def test_keeper_chains_are_rejected_until_dependent_choices_are_undone(self) -> None:
        """Keep direct keeper relationships rather than silently following a chain."""
        first, redundant, third = [make_duplicate_record() for _ in range(3)]
        review = DuplicateReview([first, redundant, third], reference_date=REFERENCE_DATE)
        initial = review.confirm_duplicate(pending_pair(review, first, redundant),
                                           keep_record_id=first.record_id)
        with self.assertRaises(ValueError):
            review.confirm_duplicate(pending_pair(review, first, third),
                                     keep_record_id=third.record_id)
        self.assertEqual(redundant.confirmed_duplicate_of, first.record_id)
        self.assertIsNone(first.confirmed_duplicate_of)
        review.undo_decision(initial.record_ids)
        review.confirm_duplicate(pending_pair(review, first, third),
                                 keep_record_id=third.record_id)
        self.assertIsNone(redundant.confirmed_duplicate_of)
        self.assertEqual(first.confirmed_duplicate_of, third.record_id)
        self.assertEqual(len(review.get_pending_candidates()), 1)

    def test_blank_petition_keeper_cannot_combine_different_populated_petitions(self) -> None:
        """Pairwise choices must preserve the rule that different petitions retain rows."""
        blank = make_duplicate_record()
        first = make_duplicate_record({"PROISSSUB ": "PET-1"})
        second = make_duplicate_record({"PROISSSUB ": "PET-2"})
        review = DuplicateReview([blank, first, second], reference_date=REFERENCE_DATE)
        review.confirm_duplicate(pending_pair(review, blank, first),
                                 keep_record_id=blank.record_id)
        with self.assertRaises(ValueError):
            review.confirm_duplicate(pending_pair(review, blank, second),
                                     keep_record_id=blank.record_id)
        review.keep_both(pending_pair(review, blank, second))
        self.assertEqual(review.get_correction_records(), (blank, second))
        self.assertEqual(first.confirmed_duplicate_of, blank.record_id)
        self.assertIsNone(second.confirmed_duplicate_of)

    def test_keep_both_choice_prevents_collapsing_both_under_a_third_keeper(self) -> None:
        """Respect a distinct-record choice across later directly confirmed pairs."""
        first, second, keeper = [make_duplicate_record() for _ in range(3)]
        review = DuplicateReview([first, second, keeper], reference_date=REFERENCE_DATE)
        review.keep_both(pending_pair(review, first, second))
        review.confirm_duplicate(pending_pair(review, first, keeper),
                                 keep_record_id=keeper.record_id)
        with self.assertRaises(ValueError):
            review.confirm_duplicate(pending_pair(review, second, keeper),
                                     keep_record_id=keeper.record_id)
        review.keep_both(pending_pair(review, second, keeper))
        self.assertEqual(review.get_correction_records(), (second, keeper))

    def test_confirming_one_pair_does_not_exclude_a_transitive_match(self) -> None:
        """A-B by email and B-C by phone do not justify excluding C under A."""
        first = make_duplicate_record({"Email": "one@example.com",
                                       "Primary Cell/Mobile Phone": "2025550101"})
        middle = make_duplicate_record({"Email": "one@example.com",
                                        "Primary Cell/Mobile Phone": "2025550102"})
        last = make_duplicate_record({"Email": "three@example.com",
                                      "Primary Cell/Mobile Phone": "2025550102"})
        review = DuplicateReview([first, middle, last], reference_date=REFERENCE_DATE)
        decision = review.confirm_duplicate(pending_pair(review, first, middle),
                                            keep_record_id=first.record_id)
        self.assertEqual(review.get_correction_records(), (first, last))
        self.assertIsNone(last.confirmed_duplicate_of)
        review.undo_decision(decision.record_ids)
        self.assertEqual(len(review.get_pending_candidates()), 2)

    def test_same_value_edit_and_rule_invalidation_reopen_a_saved_choice(self) -> None:
        """Revision changes require renewed confirmation even when text stays equal."""
        left, right = make_duplicate_record(), make_duplicate_record()
        review = DuplicateReview([left, right], reference_date=REFERENCE_DATE)
        review.keep_both(review.get_pending_candidates()[0])
        left.edit_field("First Name", left.working_values["First Name"])
        self.assertEqual(len(review.get_pending_candidates()), 1)
        review.keep_both(review.get_pending_candidates()[0])
        left.invalidate_evaluation()
        self.assertEqual(len(review.get_pending_candidates()), 1)

    def test_unowned_links_and_unknown_undo_requests_are_not_silently_applied(self) -> None:
        """Use the controller for choices and leave invalid external state visible."""
        left, right = make_duplicate_record(), make_duplicate_record()
        review = DuplicateReview([left, right], reference_date=REFERENCE_DATE)
        review.keep_both(review.get_pending_candidates()[0])
        with self.assertRaises(ValueError):
            review.undo_decision(("unknown", "other"))
        self.assertEqual(len(review.get_decisions()), 1)
        right.confirmed_duplicate_of = "unowned-link"
        with self.assertRaises(ValueError):
            review.get_pending_candidates()
        self.assertEqual(right.confirmed_duplicate_of, "unowned-link")

    def test_choices_preserve_source_data_and_correction_order(self) -> None:
        """Keep source/working values and IDs intact across keep-both and keeper choices."""
        left = make_duplicate_record({"Email": "left@example.com", **FULL_ADDRESS},
                                     unit="Apartment 004b")
        right = make_duplicate_record({"Email": "right@example.com"})
        third = make_duplicate_record({"First Name": "Casey"})
        records = [right, left, third]
        before = [(record.record_id, record.revision, record.original_source_values,
                   dict(record.original_mapped_values), record.original_unit_value,
                   dict(record.working_values), dict(record.manual_overrides))
                  for record in records]
        review = DuplicateReview(records, reference_date=REFERENCE_DATE)
        both = review.keep_both(pending_pair(review, left, right))
        self.assertEqual(review.get_correction_records(), tuple(records))
        review.undo_decision(both.record_ids)
        review.confirm_duplicate(pending_pair(review, left, right),
                                 keep_record_id=right.record_id)
        self.assertEqual(review.get_correction_records(), (right, third))
        after = [(record.record_id, record.revision, record.original_source_values,
                  dict(record.original_mapped_values), record.original_unit_value,
                  dict(record.working_values), dict(record.manual_overrides))
                 for record in records]
        self.assertEqual(before, after)

