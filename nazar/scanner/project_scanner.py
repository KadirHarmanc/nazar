"""Project Scanner - Herhangi bir projeyi tarar, teknik mimariyi analiz eder."""
import os
import re
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

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


# OPT 5 - Pre-compile base_url patterns at module level
_BASE_URL_PATTERNS = [
    re.compile(r"""(?:BASE_URL|API_URL|BACKEND_URL)\s*[:=]\s*[`'"](https?://[^`'"]+)[`'"]"""),
    re.compile(r"""baseURL\s*[:=]\s*[`'"](https?://[^`'"]+)[`'"]"""),
]


class ProjectScanner:
    def __init__(self, project_path: str):
        self.root = Path(project_path).resolve()
        self.result = ScanResult()
        # OPT 2 - Content cache: dosya iceriklerini bir kez oku, tekrar kullan
        self._content_cache: Dict[str, str] = {}

    # OPT 2 - Cached file read
    def _read_file(self, rel_path: str) -> str:
        """Dosya oku ve cache'le. Ayni dosya iki kez okunmaz."""
        if rel_path in self._content_cache:
            return self._content_cache[rel_path]
        try:
            target = (self.root / rel_path).resolve()
            if not str(target).startswith(str(self.root)):
                return ""
            content = target.read_text(errors="ignore")
            if len(content) < 500_000:
                self._content_cache[rel_path] = content
            return content
        except Exception:
            return ""

    def scan(self) -> ScanResult:
        self.result.project_name = self.root.name
        self._detect_tech_stack()
        self._collect_source_files()
        # OPT 1 - Merged: screens + endpoints tek geciste, paralel
        self._find_screens_and_endpoints()
        self._find_test_files()
        self._detect_state_management()
        self._detect_navigation()
        self._detect_base_url()
        self._detect_architecture()
        self._find_config_files()
        return self.result

    # OPT 3 - Tech stack detection with cached file reads
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
                        # OPT 3 - cached read instead of raw read_text
                        content = self._read_file(marker_file)
                        if keyword is None or keyword in content:
                            self.result.tech_stack = tech
                            break
            if self.result.tech_stack != "unknown":
                break
        self.result.framework = self.result.tech_stack

    def _read_dependencies(self):
        pkg = self.root / "package.json"
        if pkg.exists():
            try:
                # OPT 3 - cached read
                data = json.loads(self._read_file("package.json"))
                self.result.dependencies = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            except json.JSONDecodeError:
                pass

        pubspec = self.root / "pubspec.yaml"
        if pubspec.exists():
            try:
                import yaml
                data = yaml.safe_load(self._read_file("pubspec.yaml"))
                if data and "dependencies" in data:
                    self.result.dependencies = {k: str(v) for k, v in data["dependencies"].items()}
            except Exception:
                pass

        for req_file in ["requirements.txt", "pyproject.toml"]:
            path = self.root / req_file
            if path.exists():
                # OPT 3 - cached read
                content = self._read_file(req_file)
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("["):
                        name = re.split(r"[><=!~\[]", line, 1)[0].strip().strip('"')
                        if name:
                            self.result.dependencies[name] = ""

    # OPT 4 - os.scandir instead of os.walk
    def _collect_source_files(self):
        found_langs = set()
        self._scandir_recursive(self.root, found_langs)
        self.result.languages = sorted(found_langs)

    def _scandir_recursive(self, directory: Path, found_langs: set):
        """OPT 4 - Recursive os.scandir, os.walk yerine daha hizli."""
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name not in IGNORE_DIRS:
                                self._scandir_recursive(Path(entry.path), found_langs)
                        elif entry.is_file(follow_symlinks=False):
                            ext = os.path.splitext(entry.name)[1].lower()
                            if ext in SOURCE_EXTS:
                                rel = os.path.relpath(entry.path, self.root)
                                self.result.source_files.append(rel)
                                if ext in EXT_TO_LANG:
                                    found_langs.add(EXT_TO_LANG[ext])
                    except PermissionError:
                        continue
        except PermissionError:
            pass

    # OPT 1 - Merged parallel scan: screens + endpoints tek geciste
    def _find_screens_and_endpoints(self):
        """Ekran ve API endpoint tespitini tek paralel geciste yapar."""
        # OPT 5 - Pre-compile all screen patterns
        screen_pats = SCREEN_PATTERNS.get(self.result.tech_stack, SCREEN_PATTERNS["generic"])
        compiled_screen = [(re.compile(p), ct) for p, ct in screen_pats]

        # OPT 5 - Pre-compile all API patterns per language
        compiled_api: Dict[str, list] = {}
        for lang, patterns in API_PATTERNS.items():
            compiled_api[lang] = [(re.compile(p, re.DOTALL), dm) for p, dm in patterns]

        # UI dosyalari (screen tespiti icin)
        ui_exts = {".tsx", ".jsx", ".ts", ".js", ".dart", ".swift", ".kt", ".vue", ".svelte"}

        # Taranacak dosyalari belirle: test dosyalari haric, max 200
        scan_files = [f for f in self.result.source_files if "test" not in f.lower()][:200]

        seen_screens = set()
        seen_endpoints = set()
        all_screens = []
        all_endpoints = []

        def process_file(src_file: str):
            """Tek dosyayi oku, hem screen hem endpoint cikar."""
            file_screens = []
            file_endpoints = []

            # OPT 2 - cached read
            content = self._read_file(src_file)
            if not content or len(content) > 200_000:
                return file_screens, file_endpoints

            ext = os.path.splitext(src_file)[1].lower()

            # Screen detection (sadece UI dosyalari icin)
            if ext in ui_exts:
                for compiled_pat, comp_type in compiled_screen:
                    for match in compiled_pat.finditer(content):
                        name = match.group(1)
                        key = f"{name}:{src_file}"
                        if name and len(name) > 1 and not name.startswith("_"):
                            file_screens.append((key, {"name": name, "file": src_file, "type": comp_type}))

            # API endpoint detection
            lang = EXT_TO_API_LANG.get(ext)
            if lang and lang in compiled_api:
                for compiled_pat, default_method in compiled_api[lang]:
                    for match in compiled_pat.finditer(content):
                        groups = match.groups()
                        if len(groups) == 2 and default_method is None:
                            method, url = groups[0].upper(), groups[1]
                        elif len(groups) == 1:
                            method, url = (default_method or "GET"), groups[0]
                        else:
                            continue
                        ep_key = f"{method}:{url}"
                        if url and len(url) > 1:
                            file_endpoints.append((ep_key, {"method": method, "url": url, "file": src_file}))

            return file_screens, file_endpoints

        # OPT 1 - ThreadPoolExecutor ile paralel dosya okuma
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(process_file, f): f for f in scan_files}
            for future in as_completed(futures):
                try:
                    file_screens, file_endpoints = future.result()
                    for key, screen in file_screens:
                        if key not in seen_screens:
                            seen_screens.add(key)
                            all_screens.append(screen)
                    for key, endpoint in file_endpoints:
                        if key not in seen_endpoints:
                            seen_endpoints.add(key)
                            all_endpoints.append(endpoint)
                except Exception:
                    continue

        self.result.screens = all_screens
        self.result.api_endpoints = all_endpoints

    def _find_test_files(self):
        compiled_test = [re.compile(p) for p in TEST_PATTERNS]
        for src_file in self.result.source_files:
            filename = os.path.basename(src_file).lower()
            if any(pat.match(filename) for pat in compiled_test):
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

    # OPT 5 - Pre-compiled base_url patterns (module-level _BASE_URL_PATTERNS)
    def _detect_base_url(self):
        search_files = []
        # .env dosyalari
        for env_path in self.root.glob(".env*"):
            try:
                rel = os.path.relpath(env_path, self.root)
                search_files.append(rel)
            except Exception:
                pass
        # Ilk 30 kaynak dosya
        search_files.extend(self.result.source_files[:30])

        for rel_path in search_files:
            try:
                # OPT 2 - cached read
                content = self._read_file(rel_path)
                # OPT 5 - pre-compiled patterns
                for compiled_pat in _BASE_URL_PATTERNS:
                    match = compiled_pat.search(content)
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
