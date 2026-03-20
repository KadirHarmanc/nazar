"""YAML Pattern Engine - Semgrep benzeri kural motoru.

Kullanici kendi kurallarini YAML formatinda tanimlayip calistirir.
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any

from nazar.runners.base import BaseRunner, IGNORE_DIRS, SOURCE_EXTS

try:
    import yaml
except ImportError:
    yaml = None


class PatternRule:
    """Tek bir YAML kurali."""

    def __init__(self, data: dict):
        self.id = data.get("id", "unknown")
        self.message = data.get("message", "Kural ihlali")
        self.severity = data.get("severity", "warning")
        self.languages = data.get("languages", [])
        self.pattern = data.get("pattern", "")
        self.pattern_not = data.get("pattern_not", "")
        self.pattern_either = data.get("pattern_either", [])
        self.constraint = data.get("constraint", {})
        self.fix = data.get("fix", "")
        self.metadata = data.get("metadata", {})
        self._compiled = None
        self._compiled_not = None

    @property
    def compiled_pattern(self):
        if self._compiled is None and self.pattern:
            self._compiled = self._compile_pattern(self.pattern)
        return self._compiled

    @property
    def compiled_not_pattern(self):
        if self._compiled_not is None and self.pattern_not:
            self._compiled_not = self._compile_pattern(self.pattern_not)
        return self._compiled_not

    def _compile_pattern(self, pattern: str) -> re.Pattern:
        """Semgrep-style pattern'i regex'e cevir.

        $VAR -> yakalama grubu
        ... -> herhangi bir sey
        $VALUE -> yakalama grubu
        """
        # $IDENTIFIER'lari regex gruplarina cevir
        regex = re.escape(pattern)
        # $VAR, $VALUE gibi placeholder'lari regex'e cevir
        regex = re.sub(r'\\\$([A-Z_]+)', r'(?P<\1>[^\'"\\s,;]+)', regex)
        # ... (ellipsis) -> herhangi bir sey
        regex = regex.replace(r'\.\.\.', r'.*?')
        # Bazi karakter duzeltmeleri
        regex = regex.replace(r"\ =\ ", r"\s*=\s*")
        regex = regex.replace(r"\ \(", r"\s*\(")
        return re.compile(regex, re.MULTILINE | re.IGNORECASE)

    def matches_language(self, file_path: str) -> bool:
        """Dosya uzantisi kuraldaki dil ile eslesir mi."""
        if not self.languages:
            return True
        ext_map = {
            "javascript": {".js", ".jsx", ".mjs"},
            "typescript": {".ts", ".tsx"},
            "python": {".py"},
            "go": {".go"},
            "rust": {".rs"},
            "java": {".java"},
            "kotlin": {".kt", ".kts"},
            "swift": {".swift"},
            "ruby": {".rb"},
            "php": {".php"},
            "dart": {".dart"},
            "csharp": {".cs"},
        }
        file_ext = Path(file_path).suffix.lower()
        for lang in self.languages:
            exts = ext_map.get(lang.lower(), set())
            if file_ext in exts:
                return True
        return False

    def check_constraints(self, match: re.Match) -> bool:
        """Constraint'leri kontrol et."""
        if not self.constraint:
            return True
        for var_name, constraint_pattern in self.constraint.items():
            try:
                captured = match.group(var_name)
            except (IndexError, KeyError):
                continue
            if not captured:
                continue
            # Constraint bir regex pattern ise
            if constraint_pattern.startswith("/") and constraint_pattern.endswith("/i"):
                regex = constraint_pattern[1:-2]
                if not re.search(regex, captured, re.IGNORECASE):
                    return False
            elif constraint_pattern.startswith("/") and constraint_pattern.endswith("/"):
                regex = constraint_pattern[1:-1]
                if not re.search(regex, captured):
                    return False
            else:
                if captured != constraint_pattern:
                    return False
        return True


class YAMLRuleEngine(BaseRunner):
    """YAML tabanli kural motoru."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self._rules: List[PatternRule] = []
        self._loaded = False

    def load_rules(self, rule_paths: List[str] = None) -> int:
        """YAML kural dosyalarini yukle."""
        if yaml is None:
            return 0

        if rule_paths is None:
            rule_paths = self._find_rule_files()

        for path in rule_paths:
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                if data and "rules" in data:
                    for rule_data in data["rules"]:
                        self._rules.append(PatternRule(rule_data))
            except (yaml.YAMLError, OSError, KeyError):
                continue

        self._loaded = True
        return len(self._rules)

    def _find_rule_files(self) -> List[str]:
        """Kural dosyalarini bul."""
        paths = []
        # Proje icindeki .nazar/rules/ dizini
        nazar_rules = self.root / ".nazar" / "rules"
        if nazar_rules.is_dir():
            for f in nazar_rules.glob("*.yml"):
                paths.append(str(f))
            for f in nazar_rules.glob("*.yaml"):
                paths.append(str(f))

        # Proje kokunde nazar-rules.yml
        for name in ["nazar-rules.yml", "nazar-rules.yaml", ".nazar-rules.yml"]:
            if (self.root / name).exists():
                paths.append(str(self.root / name))

        # Nazar dahili kurallar
        builtin = Path(__file__).parent.parent / "rules"
        if builtin.is_dir():
            for f in builtin.glob("*.yml"):
                paths.append(str(f))
            for f in builtin.glob("*.yaml"):
                paths.append(str(f))

        return paths

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        """Kural motorunu calistir."""
        if not self._loaded:
            self.load_rules()

        if not self._rules:
            return True, "YAML kural bulunamadi, SKIP"

        checks = {
            "yaml_security": lambda t: self._run_category("security", t),
            "yaml_code_quality": lambda t: self._run_category("code_quality", t),
            "yaml_custom": lambda t: self._run_all(t),
        }
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    def _run_category(self, category: str, test: dict) -> Tuple[bool, str]:
        """Belirli kategorideki kurallari calistir."""
        category_rules = [r for r in self._rules
                         if r.metadata.get("category", "") == category
                         or r.severity == category]
        if not category_rules:
            return True, "Bu kategoride kural yok"
        return self._scan_with_rules(category_rules)

    def _run_all(self, test: dict) -> Tuple[bool, str]:
        """Tum kurallari calistir."""
        return self._scan_with_rules(self._rules)

    def _scan_with_rules(self, rules: List[PatternRule]) -> Tuple[bool, str]:
        """Dosyalari verilen kurallarla tara."""
        all_findings = []

        for f in self.src_files()[:200]:
            # Test ve nazar dosyalarini atla
            if "test" in f.lower() or f.startswith("nazar/"):
                continue

            content = self.read(f)
            if not content:
                continue

            for rule in rules:
                if not rule.matches_language(f):
                    continue
                if not rule.compiled_pattern:
                    continue

                for match in rule.compiled_pattern.finditer(content):
                    # pattern_not kontrolu
                    if rule.compiled_not_pattern:
                        line_start = content.rfind("\n", 0, match.start()) + 1
                        line_end = content.find("\n", match.end())
                        line = content[line_start:line_end if line_end > 0 else len(content)]
                        if rule.compiled_not_pattern.search(line):
                            continue

                    # Constraint kontrolu
                    if not rule.check_constraints(match):
                        continue

                    line_num = content[:match.start()].count("\n") + 1
                    all_findings.append({
                        "rule_id": rule.id,
                        "message": rule.message,
                        "severity": rule.severity,
                        "file": f,
                        "line": line_num,
                        "match": match.group()[:80],
                        "fix": rule.fix,
                    })

        if not all_findings:
            return True, "Temiz - {} kural ile tarandi".format(len(rules))

        # Severity'e gore sirala
        severity_order = {"critical": 0, "high": 1, "warning": 2, "info": 3}
        all_findings.sort(key=lambda x: severity_order.get(x["severity"], 9))

        first = all_findings[0]
        return False, "{} bulgu: [{}] {} ({}:{})".format(
            len(all_findings), first["severity"],
            first["message"], first["file"], first["line"],
        )

    def get_findings_detail(self, rules: List[PatternRule] = None) -> List[Dict]:
        """Detayli bulgu listesi (rapor icin)."""
        if rules is None:
            rules = self._rules
        _, _ = self._scan_with_rules(rules)
        # Tekrar tara ve detayli sonuc don
        all_findings = []
        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            for rule in rules:
                if not rule.matches_language(f) or not rule.compiled_pattern:
                    continue
                for match in rule.compiled_pattern.finditer(content):
                    if rule.compiled_not_pattern:
                        line_start = content.rfind("\n", 0, match.start()) + 1
                        line_end = content.find("\n", match.end())
                        line = content[line_start:line_end if line_end > 0 else len(content)]
                        if rule.compiled_not_pattern.search(line):
                            continue
                    if not rule.check_constraints(match):
                        continue
                    line_num = content[:match.start()].count("\n") + 1
                    all_findings.append({
                        "rule_id": rule.id,
                        "message": rule.message,
                        "severity": rule.severity,
                        "file": f,
                        "line": line_num,
                        "match": match.group()[:120],
                        "fix": rule.fix,
                    })
        return all_findings
