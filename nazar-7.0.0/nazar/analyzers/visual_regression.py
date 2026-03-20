"""Visual Regression Analyzer - Statik snapshot/screenshot analizi (browser/cihaz gerektirmez)."""
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Set

from nazar.runners.base import BaseRunner, IGNORE_DIRS

# Bilinen snapshot dizinleri
SNAPSHOT_DIRS = [
    ".nazar/snapshots",
    "__snapshots__",
    "screenshots",
    "__image_snapshots__",
    "snap",
    ".storybook/snapshots",
]

# Snapshot dosya uzantilari
SNAPSHOT_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".snap", ".diff.png"}

# Snapshot testing import desenleri
SNAPSHOT_IMPORT_PATTERNS = [
    r"toMatchSnapshot\s*\(",
    r"toMatchInlineSnapshot\s*\(",
    r"toMatchImageSnapshot\s*\(",
    r"matchesGoldenFile\s*\(",
    r"expectScreenshot\s*\(",
    r"compareScreenshot\s*\(",
    r"assertSnapshot\s*\(",
    r"verifyNeverGoldenFileUpdated\s*\(",
    r"from\s+['\"].*snapshot.*['\"]",
    r"require\s*\(\s*['\"].*snapshot.*['\"]\s*\)",
]

# Buyuk snapshot esigi (byte)
LARGE_SNAPSHOT_THRESHOLD = 500 * 1024  # 500KB


class VisualRegressionAnalyzer(BaseRunner):
    """Statik gorsel regresyon analizi - snapshot dosyalarini analiz eder."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self._snapshot_files_cache: List[str] = []
        self._snapshot_dirs_cache: List[str] = []
        self._test_files_cache: List[str] = []

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = {
            "stale_snapshots": self._stale_snapshots,
            "missing_snapshots": self._missing_snapshots,
            "snapshot_naming": self._snapshot_naming,
            "large_snapshots": self._large_snapshots,
            "uncommitted_snapshots": self._uncommitted_snapshots,
            "snapshot_directory_check": self._snapshot_directory_check,
        }
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    # ---- Yardimci Metodlar ----

    def _find_snapshot_dirs(self) -> List[str]:
        """Projedeki snapshot dizinlerini bul."""
        if self._snapshot_dirs_cache:
            return self._snapshot_dirs_cache

        found = []
        for root_dir, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            rel = os.path.relpath(root_dir, self.root)
            for sdir in SNAPSHOT_DIRS:
                # Dizin adi dogrudan match
                if rel.endswith(sdir) or os.path.basename(root_dir) in ("__snapshots__", "__image_snapshots__", "screenshots", "snap"):
                    found.append(rel)
                    break
                # Alt dizinde snapshot dizini var mi
                target = os.path.join(root_dir, sdir.split("/")[-1])
                if os.path.isdir(target):
                    found.append(os.path.relpath(target, self.root))

        # Tekrarlari kaldir
        self._snapshot_dirs_cache = list(set(found))
        return self._snapshot_dirs_cache

    def _find_snapshot_files(self) -> List[str]:
        """Tum snapshot dosyalarini bul."""
        if self._snapshot_files_cache:
            return self._snapshot_files_cache

        snap_dirs = self._find_snapshot_dirs()
        found = []

        for sdir in snap_dirs:
            full_dir = self.root / sdir
            if not full_dir.is_dir():
                continue
            for root_dir, dirs, files in os.walk(full_dir):
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext in SNAPSHOT_EXTS or f.endswith(".snap"):
                        rel = os.path.relpath(os.path.join(root_dir, f), self.root)
                        found.append(rel)

        self._snapshot_files_cache = found
        return self._snapshot_files_cache

    def _find_test_files(self) -> List[str]:
        """Test dosyalarini bul."""
        if self._test_files_cache:
            return self._test_files_cache

        test_patterns = re.compile(
            r"(\.test\.|\.spec\.|_test\.|_spec\.|test_|spec_)", re.IGNORECASE
        )
        for f in self.src_files():
            if test_patterns.search(f):
                self._test_files_cache.append(f)

        return self._test_files_cache

    def _test_files_with_snapshot_usage(self) -> List[str]:
        """Snapshot testi kullanan test dosyalarini bul."""
        combined = "|".join(SNAPSHOT_IMPORT_PATTERNS)
        compiled = re.compile(combined, re.IGNORECASE)
        result = []

        for f in self._find_test_files():
            content = self.read(f)
            if content and compiled.search(content):
                result.append(f)

        return result

    def _is_git_repo(self) -> bool:
        """Proje git reposu mu?"""
        return (self.root / ".git").is_dir()

    def _git_uncommitted_files(self, paths: List[str]) -> List[str]:
        """Git'te commit edilmemis snapshot dosyalarini bul."""
        if not self._is_git_repo() or not paths:
            return []

        uncommitted = []
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "--"] + paths,
                capture_output=True, text=True, cwd=str(self.root),
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        # Status kodu (M, A, ??, vb.) + dosya yolu
                        status = line[:2].strip()
                        filepath = line[3:].strip()
                        if status:
                            uncommitted.append(filepath)
        except Exception:
            pass

        return uncommitted

    # ---- Check Metodlari ----

    def _stale_snapshots(self, t: dict) -> Tuple[bool, str]:
        """Test dosyasina karsilik gelmeyen snapshot dosyalarini bul."""
        snap_files = self._find_snapshot_files()
        if not snap_files:
            return True, "Snapshot dosyasi bulunamadi"

        test_files = self._find_test_files()
        test_basenames: Set[str] = set()
        for tf in test_files:
            # Test dosyasinin adi (uzanti haric)
            name = Path(tf).stem
            # .test, .spec gibi sonekleri cikar
            for suffix in [".test", ".spec", "_test", "_spec"]:
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
                    break
            test_basenames.add(name.lower())

        stale = []
        for sf in snap_files:
            snap_name = Path(sf).stem.lower()
            # .snap uzantisini cikar
            if snap_name.endswith(".snap"):
                snap_name = snap_name[:-5]
            # Snapshot ismi herhangi bir test dosyasiyla eslesiyor mu?
            matched = False
            for tb in test_basenames:
                if tb in snap_name or snap_name in tb:
                    matched = True
                    break
            if not matched:
                stale.append(sf)

        if not stale:
            return True, f"{len(snap_files)} snapshot dosyasi, hepsi eslestirildi"

        first = stale[0]
        return False, f"{len(stale)} yetim snapshot: {first}" + (
            f" ve {len(stale)-1} daha" if len(stale) > 1 else ""
        )

    def _missing_snapshots(self, t: dict) -> Tuple[bool, str]:
        """Snapshot testi kullanan ama snapshot dosyasi olmayan test dosyalarini bul."""
        test_with_snap = self._test_files_with_snapshot_usage()
        if not test_with_snap:
            return True, "Snapshot testi kullanan dosya yok"

        snap_files = self._find_snapshot_files()
        snap_basenames: Set[str] = set()
        for sf in snap_files:
            name = Path(sf).stem.lower()
            snap_basenames.add(name)

        missing = []
        for tf in test_with_snap:
            test_name = Path(tf).stem.lower()
            # Test dosyasinin snapshot'i var mi?
            found = False
            for sb in snap_basenames:
                if test_name in sb or sb in test_name:
                    found = True
                    break
            # Ayni dizinde __snapshots__ var mi kontrol et
            test_dir = (self.root / tf).parent
            snap_subdir = test_dir / "__snapshots__"
            if snap_subdir.is_dir():
                found = True

            if not found:
                missing.append(tf)

        if not missing:
            return True, f"{len(test_with_snap)} snapshot testi, hepsinin snapshot'i mevcut"

        first = missing[0]
        return False, f"{len(missing)} eksik snapshot: {first}" + (
            f" ve {len(missing)-1} daha" if len(missing) > 1 else ""
        )

    def _snapshot_naming(self, t: dict) -> Tuple[bool, str]:
        """Snapshot dosya isimlendirme tutarliligi kontrolu."""
        snap_files = self._find_snapshot_files()
        if not snap_files:
            return True, "Snapshot dosyasi yok"

        # Isimlendirme kaliplarini tespit et
        patterns = {
            "kebab-case": re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.\w+$"),
            "snake_case": re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*\.\w+$"),
            "camelCase": re.compile(r"^[a-z][a-zA-Z0-9]*\.\w+$"),
            "PascalCase": re.compile(r"^[A-Z][a-zA-Z0-9]*\.\w+$"),
        }

        pattern_counts: Dict[str, int] = {k: 0 for k in patterns}
        unmatched = 0

        for sf in snap_files:
            filename = Path(sf).name
            matched = False
            for pname, pat in patterns.items():
                if pat.match(filename):
                    pattern_counts[pname] += 1
                    matched = True
                    break
            if not matched:
                unmatched += 1

        total = len(snap_files)
        if total <= 1:
            return True, "Tek snapshot, isimlendirme kontrolu atlandi"

        # Baskin kalip
        dominant = max(pattern_counts, key=pattern_counts.get)
        dominant_count = pattern_counts[dominant]

        # Tutarsizlik orani
        inconsistent = total - dominant_count
        if inconsistent == 0:
            return True, f"{total} snapshot, hepsi {dominant} formatinda"

        ratio = inconsistent / total
        if ratio > 0.3:
            return False, f"Tutarsiz isimlendirme: {dominant_count}/{total} {dominant}, {inconsistent} farkli"

        return True, f"Cogunluk {dominant} ({dominant_count}/{total})"

    def _large_snapshots(self, t: dict) -> Tuple[bool, str]:
        """500KB uzerindeki snapshot dosyalarini tespit et."""
        snap_files = self._find_snapshot_files()
        if not snap_files:
            return True, "Snapshot dosyasi yok"

        large = []
        for sf in snap_files:
            full_path = self.root / sf
            try:
                size = full_path.stat().st_size
                if size > LARGE_SNAPSHOT_THRESHOLD:
                    large.append({"file": sf, "size_kb": round(size / 1024)})
            except OSError:
                continue

        if not large:
            return True, f"{len(snap_files)} snapshot, hepsi 500KB altinda"

        large.sort(key=lambda x: x["size_kb"], reverse=True)
        first = large[0]
        return False, f"{len(large)} buyuk snapshot: {first['file']} ({first['size_kb']}KB)" + (
            f" ve {len(large)-1} daha" if len(large) > 1 else ""
        )

    def _uncommitted_snapshots(self, t: dict) -> Tuple[bool, str]:
        """Git'te commit edilmemis snapshot degisiklikleri."""
        if not self._is_git_repo():
            return True, "Git reposu degil, SKIP"

        snap_files = self._find_snapshot_files()
        if not snap_files:
            return True, "Snapshot dosyasi yok"

        uncommitted = self._git_uncommitted_files(snap_files)
        if not uncommitted:
            return True, f"{len(snap_files)} snapshot, hepsi commit edilmis"

        first = uncommitted[0]
        return False, f"{len(uncommitted)} commit edilmemis snapshot: {first}" + (
            f" ve {len(uncommitted)-1} daha" if len(uncommitted) > 1 else ""
        )

    def _snapshot_directory_check(self, t: dict) -> Tuple[bool, str]:
        """Snapshot dizinlerini kontrol et - var mi, yapisi uygun mu."""
        snap_dirs = self._find_snapshot_dirs()
        if not snap_dirs:
            return True, "Snapshot dizini bulunamadi (snapshot testi kullanilmiyor olabilir)"

        issues = []
        for sd in snap_dirs:
            full = self.root / sd
            if not full.is_dir():
                continue
            # Bos dizin kontrolu
            file_count = sum(1 for _ in full.rglob("*") if _.is_file())
            if file_count == 0:
                issues.append(f"Bos dizin: {sd}")

        if not issues:
            return True, f"{len(snap_dirs)} snapshot dizini bulundu, hepsi uygun"

        return False, "; ".join(issues[:3])
