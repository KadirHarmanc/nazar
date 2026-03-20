"""Rule Validator - YAML kural dosyasi dogrulayici."""

import re
from pathlib import Path
from typing import Union

try:
    import yaml as _yaml
except ImportError:
    _yaml = None


SEVERITY_CHOICES = ("critical", "high", "medium", "low")
REQUIRED_FIELDS = ("id", "pattern", "message", "severity")


def validate_yaml_rules(path: Union[str, Path]) -> list:
    """YAML kural dosyasini dogrular.

    Kontrol ettikleri:
    - Dosya var mi ve okunabiliyor mu
    - Gecerli YAML formati mi
    - 'rules' alani var mi ve liste mi
    - Her kuralda zorunlu alanlar var mi (id, pattern, message, severity)
    - Regex gecerli mi
    - Tekrar eden ID var mi

    Args:
        path: YAML dosya yolu.

    Returns:
        list: Hata mesajlari listesi. Bossa dosya gecerlidir.
    """
    if _yaml is None:
        return ["PyYAML modulu kurulu degil. pip install pyyaml"]

    path = Path(path)
    errors = []

    # Dosya kontrolu
    if not path.exists():
        return [f"Dosya bulunamadi: {path}"]

    if not path.is_file():
        return [f"Bu bir dosya degil: {path}"]

    if path.suffix.lower() not in (".yaml", ".yml"):
        errors.append(f"Uyari: Dosya uzantisi .yaml veya .yml degil: {path.suffix}")

    # YAML okuma
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f)
    except _yaml.YAMLError as e:
        return [f"YAML parse hatasi: {e}"]
    except UnicodeDecodeError as e:
        return [f"Dosya okunamadi (encoding hatasi): {e}"]

    if data is None:
        return ["Dosya bos"]

    if not isinstance(data, dict):
        return ["YAML root bir dict olmali (rules: [...] formatinda)"]

    # rules alani kontrolu
    rules = data.get("rules")
    if rules is None:
        return ["'rules' alani bulunamadi. Beklenen format: rules: [...]"]

    if not isinstance(rules, list):
        return ["'rules' alani bir liste olmali"]

    if len(rules) == 0:
        errors.append("Uyari: rules listesi bos")
        return errors

    # Her kurali dogrula
    seen_ids = set()

    for idx, rule in enumerate(rules):
        prefix = f"Kural #{idx + 1}"

        if not isinstance(rule, dict):
            errors.append(f"{prefix}: Kural bir dict olmali, {type(rule).__name__} bulundu")
            continue

        rule_id = rule.get("id", f"<isimsiz-{idx + 1}>")
        prefix = f"Kural '{rule_id}'"

        # Zorunlu alan kontrolu
        for field in REQUIRED_FIELDS:
            val = rule.get(field)
            if val is None:
                errors.append(f"{prefix}: Zorunlu alan eksik: '{field}'")
            elif isinstance(val, str) and not val.strip():
                errors.append(f"{prefix}: Alan bos olamaz: '{field}'")

        # Regex gecerliligi
        pattern = rule.get("pattern", "")
        if pattern:
            try:
                re.compile(str(pattern))
            except re.error as e:
                errors.append(f"{prefix}: Gecersiz regex pattern: {e}")

        # Severity kontrolu
        severity = rule.get("severity", "")
        if severity and str(severity) not in SEVERITY_CHOICES:
            errors.append(
                f"{prefix}: Gecersiz severity '{severity}'. "
                f"Gecerli: {', '.join(SEVERITY_CHOICES)}"
            )

        # ID format kontrolu
        if rule.get("id"):
            rid = str(rule["id"])
            if not re.match(r'^[a-zA-Z0-9_-]+$', rid):
                errors.append(
                    f"{prefix}: Gecersiz ID formati. "
                    "Sadece harf, rakam, tire ve alt cizgi kullanin."
                )

        # Tekrar eden ID kontrolu
        if rule.get("id"):
            rid = str(rule["id"])
            if rid in seen_ids:
                errors.append(f"{prefix}: Tekrar eden ID: '{rid}'")
            seen_ids.add(rid)

        # Languages kontrolu (varsa liste olmali)
        languages = rule.get("languages")
        if languages is not None and not isinstance(languages, list):
            errors.append(f"{prefix}: 'languages' alani bir liste olmali")

        # File patterns kontrolu (varsa liste olmali)
        file_patterns = rule.get("file_patterns")
        if file_patterns is not None and not isinstance(file_patterns, list):
            errors.append(f"{prefix}: 'file_patterns' alani bir liste olmali")

    return errors
