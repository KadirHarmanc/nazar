"""YAML UI Test Runner - YAML UI testlerini statik analiz ile calistirir."""
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

from nazar.runners.base import BaseRunner, IGNORE_DIRS


DESTEKLENEN_ACTIONLAR = {
    "launchApp", "navigate", "goBack", "scrollDown", "scrollUp",
    "tapOn", "longPress", "doubleTap", "inputText", "clearText",
    "selectOption", "assertVisible", "assertNotVisible", "assertText",
    "assertEnabled", "assertDisabled", "waitForVisible", "screenshot",
    "wait", "conditional", "runFlow",
}

ZORUNLU_ALANLAR = {
    "tapOn": ["target"], "longPress": ["target"], "doubleTap": ["target"],
    "inputText": ["target", "value"], "clearText": ["target"],
    "selectOption": ["target", "value"], "assertVisible": ["target"],
    "assertNotVisible": ["target"], "assertText": ["target", "value"],
    "assertEnabled": ["target"], "assertDisabled": ["target"],
    "waitForVisible": ["target"], "navigate": ["target"],
    "wait": ["duration"], "runFlow": ["flow"],
}


class YAMLUITestRunner(BaseRunner):
    """YAML UI test dosyalarini statik analiz ile calistirir."""

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = {
            "yaml_ui_syntax": self._yaml_ui_syntax,
            "yaml_ui_targets": self._yaml_ui_targets,
            "yaml_ui_coverage": self._yaml_ui_coverage,
        }
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    def _find_yaml_tests(self) -> List[Path]:
        """UI test YAML dosyalarini bul."""
        ui_dir = self.root / ".nazar" / "ui-tests"
        if not ui_dir.exists():
            return []
        files = []
        for ext in ("*.yml", "*.yaml"):
            files.extend(ui_dir.glob(ext))
        return files

    def _parse_yaml(self, path: Path) -> dict:
        try:
            return yaml.safe_load(path.read_text(errors="ignore")) or {}
        except yaml.YAMLError:
            return {}

    def _yaml_ui_syntax(self, t: dict) -> Tuple[bool, str]:
        """YAML test dosyalarinin syntax ve schema kontrolu."""
        files = self._find_yaml_tests()
        if not files:
            return True, "UI test dosyasi yok (.nazar/ui-tests/)"

        errors = []
        for f in files:
            data = self._parse_yaml(f)
            if not data:
                errors.append("{}: bos veya gecersiz YAML".format(f.name))
                continue
            if "steps" not in data:
                errors.append("{}: 'steps' alani eksik".format(f.name))
                continue
            for i, step in enumerate(data.get("steps", []), 1):
                if not isinstance(step, dict):
                    errors.append("{} step {}: dict olmali".format(f.name, i))
                    continue
                action = step.get("action", "")
                if action not in DESTEKLENEN_ACTIONLAR:
                    errors.append("{} step {}: bilinmeyen action '{}'".format(f.name, i, action))
                    continue
                for alan in ZORUNLU_ALANLAR.get(action, []):
                    if alan not in step:
                        errors.append("{} step {} ({}): '{}' eksik".format(f.name, i, action, alan))

        if errors:
            return False, "{} syntax hatasi: {}".format(len(errors), errors[0])
        return True, "{} YAML dosyasi gecerli".format(len(files))

    def _yaml_ui_targets(self, t: dict) -> Tuple[bool, str]:
        """YAML'daki hedeflerin projede var olup olmadigini kontrol et."""
        files = self._find_yaml_tests()
        if not files:
            return True, "UI test dosyasi yok"

        all_targets = set()
        for f in files:
            data = self._parse_yaml(f)
            for step in data.get("steps", []):
                target = step.get("target", "")
                if target and step.get("action") in ("tapOn", "assertVisible", "assertNotVisible",
                                                       "inputText", "assertText", "waitForVisible"):
                    all_targets.add(target)

        if not all_targets:
            return True, "Hedef bulunamadi"

        # Projede ara
        all_content = ""
        for f in self.src_files()[:300]:
            if "nazar/" not in f and "test" not in f.lower():
                all_content += self.read(f) + "\n"

        missing = []
        for target in all_targets:
            if target not in all_content:
                similar = self._find_similar(target, all_content)
                missing.append({"target": target, "suggestion": similar})

        if not missing:
            return True, "{} hedef, hepsi projede mevcut".format(len(all_targets))

        first = missing[0]
        detail = "{} hedef bulunamadi: '{}'".format(len(missing), first["target"])
        if first["suggestion"]:
            detail += " (belki '{}' mi?)".format(first["suggestion"])
        return False, detail

    def _yaml_ui_coverage(self, t: dict) -> Tuple[bool, str]:
        """UI test kapsami: kac ekran test edilmis."""
        files = self._find_yaml_tests()
        if not files:
            return True, "UI test dosyasi yok"

        # Ekranlari bul
        screens = set()
        for f in self.src_files()[:300]:
            content = self.read(f)
            for m in re.finditer(r'<(?:Stack|Tab|Drawer)\.Screen\s+[^>]*name=["\'](\w+)["\']', content):
                screens.add(m.group(1))
            for m in re.finditer(r'(?:export\s+)?(?:const|function)\s+(\w+Screen|\w+Page)', content):
                screens.add(m.group(1))

        if not screens:
            return True, "Ekran bulunamadi"

        # YAML'lardan test edilen ekranlar
        tested = set()
        for f in files:
            data = self._parse_yaml(f)
            for step in data.get("steps", []):
                if step.get("action") == "navigate":
                    tested.add(step.get("target", ""))

        untested = screens - tested
        coverage = ((len(screens) - len(untested)) / len(screens) * 100) if screens else 100

        if not untested:
            return True, "{} ekran, hepsi UI test kapsaminda".format(len(screens))
        return False, "{}/{} ekran test edilmemis ({:.0f}% kapsam)".format(
            len(untested), len(screens), coverage)

    def _find_similar(self, target: str, content: str) -> str:
        """Icerikte benzer string bul."""
        words = set(re.findall(r'\b\w{3,}\b', content))
        best, best_dist = "", 999
        for w in words:
            d = self._lev(target.lower(), w.lower())
            if d < best_dist and d <= 3:
                best_dist = d
                best = w
        return best

    @staticmethod
    def _lev(s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return YAMLUITestRunner._lev(s2, s1)
        if not s2:
            return len(s1)
        prev = range(len(s2) + 1)
        for c1 in s1:
            curr = [prev[0] + 1]
            for j, c2 in enumerate(s2):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
            prev = curr
        return prev[len(s2)]


class YAMLUIGenerator(BaseRunner):
    """Projedeki ekranlardan otomatik YAML test dosyasi uretir."""

    def generate(self, output_dir: str = None) -> List[str]:
        """Her ekran icin YAML test dosyasi olustur."""
        if output_dir is None:
            output_dir = str(self.root / ".nazar" / "ui-tests")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        screens = self._discover_screens()
        created = []

        for screen in screens:
            filename = self._screen_to_filename(screen["name"])
            filepath = Path(output_dir) / filename
            if filepath.exists():
                continue

            content = self._generate_yaml(screen)
            filepath.write_text(content)
            created.append(str(filepath))

        return created

    def _discover_screens(self) -> List[Dict]:
        """Ekranlari ve elementlerini bul."""
        screens = []
        for f in self.src_files()[:300]:
            if "test" in f.lower() or f.startswith("nazar/"):
                continue
            content = self.read(f)
            ext = Path(f).suffix.lower()
            if ext not in (".tsx", ".jsx", ".ts", ".js"):
                continue

            for m in re.finditer(r'(?:export\s+)?(?:const|function)\s+(\w+Screen|\w+Page)\s*', content):
                name = m.group(1)
                elements = self._find_elements(content)
                screens.append({"name": name, "file": f, "elements": elements})

        return screens

    def _find_elements(self, content: str) -> List[Dict]:
        """Dosyadaki UI elementlerini bul."""
        elements = []
        for m in re.finditer(r'<Text[^>]*>([^<{]+)</Text>', content):
            elements.append({"type": "Text", "text": m.group(1).strip()})
        for m in re.finditer(r'placeholder=["\']([^"\']+)["\']', content):
            elements.append({"type": "TextInput", "text": m.group(1)})
        for m in re.finditer(r'title=["\']([^"\']+)["\']', content):
            elements.append({"type": "Button", "text": m.group(1)})
        return elements

    def _generate_yaml(self, screen: Dict) -> str:
        """Tek ekran icin YAML icerik olustur."""
        lines = [
            "apiVersion: nazar/v1",
            "name: {} Testi".format(screen["name"]),
            "description: {} ekraninin temel kontrolleri".format(screen["name"]),
            "platform: all",
            "priority: high",
            "",
            "steps:",
            "  - action: navigate",
            '    target: "{}"'.format(screen["name"]),
        ]

        for el in screen.get("elements", [])[:10]:
            lines.append("")
            lines.append("  - action: assertVisible")
            lines.append('    target: "{}"  # {} elementi'.format(el["text"], el["type"]))

        lines.append("")
        lines.append("  # TODO: Ekran akisini tamamlayin")
        lines.append("  # - action: inputText")
        lines.append('  #   target: "alan_adi"')
        lines.append('  #   value: "test_degeri"')

        return "\n".join(lines) + "\n"

    @staticmethod
    def _screen_to_filename(name: str) -> str:
        """ScreenName -> screen-name.yml"""
        # Ilk buyuk harften once tire koyma
        result = re.sub(r'(?<!^)([A-Z])', r'-\1', name).lower()
        return "{}.yml".format(result)
