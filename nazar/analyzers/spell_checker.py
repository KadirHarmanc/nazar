"""Spell Checker - UI stringlerinde yazim hatasi tespiti.

Turkce: Zeyrek (optional) + dahili sozluk fallback
Ingilizce: pyspellchecker (optional) + dahili sozluk fallback
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Set

from nazar.runners.base import BaseRunner
from nazar.analyzers.ui_element_extractor import UIElementExtractor, UIElement

# Dahili Ingilizce yaygın UI terimleri (false positive onleme)
KNOWN_UI_TERMS = {
    "login", "logout", "signup", "signin", "username", "password", "email",
    "submit", "cancel", "save", "delete", "edit", "update", "search",
    "settings", "profile", "home", "dashboard", "loading", "error",
    "retry", "refresh", "ok", "yes", "no", "back", "next", "prev",
    "continue", "skip", "done", "close", "open", "add", "remove",
    "share", "send", "upload", "download", "photo", "camera", "gallery",
    "notification", "message", "chat", "call", "video", "audio",
    "placeholder", "default", "sample", "example", "demo", "test",
    "app", "menu", "tab", "nav", "btn", "img", "icon", "logo",
    "todo", "fixme", "hack", "url", "api", "http", "https", "www",
}

# Framework / kod terimleri (hata degil)
CODE_TERMS = {
    "usestate", "useeffect", "useref", "usememo", "usecallback",
    "usequery", "useswr", "usemutation", "useform", "usenavigate",
    "asyncstorage", "stylesheet", "flatlist", "scrollview", "textinput",
    "touchableopacity", "pressable", "safeareaview", "keyboardavoidingview",
    "imagebackground", "activityindicator", "sectionlist",
    "navigator", "stacknavigator", "tabnavigator", "drawernavigator",
    "onpress", "onchange", "onsubmit", "onclick", "onblur", "onfocus",
    "setstate", "getstate", "dispatch", "reducer", "middleware",
    "flexdirection", "justifycontent", "alignitems", "flexwrap",
    "fontsize", "fontweight", "fontfamily", "lineheight", "textalign",
    "backgroundcolor", "borderradius", "borderwidth", "bordercolor",
    "marginvertical", "marginhorizontal", "paddingvertical", "paddinghorizontal",
    "supabase", "firebase", "expo", "react", "redux", "mobx",
}

SKIP_PATTERNS = [
    r'^[0-9\s\.\,\-\+\*\/\=\<\>\!\?\@\#\$\%\^\&\(\)\[\]\{\}]+$',
    r'^[A-Z]{1,5}$',
    r'^https?://',
    r'^[a-zA-Z0-9._%+-]+@',
    r'^\d+x\d+$',
    r'^[/\\]',
    r'^\w+\.\w+$',  # dosya adi (file.ext)
]


class SpellChecker(BaseRunner):
    """UI stringlerinde yazim hatasi tespiti."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self._zeyrek = None
        self._en_checker = None
        self._extractor = UIElementExtractor(project_path)
        self._custom_dict: Set[str] = set()
        self._load_custom_dict()

    def _load_custom_dict(self):
        """Proje bazli ozel sozluk yukle."""
        dict_file = self.root / ".nazar" / "dictionary.txt"
        if dict_file.exists():
            self._custom_dict = set(dict_file.read_text(errors="ignore").lower().split())

    def _init_zeyrek(self):
        if self._zeyrek is not None:
            return
        try:
            import zeyrek
            self._zeyrek = zeyrek.MorphAnalyzer()
        except (ImportError, Exception):
            self._zeyrek = False  # Yuklu degil

    def _init_en_checker(self):
        if self._en_checker is not None:
            return
        try:
            from spellchecker import SpellChecker as PySpell
            self._en_checker = PySpell()
        except ImportError:
            self._en_checker = False

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        if subtype == "spell_check":
            return self._spell_check(test)
        return True, "SKIP"

    def _spell_check(self, t: dict) -> Tuple[bool, str]:
        """UI elementlerindeki yazim hatalarini tespit et."""
        elements = self._extractor.extract()
        if not elements:
            return True, "UI elementi bulunamadi"

        findings = []
        for el in elements:
            text = el.text.strip()
            if not text or len(text) < 2:
                continue
            if el.props.get("i18n"):
                continue  # i18n key, kontrol etme

            words = self._tokenize(text)
            for word in words:
                if self._should_skip(word):
                    continue
                result = self._check_word(word)
                if not result["valid"]:
                    findings.append({
                        "word": word,
                        "suggestion": result.get("suggestion", ""),
                        "file": el.file,
                        "line": el.line,
                        "element": el.element_type,
                        "confidence": result.get("confidence", 70),
                    })

        if not findings:
            return True, "Yazim hatasi bulunamadi"

        # Confidence 70+ olanlari raporla
        high_conf = [f for f in findings if f["confidence"] >= 70]
        if not high_conf:
            return True, "Yazim hatasi bulunamadi (dusuk confidence atlanidi)"

        first = high_conf[0]
        detail = "{} yazim hatasi: '{}' -> '{}' ({}:{})".format(
            len(high_conf), first["word"], first["suggestion"], first["file"], first["line"])
        return False, detail

    def _tokenize(self, text: str) -> List[str]:
        """Metni kelimelere ayir. camelCase parcala."""
        # camelCase parcala: userName -> user, Name
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        # snake_case parcala
        text = text.replace("_", " ")
        words = re.findall(r'[a-zA-ZğüşıöçĞÜŞİÖÇ]{2,}', text)
        return words

    def _should_skip(self, word: str) -> bool:
        """Bu kelime kontrol edilmemeli mi?"""
        lower = word.lower()
        if lower in KNOWN_UI_TERMS or lower in CODE_TERMS:
            return True
        if lower in self._custom_dict:
            return True
        if any(re.match(p, word) for p in SKIP_PATTERNS):
            return True
        if len(word) <= 2:
            return True
        return False

    def _check_word(self, word: str) -> dict:
        """Kelimeyi kontrol et. Turkce ve Ingilizce."""
        lower = word.lower()

        # 1. Zeyrek ile Turkce kontrol
        self._init_zeyrek()
        if self._zeyrek and self._zeyrek is not False:
            try:
                results = self._zeyrek.lemmatize(lower)
                if results and results[0][1] and results[0][1] != [lower]:
                    return {"valid": True, "root": results[0][1][0]}
                # Zeyrek kok bulamadi - Turkce hatali olabilir
                if results and results[0][1] == [lower]:
                    # Kok kendisi = bilinmeyen kelime, Ingilizce'ye gec
                    pass
            except Exception:
                pass

        # 2. Ingilizce kontrol
        self._init_en_checker()
        if self._en_checker and self._en_checker is not False:
            unknown = self._en_checker.unknown([lower])
            if not unknown:
                return {"valid": True}
            # Ingilizce'de de bilinmiyor - oneri bul
            correction = self._en_checker.correction(lower)
            if correction and correction != lower:
                return {"valid": False, "suggestion": correction, "confidence": 75}

        # 3. Zeyrek varsa ve Ingilizce de bilmiyorsa - Turkce hatali
        if self._zeyrek and self._zeyrek is not False:
            suggestion = self._suggest_turkish(lower)
            if suggestion:
                return {"valid": False, "suggestion": suggestion, "confidence": 80}

        # 4. Hicbir sozlukte yok - bilinmeyen (hata sayma)
        return {"valid": True}  # Bilinmeyen = hata sayma, false positive onle

    def _suggest_turkish(self, word: str) -> str:
        """Turkce benzer kelime onerisi (Levenshtein)."""
        # Basit: kok analizi yapilabilen en yakin kelimeyi bul
        if not self._zeyrek or self._zeyrek is False:
            return ""
        # Tek harf degisiklikleri dene
        candidates = []
        alphabet = "abcdefghijklmnoprstuvyzçğıöşü"
        for i in range(len(word)):
            for c in alphabet:
                candidate = word[:i] + c + word[i+1:]
                if candidate != word:
                    try:
                        results = self._zeyrek.lemmatize(candidate)
                        if results and results[0][1] and results[0][1] != [candidate]:
                            return candidate
                    except Exception:
                        pass
        return ""
