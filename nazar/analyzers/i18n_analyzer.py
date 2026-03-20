"""i18n Analyzer - Hardcoded string tespiti ve i18n hazirlik skoru."""
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

from nazar.runners.base import BaseRunner

SKIP_PATTERNS = [
    r'^[0-9\s\.\,\-\+\*\/\=\<\>\!\?\@\#\$\%\^\&\(\)\[\]\{\}]+$',
    r'^[A-Z]{1,5}$',
    r'^https?://',
    r'^[a-zA-Z0-9._%+-]+@',
    r'^\d+x\d+$',
    r'^[/\\]',
    r'^\s*$',
    r'^[\u2600-\u27BF\U0001F600-\U0001F64F]',
]


class I18nAnalyzer(BaseRunner):
    """Hardcoded string tespiti ve i18n hazirlik skoru."""

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        if subtype == "i18n_deep":
            return self._i18n_deep(test)
        return True, "SKIP"

    def _detect_i18n_system(self) -> bool:
        indicators = [
            "i18n.ts", "i18n.js", "i18next.config.js", "i18next.config.ts",
            "src/i18n.ts", "src/i18n.js", "src/locales", "locales",
            "translations", "lang", "src/translations", "src/lang",
        ]
        for ind in indicators:
            if (self.root / ind).exists():
                return True
        pkg = self.root / "package.json"
        if pkg.exists():
            content = pkg.read_text(errors="ignore")
            if any(k in content for k in ["i18next", "react-intl", "vue-i18n", "i18n"]):
                return True
        return False

    def _i18n_deep(self, t: dict) -> Tuple[bool, str]:
        """Derin i18n analizi."""
        has_i18n = self._detect_i18n_system()
        hardcoded = []
        translated = []

        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            ext = Path(f).suffix.lower()
            if ext not in (".tsx", ".jsx", ".ts", ".js"):
                continue

            content = self.read(f)
            if not content:
                continue

            # <Text>{t('key')}</Text> = translated
            for m in re.finditer(r'<Text[^>]*>\{t\(["\']([^"\']+)["\']\)\}</Text>', content):
                translated.append({"key": m.group(1), "file": f})

            # <Text>hardcoded</Text> = hardcoded
            for m in re.finditer(r'<Text[^>]*>([^<{]+)</Text>', content):
                text = m.group(1).strip()
                if not text or len(text) < 2:
                    continue
                if any(re.match(p, text) for p in SKIP_PATTERNS):
                    continue
                line = content[:m.start()].count("\n") + 1
                hardcoded.append({"text": text, "file": f, "line": line})

            # title="hardcoded" props
            for m in re.finditer(r'(?:title|label|placeholder)=["\']([^"\']+)["\']', content):
                text = m.group(1).strip()
                if len(text) >= 3 and not any(re.match(p, text) for p in SKIP_PATTERNS):
                    # t() icinde mi kontrol et
                    context = content[max(0, m.start()-20):m.start()]
                    if "t(" not in context:
                        line = content[:m.start()].count("\n") + 1
                        hardcoded.append({"text": text, "file": f, "line": line})

        total = len(hardcoded) + len(translated)
        if total == 0:
            return True, "UI string bulunamadi"

        coverage = (len(translated) / total * 100) if total else 100

        if not hardcoded:
            return True, "i18n coverage %100 ({} string)".format(total)

        # En onemli 5
        top5 = hardcoded[:5]
        top5_str = ", ".join(['"{}"'.format(h["text"][:20]) for h in top5])

        if has_i18n:
            return False, "{} hardcoded string (i18n coverage {:.0f}%): {}".format(
                len(hardcoded), coverage, top5_str)
        return False, "{} hardcoded string, i18n sistemi kurulmamis: {}".format(
            len(hardcoded), top5_str)
