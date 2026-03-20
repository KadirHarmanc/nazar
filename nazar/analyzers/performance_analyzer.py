"""Performance Analyzer - Statik performans analizi (runtime gerektirmez)."""
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

from nazar.runners.base import BaseRunner, IGNORE_DIRS


class PerformanceStaticAnalyzer(BaseRunner):
    """Statik performans analizi."""

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = {
            "large_assets": self._large_assets,
            "render_performance": self._render_performance,
            "bundle_issues": self._bundle_issues,
        }
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    def _large_assets(self, t: dict) -> Tuple[bool, str]:
        """500KB+ gorsel dosyalari."""
        large = []
        img_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
        for root_dir, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for f in files:
                if Path(f).suffix.lower() in img_exts:
                    full = os.path.join(root_dir, f)
                    try:
                        size = os.path.getsize(full)
                        if size > 500 * 1024:
                            rel = os.path.relpath(full, self.root)
                            large.append({"file": rel, "size_kb": size // 1024})
                    except OSError:
                        pass

        if not large:
            return True, "Buyuk gorsel yok"
        large.sort(key=lambda x: -x["size_kb"])
        first = large[0]
        return False, "{} buyuk gorsel: {} ({}KB) - optimize edin".format(
            len(large), first["file"], first["size_kb"])

    def _render_performance(self, t: dict) -> Tuple[bool, str]:
        """Render performans sorunlari."""
        findings = []
        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            # .map() ile buyuk liste (FlatList onerisi)
            if re.search(r'\.map\(\s*\(', content) and "FlatList" not in content:
                if re.search(r'return\s*\(?\s*<', content):
                    line = 0
                    m = re.search(r'\.map\(', content)
                    if m:
                        line = content[:m.start()].count("\n") + 1
                    findings.append({"file": f, "line": line,
                                    "issue": ".map() ile render - FlatList kullanin"})
            # useEffect icinde setState (dongu riski)
            effect_blocks = re.finditer(r'useEffect\(\s*\(\)\s*=>\s*\{(.{0,800}?)\}\s*,\s*\[', content, re.DOTALL)
            for em in effect_blocks:
                block = em.group(1)
                if re.search(r'set[A-Z]\w*\(', block):
                    deps_after = content[em.end():em.end()+50]
                    if "[]" not in deps_after:
                        line = content[:em.start()].count("\n") + 1
                        findings.append({"file": f, "line": line,
                                        "issue": "useEffect+setState dependency dizisi eksik"})

        if not findings:
            return True, "Render performans sorunu yok"
        first = findings[0]
        return False, "{} performans sorunu: {} ({}:{})".format(
            len(findings), first["issue"], first["file"], first["line"])

    def _bundle_issues(self, t: dict) -> Tuple[bool, str]:
        """Bundle boyut sorunlari."""
        findings = []
        pkg = self.root / "package.json"
        if not pkg.exists():
            return True, "package.json yok"

        content = pkg.read_text(errors="ignore")
        # Buyuk kutuphaneler
        heavy_libs = {
            "moment": "dayjs veya date-fns kullanin (moment 300KB+)",
            "lodash": "lodash/specific veya lodash-es kullanin (full lodash 70KB+)",
            "underscore": "lodash-es veya native Array methods kullanin",
        }
        for lib, suggestion in heavy_libs.items():
            if '"{}":'.format(lib) in content or "'{}':".format(lib) in content:
                findings.append({"lib": lib, "suggestion": suggestion})

        # Kaynak dosyalarda full lodash import
        for f in self.src_files()[:100]:
            c = self.read(f)
            if re.search(r"import\s+_\s+from\s+['\"]lodash['\"]", c):
                line = 0
                m = re.search(r"import\s+_\s+from\s+['\"]lodash['\"]", c)
                if m:
                    line = c[:m.start()].count("\n") + 1
                findings.append({"lib": "lodash full import", "suggestion":
                                "import {{ debounce }} from 'lodash/debounce' kullanin ({}:{})".format(f, line)})

        if not findings:
            return True, "Bundle sorunu yok"
        first = findings[0]
        return False, "{} bundle sorunu: {} - {}".format(
            len(findings), first["lib"], first["suggestion"])
