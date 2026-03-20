"""UI Analyzer - Sayfa kesfetme, kirik route, icerik kalitesi, API hata state.

Wave 1 MVP: Runtime gerektirmez, tamamen statik analiz.
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

from nazar.runners.base import BaseRunner, IGNORE_DIRS


class UIAnalyzer(BaseRunner):
    """UI motoru MVP - 4 katman birlesik."""

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = {
            "page_discovery": self._page_discovery,
            "dead_routes": self._dead_routes,
            "content_quality": self._content_quality,
            "loading_state": self._loading_state,
            "error_state": self._error_state,
            "empty_state": self._empty_state,
        }
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    # ==========================================
    # KATMAN 1: Sayfa Kesfetme
    # ==========================================

    def _get_all_screens(self) -> List[Dict]:
        """Projedeki tum ekranlari bul."""
        screens = []
        for f in self.src_files()[:300]:
            if "test" in f.lower() or "spec" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            ext = Path(f).suffix.lower()

            # React Navigation: Stack.Screen name="X"
            if ext in (".tsx", ".jsx", ".ts", ".js"):
                for m in re.finditer(r'<(?:Stack|Tab|Drawer)\.Screen\s+[^>]*name=["\'](\w+)["\']', content):
                    screens.append({"name": m.group(1), "file": f, "line": content[:m.start()].count("\n") + 1, "type": "screen"})
                # export default function XScreen
                for m in re.finditer(r'(?:export\s+default\s+)?function\s+(\w+Screen|\w+Page)\s*\(', content):
                    screens.append({"name": m.group(1), "file": f, "line": content[:m.start()].count("\n") + 1, "type": "screen"})
                # const XScreen = () =>
                for m in re.finditer(r'(?:export\s+)?const\s+(\w+Screen|\w+Page)\s*=', content):
                    screens.append({"name": m.group(1), "file": f, "line": content[:m.start()].count("\n") + 1, "type": "screen"})

            # Next.js: pages/ veya app/ dizin yapisi
            if "pages/" in f and ext in (".tsx", ".jsx", ".ts", ".js"):
                route = f.split("pages/")[1].rsplit(".", 1)[0]
                if route not in ("_app", "_document", "_error"):
                    screens.append({"name": route, "file": f, "type": "page"})

            # Flutter
            if ext == ".dart":
                for m in re.finditer(r'class\s+(\w+(?:Screen|Page|View))\s+extends\s+(?:Stateless|Stateful)Widget', content):
                    screens.append({"name": m.group(1), "file": f, "line": content[:m.start()].count("\n") + 1, "type": "screen"})

            # Django
            if ext == ".py" and ("views" in f.lower() or "urls" in f.lower()):
                for m in re.finditer(r"path\(\s*['\"]([^'\"]+)['\"]", content):
                    screens.append({"name": m.group(1), "file": f, "line": content[:m.start()].count("\n") + 1, "type": "route"})

        # Deduplicate
        seen = set()
        unique = []
        for s in screens:
            key = s["name"]
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique

    def _get_navigate_targets(self) -> List[Dict]:
        """Projedeki tum navigation.navigate() hedeflerini bul."""
        targets = []
        for f in self.src_files()[:300]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            # navigate('X') / push('X') / replace('X')
            for m in re.finditer(r'(?:navigation|navigator|router)\s*\.\s*(?:navigate|push|replace)\s*\(\s*["\'](\w+)["\']', content, re.IGNORECASE):
                targets.append({
                    "target": m.group(1),
                    "file": f,
                    "line": content[:m.start()].count("\n") + 1,
                    "confidence": 98,
                })
            # navigate(variable) - const takip
            for m in re.finditer(r'(?:navigation|navigator|router)\s*\.\s*(?:navigate|push|replace)\s*\(\s*(\w+)\s*[,)]', content, re.IGNORECASE):
                var_name = m.group(1)
                if var_name[0].islower() and var_name not in ("route", "screen", "path"):
                    const_m = re.search(rf'(?:const|let|var)\s+{re.escape(var_name)}\s*=\s*["\'](\w+)["\']', content)
                    if const_m:
                        targets.append({
                            "target": const_m.group(1),
                            "file": f,
                            "line": content[:m.start()].count("\n") + 1,
                            "confidence": 85,
                        })
            # Flutter: Navigator.pushNamed(context, '/route')
            for m in re.finditer(r'Navigator\.\w+Named\s*\([^,]+,\s*["\']([^"\']+)["\']', content):
                targets.append({
                    "target": m.group(1),
                    "file": f,
                    "line": content[:m.start()].count("\n") + 1,
                    "confidence": 95,
                })
        return targets

    def _page_discovery(self, t: dict) -> Tuple[bool, str]:
        """Kac ekran var, kaci test edilmis."""
        screens = self._get_all_screens()
        if not screens:
            return True, "Ekran/sayfa bulunamadi (statik site olabilir)"

        # Test dosyalari ile eslesme kontrolu
        test_files = set()
        for f in self.src_files():
            if "test" in f.lower() or "spec" in f.lower():
                test_files.add(f.lower())

        tested = 0
        for s in screens:
            screen_name = s["name"].lower()
            if any(screen_name in tf for tf in test_files):
                tested += 1

        untested = len(screens) - tested
        if untested == 0:
            return True, "{} ekran, hepsi test edilmis".format(len(screens))
        return False, "{} ekran bulundu, {} tanesi test edilmemis".format(len(screens), untested)

    # ==========================================
    # KATMAN 2: Kirik Route / Dead Route
    # ==========================================

    def _dead_routes(self, t: dict) -> Tuple[bool, str]:
        """Varolmayan ekrana navigate eden kodlari bul."""
        screens = self._get_all_screens()
        screen_names = {s["name"] for s in screens}
        targets = self._get_navigate_targets()

        if not targets:
            return True, "Navigation cagrisi bulunamadi"

        dead = []
        for nav in targets:
            target = nav["target"]
            if target not in screen_names:
                # Fuzzy match dene - belki isim degismis
                suggestion = self._find_similar(target, screen_names)
                dead.append({
                    "target": target,
                    "file": nav["file"],
                    "line": nav["line"],
                    "suggestion": suggestion,
                })

        if not dead:
            return True, "{} navigate cagrisi, hepsi gecerli".format(len(targets))

        first = dead[0]
        detail = "{} dead route: navigate('{}') {}:{}".format(len(dead), first["target"], first["file"], first["line"])
        if first["suggestion"]:
            detail += " (belki '{}' mi demek istediniz?)".format(first["suggestion"])
        return False, detail

    def _find_similar(self, target: str, valid_names: set) -> str:
        """Levenshtein ile en yakin ekran ismini bul."""
        best = ""
        best_dist = 999
        target_lower = target.lower()
        for name in valid_names:
            dist = self._levenshtein(target_lower, name.lower())
            if dist < best_dist and dist <= 3:
                best_dist = dist
                best = name
        return best

    @staticmethod
    def _levenshtein(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return UIAnalyzer._levenshtein(s2, s1)
        if len(s2) == 0:
            return len(s1)
        prev = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            curr = [i + 1]
            for j, c2 in enumerate(s2):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
            prev = curr
        return prev[len(s2)]

    # ==========================================
    # KATMAN 3: Icerik Kalitesi
    # ==========================================

    PLACEHOLDER_PATTERNS = [
        (r"lorem\s+ipsum", 99, "Lorem ipsum placeholder"),
        (r"test@test\.com|test@example\.com|user@example", 97, "Test email adresi"),
        (r"(?:xxx|aaa|asdf|qwerty){2,}", 95, "Anlamsiz karakter dizisi"),
        (r"\bTODO\b|\bFIXME\b|\bHACK\b|\bPLACEHOLDER\b", 93, "Placeholder isareti"),
        (r"123-?456-?789\d?", 90, "Test telefon numarasi"),
        (r"John\s+Doe|Jane\s+Doe", 80, "Ornek isim"),
        (r"foo\s*bar|baz\s*qux", 90, "Placeholder degisken"),
    ]

    def _content_quality(self, t: dict) -> Tuple[bool, str]:
        """Placeholder, test verisi, lorem ipsum tespiti."""
        findings = []
        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                # Yorum satirlarini atla
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("*"):
                    continue
                for pattern, confidence, desc in self.PLACEHOLDER_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        # JSX context mi kontrol et
                        if confidence >= 90 or self._is_ui_context(line):
                            findings.append({
                                "file": f, "line": i,
                                "match": re.search(pattern, line, re.IGNORECASE).group()[:50],
                                "description": desc, "confidence": confidence,
                            })
                            break  # Ayni satir icin bir bulgu yeter

        if not findings:
            return True, "Placeholder/test verisi bulunamadi"
        first = findings[0]
        return False, "{} placeholder: {} ({}:{}, {})".format(
            len(findings), first["description"], first["file"], first["line"], first["match"])

    def _is_ui_context(self, line: str) -> bool:
        """Satir UI render context'inde mi?"""
        ui_indicators = ["<Text", "<Button", "title=", "label=", "placeholder=",
                        "Alert.alert", "console.log", "Text(", "print("]
        return any(ind in line for ind in ui_indicators)

    # ==========================================
    # KATMAN 4: API Hata State'leri
    # ==========================================

    # Bilinen data fetching hook/fonksiyonlari
    FETCH_INDICATORS = [
        r"useQuery\s*\(", r"useSWR\s*\(", r"useMutation\s*\(",
        r"useLazyQuery\s*\(", r"useInfiniteQuery\s*\(",
        r"fetch\s*\(", r"axios\.\w+\s*\(",
        r"\.get\s*\(", r"\.post\s*\(", r"\.put\s*\(", r"\.delete\s*\(",
    ]

    LOADING_INDICATORS = [
        r"isLoading", r"isPending", r"isFetching", r"loading",
        r"<ActivityIndicator", r"<Spinner", r"<Skeleton", r"<Loading",
        r"if\s*\(\s*(?:isLoading|loading|isPending)",
        r"(?:isLoading|loading|isPending)\s*(?:&&|\?)",
    ]

    ERROR_INDICATORS = [
        r"isError", r"error\s*&&", r"error\s*\?",
        r"\.catch\s*\(", r"onError", r"onFailure",
        r"<ErrorBoundary", r"Alert\.alert\s*\([^)]*(?:hata|error|basarisiz)",
    ]

    EMPTY_INDICATORS = [
        r"ListEmptyComponent", r"EmptyState", r"<Empty",
        r"\.length\s*===?\s*0", r"data\s*&&\s*data\.length",
        r"renderEmpty", r"noDataComponent",
    ]

    def _loading_state(self, t: dict) -> Tuple[bool, str]:
        """API cagrisi olan component'lerde loading state var mi?"""
        missing = []
        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            # Bu dosyada fetch var mi?
            has_fetch = any(re.search(p, content) for p in self.FETCH_INDICATORS)
            if not has_fetch:
                continue
            # Loading gosterimi var mi?
            has_loading = any(re.search(p, content, re.IGNORECASE) for p in self.LOADING_INDICATORS)
            if not has_loading:
                # Custom hook kontrol: use ile baslayan import var mi?
                has_custom_hook = bool(re.search(r'(?:const|let)\s+\{[^}]*\}\s*=\s*use\w+\(', content))
                if has_custom_hook:
                    continue  # Custom hook muhtemelen loading yonetiyor, warning verme
                missing.append(f)

        if not missing:
            return True, "API cagrisi olan dosyalarda loading state mevcut"
        return False, "{} dosyada loading state eksik: {}".format(len(missing), missing[0])

    def _error_state(self, t: dict) -> Tuple[bool, str]:
        """API hata durumunda UI gosterimi var mi?"""
        missing = []
        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            has_fetch = any(re.search(p, content) for p in self.FETCH_INDICATORS)
            if not has_fetch:
                continue
            has_error = any(re.search(p, content, re.IGNORECASE) for p in self.ERROR_INDICATORS)
            if not has_error:
                has_custom_hook = bool(re.search(r'(?:const|let)\s+\{[^}]*\}\s*=\s*use\w+\(', content))
                if has_custom_hook:
                    continue
                missing.append(f)

        if not missing:
            return True, "API hata state'leri yonetiliyor"
        return False, "{} dosyada error state eksik: {}".format(len(missing), missing[0])

    def _empty_state(self, t: dict) -> Tuple[bool, str]:
        """Liste/veri gosteriminde bos durum kontrolu."""
        missing = []
        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            # Liste render var mi? (FlatList, .map(), vb.)
            has_list = bool(re.search(r'<FlatList|<SectionList|\.map\s*\(', content))
            if not has_list:
                continue
            has_empty = any(re.search(p, content, re.IGNORECASE) for p in self.EMPTY_INDICATORS)
            if not has_empty:
                missing.append(f)

        if not missing:
            return True, "Liste bos durumlari yonetiliyor"
        return False, "{} dosyada empty state eksik: {}".format(len(missing), missing[0])
