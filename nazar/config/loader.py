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
    # .nazar/config.yaml destegi - yeni alanlar
    profile: Optional[str] = None
    min_confidence: int = 50
    ignore_rules: List[str] = field(default_factory=list)
    custom_dict: List[str] = field(default_factory=list)


class ConfigLoader:
    """nazar.yaml dosyasini yukler."""

    CONFIG_NAMES = ["nazar.yaml", "nazar.yml", ".nazar.yaml", ".nazar.yml"]
    DOT_NAZAR_CONFIG = [".nazar/config.yaml", ".nazar/config.yml"]

    @classmethod
    def load(cls, project_path: str) -> NazarConfig:
        """Proje dizininden nazar.yaml yukle. .nazar/config.yaml de desteklenir."""
        root = Path(project_path)
        # Once .nazar/config.yaml kontrol et (oncelikli)
        for name in cls.DOT_NAZAR_CONFIG:
            config_file = root / name
            if config_file.exists():
                return cls._parse(config_file)
        # Sonra proje kokunde nazar.yaml
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
        # .nazar/config.yaml yeni alanlari
        if "profile" in data and isinstance(data["profile"], str):
            config.profile = data["profile"]
        if "min_confidence" in data and isinstance(data["min_confidence"], int):
            config.min_confidence = data["min_confidence"]
        ignore_rules = data.get("ignore_rules", [])
        if isinstance(ignore_rules, list):
            config.ignore_rules = ignore_rules
        custom_dict = data.get("custom_dict", [])
        if isinstance(custom_dict, list):
            config.custom_dict = custom_dict
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
            "# Profil ve filtreleme (.nazar/config.yaml destegi)",
            "# profile: security  # full, frontend, backend, security, mobile, ci",
            "# min_confidence: 60  # 0-100 arasi guven esigi",
            "# ignore_rules: [todo_count, naming_conventions]",
            "# custom_dict: [myapp, signup]  # Spell check icin ozel sozluk", "",
        ]
        Path(output_path).write_text("\n".join(lines))
        return output_path
