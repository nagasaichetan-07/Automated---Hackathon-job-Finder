"""
Unit tests for Celery background tasks.

Verifies that:
1. proof_of_life_task executes successfully.
2. Returns expected structured response with timestamp and echo payload.
"""

from apps.worker.tasks import proof_of_life_task


def test_proof_of_life_task_execution():
    """Verify synchronous execution of the proof-of-life ping task."""
    result = proof_of_life_task(echo="test_ping")
    assert isinstance(result, dict)
    assert result["status"] == "success"
    assert result["echo"] == "test_ping"
    assert "worker_timestamp" in result


def test_proof_of_life_task_default_arg():
    """Verify task executes with default parameter."""
    result = proof_of_life_task()
    assert result["status"] == "success"
    assert result["echo"] == "pong"
