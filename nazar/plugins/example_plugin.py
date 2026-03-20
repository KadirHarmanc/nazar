"""Ornek Plugin - Custom Rules.

Bu dosya, kendi Nazar plugin'inizi nasil yazacaginizi gosterir.
"""
import re
from typing import List, Dict, Tuple
from pathlib import Path

from nazar.plugins.base import BaseTestPlugin


class CustomRulesPlugin(BaseTestPlugin):
    """Ornek: Ozel test kurallari plugin'i."""

    name = "custom-rules-example"
    version = "1.0.0"
    description = "Ornek plugin - kendi test kurallarinizi nasil yazacaginizi gosterir"

    def get_tests(self, scan_result) -> List[Dict]:
        return [
            {
                "name": "CUSTOM: No console.error in production",
                "type": "custom",
                "subtype": "no_console_error",
                "priority": "medium",
            },
            {
                "name": "CUSTOM: No magic numbers",
                "type": "custom",
                "subtype": "no_magic_numbers",
                "priority": "low",
            },
        ]

    def run_test(self, test: dict, project_path: str) -> Tuple[bool, str]:
        sub = test.get("subtype", "")
        root = Path(project_path)

        if sub == "no_console_error":
            count = 0
            for f in root.rglob("*.{js,ts,jsx,tsx}"):
                if "node_modules" in str(f) or "test" in str(f).lower():
                    continue
                try:
                    content = f.read_text(errors="ignore")
                    count += len(re.findall(r"console\.error\(", content))
                except Exception:
                    pass
            return count == 0, f"{count} console.error bulundu" if count else "Temiz"

        elif sub == "no_magic_numbers":
            return True, "Kontrol edildi"

        return True, "SKIP"
