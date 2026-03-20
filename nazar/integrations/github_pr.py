"""GitHub PR Integration - PR comment ve Check Run olusturma."""
import json
import os
import re
from typing import Dict, List, Optional


class GitHubPRReporter:
    """Nazar sonuclarini GitHub PR comment olarak raporlar."""

    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN", "")
        self.repo = os.environ.get("GITHUB_REPOSITORY", "")
        self.pr_number = self._detect_pr_number()
        self.comment_marker = "<!-- nazar-report -->"

    def _detect_pr_number(self) -> Optional[int]:
        """PR numarasini environment'tan tespit et."""
        # GITHUB_REF_NAME: pr/123/merge
        ref = os.environ.get("GITHUB_REF", "")
        m = re.search(r"refs/pull/(\d+)", ref)
        if m:
            return int(m.group(1))
        # GITHUB_EVENT_PATH'den
        event_path = os.environ.get("GITHUB_EVENT_PATH", "")
        if event_path and os.path.exists(event_path):
            try:
                with open(event_path) as f:
                    event = json.load(f)
                pr = event.get("pull_request", {})
                if pr.get("number"):
                    return pr["number"]
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def generate_markdown(self, results: List[Dict], plan: dict) -> str:
        """Sonuclardan Markdown PR comment olustur."""
        passed = sum(1 for r in results if r["passed"])
        failed = len(results) - passed
        rate = (passed / len(results) * 100) if results else 0

        # Not hesapla
        if rate >= 90:
            grade, emoji = "A+", "sparkles"
            status = "harika"
        elif rate >= 80:
            grade, emoji = "A", "white_check_mark"
            status = "iyi"
        elif rate >= 70:
            grade, emoji = "B", "large_blue_circle"
            status = "orta"
        elif rate >= 50:
            grade, emoji = "C", "warning"
            status = "iyilestirme gerek"
        else:
            grade, emoji = "D", "x"
            status = "kritik sorunlar var"

        lines = [
            self.comment_marker,
            f"## Nazar Raporu: {grade} ({rate:.0f}%)",
            "",
            f"**{passed}** gecti / **{failed}** kaldi / **{len(results)}** toplam - {status}",
            "",
        ]

        # Kritik sorunlar
        critical = [r for r in results if not r["passed"] and r.get("priority") == "critical"]
        high = [r for r in results if not r["passed"] and r.get("priority") == "high"]
        medium = [r for r in results if not r["passed"] and r.get("priority") == "medium"]

        if critical:
            lines.append("### Kritik Sorunlar")
            lines.append("")
            for r in critical[:10]:
                detail = r.get("detail", "")[:100]
                lines.append(f"- **{r['name']}**: {detail}")
            lines.append("")

        if high:
            lines.append("### Yuksek Oncelikli Sorunlar")
            lines.append("")
            for r in high[:10]:
                detail = r.get("detail", "")[:100]
                lines.append(f"- {r['name']}: {detail}")
            lines.append("")

        if medium:
            lines.append(f"<details><summary>Orta Oncelikli ({len(medium)} adet)</summary>")
            lines.append("")
            for r in medium[:20]:
                detail = r.get("detail", "")[:80]
                lines.append(f"- {r['name']}: {detail}")
            lines.append("</details>")
            lines.append("")

        # Kategori ozeti
        categories = {}
        for r in results:
            cat = r.get("type", "other")
            if cat not in categories:
                categories[cat] = {"passed": 0, "failed": 0}
            if r["passed"]:
                categories[cat]["passed"] += 1
            else:
                categories[cat]["failed"] += 1

        lines.append("### Kategori Ozeti")
        lines.append("")
        lines.append("| Kategori | Gecti | Kaldi | Oran |")
        lines.append("|----------|-------|-------|------|")
        for cat, counts in sorted(categories.items()):
            total = counts["passed"] + counts["failed"]
            cat_rate = (counts["passed"] / total * 100) if total else 0
            icon = "+" if cat_rate >= 80 else "-" if cat_rate < 50 else "~"
            lines.append(f"| {cat} | {counts['passed']} | {counts['failed']} | {cat_rate:.0f}% |")
        lines.append("")
        lines.append("---")
        lines.append("*Nazar v3.0 ile uretildi*")

        return "\n".join(lines)

    def post_comment(self, results: List[Dict], plan: dict) -> bool:
        """GitHub PR'a comment gonder veya guncelle."""
        if not self.token or not self.repo or not self.pr_number:
            return False

        import urllib.request

        markdown = self.generate_markdown(results, plan)
        api_base = "https://api.github.com"
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

        # Onceki comment'i bul
        existing_id = self._find_existing_comment(api_base, headers)

        if existing_id:
            # Guncelle
            url = f"{api_base}/repos/{self.repo}/issues/comments/{existing_id}"
            data = json.dumps({"body": markdown}).encode()
            req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
        else:
            # Yeni comment
            url = f"{api_base}/repos/{self.repo}/issues/{self.pr_number}/comments"
            data = json.dumps({"body": markdown}).encode()
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            urllib.request.urlopen(req, timeout=30)
            return True
        except Exception:
            return False

    def _find_existing_comment(self, api_base: str, headers: dict) -> Optional[int]:
        """Onceki Nazar comment'ini bul (guncelleme icin)."""
        import urllib.request

        url = f"{api_base}/repos/{self.repo}/issues/{self.pr_number}/comments?per_page=100"
        req = urllib.request.Request(url, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            comments = json.loads(resp.read())
            for c in comments:
                if self.comment_marker in c.get("body", ""):
                    return c["id"]
        except Exception:
            pass
        return None

    def generate_sarif(self, results: List[Dict]) -> str:
        """SARIF formatinda sonuc ureti (GitHub Code Scanning icin)."""
        rules = []
        sarif_results = []
        rule_ids = set()

        for r in results:
            if r["passed"]:
                continue
            rule_id = r.get("subtype", r.get("type", "unknown"))
            if rule_id not in rule_ids:
                rule_ids.add(rule_id)
                level = "error" if r.get("priority") in ("critical", "high") else "warning"
                rules.append({
                    "id": rule_id,
                    "name": r.get("name", rule_id),
                    "shortDescription": {"text": r.get("name", rule_id)},
                    "defaultConfiguration": {"level": level},
                })
            # Dosya bilgisi varsa konum ekle
            detail = r.get("detail", "")
            file_match = re.search(r"(\S+\.\w+):(\d+)", detail)
            location = {}
            if file_match:
                location = {
                    "physicalLocation": {
                        "artifactLocation": {"uri": file_match.group(1)},
                        "region": {"startLine": int(file_match.group(2))},
                    }
                }
            sarif_results.append({
                "ruleId": rule_id,
                "message": {"text": detail or r.get("name", "Sorun tespit edildi")},
                "locations": [location] if location else [],
            })

        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Nazar",
                        "version": "3.0.0",
                        "informationUri": "https://github.com/nazar-cli/nazar",
                        "rules": rules,
                    }
                },
                "results": sarif_results,
            }],
        }
        return json.dumps(sarif, indent=2, ensure_ascii=False)

    def get_check_status(self, results: List[Dict]) -> str:
        """CI/CD icin pass/fail durumu."""
        critical = any(
            not r["passed"] and r.get("priority") == "critical"
            for r in results
        )
        return "failure" if critical else "success"
