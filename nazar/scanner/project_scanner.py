"""Project Scanner - Herhangi bir projeyi tarar, teknik mimariyi analiz eder."""
import os
import re
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

from nazar.scanner.patterns import (
    IGNORE_DIRS, TECH_MARKERS, API_PATTERNS, TEST_PATTERNS,
    SCREEN_PATTERNS, STATE_LIBS, NAVIGATION_LIBS,
    SOURCE_EXTS, EXT_TO_LANG, EXT_TO_API_LANG,
)


@dataclass
class ScanResult:
    project_name: str = ""
    tech_stack: str = "unknown"
    framework: Optional[str] = None
    languages: List[str] = field(default_factory=list)
    screens: List[Dict] = field(default_factory=list)
    api_endpoints: List[Dict] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    dependencies: Dict[str, str] = field(default_factory=dict)
    test_files: List[str] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)
    architecture_pattern: str = "unknown"
    has_navigation: bool = False
    has_state_management: bool = False
    state_management_lib: Optional[str] = None
    navigation_lib: Optional[str] = None
    base_url: Optional[str] = None

    @property
    def screen_count(self) -> int:
        return len(self.screens)

    @property
    def api_endpoint_count(self) -> int:
        return len(self.api_endpoints)

    @property
    def existing_test_count(self) -> int:
        return len(self.test_files)

    def to_dict(self) -> dict:
        return asdict(self)


class ProjectScanner:
    def __init__(self, project_path: str):
        self.root = Path(project_path).resolve()
        self.result = ScanResult()

    def scan(self) -> ScanResult:
        self.result.project_name = self.root.name
        self._detect_tech_stack()
        self._collect_source_files()
        self._find_screens()
        self._find_api_endpoints()
        self._find_test_files()
        self._detect_state_management()
        self._detect_navigation()
        self._detect_base_url()
        self._detect_architecture()
        self._find_config_files()
        return self.result

    def _detect_tech_stack(self):
        self._read_dependencies()
        for tech, markers in TECH_MARKERS.items():
            for keyword, marker_file in markers:
                if "*" in marker_file:
                    if list(self.root.glob(marker_file)):
                        self.result.tech_stack = tech
                        break
                else:
                    path = self.root / marker_file
                    if path.exists():
                        if keyword is None or keyword in path.read_text(errors="ignore"):
                            self.result.tech_stack = tech
                            break
            if self.result.tech_stack != "unknown":
                break
        self.result.framework = self.result.tech_stack

    def _read_dependencies(self):
        pkg = self.root / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                self.result.dependencies = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            except json.JSONDecodeError:
                pass

        pubspec = self.root / "pubspec.yaml"
        if pubspec.exists():
            try:
                import yaml
                data = yaml.safe_load(pubspec.read_text())
                if data and "dependencies" in data:
                    self.result.dependencies = {k: str(v) for k, v in data["dependencies"].items()}
            except Exception:
                pass

        for req_file in ["requirements.txt", "pyproject.toml"]:
            path = self.root / req_file
            if path.exists():
                for line in path.read_text(errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("["):
                        name = re.split(r"[><=!~\[]", line, 1)[0].strip().strip('"')
                        if name:
                            self.result.dependencies[name] = ""

    def _collect_source_files(self):
        found_langs = set()
        for root_dir, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in SOURCE_EXTS:
                    rel = os.path.relpath(os.path.join(root_dir, f), self.root)
                    self.result.source_files.append(rel)
                    if ext in EXT_TO_LANG:
                        found_langs.add(EXT_TO_LANG[ext])
        self.result.languages = sorted(found_langs)

    def _find_screens(self):
        patterns = SCREEN_PATTERNS.get(self.result.tech_stack, SCREEN_PATTERNS["generic"])
        seen = set()
        for src_file in self.result.source_files:
            try:
                content = (self.root / src_file).read_text(errors="ignore")
            except Exception:
                continue
            for pattern, comp_type in patterns:
                for match in re.finditer(pattern, content):
                    name = match.group(1)
                    key = f"{name}:{src_file}"
                    if name and len(name) > 1 and not name.startswith("_") and key not in seen:
                        seen.add(key)
                        self.result.screens.append({"name": name, "file": src_file, "type": comp_type})

    def _find_api_endpoints(self):
        seen = set()
        for src_file in self.result.source_files:
            ext = Path(src_file).suffix.lower()
            lang = EXT_TO_API_LANG.get(ext)
            if not lang or lang not in API_PATTERNS:
                continue
            try:
                content = (self.root / src_file).read_text(errors="ignore")
            except Exception:
                continue
            for pattern, default_method in API_PATTERNS[lang]:
                for match in re.finditer(pattern, content, re.DOTALL):
                    groups = match.groups()
                    if len(groups) == 2 and default_method is None:
                        method, url = groups[0].upper(), groups[1]
                    elif len(groups) == 1:
                        method, url = (default_method or "GET"), groups[0]
                    else:
                        continue
                    key = f"{method}:{url}"
                    if url and len(url) > 1 and key not in seen:
                        seen.add(key)
                        self.result.api_endpoints.append({"method": method, "url": url, "file": src_file})

    def _find_test_files(self):
        for src_file in self.result.source_files:
            filename = os.path.basename(src_file).lower()
            if any(re.match(p, filename) for p in TEST_PATTERNS):
                self.result.test_files.append(src_file)

    def _detect_state_management(self):
        for lib_name, packages in STATE_LIBS.items():
            if any(pkg in self.result.dependencies for pkg in packages):
                self.result.has_state_management = True
                self.result.state_management_lib = lib_name
                return

    def _detect_navigation(self):
        for lib_name, packages in NAVIGATION_LIBS.items():
            if any(pkg in self.result.dependencies for pkg in packages):
                self.result.has_navigation = True
                self.result.navigation_lib = lib_name
                return

    def _detect_base_url(self):
        patterns = [
            r"""(?:BASE_URL|API_URL|BACKEND_URL)\s*[:=]\s*[`'"](https?://[^`'"]+)[`'"]""",
            r"""baseURL\s*[:=]\s*[`'"](https?://[^`'"]+)[`'"]""",
        ]
        search_files = list(self.root.glob(".env*")) + [self.root / f for f in self.result.source_files[:100]]
        for path in search_files:
            try:
                content = path.read_text(errors="ignore")
                for p in patterns:
                    match = re.search(p, content)
                    if match:
                        self.result.base_url = match.group(1)
                        return
            except Exception:
                pass

    def _detect_architecture(self):
        dirs = set()
        for src_file in self.result.source_files:
            parts = Path(src_file).parts
            for p in parts[:2]:
                dirs.add(p.lower())

        if {"domain", "data", "presentation"} <= dirs:
            self.result.architecture_pattern = "clean-architecture"
        elif {"models", "views", "controllers"} <= dirs:
            self.result.architecture_pattern = "mvc"
        elif {"models", "views", "viewmodels"} <= dirs:
            self.result.architecture_pattern = "mvvm"
        elif {"features"} <= dirs:
            self.result.architecture_pattern = "feature-based"
        elif {"screens", "components"} <= dirs:
            self.result.architecture_pattern = "component-based"

    def _find_config_files(self):
        config_patterns = [
            "package.json", "pubspec.yaml", "go.mod", "Cargo.toml",
            "requirements.txt", "pyproject.toml", "Gemfile", "composer.json",
            "tsconfig.json", "Dockerfile", "docker-compose.yml", "Makefile",
        ]
        for pattern in config_patterns:
            for match in self.root.glob(pattern):
                if match.is_file():
                    self.result.config_files.append(match.name)
