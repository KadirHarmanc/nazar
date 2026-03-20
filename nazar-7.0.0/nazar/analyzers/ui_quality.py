"""UI Quality Analyzer - Renk/A11y birlesik, Font tutarliligi, Form validasyon.

Wave 2 Core: Shared Element Extractor verisini kullanir.
"""
import re
from pathlib import Path
from typing import Dict, List, Tuple

from nazar.runners.base import BaseRunner
from nazar.analyzers.ui_element_extractor import UIElementExtractor, UIElement


class UIQualityAnalyzer(BaseRunner):
    """Renk, accessibility, font, form analizi."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self._extractor = UIElementExtractor(project_path)
        self._theme_colors = None

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = {
            "color_consistency": self._color_consistency,
            "contrast_wcag": self._contrast_wcag,
            "font_consistency": self._font_consistency,
            "form_validation_coverage": self._form_validation_coverage,
            "form_error_messages": self._form_error_messages,
        }
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    # ==========================================
    # Tema tespiti
    # ==========================================

    def _get_theme_colors(self) -> set:
        """Tema dosyasindaki renkleri otomatik tespit et."""
        if self._theme_colors is not None:
            return self._theme_colors

        self._theme_colors = set()
        theme_paths = [
            "src/theme.ts", "src/theme.js", "src/theme/colors.ts", "src/theme/colors.js",
            "src/constants/colors.ts", "src/constants/colors.js",
            "src/styles/colors.ts", "src/styles/colors.js",
            "theme.ts", "theme.js", "colors.ts", "colors.js",
            "tailwind.config.js", "tailwind.config.ts",
            "src/styles/variables.scss", "src/styles/variables.css",
            "lib/theme.dart", "lib/constants/colors.dart",
        ]
        for tp in theme_paths:
            full = self.root / tp
            if full.exists():
                content = full.read_text(errors="ignore")
                for m in re.finditer(r'#[0-9A-Fa-f]{3,8}', content):
                    self._theme_colors.add(m.group().lower())
        return self._theme_colors

    # ==========================================
    # Renk tutarliligi
    # ==========================================

    def _color_consistency(self, t: dict) -> Tuple[bool, str]:
        """Tema disinda hardcoded renk tespiti."""
        theme = self._get_theme_colors()
        hardcoded = []

        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            ext = Path(f).suffix.lower()
            if ext not in (".tsx", ".jsx", ".ts", ".js", ".dart", ".swift"):
                continue
            # Tema dosyalarini atla
            if any(kw in f.lower() for kw in ("theme", "color", "token", "variable", "tailwind")):
                continue

            content = self.read(f)
            if not content:
                continue

            for m in re.finditer(r'(?:color|backgroundColor|borderColor)\s*:\s*["\']?(#[0-9A-Fa-f]{3,8})["\']?', content):
                color = m.group(1).lower()
                if color not in theme and color not in ("#fff", "#ffffff", "#000", "#000000", "transparent"):
                    line = content[:m.start()].count("\n") + 1
                    hardcoded.append({"color": color, "file": f, "line": line})

        if not hardcoded:
            return True, "Renk tutarliligi iyi - tema kullaniliyor"

        unique_colors = len(set(h["color"] for h in hardcoded))
        first = hardcoded[0]
        return False, "{} hardcoded renk ({} farkli): {} ({}:{})".format(
            len(hardcoded), unique_colors, first["color"], first["file"], first["line"])

    # ==========================================
    # WCAG Kontrast
    # ==========================================

    @staticmethod
    def _relative_luminance(r: int, g: int, b: int) -> float:
        def lin(c):
            c = c / 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple:
        h = hex_color.lstrip('#')
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        if len(h) < 6:
            return (0, 0, 0)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def _contrast_ratio(self, c1: str, c2: str) -> float:
        rgb1 = self._hex_to_rgb(c1)
        rgb2 = self._hex_to_rgb(c2)
        l1 = self._relative_luminance(*rgb1)
        l2 = self._relative_luminance(*rgb2)
        lighter, darker = max(l1, l2), min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    def _contrast_wcag(self, t: dict) -> Tuple[bool, str]:
        """WCAG AA kontrast orani kontrolu (min 4.5:1)."""
        violations = []

        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue

            # color + backgroundColor ayni blokta mi bul
            # Style objeleri icindeki renk ciftlerini bul
            style_blocks = re.finditer(
                r'(?:style\s*=\s*\{?\{|StyleSheet\.create\(\{)[^}]*\}',
                content, re.DOTALL
            )
            for block_m in style_blocks:
                block = block_m.group()
                fg_m = re.search(r'color:\s*["\']?(#[0-9A-Fa-f]{3,8})["\']?', block)
                bg_m = re.search(r'backgroundColor:\s*["\']?(#[0-9A-Fa-f]{3,8})["\']?', block)
                if fg_m and bg_m:
                    ratio = self._contrast_ratio(fg_m.group(1), bg_m.group(1))
                    if ratio < 4.5:
                        line = content[:block_m.start()].count("\n") + 1
                        violations.append({
                            "ratio": round(ratio, 1),
                            "fg": fg_m.group(1),
                            "bg": bg_m.group(1),
                            "file": f,
                            "line": line,
                        })

        if not violations:
            return True, "WCAG AA kontrast kontrolu gecti"

        first = violations[0]
        return False, "{} kontrast ihlali: {}:1 (min 4.5:1) fg={} bg={} ({}:{})".format(
            len(violations), first["ratio"], first["fg"], first["bg"], first["file"], first["line"])

    # ==========================================
    # Font tutarliligi
    # ==========================================

    def _font_consistency(self, t: dict) -> Tuple[bool, str]:
        """Font ailesi ve boyutu tutarliligi."""
        font_sizes = {}
        font_families = {}

        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            # fontSize
            for m in re.finditer(r'fontSize:\s*(\d+)', content):
                size = m.group(1)
                font_sizes.setdefault(size, []).append(f)
            # fontFamily
            for m in re.finditer(r'fontFamily:\s*["\']([^"\']+)["\']', content):
                family = m.group(1)
                font_families.setdefault(family, []).append(f)

        issues = []
        if len(font_sizes) > 8:
            sizes = sorted(font_sizes.keys(), key=int)
            issues.append("{} farkli fontSize: {}".format(len(font_sizes), ", ".join(sizes)))
        if len(font_families) > 3:
            issues.append("{} farkli fontFamily: {}".format(len(font_families), ", ".join(font_families.keys())))

        if not issues:
            return True, "Font tutarliligi iyi ({} size, {} family)".format(len(font_sizes), len(font_families))
        return False, "; ".join(issues)

    # ==========================================
    # Form validasyon
    # ==========================================

    # Schema pattern'leri
    ZOD_FIELD = r"(\w+)\s*:\s*z\.(?:string|number|boolean|date|enum|array|object)\("
    YUP_FIELD = r"(\w+)\s*:\s*yup\.(?:string|number|boolean|date|mixed|object)\("

    # Form field pattern'leri
    FORM_FIELDS = [
        r'<TextInput[^>]*(?:name|testID)=["\'](\w+)["\']',
        r'<input[^>]*name=["\'](\w+)["\']',
        r'register\(["\'](\w+)["\']',
        r'Field\s+name=["\'](\w+)["\']',
        r'Controller\s+name=["\'](\w+)["\']',
    ]

    def _form_validation_coverage(self, t: dict) -> Tuple[bool, str]:
        """Form alanlarinin validation schema ile kapsami."""
        total_forms = 0
        issues = []

        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue

            # Schema alanlari
            schema_fields = set()
            for m in re.finditer(self.ZOD_FIELD, content):
                schema_fields.add(m.group(1))
            for m in re.finditer(self.YUP_FIELD, content):
                schema_fields.add(m.group(1))

            # Form alanlari
            form_fields = set()
            for pattern in self.FORM_FIELDS:
                for m in re.finditer(pattern, content):
                    form_fields.add(m.group(1))

            if not form_fields:
                continue

            total_forms += 1

            # Form'da var ama schema'da yok
            missing_validation = form_fields - schema_fields
            if missing_validation and schema_fields:
                for field in missing_validation:
                    issues.append("{}:{} - '{}' alani icin validation yok".format(
                        f, 0, field))

            # Schema yok ama form var
            if not schema_fields and form_fields:
                issues.append("{} - {} form alani var ama validation schema yok".format(
                    f, len(form_fields)))

        if total_forms == 0:
            return True, "Form bulunamadi"
        if not issues:
            return True, "{} form, validation kapsami tam".format(total_forms)

        return False, "{} form sorunu: {}".format(len(issues), issues[0][:70])

    def _form_error_messages(self, t: dict) -> Tuple[bool, str]:
        """Her form alani icin hata mesaji render ediliyor mu."""
        missing_error_ui = []

        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue

            # Schema alanlari bul
            fields = set()
            for m in re.finditer(self.ZOD_FIELD, content):
                fields.add(m.group(1))
            for m in re.finditer(self.YUP_FIELD, content):
                fields.add(m.group(1))

            if not fields:
                continue

            # Her alan icin error render var mi
            for field in fields:
                error_pattern = r"errors\.{}|errors\[.{}.\]|formState\.errors\.{}".format(
                    re.escape(field), re.escape(field), re.escape(field))
                if not re.search(error_pattern, content):
                    missing_error_ui.append("{}:{} - '{}' icin hata mesaji render yok".format(f, 0, field))

        if not missing_error_ui:
            return True, "Form hata mesajlari render ediliyor"
        return False, "{} eksik: {}".format(len(missing_error_ui), missing_error_ui[0][:70])
