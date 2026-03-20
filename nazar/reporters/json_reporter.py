"""JSON Reporter - Test sonuclarini JSON formatinda ciktilar."""
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict


class JSONReporter:
    """JSON cikti reporter'i."""

    def generate(self, results: List[Dict], plan: dict, output_path: str = None) -> str:
        """JSON rapor olustur."""
        total = len(results)
        passed = sum(1 for r in results if r["passed"])
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0

        categories = {}
        for r in results:
            cat = r.get("type", "other")
            if cat not in categories:
                categories[cat] = {"passed": 0, "failed": 0, "tests": []}
            if r["passed"]:
                categories[cat]["passed"] += 1
            else:
                categories[cat]["failed"] += 1
            categories[cat]["tests"].append({
                "name": r["name"],
                "passed": r["passed"],
                "duration": r.get("duration", 0),
                "detail": r.get("detail", ""),
                "priority": r.get("priority", "medium"),
            })

        report = {
            "nazar_version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": round(pass_rate, 1),
                "grade": self._grade(pass_rate),
                "duration": sum(r.get("duration", 0) for r in results),
            },
            "categories": {
                name: {
                    "passed": data["passed"],
                    "failed": data["failed"],
                    "total": data["passed"] + data["failed"],
                    "pass_rate": round(
                        data["passed"] / (data["passed"] + data["failed"]) * 100
                        if (data["passed"] + data["failed"]) > 0 else 0, 1
                    ),
                }
                for name, data in categories.items()
            },
            "tests": [
                {
                    "name": r["name"],
                    "type": r.get("type", ""),
                    "subtype": r.get("subtype", ""),
                    "passed": r["passed"],
                    "duration": round(r.get("duration", 0), 3),
                    "detail": r.get("detail", ""),
                    "priority": r.get("priority", "medium"),
                }
                for r in results
            ],
        }

        output = json.dumps(report, indent=2, ensure_ascii=False)
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
