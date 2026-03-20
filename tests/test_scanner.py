"""Tests for project scanner."""
import os
import tempfile
from pathlib import Path
from nazar.scanner.project_scanner import ProjectScanner


def test_scanner_detects_python_project(tmp_path):
    """Scan a minimal Python project."""
    (tmp_path / "requirements.txt").write_text("flask>=2.0")
    (tmp_path / "app.py").write_text("from flask import Flask\napp = Flask(__name__)\n")
    scanner = ProjectScanner(str(tmp_path))
    result = scanner.scan()
    assert result.project_name
    assert "Python" in result.languages


def test_scanner_detects_js_project(tmp_path):
    """Scan a minimal JS project."""
    (tmp_path / "package.json").write_text('{"name":"test","dependencies":{"express":"^4.0"}}')
    (tmp_path / "index.js").write_text("const express = require('express');\n")
    scanner = ProjectScanner(str(tmp_path))
    result = scanner.scan()
    assert result.project_name
    assert "JavaScript" in result.languages


def test_scanner_empty_project(tmp_path):
    """Scan an empty directory."""
    scanner = ProjectScanner(str(tmp_path))
    result = scanner.scan()
    assert result.project_name
    assert result.screen_count == 0


def test_scan_result_to_dict(tmp_path):
    """ScanResult.to_dict works."""
    (tmp_path / "main.py").write_text("print('hello')\n")
    scanner = ProjectScanner(str(tmp_path))
    result = scanner.scan()
    d = result.to_dict()
    assert isinstance(d, dict)
    assert "project_name" in d
