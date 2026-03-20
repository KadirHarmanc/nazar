"""Config Loader - nazar.yaml yukleyici."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional

import yaml


@dataclass
class NazarConfig:
    """Nazar yapilandirmasi."""
    exclude_dirs: List[str] = field(default_factory=lambda: ["node_modules", ".git", "dist", "build", "vendor", "venv"])
    exclude_files: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    severity: Dict[str, str] = field(default_factory=dict)
    disabled_categories: List[str] = field(default_factory=list)
    disabled_rules: List[str] = field(default_factory=list)
    max_file_size_mb: float = 10.0
    max_files: int = 500
    timeout_seconds: int = 300
    parallel_workers: int = 4
    cache_enabled: bool = True
    output_format: str = "html"
    report_path: str = "nazar-report.html"
    plugin_dirs: List[str] = field(default_factory=list)
    custom_patterns: Dict[str, str] = field(default_factory=dict)


class ConfigLoader:
    """nazar.yaml dosyasini yukler."""

    CONFIG_NAMES = ["nazar.yaml", "nazar.yml", ".nazar.yaml", ".nazar.yml"]

    @classmethod
    def load(cls, project_path: str) -> NazarConfig:
        """Proje dizininden nazar.yaml yukle."""
        root = Path(project_path)
        for name in cls.CONFIG_NAMES:
            config_file = root / name
            if config_file.exists():
                return cls._parse(config_file)
        return NazarConfig()

    @classmethod
    def _parse(cls, config_file: Path) -> NazarConfig:
        """YAML dosyasini parse et."""
        try:
            with open(config_file) as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            return NazarConfig()
        config = NazarConfig()
        exc = data.get("exclude", {})
        if isinstance(exc, dict):
            config.exclude_dirs = exc.get("dirs", config.exclude_dirs)
            config.exclude_files = exc.get("files", config.exclude_files)
            config.exclude_patterns = exc.get("patterns", config.exclude_patterns)
        sev = data.get("severity", {})
        if isinstance(sev, dict):
            config.severity = sev
        dis = data.get("disable", {})
        if isinstance(dis, dict):
            config.disabled_categories = dis.get("categories", [])
            config.disabled_rules = dis.get("rules", [])
        lim = data.get("limits", {})
        if isinstance(lim, dict):
            config.max_file_size_mb = lim.get("max_file_size_mb", config.max_file_size_mb)
            config.max_files = lim.get("max_files", config.max_files)
            config.timeout_seconds = lim.get("timeout", config.timeout_seconds)
        config.parallel_workers = data.get("parallel", config.parallel_workers)
        config.cache_enabled = data.get("cache", config.cache_enabled)
        config.output_format = data.get("output", config.output_format)
        config.report_path = data.get("report", config.report_path)
        plugins = data.get("plugins", [])
        if isinstance(plugins, list):
            config.plugin_dirs = plugins
        patterns = data.get("custom_patterns", {})
        if isinstance(patterns, dict):
            config.custom_patterns = patterns
        return config

    @classmethod
    def generate_template(cls, output_path: str) -> str:
        """nazar.yaml sablonu olustur."""
        lines = [
            "# Nazar Configuration", "",
            "exclude:", "  dirs: [node_modules, .git, dist, build, vendor, venv, .venv, __pycache__]",
            "  files: []", '  patterns: ["*.min.js", "*.bundle.js"]', "",
            "severity: {}", "  # secrets: critical", "",
            "disable:", "  categories: []  # visual, accessibility",
            "  rules: []  # todo_count, short_vars", "",
            "limits:", "  max_file_size_mb: 10", "  max_files: 500", "  timeout: 300", "",
            "parallel: 4", "cache: true", "output: html",
            "report: nazar-report.html", "plugins: []", "custom_patterns: {}", "",
        ]
        Path(output_path).write_text("\n".join(lines))
        return output_path
