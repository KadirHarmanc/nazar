"""Base runner - Tum runner'lar icin ortak yardimci fonksiyonlar."""
import os
import re
from pathlib import Path
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from nazar.runners.ignore_manager import IgnoreManager

IGNORE_DIRS = {"node_modules", ".git", "build", "dist", "Pods", ".gradle", "vendor", "venv", ".venv", "__pycache__", ".expo", "coverage"}
SOURCE_EXTS = {".js", ".jsx", ".ts", ".tsx", ".py", ".dart", ".swift", ".kt", ".java", ".go", ".rs", ".rb", ".php", ".cs"}

# Buyuk proje esigi
LARGE_PROJECT_THRESHOLD = 2000  # dosya sayisi
CHUNK_SIZE = 500  # paralel tarama chunk boyutu


class BaseRunner:
    def __init__(self, project_path: str):
        self.root = Path(project_path).resolve()
        self._source_cache: List[str] = []
        self._ignore_manager = None
        self._content_cache: Dict[str, str] = {}

    @property
    def ignore_manager(self) -> IgnoreManager:
        if self._ignore_manager is None:
            self._ignore_manager = IgnoreManager(str(self.root))
        return self._ignore_manager

    @property
    def is_large_project(self) -> bool:
        return len(self.src_files()) > LARGE_PROJECT_THRESHOLD

    def src_files(self) -> List[str]:
        if self._source_cache:
            return self._source_cache
        for root_dir, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for f in files:
                if Path(f).suffix.lower() in SOURCE_EXTS:
                    self._source_cache.append(os.path.relpath(os.path.join(root_dir, f), self.root))
        return self._source_cache

    def src_files_chunked(self, chunk_size: int = CHUNK_SIZE) -> List[List[str]]:
        """Dosyalari chunk'lara bol (buyuk projeler icin paralel tarama)."""
        files = self.src_files()
        return [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]

    def read(self, rel_path: str) -> str:
        if rel_path in self._content_cache:
            return self._content_cache[rel_path]
        try:
            target = (self.root / rel_path).resolve()
            if not str(target).startswith(str(self.root.resolve())):
                return ""
            content = target.read_text(errors="ignore")
            # Sadece kucuk dosyalari cache'le (bellek korumasi)
            if len(content) < 100_000:
                self._content_cache[rel_path] = content
            return content
        except Exception:
            return ""

    def scan_pattern(self, pattern: str, flags=re.IGNORECASE | re.MULTILINE, skip_test=True, skip_env=True, skip_nazar=True, limit=200, subtype: str = "") -> List[Dict]:
        files = self._filter_files(skip_test, skip_env, skip_nazar, limit)

        # Buyuk projede chunk bazli paralel tarama
        if len(files) > CHUNK_SIZE:
            return self._scan_pattern_parallel(pattern, flags, files, subtype)

        hits = []
        compiled = re.compile(pattern, flags)
        for f in files:
            content = self.read(f)
            lines = content.split("\n")
            for m in compiled.finditer(content):
                line_num = content[:m.start()].count("\n") + 1
                # Inline ignore kontrolu: ust satir veya ayni satirdaki nazar-ignore
                if subtype and self._check_inline_ignore(lines, line_num, subtype):
                    continue
                hits.append({"file": f, "line": line_num, "match": m.group()[:80].replace("\n", " ").replace("\r", "")})
        if subtype:
            hits = self.ignore_manager.filter_hits(hits, subtype)
        return hits

    def _check_inline_ignore(self, lines: List[str], line_num: int, subtype: str) -> bool:
        """Satir bazinda nazar-ignore kontrolu.

        Ust satir veya ayni satirda '// nazar-ignore: subtype' veya '# nazar-ignore: subtype'
        varsa True doner, o hit atlanir.
        """
        if line_num < 1 or line_num > len(lines):
            return False
        # Ayni satir kontrolu
        current_line = lines[line_num - 1]
        ignore_pat = re.compile(r'(?://|#)\s*nazar-ignore(?:[:\s]+(\S+))?')
        m = ignore_pat.search(current_line)
        if m:
            specified = m.group(1)
            if not specified or specified == subtype:
                return True
        # Ust satir kontrolu (nazar-ignore-next-line veya nazar-ignore)
        if line_num >= 2:
            prev_line = lines[line_num - 2]
            m = ignore_pat.search(prev_line)
            if m:
                specified = m.group(1)
                if not specified or specified == subtype:
                    return True
            # nazar-ignore-next-line formati
            m2 = re.search(r'(?://|#)\s*nazar-ignore-next-line(?:[:\s]+(\S+))?', prev_line)
            if m2:
                specified = m2.group(1)
                if not specified or specified == subtype:
                    return True
        return False

    def _filter_files(self, skip_test=True, skip_env=True, skip_nazar=True, limit=200) -> List[str]:
        """Dosyalari filtrele."""
        filtered = []
        for f in self.src_files()[:limit]:
            if skip_test and ("test" in f.lower() or "spec" in f.lower()):
                continue
            if skip_env and f.startswith(".env"):
                continue
            if skip_nazar and f.startswith("nazar/"):
                continue
            if self.ignore_manager.is_file_ignored(f):
                continue
            filtered.append(f)
        return filtered

    def _scan_pattern_parallel(self, pattern: str, flags: int, files: List[str], subtype: str) -> List[Dict]:
        """Buyuk projeler icin paralel pattern tarama."""
        compiled = re.compile(pattern, flags)
        all_hits = []

        def scan_chunk(chunk):
            hits = []
            for f in chunk:
                content = self.read(f)
                lines = content.split("\n")
                for m in compiled.finditer(content):
                    line_num = content[:m.start()].count("\n") + 1
                    # Inline ignore kontrolu
                    if subtype and self._check_inline_ignore(lines, line_num, subtype):
                        continue
                    hits.append({"file": f, "line": line_num, "match": m.group()[:80].replace("\n", " ").replace("\r", "")})
            return hits

        chunks = [files[i:i + CHUNK_SIZE] for i in range(0, len(files), CHUNK_SIZE)]
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(scan_chunk, chunk): chunk for chunk in chunks}
            for future in as_completed(futures):
                all_hits.extend(future.result())

        if subtype:
            all_hits = self.ignore_manager.filter_hits(all_hits, subtype)
        return all_hits
