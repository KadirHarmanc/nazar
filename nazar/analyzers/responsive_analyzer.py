"""Responsive Analyzer - Statik layout analizi (runtime gerektirmez)."""
import re
from pathlib import Path
from typing import Dict, List, Tuple

from nazar.runners.base import BaseRunner


class ResponsiveAnalyzer(BaseRunner):
    """Statik responsive ve layout analizi."""

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = {
            "fixed_dimensions": self._fixed_dimensions,
            "scroll_issues": self._scroll_issues,
            "responsive_patterns": self._responsive_patterns,
        }
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    def _fixed_dimensions(self, t: dict) -> Tuple[bool, str]:
        """Sabit pixel boyutlari (responsive degil)."""
        findings = []
        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            for m in re.finditer(r'width:\s*(\d{3,})', content):
                val = int(m.group(1))
                if val >= 300 and val not in (1024, 768):  # bilinen sabitler haric
                    line = content[:m.start()].count("\n") + 1
                    findings.append({"value": val, "file": f, "line": line})

        if not findings:
            return True, "Sabit boyut sorunu yok"
        first = findings[0]
        return False, "{} sabit genislik: width:{} ({}:{})".format(
            len(findings), first["value"], first["file"], first["line"])

    def _scroll_issues(self, t: dict) -> Tuple[bool, str]:
        """ScrollView icinde FlatList gibi sorunlar."""
        findings = []
        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            if re.search(r'<ScrollView[^>]*>.*<(?:FlatList|SectionList)', content, re.DOTALL):
                line = content.find("ScrollView")
                line_num = content[:line].count("\n") + 1 if line >= 0 else 1
                findings.append({"file": f, "line": line_num, "issue": "ScrollView icinde FlatList"})

        if not findings:
            return True, "Scroll sorunu yok"
        first = findings[0]
        return False, "{} scroll sorunu: {} ({}:{})".format(
            len(findings), first["issue"], first["file"], first["line"])

    def _responsive_patterns(self, t: dict) -> Tuple[bool, str]:
        """Responsive pattern kontrolu."""
        findings = []
        for f in self.src_files()[:200]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            if not content:
                continue
            # Dimensions.get yerine useWindowDimensions
            if "Dimensions.get" in content and "useWindowDimensions" not in content:
                line = content.find("Dimensions.get")
                line_num = content[:line].count("\n") + 1 if line >= 0 else 1
                findings.append({"file": f, "line": line_num,
                                "issue": "Dimensions.get yerine useWindowDimensions oneriliyor"})
            # flexDirection row + flexWrap yok
            if re.search(r'flexDirection\s*:\s*["\']row["\']', content):
                if "flexWrap" not in content:
                    findings.append({"file": f, "line": 0,
                                    "issue": "flexDirection:row ama flexWrap yok"})

        if not findings:
            return True, "Responsive pattern'ler uygun"
        first = findings[0]
        return False, "{} responsive sorunu: {} ({}:{})".format(
            len(findings), first["issue"], first["file"], first["line"])
