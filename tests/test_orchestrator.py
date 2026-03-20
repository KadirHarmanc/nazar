"""Tests for test orchestrator."""
from nazar.runners.orchestrator import TestOrchestrator


def test_orchestrator_runs_security_test(tmp_path):
    """Orchestrator can run a security test."""
    (tmp_path / "app.py").write_text("x = 1\n")
    plan = {"tests": [
        {"name": "test sec", "type": "security", "subtype": "secrets", "priority": "critical"}
    ]}
    orch = TestOrchestrator(str(tmp_path), plan)
    results = orch.run_all()
    assert len(results) == 1
    assert "passed" in results[0]
    assert "duration" in results[0]


def test_orchestrator_runs_doc_test(tmp_path):
    """Orchestrator can run documentation test."""
    (tmp_path / "README.md").write_text("# My Project\nSome content here\n" * 10)
    plan = {"tests": [
        {"name": "test doc", "type": "documentation", "subtype": "readme_exists", "priority": "medium"}
    ]}
    orch = TestOrchestrator(str(tmp_path), plan)
    results = orch.run_all()
    assert results[0]["passed"] is True


def test_orchestrator_unknown_type(tmp_path):
    """Unknown test type returns SKIP."""
    plan = {"tests": [
        {"name": "test unknown", "type": "nonexistent", "subtype": "x", "priority": "low"}
    ]}
    orch = TestOrchestrator(str(tmp_path), plan)
    results = orch.run_all()
    assert results[0]["passed"] is True
    assert "SKIP" in results[0]["detail"]


def test_orchestrator_how_to_fix(tmp_path):
    """How to fix info is added for known failures."""
    secret_content = "password = 'supersecretpassword123'\n"
    (tmp_path / "config.py").write_text(secret_content)
    plan = {"tests": [
        {"name": "test secrets", "type": "security", "subtype": "secrets", "priority": "critical"}
    ]}
    orch = TestOrchestrator(str(tmp_path), plan)
    results = orch.run_all()
    assert results[0]["passed"] is False
    assert "how_to_fix" in results[0]
