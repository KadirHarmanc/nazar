"""Tests for reporters."""
from nazar.reporters.json_reporter import JSONReporter
from nazar.reporters.markdown_reporter import MarkdownReporter
import json


SAMPLE_RESULTS = [
    {"name": "test1", "type": "security", "subtype": "secrets", "passed": True, "duration": 0.1, "detail": "ok", "priority": "high"},
    {"name": "test2", "type": "security", "subtype": "api_keys", "passed": False, "duration": 0.2, "detail": "found", "priority": "critical"},
    {"name": "test3", "type": "code_quality", "subtype": "complexity", "passed": True, "duration": 0.05, "detail": "ok", "priority": "medium"},
]
SAMPLE_PLAN = {"tests": SAMPLE_RESULTS, "total_tests": 3}


def test_json_reporter_output():
    """JSON reporter produces valid JSON."""
    reporter = JSONReporter()
    output = reporter.generate(SAMPLE_RESULTS, SAMPLE_PLAN)
    d = json.loads(output)
    assert d["summary"]["total"] == 3
    assert d["summary"]["passed"] == 2
    assert d["summary"]["failed"] == 1


def test_json_reporter_grade():
    """Grade calculation works."""
    assert JSONReporter._grade(98) == "A+"
    assert JSONReporter._grade(85) == "B"
    assert JSONReporter._grade(50) == "F"


def test_markdown_reporter_output():
    """Markdown reporter produces valid markdown."""
    reporter = MarkdownReporter()
    output = reporter.generate(SAMPLE_RESULTS, SAMPLE_PLAN)
    assert "# Nazar Test Raporu" in output
    assert "Basarisiz Testler" in output
    assert "test2" in output


def test_markdown_reporter_grade():
    """Grade calculation works."""
    assert MarkdownReporter._grade(95) == "A"
    assert MarkdownReporter._grade(72) == "C-"
    assert MarkdownReporter._grade(30) == "F"
