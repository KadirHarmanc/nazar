"""Tests for test planner."""
from nazar.scanner.project_scanner import ProjectScanner, ScanResult
from nazar.planner.test_planner import TestPlanner, TestPlan


def test_planner_creates_plan(tmp_path):
    """Planner creates a non-empty plan."""
    (tmp_path / "app.py").write_text("import os\nprint('hello')\n")
    scanner = ProjectScanner(str(tmp_path))
    scan_result = scanner.scan()
    planner = TestPlanner(scan_result)
    plan = planner.create_plan()
    assert plan.total_tests > 0
    assert len(plan.tests) > 0
    assert len(plan.categories) > 0


def test_planner_includes_security(tmp_path):
    """Plan always includes security tests."""
    (tmp_path / "main.py").write_text("x = 1\n")
    scanner = ProjectScanner(str(tmp_path))
    planner = TestPlanner(scanner.scan())
    plan = planner.create_plan()
    sec_tests = [t for t in plan.tests if t["type"] == "security"]
    assert len(sec_tests) > 0


def test_plan_to_dict(tmp_path):
    """TestPlan.to_dict serializes correctly."""
    (tmp_path / "main.py").write_text("x = 1\n")
    scanner = ProjectScanner(str(tmp_path))
    planner = TestPlanner(scanner.scan())
    plan = planner.create_plan()
    d = plan.to_dict()
    assert "tests" in d
    assert "total_tests" in d
    assert d["total_tests"] == len(d["tests"])


def test_planner_estimates_duration(tmp_path):
    """Duration estimation works."""
    (tmp_path / "main.py").write_text("x = 1\n")
    scanner = ProjectScanner(str(tmp_path))
    planner = TestPlanner(scanner.scan())
    plan = planner.create_plan()
    assert plan.estimated_duration
    assert "s" in plan.estimated_duration or "m" in plan.estimated_duration
