"""Coverage Reporter - Test kapsami raporu olusturur."""
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class CoverageReporter:
    """Tarama kapsami raporu.

    Kategori bazli gecme/kalma, dosya bazli sorun yogunlugu,
    guven dagilimi ve onceki taramayla trend verisi uretir.
    """

    # Guven esikleri
    CONFIDENCE_HIGH = 80
    CONFIDENCE_MEDIUM = 50

    def generate(
        self,
        results: List[Dict],
        plan: dict,
        output_path: Optional[str] = None,
    ) -> str:
        """Kapsam raporu olustur ve JSON olarak dondur.

        Args:
            results: Test sonuclari listesi.
            plan: Test plani dict'i.
            output_path: Opsiyonel dosya yolu. Verilirse JSON dosyaya yazilir.

        Returns:
            JSON string.
        """
        total = len(results)
        passed = sum(1 for r in results if r.get("passed"))
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0

        report = {
            "nazar_version": self._get_version(),
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_checks": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": round(pass_rate, 1),
                "grade": self._grade(pass_rate),
            },
            "category_coverage": self._category_coverage(results, plan),
            "file_issue_density": self._file_issue_density(results),
            "confidence_distribution": self._confidence_distribution(results),
            "severity_breakdown": self._severity_breakdown(results),
            "trend": self._trend_data(results, plan),
        }

        output = json.dumps(report, indent=2, ensure_ascii=False)
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(output)
        return output

    # ------------------------------------------------------------------
    # Kategori kapsami
    # ------------------------------------------------------------------

    def _category_coverage(self, results: List[Dict], plan: dict) -> Dict:
        """Kategori bazinda gecme/kalma istatistikleri."""
        cats: Dict[str, Dict] = {}
        for r in results:
            cat = r.get("type", "other")
            if cat not in cats:
                cats[cat] = {"passed": 0, "failed": 0, "tests": []}
            if r.get("passed"):
                cats[cat]["passed"] += 1
            else:
                cats[cat]["failed"] += 1
            cats[cat]["tests"].append(r.get("name", ""))

        # Plandan beklenen kategorileri de ekle (0 sonuclu olanlar icin)
        for test in plan.get("tests", []):
            cat = test.get("type", "other")
            if cat not in cats:
                cats[cat] = {"passed": 0, "failed": 0, "tests": []}

        out = {}
        for cat, data in sorted(cats.items()):
            total = data["passed"] + data["failed"]
            rate = (data["passed"] / total * 100) if total > 0 else 0
            out[cat] = {
                "total": total,
                "passed": data["passed"],
                "failed": data["failed"],
                "pass_rate": round(rate, 1),
                "status": "clean" if rate == 100 else "partial" if rate >= 50 else "needs_attention",
            }
        return out

    # ------------------------------------------------------------------
    # Dosya bazli sorun yogunlugu
    # ------------------------------------------------------------------

    def _file_issue_density(self, results: List[Dict]) -> List[Dict]:
        """En cok sorun iceren dosyalari dondur."""
        file_issues: Dict[str, int] = Counter()
        file_severity: Dict[str, List[str]] = defaultdict(list)

        for r in results:
            if r.get("passed"):
                continue
            # detail icerisinden dosya yolunu cikarmaya calis
            detail = r.get("detail", "")
            target = r.get("target", "")
            file_path = target or self._extract_file_from_detail(detail)
            if file_path:
                file_issues[file_path] += 1
                file_severity[file_path].append(r.get("priority", "medium"))

        ranked = []
        for fp, count in file_issues.most_common(20):
            severities = file_severity.get(fp, [])
            ranked.append({
                "file": fp,
                "issue_count": count,
                "highest_severity": self._highest_severity(severities),
                "severities": dict(Counter(severities)),
            })
        return ranked

    # ------------------------------------------------------------------
    # Guven dagilimi
    # ------------------------------------------------------------------

    def _confidence_distribution(self, results: List[Dict]) -> Dict:
        """Bulgularin guven puani dagilimi (sadece failed icin)."""
        high = 0
        medium = 0
        low = 0
        scores = []

        for r in results:
            if r.get("passed"):
                continue
            conf = r.get("confidence", 50)
            if isinstance(conf, str):
                try:
                    conf = int(conf)
                except (ValueError, TypeError):
                    conf = 50
            scores.append(conf)
            if conf >= self.CONFIDENCE_HIGH:
                high += 1
            elif conf >= self.CONFIDENCE_MEDIUM:
                medium += 1
            else:
                low += 1

        total_findings = high + medium + low
        avg = round(sum(scores) / len(scores), 1) if scores else 0

        return {
            "high": {"count": high, "min_score": self.CONFIDENCE_HIGH, "label": "Kesin sorun"},
            "medium": {"count": medium, "min_score": self.CONFIDENCE_MEDIUM, "label": "Muhtemel sorun"},
            "low": {"count": low, "min_score": 0, "label": "Bilgilendirme"},
            "total_findings": total_findings,
            "average_confidence": avg,
        }

    # ------------------------------------------------------------------
    # Severity (oncelik) dagilimi
    # ------------------------------------------------------------------

    def _severity_breakdown(self, results: List[Dict]) -> Dict:
        """Oncelik bazinda toplam dagilim."""
        breakdown: Dict[str, Dict] = {}
        for level in ("critical", "high", "medium", "low"):
            breakdown[level] = {"total": 0, "passed": 0, "failed": 0}

        for r in results:
            pri = r.get("priority", "medium").lower()
            if pri not in breakdown:
                pri = "medium"
            breakdown[pri]["total"] += 1
            if r.get("passed"):
                breakdown[pri]["passed"] += 1
            else:
                breakdown[pri]["failed"] += 1

        return breakdown

    # ------------------------------------------------------------------
    # Trend verisi (onceki taramayla karsilastirma)
    # ------------------------------------------------------------------

    def _trend_data(self, results: List[Dict], plan: dict) -> Optional[Dict]:
        """Onceki tarama varsa karsilastirma verisi uret."""
        # Plan icerisinde proje yolu olabilir
        project_path = plan.get("project_path", "")
        if not project_path:
            # results'tan cikarmayi dene
            for r in results:
                detail = r.get("detail", "")
                target = r.get("target", "")
                if target and os.path.sep in target:
                    project_path = str(Path(target).parent)
                    break

        if not project_path:
            return None

        # .nazar/last-scan.json'u oku
        last_scan_path = Path(project_path) / ".nazar" / "last-scan.json"
        if not last_scan_path.exists():
            return {"available": False, "message": "Onceki tarama bulunamadi"}

        try:
            prev_data = json.loads(last_scan_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"available": False, "message": "Onceki tarama okunamadi"}

        prev_rate = prev_data.get("pass_rate", 0)
        prev_grade = prev_data.get("grade", "?")
        prev_total = prev_data.get("total", 0)
        prev_failed = prev_data.get("failed", 0)
        prev_timestamp = prev_data.get("timestamp", "")

        current_total = len(results)
        current_passed = sum(1 for r in results if r.get("passed"))
        current_rate = (current_passed / current_total * 100) if current_total > 0 else 0
        current_failed = current_total - current_passed

        delta = round(current_rate - prev_rate, 1)

        # Onceki failed isimleri
        prev_failed_names = set()
        for t in prev_data.get("tests", []):
            if not t.get("passed", True):
                prev_failed_names.add(t.get("name", ""))

        current_failed_names = set()
        for r in results:
            if not r.get("passed"):
                current_failed_names.add(r.get("name", ""))

        fixed = prev_failed_names - current_failed_names
        new_issues = current_failed_names - prev_failed_names

        return {
            "available": True,
            "previous": {
                "grade": prev_grade,
                "pass_rate": prev_rate,
                "total": prev_total,
                "failed": prev_failed,
                "timestamp": prev_timestamp,
            },
            "current": {
                "grade": self._grade(current_rate),
                "pass_rate": round(current_rate, 1),
                "total": current_total,
                "failed": current_failed,
            },
            "delta_rate": delta,
            "direction": "improving" if delta > 0 else "regressing" if delta < 0 else "stable",
            "fixed_count": len(fixed),
            "new_issues_count": len(new_issues),
            "fixed": sorted(fixed)[:10],
            "new_issues": sorted(new_issues)[:10],
        }

    # ------------------------------------------------------------------
    # Yardimci metodlar
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_file_from_detail(detail: str) -> str:
        """Detail stringinden dosya yolunu cikar."""
        m = re.search(r'([a-zA-Z0-9_/\-\.()]+\.[a-zA-Z]{1,5})(?::(\d+))?', detail)
        if m:
            return m.group(1)
        return ""

    @staticmethod
    def _highest_severity(severities: List[str]) -> str:
        """Listeden en yuksek severity'yi dondur."""
        order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        if not severities:
            return "low"
        return max(severities, key=lambda s: order.get(s, 0))

    @staticmethod
    def _grade(rate: float) -> str:
        for min_r, g in [
            (97, "A+"), (93, "A"), (90, "A-"),
            (87, "B+"), (83, "B"), (80, "B-"),
            (77, "C+"), (73, "C"), (70, "C-"),
            (67, "D+"), (63, "D"), (60, "D-"),
            (0, "F"),
        ]:
            if rate >= min_r:
                return g
        return "F"

    @staticmethod
    def _get_version() -> str:
        try:
            from nazar import __version__
            return __version__
        except (ImportError, AttributeError):
            return "unknown"
