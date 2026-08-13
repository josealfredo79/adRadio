"""Tests for format_time_gap_note — found in production 2026-08-12: the bot
strips timestamps from conversation_history before calling Claude (its API
rejects that field), so without this note the model has zero signal that
months passed between a contact's messages and can talk as if no time
elapsed at all."""
from datetime import datetime, timedelta, timezone

from app.services.claude_service import format_time_gap_note


def test_none_returns_empty():
    assert format_time_gap_note(None) == ""


def test_recent_activity_returns_empty():
    recent = datetime.now(timezone.utc) - timedelta(hours=2)
    assert format_time_gap_note(recent) == ""


def test_few_days_gap_mentions_days():
    gap = datetime.now(timezone.utc) - timedelta(days=3)
    note = format_time_gap_note(gap)
    assert "3 día" in note


def test_months_gap_mentions_months():
    gap = datetime.now(timezone.utc) - timedelta(days=180)
    note = format_time_gap_note(gap)
    assert "mes" in note
    assert "6 mes" in note


def test_naive_datetime_does_not_raise():
    naive = datetime.now() - timedelta(days=40)
    note = format_time_gap_note(naive)
    assert "mes" in note
