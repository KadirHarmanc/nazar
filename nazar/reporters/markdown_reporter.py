"""Markdown Reporter - PR yorumu veya README icin Markdown formati."""
from datetime import datetime
from pathlib import Path
from typing import List, Dict


class MarkdownReporter:
    """Markdown cikti reporter'i."""

    def generate(self, results: List[Dict], plan: dict, output_path: str = None) -> str:
        """Markdown rapor olustur."""
        total = len(results)
        passed = sum(1 for r in results if r["passed"])
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0
        grade = self._grade(pass_rate)

        lines = [
            f"# Nazar Test Raporu",
            f"",
            f"**Tarih:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Not:** {grade} ({pass_rate:.0f}%)",
            f"",
            f"## Ozet",
            f"",
            f"| Metrik | Deger |",
            f"|--------|-------|",
            f"| Toplam Test | {total} |",
            f"| Gecen | {passed} |",
            f"| Kalan | {failed} |",
            f"| Basari Orani | {pass_rate:.0f}% |",
            f"",
        ]

        # Kategori tablosu
        categories: Dict[str, Dict] = {}
        for r in results:
            cat = r.get("type", "other")
            if cat not in categories:
                categories[cat] = {"passed": 0, "failed": 0}
            if r["passed"]:
                categories[cat]["passed"] += 1
            else:
                categories[cat]["failed"] += 1

        lines.extend([
            "## Kategoriler",
            "",
            "| Kategori | Gecen | Kalan | Oran |",
            "|----------|-------|-------|------|",
        ])
        for cat, data in categories.items():
            cat_total = data["passed"] + data["failed"]
            cat_rate = (data["passed"] / cat_total * 100) if cat_total > 0 else 0
            emoji = "+" if cat_rate >= 80 else "!" if cat_rate >= 50 else "-"
            lines.append(f"| {cat.upper()} | {data['passed']} | {data['failed']} | {emoji} {cat_rate:.0f}% |")

        # Basarisiz testler
        failed_tests = [r for r in results if not r["passed"]]
        if failed_tests:
            lines.extend(["", "## Basarisiz Testler", ""])
            for r in failed_tests:
                priority = r.get("priority", "medium")
                lines.append(f"- **[{priority.upper()}]** {r['name']}: {r.get('detail', '')}")

        lines.extend(["", "---", f"*Nazar v2.0.0*"])

        output = "\n".join(lines)
        if output_path:
            Path(output_path).write_text(output)
        return output

    @staticmethod
    def _grade(rate: float) -> str:
        if rate >= 97: return "A+"
        if rate >= 93: return "A"
        if rate >= 90: return "A-"
        if rate >= 87: return "B+"
        if rate >= 83: return "B"
        if rate >= 80: return "B-"
        if rate >= 77: return "C+"
        if rate >= 73: return "C"
        if rate >= 70: return "C-"
        if rate >= 67: return "D+"
        if rate >= 63: return "D"
        if rate >= 60: return "D-"
        return "F"
