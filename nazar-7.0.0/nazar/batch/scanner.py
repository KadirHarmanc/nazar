"""Batch Scanner - Birden fazla projeyi sirayla tarar, konsolide rapor uretir."""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class BatchScanner:
    """Coklu proje tarayici.

    Birden fazla projeyi sirayla tarar, her proje icin ayri sonuc tutar,
    konsolide rapor ve markdown ozet tablosu uretir.

    Kullanim:
        scanner = BatchScanner(["/path/project1", "/path/project2"], profile="ci")
        results = scanner.scan_all()
        report = scanner.generate_report()
    """

    def __init__(self, project_paths: List[str], profile: str = "ci"):
        self.project_paths = []
        home_dir = str(Path.home().resolve())
        cwd = str(Path.cwd().resolve())
        for p in project_paths:
            resolved = str(Path(p).resolve())
            if not (resolved.startswith(home_dir) or resolved.startswith(cwd)):
                raise ValueError(
                    f"Guvenlik hatasi: '{resolved}' yolu kullanici dizini veya "
                    f"calisma dizini disinda. Sadece home veya cwd altindaki "
                    f"projeler taranabilir."
                )
            self.project_paths.append(resolved)
        self.profile = profile
        self.results: Dict[str, dict] = {}  # proje_yolu -> sonuc
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def scan_all(self) -> Dict[str, dict]:
        """Tum projeleri sirayla tara.

        Returns:
            Dict: proje_yolu -> {
                "project_name": str,
                "path": str,
                "grade": str,
                "pass_rate": float,
                "passed": int,
                "failed": int,
                "total": int,
                "duration": float,
                "results": List[dict],
                "error": Optional[str],
                "categories": dict,
            }
        """
        from nazar.scanner.project_scanner import ProjectScanner
        from nazar.planner.test_planner import TestPlanner
        from nazar.runners.orchestrator import TestOrchestrator
        from nazar.cache.scan_cache import ScanCache

        self.start_time = time.time()
        self.results = {}

        for project_path in self.project_paths:
            path = Path(project_path)
            project_name = path.name

            if not path.exists():
                self.results[project_path] = {
                    "project_name": project_name,
                    "path": project_path,
                    "grade": "F",
                    "pass_rate": 0.0,
                    "passed": 0,
                    "failed": 0,
                    "total": 0,
                    "duration": 0.0,
                    "results": [],
                    "error": f"Dizin bulunamadi: {project_path}",
                    "categories": {},
                }
                continue

            proj_start = time.time()
            try:
                # 1. Tara
                scanner = ProjectScanner(project_path)
                scan_result = scanner.scan()

                # 2. Planla
                planner = TestPlanner(scan_result, profile=self.profile)
                test_plan = planner.create_plan()
                plan_dict = test_plan.to_dict()

                # 3. Calistir
                orchestrator = TestOrchestrator(project_path, plan_dict)
                results = orchestrator.run_all()

                # 4. Hesapla
                proj_duration = time.time() - proj_start
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

                # Cache kaydet
                cache = ScanCache(project_path)
                cache.save_scan_result(results, plan_dict, self.profile, proj_duration)
                if scan_result.source_files:
                    cache.save_file_hashes(scan_result.source_files)

                self.results[project_path] = {
                    "project_name": project_name,
                    "path": project_path,
                    "grade": grade,
                    "pass_rate": round(rate, 1),
                    "passed": passed,
                    "failed": total - passed,
                    "total": total,
                    "duration": round(proj_duration, 1),
                    "results": results,
                    "error": None,
                    "categories": categories,
                }

            except Exception:
                proj_duration = time.time() - proj_start
                self.results[project_path] = {
                    "project_name": project_name,
                    "path": project_path,
                    "grade": "F",
                    "pass_rate": 0.0,
                    "passed": 0,
                    "failed": 1,
                    "total": 1,
                    "duration": round(proj_duration, 1),
                    "results": [],
                    "error": "Proje taranirken beklenmeyen bir hata olustu",
                    "categories": {},
                }

        self.end_time = time.time()
        return self.results

    def generate_report(self) -> str:
        """Markdown formatinda ozet rapor uret.

        Returns:
            str: Markdown tablosu ve ozet bilgiler
        """
        if not self.results:
            return "# Nazar Batch Raporu\n\nHenuz tarama yapilmadi.\n"

        total_duration = (self.end_time - self.start_time) if self.end_time and self.start_time else 0
        total_projects = len(self.results)
        total_passed = sum(r["passed"] for r in self.results.values())
        total_failed = sum(r["failed"] for r in self.results.values())
        total_tests = total_passed + total_failed
        total_rate = (total_passed / total_tests * 100) if total_tests else 0
        total_errors = sum(1 for r in self.results.values() if r.get("error"))

        lines = [
            "# Nazar Batch Tarama Raporu",
            "",
            f"**Tarih:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Profil:** {self.profile}",
            f"**Toplam Sure:** {total_duration:.1f}s",
            f"**Proje Sayisi:** {total_projects}",
            "",
            "## Ozet",
            "",
            f"| Metrik | Deger |",
            f"|--------|-------|",
            f"| Toplam Test | {total_tests} |",
            f"| Gecen | {total_passed} |",
            f"| Kalan | {total_failed} |",
            f"| Basari Orani | {total_rate:.1f}% |",
            f"| Not | {self._grade(total_rate)} |",
            f"| Hatali Proje | {total_errors} |",
            "",
            "## Proje Detaylari",
            "",
            "| Proje | Not | Basari | Gecen/Kalan | Sure | Durum |",
            "|-------|-----|--------|-------------|------|-------|",
        ]

        for path, data in self.results.items():
            if data.get("error"):
                status = f"HATA: {data['error'][:40]}"
            else:
                status = "OK"
            lines.append(
                f"| {data['project_name']} | {data['grade']} | "
                f"{data['pass_rate']}% | {data['passed']}/{data['failed']} | "
                f"{data['duration']}s | {status} |"
            )

        # Kategori bazli genel ozet
        all_categories: Dict[str, Dict[str, int]] = {}
        for data in self.results.values():
            for cat, counts in data.get("categories", {}).items():
                if cat not in all_categories:
                    all_categories[cat] = {"passed": 0, "failed": 0}
                all_categories[cat]["passed"] += counts["passed"]
                all_categories[cat]["failed"] += counts["failed"]

        if all_categories:
            lines.extend([
                "",
                "## Kategori Ozeti",
                "",
                "| Kategori | Gecen | Kalan | Oran |",
                "|----------|-------|-------|------|",
            ])
            for cat, counts in sorted(all_categories.items()):
                cat_total = counts["passed"] + counts["failed"]
                cat_rate = (counts["passed"] / cat_total * 100) if cat_total else 0
                lines.append(
                    f"| {cat} | {counts['passed']} | {counts['failed']} | {cat_rate:.0f}% |"
                )

        # Basarisiz testler ozeti (proje bazli)
        any_failures = False
        for data in self.results.values():
            failures = [r for r in data.get("results", []) if not r.get("passed")]
            if failures:
                if not any_failures:
                    lines.extend(["", "## Basarisiz Testler", ""])
                    any_failures = True
                lines.append(f"### {data['project_name']}")
                lines.append("")
                for f in failures[:10]:
                    pri = f.get("priority", "medium").upper()
                    lines.append(f"- **[{pri}]** {f['name']}: {f.get('detail', '')[:80]}")
                if len(failures) > 10:
                    lines.append(f"- ...ve {len(failures) - 10} sorun daha")
                lines.append("")

        lines.append("")
        lines.append("---")
        lines.append(f"*Nazar Batch Scanner | {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
        lines.append("")

        return "\n".join(lines)

    def get_consolidated_summary(self) -> dict:
        """Tum projelerin konsolide ozetini dondur."""
        total_passed = sum(r["passed"] for r in self.results.values())
        total_failed = sum(r["failed"] for r in self.results.values())
        total_tests = total_passed + total_failed
        total_rate = (total_passed / total_tests * 100) if total_tests else 0
        total_duration = (self.end_time - self.start_time) if self.end_time and self.start_time else 0

        return {
            "project_count": len(self.results),
            "total_tests": total_tests,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "pass_rate": round(total_rate, 1),
            "grade": self._grade(total_rate),
            "duration": round(total_duration, 1),
            "errors": sum(1 for r in self.results.values() if r.get("error")),
            "projects": {
                path: {
                    "name": data["project_name"],
                    "grade": data["grade"],
                    "pass_rate": data["pass_rate"],
                    "passed": data["passed"],
                    "failed": data["failed"],
                    "error": data.get("error"),
                }
                for path, data in self.results.items()
            },
        }

    @staticmethod
    def _grade(rate: float) -> str:
        for min_r, g in [(97, "A+"), (93, "A"), (90, "A-"), (87, "B+"), (83, "B"),
                         (80, "B-"), (77, "C+"), (73, "C"), (70, "C-"), (67, "D+"),
                         (63, "D"), (60, "D-"), (0, "F")]:
            if rate >= min_r:
                return g
        return "F"
