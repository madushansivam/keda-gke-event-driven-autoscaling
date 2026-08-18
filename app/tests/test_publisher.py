"""
Tests for publisher.py logic that doesn't require a live/emulated Pub/Sub connection.
"""
from app.publisher import build_message_payload


def test_build_message_payload_returns_bytes():
    payload = build_message_payload(0)
    assert isinstance(payload, bytes)


def test_build_message_payload_contains_id():
    payload = build_message_payload(42)
    assert b"42" in payload


def test_build_message_payload_format():
    payload = build_message_payload(7)
    assert payload == b"event-7"


def test_build_message_payload_different_ids_differ():
    payload_a = build_message_payload(1)
    payload_b = build_message_payload(2)
    assert payload_a != payload_b
