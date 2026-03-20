"""SARIF Reporter - GitHub Code Scanning entegrasyonu icin SARIF v2.1.0."""
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict


class SARIFReporter:
    """SARIF v2.1.0 cikti reporter'i."""

    SARIF_VERSION = "2.1.0"
    SARIF_SCHEMA = "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json"

    LEVEL_MAP = {
        "critical": "error",
        "high": "error",
        "medium": "warning",
        "low": "note",
    }

    def generate(self, results: List[Dict], plan: dict, output_path: str = None) -> str:
        """SARIF rapor olustur."""
        rules = []
        rule_ids = set()
        sarif_results = []

        for r in results:
            if r["passed"]:
                continue

            rule_id = f"nazar/{r.get('type', 'unknown')}/{r.get('subtype', 'check')}"
            if rule_id not in rule_ids:
                rule_ids.add(rule_id)
                rules.append({
                    "id": rule_id,
                    "name": r.get("subtype", "check"),
                    "shortDescription": {"text": r["name"]},
                    "defaultConfiguration": {
                        "level": self.LEVEL_MAP.get(r.get("priority", "medium"), "warning")
                    },
                })

            detail = r.get("detail", "")
            file_path = ""
            line = 1
            if ":" in detail:
                parts = detail.split(":")
                for p in parts:
                    if "/" in p or "." in p:
                        file_path = p.strip()
                    elif p.strip().isdigit():
                        line = int(p.strip())

            result = {
                "ruleId": rule_id,
                "level": self.LEVEL_MAP.get(r.get("priority", "medium"), "warning"),
                "message": {"text": f"{r['name']}: {detail}"},
            }

            if file_path:
                result["locations"] = [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": file_path},
                        "region": {"startLine": line},
                    }
                }]

            sarif_results.append(result)

        sarif = {
            "$schema": self.SARIF_SCHEMA,
            "version": self.SARIF_VERSION,
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Nazar",
                        "version": "2.0.0",
                        "informationUri": "https://github.com/user/nazar",
                        "rules": rules,
                    }
                },
                "results": sarif_results,
                "invocations": [{
                    "executionSuccessful": True,
                    "endTimeUtc": datetime.utcnow().isoformat() + "Z",
                }],
            }],
        }

        output = json.dumps(sarif, indent=2, ensure_ascii=False)
        if output_path:
            Path(output_path).write_text(output)
        return output
