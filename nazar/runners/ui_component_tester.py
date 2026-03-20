"""UI Component Tester - Component kalitesi, a11y, responsive ve tasarim kontrolu."""
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple

from nazar.runners.base import BaseRunner

def _fmt(hits, msg="bulundu"):
    if not hits:
        return True, "Temiz"
    first = hits[0]
    return False, f"{len(hits)} {msg}: {first['file']}:{first['line']}"


class UIComponentTester(BaseRunner):
    """UI component kalite ve uyumluluk testleri."""

    def check_accessibility_labels(self, t: dict) -> Tuple[bool, str]:
        """Interaktif elementlerde accessibilityLabel/Role eksik."""
        interactive = self.scan_pattern(
            r"""<(?:TouchableOpacity|Pressable|Button|TextInput|Switch)\b""",
            limit=100
        )
        with_a11y = self.scan_pattern(
            r"""<(?:TouchableOpacity|Pressable|Button|TextInput|Switch)\b[^>]*(?:accessibilityLabel|accessibilityRole|accessible)""",
            limit=100
        )
        without = len(interactive) - len(with_a11y)
        if without > 5:
            return False, f"{without}/{len(interactive)} interaktif element a11y label eksik"
        return True, f"{len(with_a11y)}/{len(interactive)} a11y kapsamli"

    def check_touch_target_size(self, t: dict) -> Tuple[bool, str]:
        """Kucuk touch target - minimum 44x44px (Apple HIG)."""
        small_targets = self.scan_pattern(
            r"""(?:hitSlop|width|height|size)\s*[:=]\s*(?:[1-3]\d)\b""",
            limit=100
        )
        interactive = self.scan_pattern(
            r"""<(?:TouchableOpacity|Pressable|Button)\b""",
            limit=100
        )
        if len(interactive) > 0 and len(small_targets) > len(interactive) * 0.3:
            return False, f"{len(small_targets)} kucuk touch target (min 44px oneriliyor)"
        return True, "Temiz"

    def check_hardcoded_colors(self, t: dict) -> Tuple[bool, str]:
        """Hardcoded renk degerleri - tema sistemi kullanilmiyor."""
        hardcoded = self.scan_pattern(
            r"""(?:color|background|backgroundColor|borderColor)\s*[:=]\s*['"]#[0-9a-fA-F]{3,8}['"]""",
            limit=100
        )
        themed = self.scan_pattern(
            r"""(?:colors\.|theme\.|useTheme|useColorScheme|--color-|tw`|className)""",
            limit=100
        )
        if len(hardcoded) > 10 and len(themed) < len(hardcoded):
            ratio = len(hardcoded) / max(len(hardcoded) + len(themed), 1) * 100
            return False, f"{len(hardcoded)} hardcoded renk (%{ratio:.0f}) - tema sistemi oneriliyor"
        return True, f"{len(themed)} tema kullanimi"

    def check_hardcoded_dimensions(self, t: dict) -> Tuple[bool, str]:
        """Hardcoded piksel boyutlari - responsive sorunlari."""
        hardcoded = self.scan_pattern(
            r"""(?:width|height)\s*[:=]\s*(?:\d{3,})\b""",
            limit=100
        )
        responsive = self.scan_pattern(
            r"""(?:Dimensions\.get|useWindowDimensions|%|flex\s*[:=]|responsive|rem|vh|vw)""",
            limit=100
        )
        if len(hardcoded) > 5 and len(responsive) < len(hardcoded) * 0.5:
            return False, f"{len(hardcoded)} hardcoded boyut - responsive birimler oneriliyor"
        return True, "Temiz"

    def check_dark_mode_support(self, t: dict) -> Tuple[bool, str]:
        """Dark mode destegi kontrolu."""
        dark_mode = self.scan_pattern(
            r"""(?:useColorScheme|colorScheme|dark:|darkMode|theme.*dark|prefers-color-scheme)""",
            limit=50
        )
        color_usage = self.scan_pattern(
            r"""(?:color|background|backgroundColor)\s*[:=]""",
            limit=100
        )
        if len(color_usage) > 20 and len(dark_mode) == 0:
            return False, f"{len(color_usage)} renk kullanimi ama dark mode destegi yok"
        return True, f"Dark mode: {len(dark_mode)} referans"

    def check_error_boundary(self, t: dict) -> Tuple[bool, str]:
        """React Error Boundary eksik - crash beyaz ekran gosterir."""
        boundary = self.scan_pattern(
            r"""(?:ErrorBoundary|componentDidCatch|getDerivedStateFromError|error[_-]?boundary|ErrorFallback)""",
            limit=50
        )
        react_files = self.scan_pattern(r"""from\s+['"]react['"]""", limit=100)
        if len(react_files) > 10 and len(boundary) == 0:
            return False, "React projesi ama ErrorBoundary yok - crash = beyaz ekran"
        return True, "Temiz"

    def check_loading_states(self, t: dict) -> Tuple[bool, str]:
        """Async islemlerde loading state eksik."""
        async_ops = self.scan_pattern(
            r"""(?:fetch\(|axios\.|useQuery|useMutation|supabase\.\w+\.\w+\(|\.invoke\()""",
            limit=100
        )
        loading = self.scan_pattern(
            r"""(?:isLoading|loading|isFetching|isPending|skeleton|Skeleton|ActivityIndicator|Spinner|shimmer)""",
            limit=100
        )
        if len(async_ops) > 5 and len(loading) < len(async_ops) * 0.3:
            return False, f"{len(async_ops)} async islem ama {len(loading)} loading state"
        return True, "Temiz"

    def check_empty_state(self, t: dict) -> Tuple[bool, str]:
        """Liste/grid component'lerde empty state eksik."""
        lists = self.scan_pattern(
            r"""(?:FlatList|SectionList|ScrollView|map\(|\.map\s*\()""",
            limit=100
        )
        empty_states = self.scan_pattern(
            r"""(?:ListEmptyComponent|emptyState|EmptyState|noData|NoData|empty.*message|no.*results|no.*items)""",
            limit=100
        )
        if len(lists) > 3 and len(empty_states) == 0:
            return False, f"{len(lists)} liste component ama empty state yok"
        return True, "Temiz"

    def check_keyboard_handling(self, t: dict) -> Tuple[bool, str]:
        """Klavye acildiginda form'un kaybolmasi sorunu."""
        inputs = self.scan_pattern(r"""<TextInput\b""", limit=100)
        keyboard_handling = self.scan_pattern(
            r"""(?:KeyboardAvoidingView|keyboardShouldPersistTaps|KeyboardAwareScrollView|keyboard.*dismiss|Keyboard\.dismiss)""",
            limit=50
        )
        if len(inputs) > 3 and len(keyboard_handling) == 0:
            return False, f"{len(inputs)} TextInput ama KeyboardAvoidingView/dismiss yok"
        return True, "Temiz"

    def check_image_optimization(self, t: dict) -> Tuple[bool, str]:
        """Gorsel optimizasyonu - cache, placeholder, progressive loading."""
        images = self.scan_pattern(r"""<(?:Image|FastImage)\b""", limit=100)
        optimized = self.scan_pattern(
            r"""(?:FastImage|expo-image|Image\.prefetch|cacheControl|placeholder|blurRadius|progressive|resizeMode)""",
            limit=100
        )
        if len(images) > 5 and len(optimized) < len(images) * 0.3:
            return False, f"{len(images)} gorsel ama {len(optimized)} optimizasyon - FastImage/cache oneriliyor"
        return True, "Temiz"

    def check_storybook_coverage(self, t: dict) -> Tuple[bool, str]:
        """Component Storybook story dosyasi kapsamligi."""
        import os
        components = []
        stories = []
        for f in self.src_files():
            basename = Path(f).stem.lower()
            if any(x in f.lower() for x in ["component", "ui/", "common/", "shared/"]):
                components.append(f)
            if ".stories." in f or ".story." in f:
                stories.append(f)
        if len(components) > 5 and len(stories) == 0:
            return False, f"{len(components)} component ama Storybook story dosyasi yok"
        return True, f"{len(stories)} story dosyasi"

    def get_all_checks(self) -> Dict[str, callable]:
        return {
            "a11y_labels": self.check_accessibility_labels,
            "touch_target_size": self.check_touch_target_size,
            "hardcoded_colors": self.check_hardcoded_colors,
            "hardcoded_dimensions": self.check_hardcoded_dimensions,
            "dark_mode_support": self.check_dark_mode_support,
            "ui_error_boundary": self.check_error_boundary,
            "loading_states": self.check_loading_states,
            "empty_state": self.check_empty_state,
            "keyboard_handling": self.check_keyboard_handling,
            "image_optimization": self.check_image_optimization,
            "storybook_coverage": self.check_storybook_coverage,
        }

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = self.get_all_checks()
        fn = checks.get(subtype)
        return fn(test) if fn else (True, "SKIP")
