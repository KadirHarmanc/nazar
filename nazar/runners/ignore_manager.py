"""Ignore Manager - .nazarignore dosyasi ve inline ignore destegi."""
import os
import re
import fnmatch
from pathlib import Path
from typing import Set, List, Dict, Tuple


class IgnoreManager:
    """Dosya ve satir bazinda ignore yonetimi."""

    def __init__(self, project_path: str):
        self.root = Path(project_path).resolve()
        self._ignored_files: Set[str] = set()
        self._ignored_rules: Dict[str, Set[str]] = {}  # file -> set of subtypes
        self._file_level_ignores: Set[str] = set()  # fully ignored files
        self._load_nazarignore()

    def _load_nazarignore(self):
        """Load .nazarignore file (gitignore format)."""
        for name in [".nazarignore", ".nazar-ignore"]:
            ignore_file = self.root / name
            if ignore_file.exists():
                for line in ignore_file.read_text(errors="ignore").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # rule:subtype format - ignore specific rule
                    if line.startswith("rule:"):
                        rule = line[5:].strip()
                        self._ignored_rules.setdefault("*", set()).add(rule)
                    else:
                        self._ignored_files.add(line)
                break

    def is_file_ignored(self, rel_path: str) -> bool:
        """Check if file should be ignored."""
        if rel_path in self._file_level_ignores:
            return True
        for pattern in self._ignored_files:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            if fnmatch.fnmatch(os.path.basename(rel_path), pattern):
                return True
        return False

    def is_rule_ignored(self, subtype: str, rel_path: str = "*") -> bool:
        """Check if a specific rule is globally ignored."""
        global_ignores = self._ignored_rules.get("*", set())
        return subtype in global_ignores

    def check_inline_ignore(self, content: str, line_num: int, subtype: str) -> bool:
        """Check if a specific line has inline nazar-ignore comment."""
        lines = content.split("\n")
        if line_num < 1 or line_num > len(lines):
            return False

        line = lines[line_num - 1]

        # Check current line for inline ignore
        # Formats: // nazar-ignore: subtype  OR  # nazar-ignore: subtype  OR  // nazar-ignore
        ignore_pattern = r"(?://|#)\s*nazar-ignore(?::?\s*(\S+))?"
        m = re.search(ignore_pattern, line)
        if m:
            specified = m.group(1)
            if not specified or specified == subtype:
                return True

        # Check previous line for ignore-next-line
        if line_num >= 2:
            prev_line = lines[line_num - 2]
            m = re.search(r"(?://|#)\s*nazar-ignore-next-line(?::?\s*(\S+))?", prev_line)
            if m:
                specified = m.group(1)
                if not specified or specified == subtype:
                    return True

        return False

    def check_file_level_ignore(self, content: str) -> bool:
        """Check if file has nazar-ignore-file comment at the top."""
        first_lines = content[:500]
        return bool(re.search(r"(?://|#)\s*nazar-ignore-file", first_lines))

    def filter_hits(self, hits: List[Dict], subtype: str, file_contents: Dict[str, str] = None) -> List[Dict]:
        """Filter scan_pattern hits based on ignore rules."""
        if self.is_rule_ignored(subtype):
            return []

        filtered = []
        for hit in hits:
            rel_path = hit.get("file", "")
            line_num = hit.get("line", 0)

            # File-level ignore
            if self.is_file_ignored(rel_path):
                continue

            # Inline ignore (if content available)
            if file_contents and rel_path in file_contents:
                content = file_contents[rel_path]
                if self.check_file_level_ignore(content):
                    continue
                if self.check_inline_ignore(content, line_num, subtype):
                    continue

            filtered.append(hit)

        return filtered
