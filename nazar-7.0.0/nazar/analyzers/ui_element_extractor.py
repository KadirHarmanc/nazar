"""UI Element Extractor - Projeden tum UI elementlerini tek seferde cikarir.

Shared Analysis Layer: Bu veri yazim, renk, font, a11y, i18n katmanlarina dagitilir.
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from nazar.runners.base import BaseRunner, IGNORE_DIRS


@dataclass
class UIElement:
    file: str
    line: int
    element_type: str       # Button, Text, TextInput, Image, View, TouchableOpacity...
    text: str = ""          # gorunen metin
    style: Dict = field(default_factory=dict)
    accessibility_label: str = ""
    test_id: str = ""
    props: Dict = field(default_factory=dict)
    placeholder: str = ""
    source: str = ""        # hangi framework (react, flutter, swift, kotlin)


class UIElementExtractor(BaseRunner):
    """Projeden tum UI elementlerini cikarir."""

    # JSX/TSX element pattern'leri
    JSX_ELEMENTS = {
        "Text": r'<Text[^>]*>([^<]*)</Text>',
        "Button": r'<(?:Button|TouchableOpacity|Pressable)[^>]*(?:title=["\']([^"\']+)["\']|>([^<]*))',
        "TextInput": r'<TextInput[^>]*',
        "Image": r'<Image[^>]*',
        "View": r'<(?:View|ScrollView|FlatList|SafeAreaView)[^>]*',
    }

    # Prop extraction
    PROP_PATTERNS = {
        "text": r'(?:title|label|children)=["\']([^"\']+)["\']',
        "placeholder": r'placeholder=["\']([^"\']+)["\']',
        "testID": r'testID=["\']([^"\']+)["\']',
        "accessibilityLabel": r'accessibilityLabel=["\']([^"\']+)["\']',
        "style_color": r'color:\s*["\']?(#[0-9A-Fa-f]{3,8}|rgb\([^)]+\))["\']?',
        "style_bg": r'backgroundColor:\s*["\']?(#[0-9A-Fa-f]{3,8}|rgb\([^)]+\))["\']?',
        "style_fontSize": r'fontSize:\s*(\d+)',
        "style_fontFamily": r'fontFamily:\s*["\']([^"\']+)["\']',
        "style_width": r'width:\s*(\d+)',
        "style_height": r'height:\s*(\d+)',
        "required": r'\brequired\b',
        "maxLength": r'maxLength=\{?(\d+)',
        "keyboardType": r'keyboardType=["\']([^"\']+)["\']',
    }

    def extract(self, source_files: List[str] = None) -> List[UIElement]:
        """Tum UI elementlerini cikar."""
        if source_files is None:
            source_files = self._ui_files()
        elements = []
        for f in source_files:
            content = self.read(f)
            if not content:
                continue
            ext = Path(f).suffix.lower()
            if ext in (".tsx", ".jsx", ".ts", ".js"):
                elements.extend(self._parse_jsx(f, content))
            elif ext == ".dart":
                elements.extend(self._parse_dart(f, content))
            elif ext == ".swift":
                elements.extend(self._parse_swift(f, content))
            elif ext == ".kt" or ext == ".java":
                elements.extend(self._parse_kotlin(f, content))
        return elements

    def _ui_files(self) -> List[str]:
        """UI dosyalarini bul (screen, component, page)."""
        ui_exts = {".tsx", ".jsx", ".ts", ".js", ".dart", ".swift", ".kt", ".java"}
        files = []
        for f in self.src_files():
            if Path(f).suffix.lower() in ui_exts:
                if "test" not in f.lower() and "spec" not in f.lower() and not f.startswith("nazar/"):
                    files.append(f)
        return files

    def _parse_jsx(self, file_path: str, content: str) -> List[UIElement]:
        """JSX/TSX dosyasini parse et."""
        elements = []
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            # <Text>icerik</Text>
            for m in re.finditer(r'<Text[^>]*>([^<]+)</Text>', line):
                text = m.group(1).strip()
                if text and not text.startswith("{"):
                    el = UIElement(file=file_path, line=i, element_type="Text", text=text, source="react")
                    self._extract_props(el, line)
                    elements.append(el)

            # <Text>{t('key')}</Text> - i18n
            for m in re.finditer(r'<Text[^>]*>\{t\(["\']([^"\']+)["\']\)\}</Text>', line):
                el = UIElement(file=file_path, line=i, element_type="Text", text=m.group(1), source="react")
                el.props["i18n"] = True
                elements.append(el)

            # <Button title="..." /> veya <TouchableOpacity>
            for m in re.finditer(r'<(?:Button|TouchableOpacity|Pressable)[^>]*title=["\']([^"\']+)["\']', line):
                el = UIElement(file=file_path, line=i, element_type="Button", text=m.group(1), source="react")
                self._extract_props(el, line)
                elements.append(el)

            # <TextInput placeholder="..." />
            for m in re.finditer(r'<TextInput[^>]*placeholder=["\']([^"\']+)["\']', line):
                el = UIElement(file=file_path, line=i, element_type="TextInput", source="react")
                el.placeholder = m.group(1)
                el.text = m.group(1)
                self._extract_props(el, line)
                elements.append(el)

            # <Image />
            if "<Image" in line and "source" in line:
                el = UIElement(file=file_path, line=i, element_type="Image", source="react")
                self._extract_props(el, line)
                elements.append(el)

        return elements

    def _parse_dart(self, file_path: str, content: str) -> List[UIElement]:
        """Flutter/Dart dosyasini parse et."""
        elements = []
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            # Text('icerik')
            for m in re.finditer(r"Text\(\s*['\"]([^'\"]+)['\"]", line):
                elements.append(UIElement(file=file_path, line=i, element_type="Text", text=m.group(1), source="flutter"))
            # ElevatedButton / TextButton
            for m in re.finditer(r"(?:ElevatedButton|TextButton|OutlinedButton)\(", line):
                el = UIElement(file=file_path, line=i, element_type="Button", source="flutter")
                # child: Text('...') bir sonraki satirda olabilir
                context = "\n".join(lines[max(0, i-1):min(len(lines), i+3)])
                tm = re.search(r"Text\(\s*['\"]([^'\"]+)['\"]", context)
                if tm:
                    el.text = tm.group(1)
                elements.append(el)
            # TextField
            if "TextField(" in line or "TextFormField(" in line:
                el = UIElement(file=file_path, line=i, element_type="TextInput", source="flutter")
                hm = re.search(r"hintText:\s*['\"]([^'\"]+)['\"]", "\n".join(lines[max(0, i-1):min(len(lines), i+5)]))
                if hm:
                    el.placeholder = hm.group(1)
                    el.text = hm.group(1)
                elements.append(el)
        return elements

    def _parse_swift(self, file_path: str, content: str) -> List[UIElement]:
        """SwiftUI dosyasini parse et."""
        elements = []
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            for m in re.finditer(r'Text\("([^"]+)"\)', line):
                elements.append(UIElement(file=file_path, line=i, element_type="Text", text=m.group(1), source="swift"))
            for m in re.finditer(r'Button\("([^"]+)"\)', line):
                elements.append(UIElement(file=file_path, line=i, element_type="Button", text=m.group(1), source="swift"))
            if "TextField(" in line:
                tm = re.search(r'TextField\("([^"]*)"', line)
                el = UIElement(file=file_path, line=i, element_type="TextInput", source="swift")
                if tm:
                    el.placeholder = tm.group(1)
                    el.text = tm.group(1)
                elements.append(el)
        return elements

    def _parse_kotlin(self, file_path: str, content: str) -> List[UIElement]:
        """Jetpack Compose / Android dosyasini parse et."""
        elements = []
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            for m in re.finditer(r'Text\(\s*(?:text\s*=\s*)?["\']([^"\']+)["\']', line):
                elements.append(UIElement(file=file_path, line=i, element_type="Text", text=m.group(1), source="kotlin"))
            for m in re.finditer(r'Button\(', line):
                el = UIElement(file=file_path, line=i, element_type="Button", source="kotlin")
                context = "\n".join(lines[max(0, i-1):min(len(lines), i+3)])
                tm = re.search(r'Text\(\s*["\']([^"\']+)["\']', context)
                if tm:
                    el.text = tm.group(1)
                elements.append(el)
        return elements

    def _extract_props(self, el: UIElement, line: str):
        """Bir satirdaki prop'lari extract et."""
        for prop_name, pattern in self.PROP_PATTERNS.items():
            m = re.search(pattern, line)
            if m:
                if prop_name == "accessibilityLabel":
                    el.accessibility_label = m.group(1) if m.lastindex else ""
                elif prop_name == "testID":
                    el.test_id = m.group(1) if m.lastindex else ""
                elif prop_name == "placeholder":
                    el.placeholder = m.group(1) if m.lastindex else ""
                elif prop_name == "style_color":
                    el.style["color"] = m.group(1) if m.lastindex else ""
                elif prop_name == "style_bg":
                    el.style["backgroundColor"] = m.group(1) if m.lastindex else ""
                elif prop_name == "style_fontSize":
                    el.style["fontSize"] = m.group(1) if m.lastindex else ""
                elif prop_name == "style_fontFamily":
                    el.style["fontFamily"] = m.group(1) if m.lastindex else ""
                elif prop_name == "required":
                    el.props["required"] = True
                elif prop_name == "maxLength":
                    el.props["maxLength"] = int(m.group(1)) if m.lastindex else 0
                elif prop_name == "keyboardType":
                    el.props["keyboardType"] = m.group(1) if m.lastindex else ""
