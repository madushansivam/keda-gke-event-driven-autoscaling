"""
Tests consumer logic without touching real GCP Pub/Sub.
"""
from app.consumer import simulate_work

def test_simulate_work_returns_duration_in_range():
    duration = simulate_work()
    assert 0.5 <= duration <= 2.5

def test_simulate_work_returns_a_float():
    duration = simulate_work()
    assert isinstance(duration, float)
