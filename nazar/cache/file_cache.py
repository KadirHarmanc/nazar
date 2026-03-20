"""File Cache - SQLite tabanli dosya hash cache sistemi."""
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict


class FileCache:
    """Dosya hash'lerine dayali test sonuc cache'i.

    ~/.cache/nazar/cache.db'de saklanir.
    """

    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = os.path.join(Path.home(), ".cache", "nazar")
        os.makedirs(cache_dir, exist_ok=True)
        self.db_path = os.path.join(cache_dir, "cache.db")
        self._init_db()

    def _init_db(self) -> None:
        """Veritabani tablosunu olustur."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_cache (
                    file_path TEXT,
                    file_hash TEXT,
                    test_type TEXT,
                    result_json TEXT,
                    cached_at REAL,
                    PRIMARY KEY (file_path, test_type)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_hash ON file_cache (file_hash)
            """)

    @staticmethod
    def hash_file(file_path: str) -> str:
        """Dosyanin SHA256 hash'ini hesapla."""
        h = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        except (IOError, OSError):
            return ""

    def get(self, file_path: str, test_type: str, file_hash: str = None) -> Optional[Dict]:
        """Cache'den sonuc getir. Hash uyusmazsa None dondur."""
        if file_hash is None:
            file_hash = self.hash_file(file_path)
        if not file_hash:
            return None

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT result_json, file_hash FROM file_cache WHERE file_path = ? AND test_type = ?",
                (file_path, test_type),
            ).fetchone()

            if row and row[1] == file_hash:
                try:
                    return json.loads(row[0])
                except (json.JSONDecodeError, TypeError):
                    return None
        return None

    def put(self, file_path: str, test_type: str, result: Dict, file_hash: str = None) -> None:
        """Sonucu cache'e yaz."""
        if file_hash is None:
            file_hash = self.hash_file(file_path)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO file_cache (file_path, file_hash, test_type, result_json, cached_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (file_path, file_hash, test_type, json.dumps(result), time.time()),
            )

    def invalidate(self, file_path: str = None) -> None:
        """Cache'i temizle. file_path verilirse sadece o dosyanin cache'i silinir."""
        with sqlite3.connect(self.db_path) as conn:
            if file_path:
                conn.execute("DELETE FROM file_cache WHERE file_path = ?", (file_path,))
            else:
                conn.execute("DELETE FROM file_cache")

    def stats(self) -> Dict:
        """Cache istatistikleri."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM file_cache").fetchone()[0]
            types = conn.execute("SELECT test_type, COUNT(*) FROM file_cache GROUP BY test_type").fetchall()
            return {"total_entries": total, "by_type": {t: c for t, c in types}}
