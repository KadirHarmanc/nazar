"""Hafif Taint Tracking - Kullanici girdisinden tehlikeli fonksiyona veri akisi tespiti.

Fonksiyon bazinda intra-procedural analiz yapar.
Source (girdi) + Sink (tehlikeli) ayni fonksiyonda = risk.

NOT: Bu dosya bir GUVENLIK TARAYICISIDIR. Tehlikeli fonksiyon isimleri
TESPIT EDILMEK UZERE listelenmistir, KULLANILMAMAKTADIR.
"""
import ast
import os
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from nazar.runners.base import BaseRunner, IGNORE_DIRS

# === SOURCES: Kullanici girdisi kaynagi ===
PYTHON_SOURCES = {
    "request.form", "request.args", "request.json", "request.data",
    "request.values", "request.headers", "request.cookies",
    "request.files", "request.get_json",
    "request.GET", "request.POST", "request.body",
    "request.META", "request.COOKIES", "request.FILES",
    "input", "sys.argv", "sys.stdin",
}

JS_SOURCES = {
    "req.body", "req.params", "req.query", "req.headers",
    "req.cookies", "req.files",
    "document.getElementById", "document.querySelector",
    "window.location", "location.search", "location.hash",
    "URLSearchParams", "formData",
    "useParams", "useSearchParams",
}

# === SINKS: Tehlikeli hedef (tespit amacli) ===
PYTHON_SINK_NAMES = {
    "execute", "executemany", "raw", "cursor.execute",
    "os.system", "os.popen",
    "subprocess.call", "subprocess.run",
    "subprocess.Popen", "subprocess.check_output",
    "eval", "exec", "compile",
    "open", "os.path.join",
    "pickle.loads", "yaml.load", "marshal.loads",
}

JS_SINK_NAMES = {
    "innerHTML", "outerHTML", "document.write",
    "dangerouslySetInnerHTML",
    "query", "execute", "raw",
    "eval", "Function",
    "writeFile", "writeFileSync", "createWriteStream",
    "redirect", "location.href",
}


class TaintTracker(BaseRunner):
    """Fonksiyon bazinda taint tracking analizi."""

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = {
            "sql_injection_taint": self._sql_injection_taint,
            "xss_taint": self._xss_taint,
            "command_injection_taint": self._command_injection_taint,
            "path_traversal_taint": self._path_traversal_taint,
            "general_taint": self._general_taint,
        }
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    def _python_files(self) -> List[str]:
        py_files = []
        for root_dir, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for f in files:
                if f.endswith(".py") and "test" not in f.lower():
                    rel = os.path.relpath(os.path.join(root_dir, f), self.root)
                    if not rel.startswith("nazar"):
                        py_files.append(rel)
        return py_files

    def _js_files(self) -> List[str]:
        js_exts = {".js", ".jsx", ".ts", ".tsx"}
        js_files = []
        for root_dir, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for f in files:
                if Path(f).suffix.lower() in js_exts and "test" not in f.lower() and "spec" not in f.lower():
                    rel = os.path.relpath(os.path.join(root_dir, f), self.root)
                    js_files.append(rel)
        return js_files

    def _analyze_python_function(self, func_node, filename: str) -> List[Dict]:
        findings = []
        tainted_vars: Set[str] = set()

        for node in ast.walk(func_node):
            if isinstance(node, ast.Attribute):
                attr_chain = self._get_attr_chain(node)
                if any(src in attr_chain for src in PYTHON_SOURCES):
                    parent = self._find_assign_target(func_node, node)
                    if parent:
                        tainted_vars.add(parent)
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "input":
                    parent = self._find_assign_target(func_node, node)
                    if parent:
                        tainted_vars.add(parent)

        for arg in func_node.args.args:
            if arg.arg in ("request", "req"):
                tainted_vars.add(arg.arg)

        if not tainted_vars:
            return findings

        for node in ast.walk(func_node):
            if not isinstance(node, ast.Call):
                continue
            sink_name = self._get_call_name(node)
            if not sink_name:
                continue
            is_sink = any(s in sink_name for s in PYTHON_SINK_NAMES)
            if not is_sink:
                continue

            for arg in node.args:
                arg_vars = self._extract_var_names(arg)
                tainted_in_args = tainted_vars & arg_vars
                if tainted_in_args:
                    findings.append({
                        "file": filename, "line": node.lineno,
                        "function": func_node.name,
                        "source_vars": list(tainted_in_args),
                        "sink": sink_name,
                        "risk": "Kullanici girdisi ({}) dogrudan {} hedefine gidiyor".format(
                            ", ".join(tainted_in_args), sink_name),
                    })
                    break

            for kw in node.keywords:
                if kw.value:
                    kw_vars = self._extract_var_names(kw.value)
                    tainted_in_kw = tainted_vars & kw_vars
                    if tainted_in_kw:
                        findings.append({
                            "file": filename, "line": node.lineno,
                            "function": func_node.name,
                            "source_vars": list(tainted_in_kw),
                            "sink": sink_name,
                            "risk": "Kullanici girdisi ({}) {} hedefine kw arg gidiyor".format(
                                ", ".join(tainted_in_kw), sink_name),
                        })
                        break
        return findings

    def _get_attr_chain(self, node: ast.Attribute) -> str:
        parts = [node.attr]
        current = node.value
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def _get_call_name(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return self._get_attr_chain(node.func)
        return None

    def _find_assign_target(self, func_node, value_node: ast.AST):
        for node in ast.walk(func_node):
            if isinstance(node, ast.Assign):
                if self._contains_node(node.value, value_node):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            return target.id
        return None

    def _contains_node(self, parent: ast.AST, target: ast.AST) -> bool:
        for child in ast.walk(parent):
            if child is target:
                return True
        return False

    def _extract_var_names(self, node: ast.AST) -> Set[str]:
        names = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                names.add(child.id)
        return names

    def _analyze_js_function(self, func_content: str, func_name: str, filename: str, start_line: int) -> List[Dict]:
        findings = []
        tainted_vars: Set[str] = set()

        for source in JS_SOURCES:
            pattern = r"(?:const|let|var)\s+(\w+)\s*=.*" + re.escape(source)
            for m in re.finditer(pattern, func_content):
                tainted_vars.add(m.group(1))

        if "req." in func_content:
            for m in re.finditer(r"req\.(?:body|params|query|headers)", func_content):
                tainted_vars.add("req")

        if not tainted_vars:
            return findings

        for sink in JS_SINK_NAMES:
            for m in re.finditer(re.escape(sink) + r"\s*[\(=]", func_content):
                line_num = func_content[:m.start()].count("\n") + start_line
                context = func_content[max(0, m.start() - 100):m.end() + 200]
                for var in tainted_vars:
                    if var in context:
                        findings.append({
                            "file": filename, "line": line_num,
                            "function": func_name,
                            "source_vars": [var], "sink": sink,
                            "risk": "Kullanici girdisi ({}) dogrudan {} hedefine gidiyor".format(var, sink),
                        })
                        break
        return findings

    def _run_python_taint(self, sink_filter: Set[str] = None) -> List[Dict]:
        all_findings = []
        for f in self._python_files()[:80]:
            try:
                content = self.read(f)
                if not content.strip():
                    continue
                tree = ast.parse(content, filename=f)
            except (SyntaxError, ValueError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    findings = self._analyze_python_function(node, f)
                    if sink_filter:
                        findings = [fd for fd in findings if any(s in fd["sink"] for s in sink_filter)]
                    all_findings.extend(findings)
        return all_findings

    def _run_js_taint(self, sink_filter: Set[str] = None) -> List[Dict]:
        all_findings = []
        func_pattern = r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(?[^)]*\)?\s*=>|(\w+)\s*\([^)]*\)\s*\{)"
        for f in self._js_files()[:80]:
            content = self.read(f)
            if not content.strip():
                continue
            for m in re.finditer(func_pattern, content):
                func_name = m.group(1) or m.group(2) or m.group(3) or "anonymous"
                start = m.start()
                start_line = content[:start].count("\n") + 1
                brace_count = 0
                end = start
                found_open = False
                for i in range(start, min(start + 5000, len(content))):
                    if content[i] == "{":
                        brace_count += 1
                        found_open = True
                    elif content[i] == "}":
                        brace_count -= 1
                    if found_open and brace_count == 0:
                        end = i + 1
                        break
                func_content = content[start:end]
                findings = self._analyze_js_function(func_content, func_name, f, start_line)
                if sink_filter:
                    findings = [fd for fd in findings if any(s in fd["sink"] for s in sink_filter)]
                all_findings.extend(findings)
        return all_findings

    def _format_findings(self, findings: List[Dict], risk_type: str) -> Tuple[bool, str]:
        if not findings:
            return True, "Temiz - taint tracking ile dogrulandi"
        first = findings[0]
        return False, "{} {} riski: {}:{} ({}.{} -> {})".format(
            len(findings), risk_type,
            first["file"], first["line"],
            first["function"], ", ".join(first["source_vars"]),
            first["sink"])

    def _sql_injection_taint(self, t: dict) -> Tuple[bool, str]:
        sql_sinks = {"execute", "executemany", "raw", "cursor.execute", "query"}
        py = self._run_python_taint(sql_sinks)
        js = self._run_js_taint(sql_sinks)
        return self._format_findings(py + js, "SQL injection")

    def _xss_taint(self, t: dict) -> Tuple[bool, str]:
        xss_sinks = {"innerHTML", "outerHTML", "document.write", "dangerouslySetInnerHTML"}
        js = self._run_js_taint(xss_sinks)
        return self._format_findings(js, "XSS")

    def _command_injection_taint(self, t: dict) -> Tuple[bool, str]:
        cmd_sinks = {"os.system", "os.popen", "subprocess.call", "subprocess.run", "subprocess.Popen"}
        py = self._run_python_taint(cmd_sinks)
        js = self._run_js_taint({"spawn"})
        return self._format_findings(py + js, "command injection")

    def _path_traversal_taint(self, t: dict) -> Tuple[bool, str]:
        path_sinks = {"open", "os.path.join", "writeFile", "writeFileSync", "createWriteStream"}
        py = self._run_python_taint(path_sinks)
        js = self._run_js_taint(path_sinks)
        return self._format_findings(py + js, "path traversal")

    def _general_taint(self, t: dict) -> Tuple[bool, str]:
        py = self._run_python_taint()
        js = self._run_js_taint()
        all_findings = py + js
        if not all_findings:
            return True, "Temiz - taint tracking ile dogrulandi"
        return False, "{} taint akisi: {}:{} ({} -> {})".format(
            len(all_findings),
            all_findings[0]["file"], all_findings[0]["line"],
            ", ".join(all_findings[0]["source_vars"]),
            all_findings[0]["sink"])
