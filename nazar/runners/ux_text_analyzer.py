"""UX Text Analyzer - UI string kalitesi, tutarlilik ve i18n hazirlik kontrolu."""
import re
from pathlib import Path
from typing import List, Dict, Tuple

from nazar.runners.base import BaseRunner

COMMON_MISSPELLINGS = {
    "occured": "occurred", "recieve": "receive", "seperate": "separate",
    "definately": "definitely", "accomodate": "accommodate", "succesful": "successful",
    "neccessary": "necessary", "occurence": "occurrence", "refered": "referred",
    "enviroment": "environment", "dependancy": "dependency", "retreive": "retrieve",
    "existance": "existence", "persistant": "persistent", "priviledge": "privilege",
    "catagory": "category", "accross": "across", "acheive": "achieve",
    "adress": "address", "agressive": "aggressive", "apparant": "apparent",
    "begining": "beginning", "beleive": "believe", "calender": "calendar",
    "commited": "committed", "concious": "conscious", "curiousity": "curiosity",
    "dissapear": "disappear", "embarass": "embarrass", "facinating": "fascinating",
    "goverment": "government", "harrass": "harass", "immediatly": "immediately",
    "independant": "independent", "knowlege": "knowledge", "liason": "liaison",
    "maintenence": "maintenance", "millenium": "millennium", "noticable": "noticeable",
    "paralell": "parallel", "perseverence": "perseverance", "publically": "publicly",
    "recomend": "recommend", "referance": "reference", "relevent": "relevant",
    "responsable": "responsible", "rythm": "rhythm", "sieze": "seize",
    "successfull": "successful", "supercede": "supersede", "tommorow": "tomorrow",
    "untill": "until", "wierd": "weird", "writting": "writing",
}

TERM_GROUPS = [
    {"login", "log in", "sign in", "signin"},
    {"logout", "log out", "sign out", "signout"},
    {"cancel", "close", "dismiss", "go back", "nevermind"},
    {"delete", "remove", "erase", "clear", "discard"},
    {"settings", "preferences", "options", "configuration"},
    {"save", "submit", "apply", "confirm", "done"},
    {"create", "add", "new", "insert"},
    {"edit", "modify", "update", "change"},
    {"search", "find", "look up", "query"},
    {"error", "problem", "issue", "failure", "fault"},
]

WEAK_BUTTON_TEXTS = {
    "ok", "yes", "no", "click here", "press here", "submit",
    "go", "next", "back", "done", "continue", "here",
}

def _fmt(hits, msg="bulundu"):
    if not hits:
        return True, "Temiz"
    first = hits[0]
    return False, f"{len(hits)} {msg}: {first['file']}:{first['line']}"


class UXTextAnalyzer(BaseRunner):
    """UI text kalitesi ve tutarlilik analizci."""

    def check_spelling(self, t: dict) -> Tuple[bool, str]:
        """UI stringlerinde yaygin yazim hatalari."""
        all_hits = []
        for wrong, correct in COMMON_MISSPELLINGS.items():
            hits = self.scan_pattern(r"\b" + wrong + r"\b", limit=100)
            for h in hits:
                h["match"] = f"{wrong} -> {correct}"
                all_hits.append(h)
        return _fmt(all_hits, "yazim hatasi")

    def check_term_consistency(self, t: dict) -> Tuple[bool, str]:
        """Ayni kavram icin farkli terimler kullanilmis."""
        inconsistencies = []
        for group in TERM_GROUPS:
            found_terms = set()
            for term in group:
                hits = self.scan_pattern(
                    r"""['"]""" + re.escape(term) + r"""['"]""",
                    limit=50
                )
                if hits:
                    found_terms.add(term)
            if len(found_terms) > 1:
                inconsistencies.append(f"{' vs '.join(found_terms)}")
        if inconsistencies:
            return False, f"{len(inconsistencies)} tutarsizlik: {inconsistencies[0]}"
        return True, "Temiz"

    def check_i18n_readiness(self, t: dict) -> Tuple[bool, str]:
        """Hardcoded UI string'ler - i18n icin hazir degil."""
        # JSX icinde sabit string
        hardcoded = self.scan_pattern(
            r"""(?:title|label|placeholder|headerTitle)\s*[:=]\s*['"][A-Z][a-zA-Z\s]{3,}['"]""",
            limit=100
        )
        # Ceviri fonksiyonu kullanimi
        i18n_usage = self.scan_pattern(
            r"""(?:t\(|i18n\.|useTranslation|intl\.formatMessage|<Trans|<FormattedMessage)""",
            limit=100
        )
        if len(hardcoded) > 10 and len(i18n_usage) == 0:
            return False, f"{len(hardcoded)} hardcoded UI string, i18n sistemi yok"
        if len(hardcoded) > 0 and len(i18n_usage) > 0:
            ratio = len(hardcoded) / (len(hardcoded) + len(i18n_usage)) * 100
            if ratio > 50:
                return False, f"%{ratio:.0f} hardcoded ({len(hardcoded)} sabit vs {len(i18n_usage)} cevrili)"
        return True, f"{len(i18n_usage)} i18n kullanimi" if i18n_usage else "Temiz"

    def check_button_text_quality(self, t: dict) -> Tuple[bool, str]:
        """Belirsiz/zayif buton metinleri."""
        weak_hits = []
        for text in WEAK_BUTTON_TEXTS:
            hits = self.scan_pattern(
                r"""(?:<(?:Button|TouchableOpacity|Pressable)[^>]*(?:title|label)\s*[:=]\s*['"]""" + re.escape(text) + r"""['"]|>\s*""" + re.escape(text) + r"""\s*<)""",
                limit=50
            )
            for h in hits:
                h["match"] = f"Zayif: '{text}' -> Eylem belirten fiil kullanin"
            weak_hits.extend(hits)
        return _fmt(weak_hits, "zayif buton metni")

    def check_error_message_quality(self, t: dict) -> Tuple[bool, str]:
        """Teknik/kullanici-dostu olmayan hata mesajlari."""
        tech_errors = self.scan_pattern(
            r"""(?:alert|showError|setError|errorMessage|toast\.error)\s*\([^)]*(?:null|undefined|NaN|stack|trace|exception|500|404|ECONNREFUSED|ETIMEDOUT)""",
            limit=50
        )
        return _fmt(tech_errors, "teknik hata mesaji (kullanici-dostu degil)")

    def check_truncation_risk(self, t: dict) -> Tuple[bool, str]:
        """Cok uzun UI string'ler - ekranda kesilme riski."""
        long_strings = self.scan_pattern(
            r"""(?:title|label|placeholder|headerTitle|buttonText)\s*[:=]\s*['"][^'"]{60,}['"]""",
            limit=50
        )
        return _fmt(long_strings, "uzun string (kesme riski)")

    def check_missing_alt_text(self, t: dict) -> Tuple[bool, str]:
        """Gorsellerde alt text / accessibilityLabel eksik."""
        images = self.scan_pattern(r"""<(?:Image|img)\b[^>]*/>""", limit=100)
        with_alt = self.scan_pattern(r"""<(?:Image|img)\b[^>]*(?:alt|accessibilityLabel)\s*=""", limit=100)
        without = len(images) - len(with_alt)
        if without > 3:
            return False, f"{without}/{len(images)} gorsel alt text/label eksik"
        return True, "Temiz"

    def check_placeholder_quality(self, t: dict) -> Tuple[bool, str]:
        """Input placeholder kalitesi - label yerine placeholder kullanimi."""
        placeholders = self.scan_pattern(
            r"""placeholder\s*[:=]\s*['"][^'"]+['"]""",
            limit=100
        )
        labels = self.scan_pattern(
            r"""(?:label|aria-label|accessibilityLabel)\s*[:=]\s*['"][^'"]+['"]""",
            limit=100
        )
        if len(placeholders) > 5 and len(labels) < len(placeholders) * 0.5:
            return False, f"{len(placeholders)} placeholder ama {len(labels)} label - placeholder label yerine gecmemeli"
        return True, "Temiz"

    def get_all_checks(self) -> Dict[str, callable]:
        return {
            "spelling": self.check_spelling,
            "term_consistency": self.check_term_consistency,
            "i18n_readiness": self.check_i18n_readiness,
            "button_text_quality": self.check_button_text_quality,
            "error_message_quality": self.check_error_message_quality,
            "truncation_risk": self.check_truncation_risk,
            "missing_alt_text": self.check_missing_alt_text,
            "placeholder_quality": self.check_placeholder_quality,
        }

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = self.get_all_checks()
        fn = checks.get(subtype)
        return fn(test) if fn else (True, "SKIP")
