"""Rule Builder - Interaktif kural olusturma araci."""

import re
import os
import glob as _glob
import threading
from pathlib import Path
from typing import Optional

try:
    import yaml as _yaml
except ImportError:
    _yaml = None


SEVERITY_CHOICES = ("critical", "high", "medium", "low")

_REGEX_TEST_TIMEOUT = 2  # saniye - kullanici regex'inin test limiti


def _test_regex_with_timeout(pattern_str: str, test_text: str, timeout: float = _REGEX_TEST_TIMEOUT) -> bool:
    """Regex'i kisa bir metin uzerinde timeout ile test eder.

    ReDoS saldirilarina karsi koruma saglar. Eger regex verilen sure
    icinde tamamlanmazsa False doner.

    Returns:
        True: regex guvenli ve zamaninda tamamlandi
        False: regex cok yavas veya hata verdi
    """
    result = [False]
    error = [None]

    def _run():
        try:
            compiled = re.compile(pattern_str)
            compiled.search(test_text)
            result[0] = True
        except re.error as e:
            error[0] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        return False
    if error[0] is not None:
        return False
    return result[0]

DEFAULT_LANGUAGES = [
    "javascript", "typescript", "python", "go", "rust", "java",
    "kotlin", "swift", "ruby", "php", "csharp",
]

DEFAULT_FILE_PATTERNS = {
    "javascript": ["*.js", "*.jsx", "*.mjs", "*.cjs"],
    "typescript": ["*.ts", "*.tsx"],
    "python": ["*.py"],
    "go": ["*.go"],
    "rust": ["*.rs"],
    "java": ["*.java"],
    "kotlin": ["*.kt", "*.kts"],
    "swift": ["*.swift"],
    "ruby": ["*.rb"],
    "php": ["*.php"],
    "csharp": ["*.cs"],
}


class RuleBuilder:
    """Interaktif kural olusturucu."""

    def create_rule(self) -> dict:
        """Kullanicidan interaktif olarak kural bilgilerini alir.

        Returns:
            dict: Kural sozlugu. Ornek:
                {
                    "id": "no-console-log",
                    "pattern": "console\\.log\\(",
                    "message": "console.log kullanilmamali",
                    "severity": "medium",
                    "languages": ["javascript", "typescript"],
                    "file_patterns": ["*.js", "*.ts"],
                }
        """
        rule = {}

        # Rule ID
        rule["id"] = input("Kural ID (ornek: no-console-log): ").strip()
        if not rule["id"]:
            raise ValueError("Kural ID bos olamaz")

        # Pattern (regex)
        pattern_str = input("Regex kalip (ornek: console\\.log\\(): ").strip()
        if not pattern_str:
            raise ValueError("Pattern bos olamaz")
        # Regex gecerliligi
        try:
            re.compile(pattern_str)
        except re.error as e:
            raise ValueError(f"Gecersiz regex: {e}")
        rule["pattern"] = pattern_str

        # Mesaj
        rule["message"] = input("Uyari mesaji: ").strip()
        if not rule["message"]:
            rule["message"] = f"Kural ihlali: {rule['id']}"

        # Severity
        print(f"Onem seviyesi ({', '.join(SEVERITY_CHOICES)}):")
        severity = input("Seviye [medium]: ").strip().lower()
        if severity not in SEVERITY_CHOICES:
            severity = "medium"
        rule["severity"] = severity

        # Diller
        print(f"Diller ({', '.join(DEFAULT_LANGUAGES)}):")
        langs_input = input("Diller (virgul ile, bos = hepsi): ").strip()
        if langs_input:
            rule["languages"] = [l.strip() for l in langs_input.split(",") if l.strip()]
        else:
            rule["languages"] = []

        # Dosya kaliplari
        if rule["languages"]:
            default_fps = []
            for lang in rule["languages"]:
                default_fps.extend(DEFAULT_FILE_PATTERNS.get(lang, []))
            if default_fps:
                print(f"Varsayilan dosya kaliplari: {', '.join(default_fps)}")
                use_default = input("Bunlari kullan? [E/h]: ").strip().lower()
                if use_default in ("", "e", "evet", "y", "yes"):
                    rule["file_patterns"] = default_fps
                else:
                    fp_input = input("Dosya kaliplari (virgul ile, ornek: *.js, *.ts): ").strip()
                    rule["file_patterns"] = [f.strip() for f in fp_input.split(",") if f.strip()] if fp_input else []
            else:
                fp_input = input("Dosya kaliplari (virgul ile, ornek: *.js, *.ts): ").strip()
                rule["file_patterns"] = [f.strip() for f in fp_input.split(",") if f.strip()] if fp_input else []
        else:
            fp_input = input("Dosya kaliplari (virgul ile, bos = hepsi): ").strip()
            rule["file_patterns"] = [f.strip() for f in fp_input.split(",") if f.strip()] if fp_input else []

        # Opsiyonel: aciklama
        desc = input("Aciklama (opsiyonel): ").strip()
        if desc:
            rule["description"] = desc

        # Opsiyonel: fix onerisi
        fix = input("Duzeltme onerisi (opsiyonel): ").strip()
        if fix:
            rule["fix"] = fix

        return rule

    @staticmethod
    def validate_rule(rule_dict: dict) -> list:
        """Kural sozlugunu dogrular.

        Args:
            rule_dict: Dogrulanacak kural.

        Returns:
            list: Hata mesajlari listesi. Bossa kural gecerlidir.
        """
        errors = []

        # Zorunlu alanlar
        required = ("id", "pattern", "message", "severity")
        for field in required:
            if field not in rule_dict or not str(rule_dict[field]).strip():
                errors.append(f"Zorunlu alan eksik: {field}")

        # Regex gecerliligi
        pattern = rule_dict.get("pattern", "")
        if pattern:
            try:
                re.compile(pattern)
            except re.error as e:
                errors.append(f"Gecersiz regex pattern: {e}")

        # Severity kontrolu
        severity = rule_dict.get("severity", "")
        if severity and severity not in SEVERITY_CHOICES:
            errors.append(f"Gecersiz severity: '{severity}'. Gecerli: {', '.join(SEVERITY_CHOICES)}")

        # ID format kontrolu (alfanumerik, tire, alt cizgi)
        rule_id = rule_dict.get("id", "")
        if rule_id and not re.match(r'^[a-zA-Z0-9_-]+$', rule_id):
            errors.append(f"Gecersiz ID formati: '{rule_id}'. Sadece harf, rakam, tire ve alt cizgi kullanin.")

        # Languages kontrolu (varsa liste olmali)
        languages = rule_dict.get("languages")
        if languages is not None and not isinstance(languages, list):
            errors.append("'languages' alani bir liste olmali")

        # File patterns kontrolu (varsa liste olmali)
        file_patterns = rule_dict.get("file_patterns")
        if file_patterns is not None and not isinstance(file_patterns, list):
            errors.append("'file_patterns' alani bir liste olmali")

        return errors

    @staticmethod
    def test_rule(rule_dict: dict, project_path: str) -> list:
        """Kurali bir proje uzerinde test eder.

        Args:
            rule_dict: Test edilecek kural.
            project_path: Proje dizini.

        Returns:
            list: Eslesen sonuclar. Her eleman:
                {"file": str, "line": int, "match": str, "context": str}
        """
        errors = RuleBuilder.validate_rule(rule_dict)
        if errors:
            raise ValueError(f"Kural gecersiz: {'; '.join(errors)}")

        # ReDoS koruması: regex'i kisa bir test metni ile timeout icinde dene
        test_text = "a" * 500 + " " * 100 + "b" * 500
        if not _test_regex_with_timeout(rule_dict["pattern"], test_text):
            raise ValueError(
                f"Regex guvenlik hatasi: '{rule_dict['pattern']}' cok yavas "
                f"veya potansiyel ReDoS riski tasiyor. Regex'i sadellestirin."
            )

        pattern = re.compile(rule_dict["pattern"])
        file_patterns = rule_dict.get("file_patterns", [])
        matches = []

        # Dosyalari topla
        project = Path(project_path)
        if not project.exists():
            raise FileNotFoundError(f"Proje dizini bulunamadi: {project_path}")

        # Taranacak dosyalari bul
        files_to_scan = []
        ignore_dirs = {
            "node_modules", ".git", "build", "dist", "__pycache__",
            ".pytest_cache", "venv", ".venv", "env", "Pods",
            ".gradle", "coverage", "vendor", ".next", ".nuxt",
        }

        if file_patterns:
            for fp in file_patterns:
                for f in project.rglob(fp):
                    if not any(ign in f.parts for ign in ignore_dirs):
                        files_to_scan.append(f)
        else:
            # Tum text dosyalari tara
            text_exts = {
                ".js", ".jsx", ".ts", ".tsx", ".py", ".go", ".rs",
                ".java", ".kt", ".swift", ".rb", ".php", ".cs",
                ".html", ".css", ".scss", ".vue", ".svelte",
                ".yaml", ".yml", ".json", ".toml", ".xml",
                ".sh", ".bash", ".zsh", ".md", ".txt",
            }
            for root, dirs, filenames in os.walk(project):
                dirs[:] = [d for d in dirs if d not in ignore_dirs]
                for fname in filenames:
                    fpath = Path(root) / fname
                    if fpath.suffix.lower() in text_exts:
                        files_to_scan.append(fpath)

        # Dosyalari tara
        for fpath in files_to_scan:
            try:
                content = fpath.read_text(errors="ignore")
                for line_num, line in enumerate(content.splitlines(), 1):
                    match = pattern.search(line)
                    if match:
                        # Birkac satir context al
                        all_lines = content.splitlines()
                        ctx_start = max(0, line_num - 3)
                        ctx_end = min(len(all_lines), line_num + 2)
                        context_lines = all_lines[ctx_start:ctx_end]

                        rel_path = str(fpath.relative_to(project))
                        matches.append({
                            "file": rel_path,
                            "line": line_num,
                            "match": match.group(0),
                            "content": line.strip(),
                            "context": "\n".join(context_lines),
                        })
            except (PermissionError, OSError):
                continue

        return matches

    @staticmethod
    def save_rule(rule_dict: dict, output_path: str, project_path: str = None) -> str:
        """Kurali YAML dosyasina kaydeder.

        Args:
            rule_dict: Kaydedilecek kural.
            output_path: Cikti dosya yolu.
            project_path: Proje dizini (path validation icin).

        Returns:
            str: Kaydedilen dosyanin yolu.
        """
        # Path validation: cikti yolu guvenli alanlarda olmali
        resolved_output = str(Path(output_path).resolve())
        home_dir = str(Path.home().resolve())
        allowed = False
        if resolved_output.startswith(home_dir):
            allowed = True
        if project_path:
            resolved_project = str(Path(project_path).resolve())
            if resolved_output.startswith(resolved_project):
                allowed = True
        if not allowed:
            raise ValueError(
                f"Guvenlik hatasi: '{resolved_output}' yolu kullanici dizini "
                f"veya proje dizini disinda. Kural dosyasi bu konuma kaydedilemez."
            )

        if _yaml is None:
            # YAML olmadan da kaydet (basit format)
            return _save_rule_simple(rule_dict, output_path)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        # Mevcut dosya varsa, kurallari yukle ve ekle
        existing_rules = []
        if output.exists():
            try:
                with open(output, "r") as f:
                    data = _yaml.safe_load(f)
                if data and isinstance(data, dict):
                    existing_rules = data.get("rules", [])
            except Exception:
                pass

        # Ayni ID varsa guncelle, yoksa ekle
        rule_id = rule_dict.get("id", "")
        updated = False
        for i, existing in enumerate(existing_rules):
            if existing.get("id") == rule_id:
                existing_rules[i] = rule_dict
                updated = True
                break
        if not updated:
            existing_rules.append(rule_dict)

        data = {"rules": existing_rules}

        with open(output, "w") as f:
            _yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return str(output)

    @staticmethod
    def list_rules(rules_dir: Optional[str] = None) -> list:
        """Tum kurallari listeler (yerlesik + ozel).

        Args:
            rules_dir: Ozel kural dizini. None ise varsayilan dizin kullanilir.

        Returns:
            list: Kural listesi. Her eleman:
                {"id": str, "severity": str, "message": str, "source": str}
        """
        all_rules = []

        # 1. Yerlesik kurallar (language_rules'dan)
        try:
            from nazar.runners.language_rules import APPLY_RULES, SKIP_RULES
            builtin_ids = set(list(APPLY_RULES.keys()) + list(SKIP_RULES.keys()))
            for rule_id in sorted(builtin_ids):
                all_rules.append({
                    "id": rule_id,
                    "severity": "medium",
                    "message": f"Yerlesik kural: {rule_id}",
                    "source": "builtin",
                    "languages": [],
                })
        except ImportError:
            pass

        # 2. Ozel kurallar (YAML dosyalarindan)
        search_dirs = []
        if rules_dir:
            search_dirs.append(rules_dir)

        # Varsayilan dizinler
        home_rules = os.path.expanduser("~/.nazar/rules")
        if os.path.isdir(home_rules):
            search_dirs.append(home_rules)

        cwd_rules = os.path.join(os.getcwd(), ".nazar", "rules")
        if os.path.isdir(cwd_rules):
            search_dirs.append(cwd_rules)

        for sdir in search_dirs:
            yaml_files = (
                _glob.glob(os.path.join(sdir, "*.yaml"))
                + _glob.glob(os.path.join(sdir, "*.yml"))
            )
            for yf in yaml_files:
                try:
                    if _yaml is None:
                        continue
                    with open(yf, "r") as f:
                        data = _yaml.safe_load(f)
                    if not data or not isinstance(data, dict):
                        continue
                    for rule in data.get("rules", []):
                        all_rules.append({
                            "id": rule.get("id", "?"),
                            "severity": rule.get("severity", "medium"),
                            "message": rule.get("message", ""),
                            "source": os.path.basename(yf),
                            "languages": rule.get("languages", []),
                            "file_patterns": rule.get("file_patterns", []),
                        })
                except Exception:
                    continue

        return all_rules


def _save_rule_simple(rule_dict: dict, output_path: str) -> str:
    """YAML modulu olmadan basit formatta kaydet."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    rule_id = rule_dict.get("id", "")

    # Duplicate ID kontrolu: mevcut dosyada ayni ID varsa hata ver
    if output.exists():
        existing = output.read_text()
        # Basit ID arama: "  - id: <rule_id>" formatinda
        existing_ids = re.findall(r'^\s*-\s*id:\s*(.+)$', existing, re.MULTILINE)
        existing_ids = [rid.strip().strip('"').strip("'") for rid in existing_ids]
        if rule_id in existing_ids:
            raise ValueError(
                f"Ayni ID ile kural zaten mevcut: '{rule_id}'. "
                f"Farkli bir ID kullanin veya YAML modulu ile guncelleme yapin."
            )

    lines = ["rules:"]
    lines.append(f"  - id: {rule_dict.get('id', '')}")
    lines.append(f"    pattern: \"{rule_dict.get('pattern', '')}\"")
    lines.append(f"    message: \"{rule_dict.get('message', '')}\"")
    lines.append(f"    severity: {rule_dict.get('severity', 'medium')}")

    langs = rule_dict.get("languages", [])
    if langs:
        lines.append("    languages:")
        for lang in langs:
            lines.append(f"      - {lang}")

    fps = rule_dict.get("file_patterns", [])
    if fps:
        lines.append("    file_patterns:")
        for fp in fps:
            lines.append(f"      - \"{fp}\"")

    desc = rule_dict.get("description")
    if desc:
        lines.append(f"    description: \"{desc}\"")

    fix = rule_dict.get("fix")
    if fix:
        lines.append(f"    fix: \"{fix}\"")

    content = "\n".join(lines) + "\n"

    # Mevcut dosya varsa append et
    if output.exists():
        existing = output.read_text()
        if "rules:" in existing:
            # Sadece kural kismini ekle (rules: basligini atla)
            rule_lines = "\n".join(lines[1:])
            content = existing.rstrip() + "\n" + rule_lines + "\n"
        else:
            content = existing.rstrip() + "\n\n" + content

    output.write_text(content)
    return str(output)
