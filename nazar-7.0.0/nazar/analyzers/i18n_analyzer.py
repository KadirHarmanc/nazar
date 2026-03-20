"""i18n Analyzer - Hardcoded string tespiti, coverage, missing/unused key, locale consistency, RTL."""
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

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

# RTL dilleri
RTL_LOCALES = {"ar", "he", "fa", "ur", "yi", "arc", "az", "dv", "ku", "ps", "sd", "ug"}

# i18n fonksiyon cagrilari pattern'leri
# t('key'), i18n.t('key'), intl.formatMessage({id: 'key'}), $t('key'), tc('key')
T_CALL_PATTERNS = [
    re.compile(r'''(?:^|[^a-zA-Z])t\(\s*['\"]([^'\"]+)['\"]\s*\)'''),
    re.compile(r'''i18n\.t\(\s*['\"]([^'\"]+)['\"]\s*\)'''),
    re.compile(r'''intl\.formatMessage\(\s*\{\s*id:\s*['\"]([^'\"]+)['\"]'''),
    re.compile(r'''\$t\(\s*['\"]([^'\"]+)['\"]\s*\)'''),
    re.compile(r'''tc\(\s*['\"]([^'\"]+)['\"]\s*\)'''),
    re.compile(r'''useTranslation.*?\bt\(\s*['\"]([^'\"]+)['\"]\s*\)'''),
    re.compile(r'''Trans\s+i18nKey=['\"]([^'\"]+)['\"]'''),
]

# Hardcoded string iceren JSX/TSX pattern'leri (genisletilmis)
HARDCODED_JSX_PATTERNS = [
    # <Text>hardcoded</Text>
    (re.compile(r'<Text[^>]*>([^<{]+)</Text>'), 2),
    # <Button title="hardcoded" />
    (re.compile(r'<Button[^>]*\btitle=["\']([^"\']+)["\']'), 3),
    # <TextInput placeholder="hardcoded" />
    (re.compile(r'<TextInput[^>]*\bplaceholder=["\']([^"\']+)["\']'), 3),
    # <Label>hardcoded</Label>
    (re.compile(r'<Label[^>]*>([^<{]+)</Label>'), 2),
    # Generic title/label/placeholder/alt/aria-label props
    (re.compile(r'(?:title|label|placeholder|alt|aria-label)=["\']([^"\']+)["\']'), 3),
    # Alert.alert('title', 'message')
    (re.compile(r'Alert\.alert\(\s*["\']([^"\']+)["\']'), 3),
    # Toast/Snackbar messages
    (re.compile(r'(?:toast|snackbar|notify)\(\s*["\']([^"\']+)["\']', re.IGNORECASE), 4),
    # <H1/H2/H3/H4/H5/H6/P>text</...>
    (re.compile(r'<(?:H[1-6]|P|Heading|Title|Paragraph)[^>]*>([^<{]+)</(?:H[1-6]|P|Heading|Title|Paragraph)>'), 2),
]


class I18nAnalyzer(BaseRunner):
    """Derin i18n analizi - coverage, missing/unused keys, locale consistency, RTL."""

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        dispatch = {
            "i18n_deep": self._i18n_deep,
            "i18n_coverage": self._i18n_coverage,
            "missing_translation_keys": self._missing_translation_keys,
            "unused_translation_keys": self._unused_translation_keys,
            "locale_consistency": self._locale_consistency,
            "rtl_support": self._rtl_support,
        }
        fn = dispatch.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    # ----------------------------------------------------------------
    # Yardimci: i18n sistemi algilama
    # ----------------------------------------------------------------
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

    # ----------------------------------------------------------------
    # Yardimci: locale dosyalarini bul
    # ----------------------------------------------------------------
    def _find_locale_files(self) -> Dict[str, Path]:
        """locale code -> dosya yolu eslesmesi dondurur.
        Ornek: {"en": Path(".../en.json"), "tr": Path(".../tr.json")}
        """
        locale_dirs = [
            "locales", "src/locales", "translations", "src/translations",
            "lang", "src/lang", "i18n", "src/i18n", "assets/locales",
            "app/locales", "public/locales",
        ]
        locale_files: Dict[str, Path] = {}

        for d in locale_dirs:
            loc_path = self.root / d
            if not loc_path.is_dir():
                continue
            # locales/en.json, locales/tr.json seklinde
            for f in loc_path.iterdir():
                if f.suffix.lower() == ".json" and f.stem.lower() not in ("index", "package"):
                    locale_files[f.stem.lower()] = f
            # locales/en/translation.json seklinde
            for sub in loc_path.iterdir():
                if sub.is_dir():
                    for f in sub.iterdir():
                        if f.suffix.lower() == ".json":
                            locale_files[sub.name.lower()] = f
                            break  # ilk json yeterli

        return locale_files

    # ----------------------------------------------------------------
    # Yardimci: locale dosyasindan key'leri cikart (nested destekli)
    # ----------------------------------------------------------------
    def _extract_keys_from_json(self, filepath: Path, prefix: str = "") -> Set[str]:
        """JSON dosyasindan tum key'leri flat olarak cikarir.
        {"common": {"hello": "Merhaba"}} -> {"common.hello"}
        """
        keys = set()
        try:
            content = filepath.read_text(errors="ignore")
            data = json.loads(content)
        except (json.JSONDecodeError, OSError):
            return keys

        def _walk(obj, path):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_path = f"{path}.{k}" if path else k
                    if isinstance(v, dict):
                        _walk(v, new_path)
                    else:
                        keys.add(new_path)
            # Dizi ise skip
        _walk(data, prefix)
        return keys

    # ----------------------------------------------------------------
    # Yardimci: koddaki t() cagrilarindan key'leri topla
    # ----------------------------------------------------------------
    def _collect_used_keys(self) -> Set[str]:
        """Kaynak koddaki tum t('key') cagrilarindaki key'leri topla."""
        used_keys: Set[str] = set()
        for f in self.src_files()[:300]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            ext = Path(f).suffix.lower()
            if ext not in (".tsx", ".jsx", ".ts", ".js", ".vue"):
                continue
            content = self.read(f)
            if not content:
                continue
            for pattern in T_CALL_PATTERNS:
                for m in pattern.finditer(content):
                    used_keys.add(m.group(1))
        return used_keys

    # ----------------------------------------------------------------
    # Yardimci: source dosyalardaki hardcoded/translated sayimi
    # ----------------------------------------------------------------
    def _count_strings(self) -> Tuple[List[Dict], List[Dict]]:
        """hardcoded ve translated stringleri dondurur."""
        hardcoded = []
        translated = []

        for f in self.src_files()[:300]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            ext = Path(f).suffix.lower()
            if ext not in (".tsx", ".jsx", ".ts", ".js", ".vue"):
                continue

            content = self.read(f)
            if not content:
                continue

            # Translated: t('key') kullanimlari
            for pattern in T_CALL_PATTERNS:
                for m in pattern.finditer(content):
                    translated.append({"key": m.group(1), "file": f})

            # Hardcoded string tespiti
            for pat, min_len in HARDCODED_JSX_PATTERNS:
                for m in pat.finditer(content):
                    text = m.group(1).strip()
                    if not text or len(text) < min_len:
                        continue
                    if any(re.match(p, text) for p in SKIP_PATTERNS):
                        continue
                    # t() icinde mi kontrol et
                    context_before = content[max(0, m.start()-30):m.start()]
                    if "t(" in context_before or "$t(" in context_before:
                        continue
                    line = content[:m.start()].count("\n") + 1
                    hardcoded.append({"text": text, "file": f, "line": line})

        return hardcoded, translated

    # ================================================================
    # SUBTYPE 1: i18n_deep (mevcut - gelistirilmis)
    # ================================================================
    def _i18n_deep(self, t: dict) -> Tuple[bool, str]:
        """Derin i18n analizi - hardcoded string ve coverage."""
        has_i18n = self._detect_i18n_system()
        hardcoded, translated = self._count_strings()

        total = len(hardcoded) + len(translated)
        if total == 0:
            return True, "UI string bulunamadi"

        coverage = (len(translated) / total * 100) if total else 100

        if not hardcoded:
            return True, "i18n coverage %100 ({} string)".format(total)

        top5 = hardcoded[:5]
        top5_str = ", ".join(['"{}"'.format(h["text"][:20]) for h in top5])

        if has_i18n:
            return False, "{} hardcoded string (i18n coverage {:.0f}%): {}".format(
                len(hardcoded), coverage, top5_str)
        return False, "{} hardcoded string, i18n sistemi kurulmamis: {}".format(
            len(hardcoded), top5_str)

    # ================================================================
    # SUBTYPE 2: i18n_coverage - detayli coverage raporu
    # ================================================================
    def _i18n_coverage(self, t: dict) -> Tuple[bool, str]:
        """Detayli i18n coverage analizi - dosya bazinda breakdown."""
        has_i18n = self._detect_i18n_system()
        if not has_i18n:
            return True, "i18n sistemi yok, coverage analizi atlanir"

        hardcoded, translated = self._count_strings()
        total = len(hardcoded) + len(translated)

        if total == 0:
            return True, "UI string bulunamadi"

        coverage = (len(translated) / total * 100) if total else 100

        # Dosya bazinda breakdown
        file_stats: Dict[str, Dict[str, int]] = {}
        for h in hardcoded:
            fname = h["file"]
            if fname not in file_stats:
                file_stats[fname] = {"hardcoded": 0, "translated": 0}
            file_stats[fname]["hardcoded"] += 1
        for tr in translated:
            fname = tr["file"]
            if fname not in file_stats:
                file_stats[fname] = {"hardcoded": 0, "translated": 0}
            file_stats[fname]["translated"] += 1

        # En kotu dosyalar (en cok hardcoded string)
        worst_files = sorted(
            [(f, s) for f, s in file_stats.items() if s["hardcoded"] > 0],
            key=lambda x: x[1]["hardcoded"],
            reverse=True
        )[:5]

        if coverage >= 95:
            return True, "i18n coverage {:.0f}% ({}/{} string translated)".format(
                coverage, len(translated), total)

        if coverage >= 80:
            worst_str = ", ".join(["{} ({})".format(Path(f).name, s["hardcoded"]) for f, s in worst_files[:3]])
            return False, "i18n coverage {:.0f}% - {} hardcoded string, en kotu dosyalar: {}".format(
                coverage, len(hardcoded), worst_str)

        worst_str = ", ".join(["{} ({})".format(Path(f).name, s["hardcoded"]) for f, s in worst_files])
        return False, "i18n coverage dusuk: {:.0f}% - {}/{} string hardcoded, kritik dosyalar: {}".format(
            coverage, len(hardcoded), total, worst_str)

    # ================================================================
    # SUBTYPE 3: missing_translation_keys
    # ================================================================
    def _missing_translation_keys(self, t: dict) -> Tuple[bool, str]:
        """Kodda kullanilan ama locale dosyalarinda olmayan key'leri bul."""
        locale_files = self._find_locale_files()
        if not locale_files:
            return True, "Locale dosyasi bulunamadi, kontrol atlanir"

        used_keys = self._collect_used_keys()
        if not used_keys:
            return True, "Kodda i18n key kullanimi bulunamadi"

        # Her locale icin eksik key'leri bul
        missing_per_locale: Dict[str, List[str]] = {}
        for locale, filepath in locale_files.items():
            defined_keys = self._extract_keys_from_json(filepath)
            missing = used_keys - defined_keys
            if missing:
                missing_per_locale[locale] = sorted(missing)

        if not missing_per_locale:
            return True, "Tum locale dosyalarinda tum key'ler mevcut ({} key, {} locale)".format(
                len(used_keys), len(locale_files))

        total_missing = sum(len(v) for v in missing_per_locale.values())

        # Rapor
        details = []
        for locale, keys in sorted(missing_per_locale.items()):
            sample = ", ".join(keys[:3])
            details.append("{}: {} eksik ({})".format(locale, len(keys), sample))

        return False, "{} eksik translation key - {}".format(
            total_missing, "; ".join(details[:4]))

    # ================================================================
    # SUBTYPE 4: unused_translation_keys
    # ================================================================
    def _unused_translation_keys(self, t: dict) -> Tuple[bool, str]:
        """Locale dosyalarinda tanimli ama kodda kullanilmayan key'leri bul."""
        locale_files = self._find_locale_files()
        if not locale_files:
            return True, "Locale dosyasi bulunamadi, kontrol atlanir"

        used_keys = self._collect_used_keys()

        # Tum locale'lerdeki key'leri topla (union)
        all_defined: Set[str] = set()
        for filepath in locale_files.values():
            all_defined |= self._extract_keys_from_json(filepath)

        if not all_defined:
            return True, "Locale dosyalarinda key bulunamadi"

        # Kullanilmayan key'ler
        unused = all_defined - used_keys

        # Bazi key'ler dinamik olarak kullanilabilir, false positive azalt
        # Ornek: t(`errors.${code}`) gibi durumlar
        # Bu yuzden key prefix'lerini kontrol et
        dynamic_prefixes = set()
        for f in self.src_files()[:300]:
            ext = Path(f).suffix.lower()
            if ext not in (".tsx", ".jsx", ".ts", ".js", ".vue"):
                continue
            content = self.read(f)
            if not content:
                continue
            # t(`prefix.${var}`) pattern'i
            for m in re.finditer(r'''t\(\s*`([^$`]+)\$\{''', content):
                dynamic_prefixes.add(m.group(1).rstrip("."))

        # Dinamik prefix ile baslayan key'leri filtrele
        if dynamic_prefixes:
            unused = {k for k in unused if not any(k.startswith(p) for p in dynamic_prefixes)}

        if not unused:
            return True, "Kullanilmayan translation key yok ({} key aktif)".format(len(used_keys))

        unused_ratio = len(unused) / len(all_defined) * 100 if all_defined else 0
        sample = sorted(unused)[:5]
        sample_str = ", ".join(sample)

        if unused_ratio > 30:
            return False, "{} kullanilmayan key ({:.0f}% atil) - temizlik gerekli: {}".format(
                len(unused), unused_ratio, sample_str)

        if len(unused) > 10:
            return False, "{} kullanilmayan translation key ({:.0f}%): {}".format(
                len(unused), unused_ratio, sample_str)

        return False, "{} kullanilmayan translation key: {}".format(len(unused), sample_str)

    # ================================================================
    # SUBTYPE 5: locale_consistency
    # ================================================================
    def _locale_consistency(self, t: dict) -> Tuple[bool, str]:
        """Tum locale dosyalarinin ayni key'lere sahip olup olmadigini kontrol et."""
        locale_files = self._find_locale_files()
        if len(locale_files) < 2:
            return True, "Tek locale veya locale dosyasi yok, consistency kontrolu atlanir"

        locale_keys: Dict[str, Set[str]] = {}
        for locale, filepath in locale_files.items():
            locale_keys[locale] = self._extract_keys_from_json(filepath)

        # Referans: en cok key'e sahip locale
        ref_locale = max(locale_keys, key=lambda k: len(locale_keys[k]))
        ref_keys = locale_keys[ref_locale]

        inconsistencies: Dict[str, List[str]] = {}
        for locale, keys in locale_keys.items():
            if locale == ref_locale:
                continue
            missing = ref_keys - keys
            extra = keys - ref_keys
            if missing or extra:
                parts = []
                if missing:
                    parts.append("{} eksik".format(len(missing)))
                if extra:
                    parts.append("{} fazla".format(len(extra)))
                inconsistencies[locale] = parts

        if not inconsistencies:
            return True, "Tum locale dosyalari tutarli ({} locale, {} key)".format(
                len(locale_files), len(ref_keys))

        details = []
        for locale, parts in sorted(inconsistencies.items()):
            missing = ref_keys - locale_keys[locale]
            sample = sorted(missing)[:3]
            detail = "{}: {}".format(locale, ", ".join(parts))
            if sample:
                detail += " (ornek: {})".format(", ".join(sample))
            details.append(detail)

        return False, "Locale tutarsizligi (referans: {}) - {}".format(
            ref_locale, "; ".join(details[:5]))

    # ================================================================
    # SUBTYPE 6: rtl_support
    # ================================================================
    def _rtl_support(self, t: dict) -> Tuple[bool, str]:
        """RTL (Right-to-Left) dil destegi kontrolu."""
        locale_files = self._find_locale_files()

        # RTL locale var mi?
        rtl_locales_found = [loc for loc in locale_files if loc in RTL_LOCALES]

        if not rtl_locales_found:
            # Locale dosyasi yoksa bile, RTL intent var mi diye bak
            has_any_rtl_ref = False
            for f in self.src_files()[:200]:
                content = self.read(f)
                if not content:
                    continue
                if re.search(r'\bI18nManager\.(?:isRTL|forceRTL|allowRTL)', content):
                    has_any_rtl_ref = True
                    break
                if re.search(r'\b(?:direction|dir)\s*[:=]\s*["\']rtl["\']', content, re.IGNORECASE):
                    has_any_rtl_ref = True
                    break

            if has_any_rtl_ref:
                return True, "RTL referansi var ama RTL locale dosyasi bulunamadi"
            return True, "RTL locale dosyasi yok, kontrol atlanir"

        # RTL locale var, RTL destegi kodda var mi?
        issues = []

        # 1. I18nManager.isRTL kullanimini kontrol et
        has_rtl_check = False
        # 2. Sabit marginLeft/marginRight/paddingLeft/paddingRight (RTL'de sorun)
        fixed_direction_count = 0
        # 3. textAlign: 'left'/'right' (RTL'de sorun)
        fixed_text_align = 0
        # 4. flexDirection kontrolu
        has_rtl_flex = False

        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            ext = Path(f).suffix.lower()
            if ext not in (".tsx", ".jsx", ".ts", ".js"):
                continue

            content = self.read(f)
            if not content:
                continue

            # RTL check var mi?
            if re.search(r'I18nManager\.(?:isRTL|forceRTL|allowRTL)', content):
                has_rtl_check = True
            if re.search(r'(?:isRTL|useRTL|rtl|RTL_LANGUAGES)', content):
                has_rtl_check = True

            # Sabit direction style'lar
            fixed_direction_count += len(re.findall(
                r'(?:marginLeft|marginRight|paddingLeft|paddingRight|left|right)\s*:', content))

            # textAlign sorunlari
            fixed_text_align += len(re.findall(
                r'textAlign\s*:\s*["\'](?:left|right)["\']', content))

            # RTL-aware flex
            if re.search(r'flexDirection.*(?:row-reverse|I18nManager)', content):
                has_rtl_flex = True

        if not has_rtl_check:
            issues.append("I18nManager.isRTL kontrolu bulunamadi")

        # marginStart/marginEnd kullanilmali
        if fixed_direction_count > 10:
            issues.append("{} sabit direction style (marginStart/End kullanin)".format(fixed_direction_count))

        if fixed_text_align > 5:
            issues.append("{} sabit textAlign (RTL'de ters gorulur)".format(fixed_text_align))

        if not has_rtl_flex:
            issues.append("RTL-aware flexDirection bulunamadi")

        if not issues:
            return True, "RTL destegi mevcut ({} RTL locale: {})".format(
                len(rtl_locales_found), ", ".join(rtl_locales_found))

        return False, "RTL locale ({}) var ama destek eksik: {}".format(
            ", ".join(rtl_locales_found), "; ".join(issues[:4]))
