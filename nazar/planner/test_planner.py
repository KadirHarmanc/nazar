"""Test Planner - Scan sonucuna dayanarak kapsamli test plani olusturur."""
from dataclasses import dataclass, field, asdict
from typing import List, Dict
from nazar.scanner.project_scanner import ScanResult


@dataclass
class TestPlan:
    categories: List[Dict] = field(default_factory=list)
    tests: List[Dict] = field(default_factory=list)
    total_tests: int = 0
    estimated_duration: str = "0s"

    def to_dict(self) -> dict:
        return asdict(self)


class TestPlanner:
    # Proje tiplerine gore hangi kategoriler gecerli
    MOBILE_STACKS = {"react-native", "flutter", "ios-native", "android-native"}
    IOS_STACKS = {"react-native", "flutter", "ios-native"}
    ANDROID_STACKS = {"react-native", "flutter", "android-native"}
    WEB_STACKS = {"nextjs", "nuxt", "react", "vue", "angular", "svelte", "express", "nestjs"}
    BACKEND_STACKS = {"django", "fastapi", "flask", "express", "nestjs", "rails", "laravel", "spring", "go", "rust"}
    HAS_UI = MOBILE_STACKS | WEB_STACKS | {"django", "flask", "rails", "laravel"}

    def __init__(self, scan_result: ScanResult, profile: str = "full"):
        self.scan = scan_result
        self.plan = TestPlan()
        self.profile = profile
        self._profile_categories = self._resolve_profile(profile)
        self._stack = scan_result.tech_stack
        self._langs = set(scan_result.languages)
        self._has_ui = self._stack in self.HAS_UI or bool(scan_result.screens)
        self._is_mobile = self._stack in self.MOBILE_STACKS
        self._is_backend = self._stack in self.BACKEND_STACKS
        self._has_python = "Python" in self._langs
        self._has_js = "JavaScript" in self._langs or "TypeScript" in self._langs
        self._has_go = "Go" in self._langs
        self._has_rust = "Rust" in self._langs

    def _resolve_profile(self, profile: str) -> set:
        """Profil kategorilerini coz."""
        from nazar.planner.profiles import get_profile_categories
        cats = get_profile_categories(profile)
        return set(cats) if cats else set()  # bos = full

    def _should_run(self, category: str) -> bool:
        """Bu kategori secili profilde calistirilmali mi?"""
        if not self._profile_categories:  # full profil
            return True
        return category in self._profile_categories

    def create_plan(self) -> TestPlan:
        # Evrensel - her proje icin (profil filtreli)
        if self._should_run("security"):
            self._plan_security_tests()
        if self._should_run("git"):
            self._plan_git_hygiene_tests()
        if self._should_run("license"):
            self._plan_license_tests()
        if self._should_run("documentation"):
            self._plan_documentation_tests()
        if self._should_run("structure"):
            self._plan_structure_tests()
        if self._should_run("performance"):
            self._plan_performance_tests()
        if self._should_run("sca"):
            self._plan_sca_tests()
        if self._should_run("yaml_rules"):
            self._plan_yaml_rule_tests()

        # Kod iceren projeler (profil filtreli)
        if self._langs:
            if self._should_run("code_quality"):
                self._plan_code_quality_tests()
            if self._should_run("import_graph"):
                self._plan_import_graph_tests()
            if self._should_run("error_handling"):
                self._plan_error_handling_tests()
            if self._should_run("naming"):
                self._plan_naming_convention_tests()
            if self._should_run("cross_file"):
                self._plan_cross_file_tests()

        # Dependency olan projeler
        if self.scan.dependencies and self._should_run("dependency"):
            self._plan_dependency_tests()

        # Env/config olan projeler
        if self.scan.config_files:
            if self._should_run("env"):
                self._plan_env_variable_tests()
            if self._should_run("config"):
                self._plan_config_tests()

        # API olan projeler
        if self.scan.api_endpoints and self._should_run("api"):
            self._plan_api_tests()

        # TypeScript/Dart projeleri
        if ("TypeScript" in self._langs or "Dart" in self._langs) and self._should_run("type_safety"):
            self._plan_type_safety_tests()

        # Python projeleri
        if self._has_python and self._should_run("ast_analysis"):
            self._plan_ast_analysis_tests()

        # Backend veya fullstack (taint tracking)
        if (self._is_backend or self._has_python or self._has_js) and self._should_run("taint"):
            self._plan_taint_tracking_tests()

        # UI Analiz (MVP)
        if self._should_run("ui_analysis"):
            self._plan_ui_analysis_tests()

        # UI Quality (Core)
        if self._has_ui:
            if self._should_run("spell_check"):
                self._plan_spell_check_tests()
            if self._should_run("ui_quality"):
                self._plan_ui_quality_tests()

        # UI olan projeler
        if self._has_ui:
            if self._should_run("ux_text"):
                self._plan_ux_text_tests()
            if self._should_run("ui_component"):
                self._plan_ui_component_tests()
            if self._should_run("visual"):
                self._plan_visual_tests()

        # Mobil projeler
        if self._is_mobile and self._should_run("accessibility"):
            self._plan_accessibility_tests()

        # iOS projeler
        if self._stack in self.IOS_STACKS and self._should_run("appstore"):
            self._plan_appstore_tests()

        # Android projeler
        if (self._stack in self.ANDROID_STACKS or any("android" in f.lower() for f in self.scan.config_files)) and self._should_run("playstore"):
            self._plan_playstore_tests()

        # YAML UI
        if self._should_run("yaml_ui"):
            self._plan_yaml_ui_tests()

        # i18n Deep
        if self._has_ui and self._should_run("i18n_deep"):
            self._plan_i18n_deep_tests()

        # Responsive
        if self._has_ui and self._should_run("responsive"):
            self._plan_responsive_tests()

        # Visual Regression
        if self._should_run("visual_regression"):
            self._plan_visual_regression_tests()

        # Performance Static
        if self._should_run("perf_static"):
            self._plan_perf_static_tests()

        # Docker
        if self._should_run("docker"):
            self._plan_docker_tests()

        # Compliance (OWASP, GDPR/KVKK, SOC2, PCI-DSS)
        if self._should_run("compliance"):
            self._plan_compliance_tests()

        self.plan.total_tests = len(self.plan.tests)
        self.plan.estimated_duration = self._estimate_duration()
        return self.plan

    def _add_category(self, name: str, tests: List[Dict], priority: str):
        if tests:
            self.plan.tests.extend(tests)
            self.plan.categories.append({"name": name, "test_count": len(tests), "priority": priority})

    def _plan_security_tests(self):
        tests = [
            # --- Mevcut testler ---
            {"name": "SEC: Hardcoded secrets in source code", "type": "security", "subtype": "secrets", "priority": "critical"},
            {"name": "SEC: API keys in source code", "type": "security", "subtype": "api_keys", "priority": "critical"},
            {"name": "SEC: Private keys in repo", "type": "security", "subtype": "private_keys", "priority": "critical"},
            {"name": "SEC: API endpoints use HTTPS", "type": "security", "subtype": "https", "priority": "high"},
            {"name": "SEC: No dangerous function usage", "type": "security", "subtype": "dangerous_functions", "priority": "high"},
            {"name": "SEC: No SQL injection patterns", "type": "security", "subtype": "sql_injection", "priority": "high"},
            {"name": "SEC: No hardcoded IPs or internal URLs", "type": "security", "subtype": "hardcoded_ips", "priority": "medium"},
            {"name": "SEC: Sensitive files not in repo", "type": "security", "subtype": "sensitive_files", "priority": "critical"},
            {"name": "SEC: Comprehensive secret scan (50+ patterns)", "type": "security", "subtype": "secrets_comprehensive", "priority": "critical"},
            {"name": "SEC: Cloud provider credentials (AWS/GCP/Azure)", "type": "security", "subtype": "cloud_keys", "priority": "critical"},
            {"name": "SEC: Payment service keys (Stripe/Square)", "type": "security", "subtype": "payment_keys", "priority": "critical"},
            {"name": "SEC: Communication tokens (Slack/Discord/Twilio)", "type": "security", "subtype": "communication_keys", "priority": "high"},
            {"name": "SEC: VCS tokens (GitHub/GitLab/Bitbucket)", "type": "security", "subtype": "vcs_keys", "priority": "high"},
            {"name": "SEC: Database connection strings", "type": "security", "subtype": "db_connection_strings", "priority": "critical"},
            {"name": "SEC: Cryptographic private keys in repo", "type": "security", "subtype": "crypto_keys", "priority": "critical"},
            {"name": "SEC: Command injection risk", "type": "security", "subtype": "command_injection", "priority": "critical"},
            {"name": "SEC: Path traversal risk", "type": "security", "subtype": "path_traversal", "priority": "high"},
            {"name": "SEC: Insecure deserialization", "type": "security", "subtype": "insecure_deserialization", "priority": "critical"},
            {"name": "SEC: Weak cryptography (MD5/SHA1/DES)", "type": "security", "subtype": "weak_crypto", "priority": "high"},
            {"name": "SEC: CORS wildcard misconfiguration", "type": "security", "subtype": "cors_wildcard", "priority": "medium"},
            {"name": "SEC: Debug mode enabled", "type": "security", "subtype": "debug_mode", "priority": "high"},
            # --- DEEP SECURITY: Hassas Veri Sizintisi ---
            {"name": "DEEP-SEC: Hardcoded credentials in config", "type": "security", "subtype": "hardcoded_credentials", "priority": "critical"},
            {"name": "DEEP-SEC: Tokens/keys in URL parameters", "type": "security", "subtype": "tokens_in_urls", "priority": "high"},
            {"name": "DEEP-SEC: Sensitive data in log statements", "type": "security", "subtype": "sensitive_logs", "priority": "high"},
            {"name": "DEEP-SEC: Info leakage in error messages", "type": "security", "subtype": "sensitive_errors", "priority": "medium"},
            {"name": "DEEP-SEC: PII exposure in client-side code", "type": "security", "subtype": "pii_exposure", "priority": "high"},
            {"name": "DEEP-SEC: Source maps in production build", "type": "security", "subtype": "source_maps_prod", "priority": "medium"},
            # --- DEEP SECURITY: Auth & Session ---
            {"name": "DEEP-SEC: JWT tokens without expiry", "type": "security", "subtype": "jwt_no_expiry", "priority": "high"},
            {"name": "DEEP-SEC: Weak/hardcoded JWT secret", "type": "security", "subtype": "jwt_weak_secret", "priority": "critical"},
            {"name": "DEEP-SEC: Missing auth middleware on routes", "type": "security", "subtype": "missing_auth_middleware", "priority": "high"},
            {"name": "DEEP-SEC: Sensitive data in insecure storage", "type": "security", "subtype": "insecure_session_storage", "priority": "high"},
            {"name": "DEEP-SEC: Missing CSRF protection", "type": "security", "subtype": "missing_csrf", "priority": "medium"},
            # --- DEEP SECURITY: Injection ---
            {"name": "DEEP-SEC: XSS vectors (innerHTML/dangerouslySet)", "type": "security", "subtype": "xss_vectors", "priority": "critical"},
            {"name": "DEEP-SEC: NoSQL injection patterns", "type": "security", "subtype": "nosql_injection", "priority": "high"},
            {"name": "DEEP-SEC: Unvalidated redirects (open redirect)", "type": "security", "subtype": "unvalidated_redirects", "priority": "medium"},
            {"name": "DEEP-SEC: File upload without validation", "type": "security", "subtype": "file_upload_no_validation", "priority": "high"},
            # --- DEEP SECURITY: Access Control ---
            {"name": "DEEP-SEC: IDOR risk (direct object reference)", "type": "security", "subtype": "idor_risk", "priority": "high"},
            {"name": "DEEP-SEC: Missing RLS / horizontal privilege", "type": "security", "subtype": "horizontal_privilege", "priority": "critical"},
            {"name": "DEEP-SEC: Mass assignment vulnerability", "type": "security", "subtype": "mass_assignment", "priority": "high"},
            # --- DEEP SECURITY: Misconfiguration ---
            {"name": "DEEP-SEC: Debug mode in production", "type": "security", "subtype": "debug_production", "priority": "high"},
            {"name": "DEEP-SEC: Default credentials left in code", "type": "security", "subtype": "default_credentials", "priority": "critical"},
            {"name": "DEEP-SEC: Missing security headers", "type": "security", "subtype": "missing_security_headers", "priority": "medium"},
            {"name": "DEEP-SEC: CORS misconfiguration (deep)", "type": "security", "subtype": "cors_misconfiguration", "priority": "medium"},
            {"name": "DEEP-SEC: Verbose error messages exposed", "type": "security", "subtype": "verbose_errors", "priority": "medium"},
            {"name": "DEEP-SEC: Server env vars exposed to client", "type": "security", "subtype": "exposed_env_vars", "priority": "high"},
            # --- DEEP SECURITY: Crypto ---
            {"name": "DEEP-SEC: Weak hashing algorithm (MD5/SHA1)", "type": "security", "subtype": "weak_hashing", "priority": "high"},
            {"name": "DEEP-SEC: Weak encryption (DES/RC4/ECB)", "type": "security", "subtype": "weak_encryption", "priority": "high"},
            {"name": "DEEP-SEC: Predictable random for security", "type": "security", "subtype": "insecure_random", "priority": "high"},
            {"name": "DEEP-SEC: Hardcoded IV/salt in crypto", "type": "security", "subtype": "hardcoded_iv_salt", "priority": "medium"},
            # --- DEEP SECURITY: Supply Chain ---
            {"name": "DEEP-SEC: Unpinned dependencies (*/latest)", "type": "security", "subtype": "unpinned_deps", "priority": "medium"},
            {"name": "DEEP-SEC: Known vulnerable packages", "type": "security", "subtype": "known_vulnerable_packages", "priority": "critical"},
            {"name": "DEEP-SEC: Risky postinstall scripts", "type": "security", "subtype": "postinstall_scripts", "priority": "medium"},
            # --- DEEP SECURITY: API ---
            {"name": "DEEP-SEC: No rate limiting on API", "type": "security", "subtype": "rate_limiting", "priority": "high"},
            {"name": "DEEP-SEC: No request body size limit", "type": "security", "subtype": "no_input_size_limit", "priority": "medium"},
            {"name": "DEEP-SEC: Excessive data exposure (SELECT *)", "type": "security", "subtype": "excessive_data_exposure", "priority": "medium"},
            # --- DEEP SECURITY: Compliance ---
            {"name": "DEEP-SEC: No user data deletion (GDPR)", "type": "security", "subtype": "gdpr_data_deletion", "priority": "high"},
            {"name": "DEEP-SEC: No privacy policy reference", "type": "security", "subtype": "privacy_policy", "priority": "medium"},
            {"name": "DEEP-SEC: No consent management", "type": "security", "subtype": "consent_management", "priority": "medium"},
            # --- DEEP SECURITY: Production Readiness ---
            {"name": "DEEP-SEC: No React ErrorBoundary", "type": "security", "subtype": "error_boundary", "priority": "medium"},
            {"name": "DEEP-SEC: Memory leak risk (uncleared timers)", "type": "security", "subtype": "memory_leaks", "priority": "medium"},
            {"name": "DEEP-SEC: Race condition risk (no locking)", "type": "security", "subtype": "race_conditions", "priority": "high"},
            {"name": "DEEP-SEC: HTTP calls without timeout", "type": "security", "subtype": "missing_timeout", "priority": "medium"},
            {"name": "DEEP-SEC: Hardcoded production URLs", "type": "security", "subtype": "hardcoded_urls", "priority": "medium"},
        ]
        # Mobil-spesifik testler
        if self.scan.tech_stack in ("react-native", "flutter", "ios-native", "android-native"):
            tests.extend([
                {"name": "DEEP-SEC: No SSL certificate pinning", "type": "security", "subtype": "certificate_pinning", "priority": "high"},
                {"name": "DEEP-SEC: Sensitive data in AsyncStorage", "type": "security", "subtype": "insecure_storage_mobile", "priority": "high"},
                {"name": "DEEP-SEC: No root/jailbreak detection", "type": "security", "subtype": "root_jailbreak_detection", "priority": "medium"},
                {"name": "DEEP-SEC: Deep link URL validation missing", "type": "security", "subtype": "deeplink_validation", "priority": "medium"},
                {"name": "DEEP-SEC: No screenshot protection on sensitive screens", "type": "security", "subtype": "screenshot_protection", "priority": "low"},
            ])
        self._add_category("Security", tests, "critical")

    def _plan_api_tests(self):
        tests = []
        for ep in self.scan.api_endpoints:
            url, method = ep["url"], ep["method"]
            tests.append({"name": f"API: {method} {url} reachable", "type": "api", "subtype": "reachability", "target": url, "method": method, "expected_status": [200, 201, 204, 301, 302, 404], "priority": "high"})
            tests.append({"name": f"API: {method} {url} valid response", "type": "api", "subtype": "format", "target": url, "method": method, "priority": "medium"})
            tests.append({"name": f"API: {method} {url} < 3s", "type": "api", "subtype": "performance", "target": url, "method": method, "max_response_time_ms": 3000, "priority": "medium"})
            tests.append({"name": f"API: {method} {url} headers check", "type": "api", "subtype": "headers", "target": url, "method": method, "priority": "low"})
        self._add_category("API", tests, "high")

    def _plan_code_quality_tests(self):
        tests = [
            # Mevcut
            {"name": "QUALITY: No functions longer than 50 lines", "type": "code_quality", "subtype": "long_functions", "max_lines": 50, "priority": "medium"},
            {"name": "QUALITY: No files longer than 300 lines", "type": "code_quality", "subtype": "long_files", "max_lines": 300, "priority": "medium"},
            {"name": "QUALITY: No deeply nested code (>4 levels)", "type": "code_quality", "subtype": "nesting_depth", "max_depth": 4, "priority": "medium"},
            {"name": "QUALITY: No duplicate code blocks", "type": "code_quality", "subtype": "duplication", "priority": "low"},
            {"name": "QUALITY: No TODO/FIXME/HACK left behind", "type": "code_quality", "subtype": "todo_count", "priority": "low"},
            {"name": "QUALITY: No debug statements in production", "type": "code_quality", "subtype": "debug_statements", "priority": "medium"},
            {"name": "QUALITY: Cyclomatic complexity reasonable", "type": "code_quality", "subtype": "complexity", "priority": "medium"},
            # Yeni: Gelismis metrikler
            {"name": "QUALITY: Cyclomatic complexity per function (CC<15)", "type": "code_quality", "subtype": "cyclomatic_complexity", "max_cc": 15, "priority": "medium"},
            {"name": "QUALITY: Maintainability Index (MI>20)", "type": "code_quality", "subtype": "maintainability_index", "min_mi": 20, "priority": "medium"},
            {"name": "QUALITY: No dead code (unused functions)", "type": "code_quality", "subtype": "dead_code", "priority": "low"},
        ]
        # Language-specific smells
        langs = self.scan.languages
        if "Python" in langs:
            tests.extend([
                {"name": "QUALITY: No mutable default arguments (Python)", "type": "code_quality", "subtype": "mutable_default", "priority": "medium"},
                {"name": "QUALITY: No bare except (Python)", "type": "code_quality", "subtype": "bare_except", "priority": "medium"},
                {"name": "QUALITY: No global usage (Python)", "type": "code_quality", "subtype": "global_usage", "priority": "low"},
                {"name": "QUALITY: No star imports (Python)", "type": "code_quality", "subtype": "star_import", "priority": "low"},
            ])
        if "JavaScript" in langs or "TypeScript" in langs:
            tests.extend([
                {"name": "QUALITY: No == loose equality (JS)", "type": "code_quality", "subtype": "loose_equality", "priority": "medium"},
                {"name": "QUALITY: No var usage (JS)", "type": "code_quality", "subtype": "var_usage", "priority": "medium"},
            ])
        if "Go" in langs:
            tests.append({"name": "QUALITY: No unchecked errors (Go)", "type": "code_quality", "subtype": "unchecked_error_go", "priority": "high"})
        if "Rust" in langs:
            tests.append({"name": "QUALITY: No unwrap() abuse (Rust)", "type": "code_quality", "subtype": "unwrap_abuse", "priority": "medium"})

        self._add_category("Code Quality", tests, "medium")

    def _plan_type_safety_tests(self):
        tests = [
            {"name": "TYPE: No 'any' type usage", "type": "type_safety", "subtype": "any_usage", "priority": "medium"},
            {"name": "TYPE: No @ts-ignore / @ts-nocheck", "type": "type_safety", "subtype": "ts_ignore", "priority": "high"},
            {"name": "TYPE: No 'as any' type assertions", "type": "type_safety", "subtype": "as_any", "priority": "medium"},
        ]
        self._add_category("Type Safety", tests, "medium")

    def _plan_import_graph_tests(self):
        tests = [
            {"name": "IMPORT: No circular dependencies", "type": "import_graph", "subtype": "circular", "priority": "high"},
            {"name": "IMPORT: No unused imports", "type": "import_graph", "subtype": "unused", "priority": "low"},
        ]
        self._add_category("Import Graph", tests, "high")

    def _plan_error_handling_tests(self):
        tests = [
            {"name": "ERROR: No empty catch blocks", "type": "error_handling", "subtype": "empty_catch", "priority": "high"},
            {"name": "ERROR: No swallowed errors", "type": "error_handling", "subtype": "swallowed_errors", "priority": "medium"},
            {"name": "ERROR: Async functions have error handling", "type": "error_handling", "subtype": "async_errors", "priority": "medium"},
        ]
        self._add_category("Error Handling", tests, "high")

    def _plan_naming_convention_tests(self):
        tests = [
            {"name": "NAMING: Files follow naming convention", "type": "naming", "subtype": "file_names", "priority": "low"},
            {"name": "NAMING: No single-letter variables", "type": "naming", "subtype": "short_vars", "priority": "low"},
            {"name": "NAMING: Constants are UPPER_CASE", "type": "naming", "subtype": "constants", "priority": "low"},
        ]
        self._add_category("Naming", tests, "low")

    def _plan_git_hygiene_tests(self):
        tests = [
            {"name": "GIT: .gitignore covers essentials", "type": "git", "subtype": "gitignore_quality", "priority": "high"},
            {"name": "GIT: No large binary files tracked", "type": "git", "subtype": "large_tracked", "priority": "medium"},
            {"name": "GIT: No sensitive files in history", "type": "git", "subtype": "sensitive_history", "priority": "critical"},
            {"name": "GIT: Lock file committed", "type": "git", "subtype": "lock_file", "priority": "medium"},
        ]
        self._add_category("Git Hygiene", tests, "high")

    def _plan_dependency_tests(self):
        tests = [
            {"name": "DEP: No known vulnerabilities", "type": "dependency", "subtype": "vulnerability", "priority": "critical"},
            {"name": f"DEP: Dependency count ({len(self.scan.dependencies)})", "type": "dependency", "subtype": "count", "count": len(self.scan.dependencies), "priority": "low"},
            {"name": "DEP: No deprecated packages", "type": "dependency", "subtype": "deprecated", "priority": "medium"},
        ]
        self._add_category("Dependencies", tests, "high")

    def _plan_license_tests(self):
        tests = [
            {"name": "LICENSE: Project has a license file", "type": "license", "subtype": "has_license", "priority": "medium"},
            {"name": "LICENSE: No GPL deps in proprietary code", "type": "license", "subtype": "gpl_check", "priority": "high"},
        ]
        self._add_category("License", tests, "medium")

    def _plan_env_variable_tests(self):
        tests = [
            {"name": "ENV: .env.example exists for team", "type": "env", "subtype": "env_example", "priority": "medium"},
            {"name": "ENV: No undefined env vars in code", "type": "env", "subtype": "undefined_vars", "priority": "medium"},
        ]
        self._add_category("Environment", tests, "medium")

    def _plan_config_tests(self):
        tests = [{"name": "CFG: .env not committed to git", "type": "config", "subtype": "env_safety", "priority": "critical"}]
        tech = self.scan.tech_stack
        required = {"react-native": ["package.json"], "flutter": ["pubspec.yaml"], "nextjs": ["package.json"], "django": ["manage.py"], "go": ["go.mod"], "rust": ["Cargo.toml"]}
        for cfg in required.get(tech, []):
            tests.append({"name": f"CFG: {cfg} exists", "type": "config", "subtype": "required", "file": cfg, "priority": "medium"})
        self._add_category("Config", tests, "medium")

    def _plan_documentation_tests(self):
        tests = [
            {"name": "DOC: README.md exists", "type": "documentation", "subtype": "readme_exists", "priority": "medium"},
            {"name": "DOC: README has content (>10 lines)", "type": "documentation", "subtype": "readme_quality", "priority": "low"},
            {"name": "DOC: CHANGELOG exists", "type": "documentation", "subtype": "changelog", "priority": "low"},
        ]
        self._add_category("Documentation", tests, "medium")

    def _plan_accessibility_tests(self):
        tests = [
            {"name": "A11Y: Interactive elements have testID", "type": "accessibility", "subtype": "test_ids", "priority": "high"},
            {"name": "A11Y: Images have accessible labels", "type": "accessibility", "subtype": "image_labels", "priority": "medium"},
        ]
        self._add_category("Accessibility", tests, "high")

    def _plan_structure_tests(self):
        src = len([f for f in self.scan.source_files if "test" not in f.lower() and "spec" not in f.lower()])
        tests = [
            {"name": f"STRUCT: Test coverage ({self.scan.existing_test_count}/{src})", "type": "structure", "subtype": "test_coverage", "source_count": src, "test_count": self.scan.existing_test_count, "priority": "high"},
            {"name": "STRUCT: No empty source files", "type": "structure", "subtype": "empty_files", "priority": "low"},
        ]
        self._add_category("Structure", tests, "medium")

    def _plan_performance_tests(self):
        tests = [
            {"name": "PERF: Source code total size", "type": "performance", "subtype": "source_size", "priority": "low"},
            {"name": "PERF: No files larger than 10MB", "type": "performance", "subtype": "large_files", "max_size_mb": 10, "priority": "medium"},
            {"name": "PERF: No oversized images (>500KB)", "type": "performance", "subtype": "large_images", "priority": "medium"},
        ]
        self._add_category("Performance", tests, "medium")

    def _plan_visual_tests(self):
        screens = [s for s in self.scan.screens if s["type"] in ("screen", "view")]
        if not screens:
            return
        tests = [{"name": f"VIS: {s['name']} exists", "type": "visual", "subtype": "render_check", "target": s["name"], "file": s["file"], "priority": "low"} for s in screens[:10]]
        self._add_category("Visual", tests, "low")

    def _plan_ux_text_tests(self):
        tests = [
            {"name": "UX: Common spelling mistakes in UI", "type": "ux_text", "subtype": "spelling", "priority": "medium"},
            {"name": "UX: Terminology consistency (Login vs Sign in)", "type": "ux_text", "subtype": "term_consistency", "priority": "medium"},
            {"name": "UX: i18n readiness (hardcoded strings)", "type": "ux_text", "subtype": "i18n_readiness", "priority": "medium"},
            {"name": "UX: Button text quality (vague labels)", "type": "ux_text", "subtype": "button_text_quality", "priority": "low"},
            {"name": "UX: Error message quality (user-friendly)", "type": "ux_text", "subtype": "error_message_quality", "priority": "medium"},
            {"name": "UX: Text truncation risk (long strings)", "type": "ux_text", "subtype": "truncation_risk", "priority": "low"},
            {"name": "UX: Missing alt text on images", "type": "ux_text", "subtype": "missing_alt_text", "priority": "high"},
            {"name": "UX: Placeholder vs label quality", "type": "ux_text", "subtype": "placeholder_quality", "priority": "low"},
        ]
        self._add_category("UX Text", tests, "medium")

    def _plan_ui_component_tests(self):
        tests = [
            {"name": "UI: Accessibility labels on interactive elements", "type": "ui_component", "subtype": "a11y_labels", "priority": "high"},
            {"name": "UI: Touch target size (min 44px)", "type": "ui_component", "subtype": "touch_target_size", "priority": "medium"},
            {"name": "UI: Hardcoded colors (use theme)", "type": "ui_component", "subtype": "hardcoded_colors", "priority": "medium"},
            {"name": "UI: Hardcoded dimensions (responsive)", "type": "ui_component", "subtype": "hardcoded_dimensions", "priority": "medium"},
            {"name": "UI: Dark mode support", "type": "ui_component", "subtype": "dark_mode_support", "priority": "medium"},
            {"name": "UI: Error boundary (crash protection)", "type": "ui_component", "subtype": "ui_error_boundary", "priority": "high"},
            {"name": "UI: Loading states for async ops", "type": "ui_component", "subtype": "loading_states", "priority": "medium"},
            {"name": "UI: Empty state for lists", "type": "ui_component", "subtype": "empty_state", "priority": "medium"},
            {"name": "UI: Keyboard handling (form overlap)", "type": "ui_component", "subtype": "keyboard_handling", "priority": "medium"},
            {"name": "UI: Image optimization (cache/placeholder)", "type": "ui_component", "subtype": "image_optimization", "priority": "low"},
        ]
        self._add_category("UI Components", tests, "medium")

    def _plan_cross_file_tests(self):
        tests = [
            {"name": "CROSS: Unused exports (dead code across files)", "type": "cross_file", "subtype": "unused_exports", "priority": "medium"},
            {"name": "CROSS: Same secret in multiple files", "type": "cross_file", "subtype": "duplicate_secrets", "priority": "high"},
            {"name": "CROSS: Orphan component files (never imported)", "type": "cross_file", "subtype": "orphan_components", "priority": "low"},
            {"name": "CROSS: Env vars used but not in .env.example", "type": "cross_file", "subtype": "env_var_mismatch", "priority": "medium"},
            {"name": "CROSS: Deep circular imports", "type": "cross_file", "subtype": "circular_imports_deep", "priority": "high"},
            {"name": "CROSS: Inconsistent file naming convention", "type": "cross_file", "subtype": "inconsistent_naming", "priority": "low"},
            {"name": "CROSS: API routes without auth middleware", "type": "cross_file", "subtype": "api_auth_coverage", "priority": "high"},
        ]
        self._add_category("Cross-File", tests, "medium")

    def _plan_appstore_tests(self):
        tests = [
            # Kritik
            {"name": "APPSTORE: Privacy manifest (PrivacyInfo.xcprivacy)", "type": "appstore", "subtype": "privacy_manifest", "priority": "critical"},
            {"name": "APPSTORE: Permission purpose strings in Info.plist", "type": "appstore", "subtype": "purpose_strings", "priority": "critical"},
            {"name": "APPSTORE: Sign in with Apple required", "type": "appstore", "subtype": "sign_in_with_apple", "priority": "critical"},
            {"name": "APPSTORE: Account deletion mechanism", "type": "appstore", "subtype": "account_deletion_apple", "priority": "critical"},
            {"name": "APPSTORE: ATT compliance for IDFA", "type": "appstore", "subtype": "att_compliance", "priority": "critical"},
            {"name": "APPSTORE: No external payment for digital goods", "type": "appstore", "subtype": "external_payment", "priority": "critical"},
            {"name": "APPSTORE: Restore Purchases mechanism", "type": "appstore", "subtype": "iap_restore", "priority": "critical"},
            {"name": "APPSTORE: IAP transaction verification", "type": "appstore", "subtype": "iap_verification", "priority": "high"},
            {"name": "APPSTORE: Recording consent + indicator", "type": "appstore", "subtype": "recording_consent", "priority": "critical"},
            {"name": "APPSTORE: No tracking in kids category", "type": "appstore", "subtype": "kids_tracking", "priority": "critical"},
            {"name": "APPSTORE: Health data not for advertising", "type": "appstore", "subtype": "health_data_ads", "priority": "critical"},
            {"name": "APPSTORE: Required Reason API declarations", "type": "appstore", "subtype": "required_reason_api", "priority": "high"},
            # Yuksek
            {"name": "APPSTORE: App icon sizes complete", "type": "appstore", "subtype": "app_icon_sizes", "priority": "high"},
            {"name": "APPSTORE: Launch/splash screen exists", "type": "appstore", "subtype": "launch_screen", "priority": "high"},
            {"name": "APPSTORE: Minimum iOS deployment target", "type": "appstore", "subtype": "min_deployment_target", "priority": "medium"},
            {"name": "APPSTORE: No deprecated API usage", "type": "appstore", "subtype": "deprecated_api_apple", "priority": "high"},
            {"name": "APPSTORE: No ads in widgets", "type": "appstore", "subtype": "widget_no_ads", "priority": "high"},
            {"name": "APPSTORE: Face auth uses LocalAuthentication", "type": "appstore", "subtype": "face_auth_method", "priority": "high"},
            {"name": "APPSTORE: Data collection types declared", "type": "appstore", "subtype": "data_collection_types", "priority": "medium"},
            # Orta
            {"name": "APPSTORE: VoiceOver accessibility support", "type": "appstore", "subtype": "voiceover_support", "priority": "medium"},
            {"name": "APPSTORE: Device orientation support", "type": "appstore", "subtype": "orientation_support", "priority": "low"},
            {"name": "APPSTORE: Subscription state handling", "type": "appstore", "subtype": "subscription_handling", "priority": "medium"},
            {"name": "APPSTORE: App thinning (large assets)", "type": "appstore", "subtype": "app_thinning", "priority": "medium"},
            # v2.2 Yeni Pre-Review
            {"name": "APPSTORE: App completeness (no placeholder/test data)", "type": "appstore", "subtype": "app_completeness", "priority": "critical"},
            {"name": "APPSTORE: No debug/development URLs in production", "type": "appstore", "subtype": "debug_urls", "priority": "critical"},
            {"name": "APPSTORE: Required Reason API reason codes valid", "type": "appstore", "subtype": "reason_code_validity", "priority": "critical"},
            {"name": "APPSTORE: Third-party SDK privacy manifests", "type": "appstore", "subtype": "sdk_privacy_manifests", "priority": "high"},
            {"name": "APPSTORE: OTA update compliance (Guideline 3.3.2)", "type": "appstore", "subtype": "ota_compliance", "priority": "high"},
            {"name": "APPSTORE: App Transport Security not overridden", "type": "appstore", "subtype": "ats_override", "priority": "high"},
            {"name": "APPSTORE: No reserved URL scheme conflicts", "type": "appstore", "subtype": "url_scheme_conflict", "priority": "high"},
            {"name": "APPSTORE: No secrets in EXPO_PUBLIC_ variables", "type": "appstore", "subtype": "bundle_secrets", "priority": "critical"},
            {"name": "APPSTORE: No UIWebView usage (deprecated 2020)", "type": "appstore", "subtype": "uiwebview_deprecated", "priority": "critical"},
        ]
        self._add_category("App Store", tests, "critical")

    def _plan_ast_analysis_tests(self):
        """Python AST tabanli kod analizi testleri."""
        tests = [
            {"name": "AST: Tehlikeli fonksiyon cagrilari (eval/exec/compile)", "type": "ast_analysis", "subtype": "dangerous_calls", "priority": "critical"},
            {"name": "AST: Bare except bloklari", "type": "ast_analysis", "subtype": "bare_except", "priority": "medium"},
            {"name": "AST: Mutable default argument", "type": "ast_analysis", "subtype": "mutable_defaults", "priority": "medium"},
            {"name": "AST: Hardcoded secret (degisken adi + deger)", "type": "ast_analysis", "subtype": "hardcoded_secrets", "priority": "critical"},
            {"name": "AST: Star import (from x import *)", "type": "ast_analysis", "subtype": "star_imports", "priority": "low"},
            {"name": "AST: Global keyword kullanimi", "type": "ast_analysis", "subtype": "global_usage", "priority": "low"},
        ]
        self._add_category("AST Analysis (Python)", tests, "high")

    def _plan_taint_tracking_tests(self):
        """Taint tracking - veri akisi analizi."""
        tests = [
            {"name": "TAINT: SQL injection (source -> query)", "type": "taint", "subtype": "sql_injection_taint", "priority": "critical"},
            {"name": "TAINT: XSS (source -> innerHTML/dangerouslySet)", "type": "taint", "subtype": "xss_taint", "priority": "critical"},
            {"name": "TAINT: Command injection (source -> system/exec)", "type": "taint", "subtype": "command_injection_taint", "priority": "critical"},
            {"name": "TAINT: Path traversal (source -> open/writeFile)", "type": "taint", "subtype": "path_traversal_taint", "priority": "high"},
            {"name": "TAINT: Genel taint akisi (tum source-sink)", "type": "taint", "subtype": "general_taint", "priority": "high"},
        ]
        self._add_category("Taint Tracking", tests, "critical")

    def _plan_sca_tests(self):
        """SCA (Software Composition Analysis) testleri."""
        tests = [
            {"name": "SCA: npm audit - bilinen guvenlik aciklari", "type": "sca", "subtype": "npm_audit", "priority": "critical"},
            {"name": "SCA: pip-audit - Python guvenlik aciklari", "type": "sca", "subtype": "pip_audit", "priority": "critical"},
            {"name": "SCA: govulncheck - Go guvenlik aciklari", "type": "sca", "subtype": "go_vulncheck", "priority": "critical"},
            {"name": "SCA: Major versiyon gerideleri", "type": "sca", "subtype": "outdated_packages", "priority": "medium"},
            {"name": "SCA: GPL dependency MIT projede", "type": "sca", "subtype": "license_compatibility", "priority": "high"},
            {"name": "SCA: Deprecated paket kullanimi", "type": "sca", "subtype": "deprecated_packages", "priority": "medium"},
            {"name": "SCA: Typosquatting paket tespiti", "type": "sca", "subtype": "typosquatting", "priority": "critical"},
        ]
        self._add_category("SCA (Dependency Security)", tests, "critical")

    def _plan_playstore_tests(self):
        """Google Play Store uyumluluk testleri."""
        tests = [
            {"name": "PLAYSTORE: targetSdkVersion >= 34 (Android 14)", "type": "playstore", "subtype": "target_sdk", "priority": "critical"},
            {"name": "PLAYSTORE: Exported component beyannamesi", "type": "playstore", "subtype": "exported_components", "priority": "critical"},
            {"name": "PLAYSTORE: Ag guvenligi (cleartext, pinning)", "type": "playstore", "subtype": "network_security", "priority": "high"},
            {"name": "PLAYSTORE: Gereksiz izin kontrolu", "type": "playstore", "subtype": "permissions", "priority": "high"},
            {"name": "PLAYSTORE: Backup kurallari", "type": "playstore", "subtype": "backup_rules", "priority": "medium"},
            {"name": "PLAYSTORE: Release debuggable=false", "type": "playstore", "subtype": "debuggable", "priority": "critical"},
            {"name": "PLAYSTORE: Metadata (versionName/Code)", "type": "playstore", "subtype": "metadata", "priority": "medium"},
            {"name": "PLAYSTORE: Data Safety beyani", "type": "playstore", "subtype": "data_safety", "priority": "high"},
            {"name": "PLAYSTORE: AAB format zorunlulugu", "type": "playstore", "subtype": "app_bundle", "priority": "medium"},
            {"name": "PLAYSTORE: ProGuard/R8 obfuscation", "type": "playstore", "subtype": "proguard", "priority": "high"},
        ]
        self._add_category("Play Store", tests, "critical")

    def _plan_spell_check_tests(self):
        """Yazim hatasi tespiti."""
        tests = [
            {"name": "UI-CORE: Yazim hatasi kontrolu (TR+EN)", "type": "spell_check", "subtype": "spell_check", "priority": "medium"},
        ]
        self._add_category("Spell Check", tests, "medium")

    def _plan_ui_quality_tests(self):
        """Renk, kontrast, font, form kalite testleri."""
        tests = [
            {"name": "UI-CORE: Hardcoded renk (tema disinda)", "type": "ui_quality", "subtype": "color_consistency", "priority": "medium"},
            {"name": "UI-CORE: WCAG AA kontrast orani (min 4.5:1)", "type": "ui_quality", "subtype": "contrast_wcag", "priority": "high"},
            {"name": "UI-CORE: Font tutarliligi (fontSize/fontFamily)", "type": "ui_quality", "subtype": "font_consistency", "priority": "low"},
            {"name": "UI-CORE: Form validation kapsami (Zod/Yup)", "type": "ui_quality", "subtype": "form_validation_coverage", "priority": "high"},
            {"name": "UI-CORE: Form hata mesaji render kontrolu", "type": "ui_quality", "subtype": "form_error_messages", "priority": "medium"},
        ]
        self._add_category("UI Quality (Core)", tests, "high")

    def _plan_ui_analysis_tests(self):
        """UI analiz testleri (MVP Wave 1)."""
        tests = [
            {"name": "UI-MVP: Sayfa/ekran kesfetme ve test kapsami", "type": "ui_analysis", "subtype": "page_discovery", "priority": "medium"},
            {"name": "UI-MVP: Kirik route / dead navigation tespiti", "type": "ui_analysis", "subtype": "dead_routes", "priority": "high"},
            {"name": "UI-MVP: Placeholder / test verisi (lorem ipsum)", "type": "ui_analysis", "subtype": "content_quality", "priority": "high"},
            {"name": "UI-MVP: Loading state eksikligi", "type": "ui_analysis", "subtype": "loading_state", "priority": "high"},
            {"name": "UI-MVP: Error state eksikligi", "type": "ui_analysis", "subtype": "error_state", "priority": "high"},
            {"name": "UI-MVP: Empty state eksikligi (bos liste)", "type": "ui_analysis", "subtype": "empty_state", "priority": "medium"},
        ]
        self._add_category("UI Analysis (MVP)", tests, "high")

    def _plan_yaml_ui_tests(self):
        """YAML UI test dosyalari kontrolu."""
        tests = [
            {"name": "YAML-UI: Test dosyalari syntax kontrolu", "type": "yaml_ui", "subtype": "yaml_ui_syntax", "priority": "medium"},
            {"name": "YAML-UI: Hedefler projede mevcut mu", "type": "yaml_ui", "subtype": "yaml_ui_targets", "priority": "high"},
            {"name": "YAML-UI: Ekran test kapsami", "type": "yaml_ui", "subtype": "yaml_ui_coverage", "priority": "medium"},
        ]
        self._add_category("YAML UI Tests", tests, "medium")

    def _plan_i18n_deep_tests(self):
        """Derin i18n analizi."""
        tests = [
            {"name": "I18N: Hardcoded string ve i18n kapsami", "type": "i18n_deep", "subtype": "i18n_deep", "priority": "medium"},
            {"name": "I18N: Detayli coverage analizi", "type": "i18n_deep", "subtype": "i18n_coverage", "priority": "medium"},
            {"name": "I18N: Eksik translation key tespiti", "type": "i18n_deep", "subtype": "missing_translation_keys", "priority": "high"},
            {"name": "I18N: Kullanilmayan translation key tespiti", "type": "i18n_deep", "subtype": "unused_translation_keys", "priority": "low"},
            {"name": "I18N: Locale dosyasi tutarliligi", "type": "i18n_deep", "subtype": "locale_consistency", "priority": "high"},
            {"name": "I18N: RTL (sag-sola) dil destegi", "type": "i18n_deep", "subtype": "rtl_support", "priority": "medium"},
        ]
        self._add_category("i18n Analysis", tests, "medium")

    def _plan_responsive_tests(self):
        """Responsive layout analizi."""
        tests = [
            {"name": "RESPONSIVE: Sabit pixel boyutlari", "type": "responsive", "subtype": "fixed_dimensions", "priority": "medium"},
            {"name": "RESPONSIVE: ScrollView icinde FlatList", "type": "responsive", "subtype": "scroll_issues", "priority": "high"},
            {"name": "RESPONSIVE: Responsive pattern kontrolu", "type": "responsive", "subtype": "responsive_patterns", "priority": "low"},
            {"name": "RESPONSIVE: Media query breakpoint analizi", "type": "responsive", "subtype": "media_query_analysis", "priority": "high"},
            {"name": "RESPONSIVE: Viewport meta tag kontrolu", "type": "responsive", "subtype": "viewport_meta", "priority": "high"},
            {"name": "RESPONSIVE: Dokunma hedefi boyutu (min 44px)", "type": "responsive", "subtype": "touch_target_size", "priority": "medium"},
            {"name": "RESPONSIVE: Flexbox/Grid layout kullanimi", "type": "responsive", "subtype": "flexbox_grid_usage", "priority": "medium"},
            {"name": "RESPONSIVE: Responsive gorsel (srcset/picture)", "type": "responsive", "subtype": "responsive_images", "priority": "medium"},
        ]
        self._add_category("Responsive", tests, "medium")

    def _plan_visual_regression_tests(self):
        """Visual regression / snapshot test analizi."""
        # Sadece test dosyalari olan projelerde calistir
        has_test_infra = False
        for f in self.scan.source_files:
            fl = f.lower()
            if "__tests__" in fl or "__snapshots__" in fl or "jest" in fl or "vitest" in fl:
                has_test_infra = True
                break
        if not has_test_infra:
            # jest/vitest config dosyalarini da kontrol et
            for cfg in self.scan.config_files:
                cl = cfg.lower()
                if "jest" in cl or "vitest" in cl:
                    has_test_infra = True
                    break
        if not has_test_infra:
            return
        tests = [
            {"name": "VISUAL-REG: Stale (eski) snapshot tespiti", "type": "visual_regression", "subtype": "stale_snapshots", "priority": "medium"},
            {"name": "VISUAL-REG: Eksik snapshot dosyalari", "type": "visual_regression", "subtype": "missing_snapshots", "priority": "high"},
            {"name": "VISUAL-REG: Snapshot isimlendirme kontrolu", "type": "visual_regression", "subtype": "snapshot_naming", "priority": "low"},
            {"name": "VISUAL-REG: Buyuk snapshot dosyalari", "type": "visual_regression", "subtype": "large_snapshots", "priority": "medium"},
            {"name": "VISUAL-REG: Commit edilmemis snapshot degisiklikleri", "type": "visual_regression", "subtype": "uncommitted_snapshots", "priority": "high"},
            {"name": "VISUAL-REG: Snapshot dizin yapisi kontrolu", "type": "visual_regression", "subtype": "snapshot_directory_check", "priority": "low"},
        ]
        self._add_category("Visual Regression", tests, "medium")

    def _plan_perf_static_tests(self):
        """Statik performans analizi."""
        tests = [
            {"name": "PERF: Buyuk gorsel dosyalari (500KB+)", "type": "perf_static", "subtype": "large_assets", "priority": "high"},
            {"name": "PERF: Render performans sorunlari", "type": "perf_static", "subtype": "render_performance", "priority": "medium"},
            {"name": "PERF: Bundle boyut sorunlari", "type": "perf_static", "subtype": "bundle_issues", "priority": "medium"},
        ]
        self._add_category("Performance (Static)", tests, "medium")

    def _plan_yaml_rule_tests(self):
        """YAML kural motoru testleri."""
        tests = [
            {"name": "YAML: Guvenlik kurallari", "type": "yaml_rules", "subtype": "yaml_security", "priority": "high"},
            {"name": "YAML: Kod kalitesi kurallari", "type": "yaml_rules", "subtype": "yaml_code_quality", "priority": "medium"},
            {"name": "YAML: Ozel kurallar (proje + dahili)", "type": "yaml_rules", "subtype": "yaml_custom", "priority": "medium"},
        ]
        self._add_category("YAML Rules", tests, "medium")

    def _plan_docker_tests(self):
        tests = [
            {"name": "DOCKER: Dockerfile base image pinned", "type": "docker", "subtype": "base_image", "priority": "medium"},
            {"name": "DOCKER: No secrets in Dockerfile", "type": "docker", "subtype": "dockerfile_secrets", "priority": "high"},
        ]
        self._add_category("Docker/Infra", tests, "medium")

    def _plan_compliance_tests(self):
        """Compliance framework kontrolleri - OWASP, GDPR/KVKK, SOC2, PCI-DSS."""
        tests = [
            # OWASP Top 10 Mapping
            {"name": "COMPLIANCE: OWASP Top 10 tam tarama", "type": "compliance", "subtype": "owasp_full", "priority": "high"},
            {"name": "COMPLIANCE: OWASP A01 - Broken Access Control", "type": "compliance", "subtype": "owasp_A01_broken_access_control", "priority": "high"},
            {"name": "COMPLIANCE: OWASP A02 - Cryptographic Failures", "type": "compliance", "subtype": "owasp_A02_cryptographic_failures", "priority": "high"},
            {"name": "COMPLIANCE: OWASP A03 - Injection", "type": "compliance", "subtype": "owasp_A03_injection", "priority": "critical"},
            {"name": "COMPLIANCE: OWASP A05 - Security Misconfiguration", "type": "compliance", "subtype": "owasp_A05_security_misconfiguration", "priority": "high"},
            {"name": "COMPLIANCE: OWASP A07 - Auth Failures", "type": "compliance", "subtype": "owasp_A07_auth_failures", "priority": "high"},
            {"name": "COMPLIANCE: OWASP A08 - Integrity Failures", "type": "compliance", "subtype": "owasp_A08_integrity_failures", "priority": "high"},
            {"name": "COMPLIANCE: OWASP A09 - Logging Failures", "type": "compliance", "subtype": "owasp_A09_logging_failures", "priority": "medium"},
            {"name": "COMPLIANCE: OWASP A10 - SSRF", "type": "compliance", "subtype": "owasp_A10_ssrf", "priority": "high"},
            # GDPR / KVKK
            {"name": "COMPLIANCE: GDPR/KVKK tam tarama", "type": "compliance", "subtype": "gdpr_full", "priority": "high"},
            {"name": "COMPLIANCE: GDPR - Riza mekanizmasi (consent)", "type": "compliance", "subtype": "gdpr_consent_mechanism", "priority": "high"},
            {"name": "COMPLIANCE: GDPR - Veri silme yetenegi", "type": "compliance", "subtype": "gdpr_data_deletion", "priority": "high"},
            {"name": "COMPLIANCE: GDPR - Gizlilik politikasi linki", "type": "compliance", "subtype": "gdpr_privacy_policy", "priority": "medium"},
            {"name": "COMPLIANCE: GDPR - Cerez onay mekanizmasi", "type": "compliance", "subtype": "gdpr_cookie_consent", "priority": "medium"},
            {"name": "COMPLIANCE: GDPR - Duragan veri sifreleme", "type": "compliance", "subtype": "gdpr_data_encryption_at_rest", "priority": "high"},
            {"name": "COMPLIANCE: GDPR - PII loglama engelleme", "type": "compliance", "subtype": "gdpr_pii_logging_prevention", "priority": "high"},
            # SOC2 Basics
            {"name": "COMPLIANCE: SOC2 tam tarama", "type": "compliance", "subtype": "soc2_full", "priority": "high"},
            {"name": "COMPLIANCE: SOC2 - Kimlik dogrulama", "type": "compliance", "subtype": "soc2_authentication", "priority": "high"},
            {"name": "COMPLIANCE: SOC2 - Erisim kontrolu", "type": "compliance", "subtype": "soc2_access_control", "priority": "high"},
            {"name": "COMPLIANCE: SOC2 - Denetim loglama", "type": "compliance", "subtype": "soc2_audit_logging", "priority": "medium"},
            {"name": "COMPLIANCE: SOC2 - HTTPS zorunlulugu", "type": "compliance", "subtype": "soc2_encryption_in_transit", "priority": "high"},
            {"name": "COMPLIANCE: SOC2 - Hata yonetimi", "type": "compliance", "subtype": "soc2_error_handling", "priority": "medium"},
            {"name": "COMPLIANCE: SOC2 - Bagimlilk guncelleme", "type": "compliance", "subtype": "soc2_dependency_updates", "priority": "medium"},
            # PCI-DSS Basics
            {"name": "COMPLIANCE: PCI-DSS tam tarama", "type": "compliance", "subtype": "pci_full", "priority": "high"},
            {"name": "COMPLIANCE: PCI-DSS - Kodda kredi karti numarasi", "type": "compliance", "subtype": "pci_no_credit_card_in_code", "priority": "critical"},
            {"name": "COMPLIANCE: PCI-DSS - PAN saklama kontrolu", "type": "compliance", "subtype": "pci_no_pan_storage", "priority": "critical"},
            {"name": "COMPLIANCE: PCI-DSS - TLS zorunlulugu", "type": "compliance", "subtype": "pci_tls_enforcement", "priority": "high"},
            {"name": "COMPLIANCE: PCI-DSS - Odeme formu girdi dogrulama", "type": "compliance", "subtype": "pci_input_validation_payment", "priority": "high"},
            # Ozet
            {"name": "COMPLIANCE: Tum framework ozet raporu", "type": "compliance", "subtype": "compliance_summary", "priority": "high"},
        ]
        self._add_category("Compliance", tests, "high")

    def _estimate_duration(self) -> str:
        weights = {"api": 3, "security": 1, "code_quality": 2, "visual": 1, "dependency": 5, "compliance": 2}
        total = sum(weights.get(t["type"], 1) for t in self.plan.tests)
        if total < 60:
            return f"{total}s"
        return f"{total // 60}m {total % 60}s"
