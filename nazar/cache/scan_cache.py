"""Scan Cache - Tarama hafizasi, incremental tarama, karsilastirma."""
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class ScanCache:
    """Proje bazli tarama hafizasi.

    Her proje icin .nazar/ dizininde:
    - scan-history.json: Tarama gecmisi
    - last-scan.json: Son tarama sonucu
    - file-hashes.json: Dosya degisim tespiti
    """

    MAX_HISTORY = 50
    MAX_HISTORY_SIZE = 5 * 1024 * 1024  # 5MB
    MAX_CACHE_SIZE = 50 * 1024 * 1024   # 50MB

    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        self.nazar_dir = self.project_path / ".nazar"
        self.history_file = self.nazar_dir / "scan-history.json"
        self.hashes_file = self.nazar_dir / "file-hashes.json"
        self.last_scan_file = self.nazar_dir / "last-scan.json"
        self.cache_dir = self.nazar_dir / "cache"

    def ensure_dir(self):
        """Dizinleri olustur."""
        self.nazar_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)

    # === Onceki Tarama ===

    def has_previous_scan(self) -> bool:
        return self.last_scan_file.exists()

    def get_last_scan_summary(self) -> Optional[dict]:
        if not self.last_scan_file.exists():
            return None
        try:
            data = json.loads(self.last_scan_file.read_text())
            return {
                "timestamp": data.get("timestamp", ""),
                "grade": data.get("grade", "?"),
                "pass_rate": data.get("pass_rate", 0),
                "passed": data.get("passed", 0),
                "failed": data.get("failed", 0),
                "total": data.get("total", 0),
                "profile": data.get("profile", "full"),
                "duration": data.get("duration", 0),
            }
        except (json.JSONDecodeError, OSError):
            return None

    def get_last_scan_results(self) -> Optional[List[dict]]:
        if not self.last_scan_file.exists():
            return None
        try:
            data = json.loads(self.last_scan_file.read_text())
            return data.get("results", [])
        except (json.JSONDecodeError, OSError):
            return None

    def time_since_last_scan(self) -> Optional[str]:
        summary = self.get_last_scan_summary()
        if not summary or not summary["timestamp"]:
            return None
        try:
            ts = datetime.fromisoformat(summary["timestamp"])
            delta = datetime.now() - ts
            if delta.days > 0:
                return f"{delta.days} gun once"
            hours = delta.seconds // 3600
            if hours > 0:
                return f"{hours} saat once"
            minutes = delta.seconds // 60
            return f"{minutes} dakika once"
        except (ValueError, TypeError):
            return None

    # === Degisim Tespiti ===

    def get_file_hashes(self) -> Dict[str, dict]:
        if not self.hashes_file.exists():
            return {}
        try:
            return json.loads(self.hashes_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def compute_file_state(self, file_path: str) -> dict:
        full = self.project_path / file_path
        try:
            stat = full.stat()
            return {
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            }
        except OSError:
            return {"mtime": 0, "size": 0}

    def compute_file_hash(self, file_path: str) -> str:
        full = self.project_path / file_path
        try:
            md5 = hashlib.md5()
            with open(full, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    md5.update(chunk)
            return md5.hexdigest()
        except OSError:
            return ""

    def get_changed_files(self, source_files: List[str]) -> Tuple[List[str], List[str], List[str]]:
        """Degisen, yeni ve silinen dosyalari bul.

        Returns: (changed, new, deleted)
        """
        previous = self.get_file_hashes()
        previous_set = set(previous.keys())
        current_set = set(source_files)

        new_files = list(current_set - previous_set)
        deleted_files = list(previous_set - current_set)

        changed_files = []
        for f in current_set & previous_set:
            prev = previous[f]
            state = self.compute_file_state(f)
            # mtime + size hizli kontrol
            if state["mtime"] == prev.get("mtime") and state["size"] == prev.get("size"):
                continue
            # mtime degismisse hash ile dogrula
            current_hash = self.compute_file_hash(f)
            if current_hash != prev.get("hash", ""):
                changed_files.append(f)

        return changed_files, new_files, deleted_files

    def save_file_hashes(self, source_files: List[str]):
        """Tum dosyalarin mtime + size + hash'ini kaydet."""
        self.ensure_dir()
        hashes = {}
        for f in source_files:
            state = self.compute_file_state(f)
            hashes[f] = {
                "mtime": state["mtime"],
                "size": state["size"],
                "hash": self.compute_file_hash(f),
                "last_scanned": datetime.now().isoformat(),
            }
        self.hashes_file.write_text(json.dumps(hashes, indent=2))

    # === Tarama Sonucu Kayit ===

    def save_scan_result(self, results: List[dict], plan: dict, profile: str, duration: float):
        """Son tarama sonucunu kaydet."""
        self.ensure_dir()
        passed = sum(1 for r in results if r.get("passed"))
        total = len(results)
        rate = (passed / total * 100) if total else 0
        grade = self._grade(rate)

        # Kategori ozet
        categories = {}
        for r in results:
            cat = r.get("type", "other")
            if cat not in categories:
                categories[cat] = {"passed": 0, "failed": 0}
            if r.get("passed"):
                categories[cat]["passed"] += 1
            else:
                categories[cat]["failed"] += 1

        scan_data = {
            "timestamp": datetime.now().isoformat(),
            "profile": profile,
            "grade": grade,
            "pass_rate": round(rate, 1),
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "duration": round(duration, 1),
            "categories": categories,
            "results": results,
        }

        # last-scan.json
        self.last_scan_file.write_text(json.dumps(scan_data, indent=2, ensure_ascii=False))

        # scan-history.json
        self._append_history(scan_data)

    def _append_history(self, scan_data: dict):
        """Tarama gecmisine ekle."""
        history = {"project": str(self.project_path), "scans": []}
        if self.history_file.exists():
            try:
                history = json.loads(self.history_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        # Sonuclari history'ye ekleme (cok buyuk olur)
        entry = {k: v for k, v in scan_data.items() if k != "results"}
        entry["id"] = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        history["scans"].append(entry)

        # Max kayit siniri
        if len(history["scans"]) > self.MAX_HISTORY:
            history["scans"] = history["scans"][-self.MAX_HISTORY:]

        self.history_file.write_text(json.dumps(history, indent=2, ensure_ascii=False))

    # === Karsilastirma ===

    def compare_with_previous(self, current_results: List[dict]) -> Optional[dict]:
        """Onceki tarama ile karsilastir."""
        prev_results = self.get_last_scan_results()
        if not prev_results:
            return None

        prev_summary = self.get_last_scan_summary()
        current_passed = sum(1 for r in current_results if r.get("passed"))
        current_total = len(current_results)
        current_rate = (current_passed / current_total * 100) if current_total else 0

        # Onceki basarisizlar -> simdi basarili (duzeltilmis)
        prev_failed = {r["subtype"]: r for r in prev_results if not r.get("passed")}
        curr_failed = {r["subtype"]: r for r in current_results if not r.get("passed")}
        curr_passed_set = {r["subtype"] for r in current_results if r.get("passed")}

        fixed = [prev_failed[s] for s in prev_failed if s in curr_passed_set]
        new_issues = [curr_failed[s] for s in curr_failed if s not in prev_failed]

        return {
            "previous_grade": prev_summary.get("grade", "?"),
            "previous_rate": prev_summary.get("pass_rate", 0),
            "current_grade": self._grade(current_rate),
            "current_rate": round(current_rate, 1),
            "delta": round(current_rate - prev_summary.get("pass_rate", 0), 1),
            "fixed_count": len(fixed),
            "fixed": [{"name": r["name"], "detail": r.get("detail", "")} for r in fixed[:10]],
            "new_issues_count": len(new_issues),
            "new_issues": [{"name": r["name"], "detail": r.get("detail", "")} for r in new_issues[:10]],
            "time_since": self.time_since_last_scan(),
        }

    # === Cache Temizlik ===

    def cleanup(self):
        """Eski cache dosyalarini temizle."""
        if not self.cache_dir.exists():
            return
        total_size = sum(f.stat().st_size for f in self.cache_dir.rglob("*") if f.is_file())
        if total_size > self.MAX_CACHE_SIZE:
            files = sorted(
                (f for f in self.cache_dir.rglob("*") if f.is_file()),
                key=lambda x: x.stat().st_mtime,
            )
            for f in files:
                if total_size <= 30 * 1024 * 1024:
                    break
                total_size -= f.stat().st_size
                f.unlink()

    @staticmethod
    def _grade(rate: float) -> str:
        for min_r, g in [(97, "A+"), (93, "A"), (90, "A-"), (87, "B+"), (83, "B"),
                         (80, "B-"), (77, "C+"), (73, "C"), (70, "C-"), (67, "D+"),
                         (63, "D"), (60, "D-"), (0, "F")]:
            if rate >= min_r:
                return g
        return "F"
