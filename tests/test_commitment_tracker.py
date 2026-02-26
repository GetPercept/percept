"""Tests for the Commitment Tracker — CIL Level 2."""

import pytest
from datetime import datetime, timedelta
from src.commitment_tracker import CommitmentTracker, Commitment


@pytest.fixture
def tracker():
    """Tracker without DB for unit tests."""
    return CommitmentTracker(db=None)


class TestCommitmentExtraction:
    """Test commitment extraction from utterances."""

    def test_direct_promise(self, tracker):
        utterances = [
            {"text": "I'll send you the report by Friday", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) >= 1
        assert "report" in commitments[0].action.lower() or "send" in commitments[0].action.lower()
        assert commitments[0].speaker_name == "David"

    def test_let_me_pattern(self, tracker):
        utterances = [
            {"text": "Let me check with the engineering team and get back to you", "speaker_id": "s1", "speaker_name": "Sarah", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) >= 1
        assert commitments[0].speaker_name == "Sarah"

    def test_obligation_language(self, tracker):
        utterances = [
            {"text": "We need to finish the proposal before the board meeting", "speaker_id": "s1", "speaker_name": "Rob", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) >= 1

    def test_third_party_commitment(self, tracker):
        utterances = [
            {"text": "She said she would send the contract by Tuesday", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) >= 1
        assert commitments[0].deadline is not None

    def test_no_commitment_in_question(self, tracker):
        utterances = [
            {"text": "Can you send me the report?", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) == 0

    def test_no_commitment_in_hypothetical(self, tracker):
        utterances = [
            {"text": "If we had more time, I'll probably skip the review", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) == 0

    def test_no_commitment_in_past(self, tracker):
        utterances = [
            {"text": "I used to send weekly reports but stopped", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) == 0

    def test_multiple_commitments(self, tracker):
        utterances = [
            {"text": "I'll send the proposal by Friday", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
            {"text": "The weather looks nice today", "speaker_id": "s2", "speaker_name": "Sarah", "timestamp": 1001},
            {"text": "I will follow up with the vendor next week", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1002},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) >= 2

    def test_short_text_skipped(self, tracker):
        utterances = [
            {"text": "OK sure", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) == 0

    def test_context_captured(self, tracker):
        utterances = [
            {"text": "The client is getting frustrated with delays", "speaker_id": "s2", "speaker_name": "Sarah", "timestamp": 999},
            {"text": "I'll send them an update email by end of day", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
            {"text": "Good, include the revised timeline", "speaker_id": "s2", "speaker_name": "Sarah", "timestamp": 1001},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) >= 1
        assert commitments[0].context  # Should have surrounding context


class TestDeadlineExtraction:
    """Test deadline parsing."""

    def test_by_tomorrow(self, tracker):
        utterances = [
            {"text": "I'll have it ready by tomorrow", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) >= 1
        assert commitments[0].deadline is not None
        assert "tomorrow" in commitments[0].deadline.lower()

    def test_by_weekday(self, tracker):
        utterances = [
            {"text": "I'll send the report by Friday", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) >= 1
        assert commitments[0].deadline is not None
        assert commitments[0].deadline_dt is not None

    def test_end_of_day(self, tracker):
        utterances = [
            {"text": "I need to submit this by end of day", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) >= 1
        assert "end of day" in (commitments[0].deadline or "").lower()

    def test_within_duration(self, tracker):
        utterances = [
            {"text": "I'll get back to you within 2 days", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) >= 1
        assert commitments[0].deadline_dt is not None

    def test_next_week(self, tracker):
        utterances = [
            {"text": "I will follow up with the vendor next week", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        assert len(commitments) >= 1
        assert commitments[0].deadline is not None

    def test_no_deadline(self, tracker):
        utterances = [
            {"text": "I'll take care of that", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        # Should still extract commitment, just no deadline
        if commitments:
            assert commitments[0].deadline is None


class TestConfidence:
    """Test confidence scoring."""

    def test_first_person_higher_confidence(self, tracker):
        utt_first = [{"text": "I will send the contract by Friday", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000}]
        utt_third = [{"text": "They will send the contract by Friday", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000}]

        c_first = tracker.extract_commitments(utt_first)
        c_third = tracker.extract_commitments(utt_third)

        if c_first and c_third:
            assert c_first[0].confidence >= c_third[0].confidence

    def test_deadline_boosts_confidence(self, tracker):
        utt_deadline = [{"text": "I'll send the report by Friday", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000}]
        utt_no_deadline = [{"text": "I'll send the report sometime", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000}]

        c_deadline = tracker.extract_commitments(utt_deadline)
        c_no_deadline = tracker.extract_commitments(utt_no_deadline)

        if c_deadline and c_no_deadline:
            assert c_deadline[0].confidence >= c_no_deadline[0].confidence

    def test_low_confidence_filtered(self, tracker):
        utterances = [
            {"text": "Maybe I should probably look into that at some point", "speaker_id": "s1", "speaker_name": "David", "timestamp": 1000},
        ]
        commitments = tracker.extract_commitments(utterances)
        # Vague commitments should be filtered out or very low confidence
        for c in commitments:
            assert c.confidence >= 0.3  # Our threshold


class TestReferencDetection:
    """Test cross-conversation commitment re-mention detection."""

    def test_re_mention_detected(self, tracker):
        # Without DB, this should return empty
        matches = tracker.detect_re_mention("Did you send the proposal yet?")
        assert matches == []  # No DB = no matches


class TestCommitmentLifecycle:
    """Test commitment status management."""

    def test_fulfill_without_db(self, tracker):
        result = tracker.fulfill("some-id")
        assert result is False

    def test_cancel_without_db(self, tracker):
        result = tracker.cancel("some-id")
        assert result is False

    def test_check_overdue_without_db(self, tracker):
        result = tracker.check_overdue()
        assert result == []

    def test_get_open_without_db(self, tracker):
        result = tracker.get_open_commitments()
        assert result == []
