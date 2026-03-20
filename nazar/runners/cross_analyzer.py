"""Cross-File Analyzer - Dosyalar arasi iliskileri analiz eder."""
import re
import os
from pathlib import Path
from typing import List, Dict, Tuple, Set

from nazar.runners.base import BaseRunner


class CrossFileAnalyzer(BaseRunner):
    """Tek dosya analizinin yakalamedigi, dosyalar arasi sorunlari bulur."""

    def check_unused_exports(self, t: dict) -> Tuple[bool, str]:
        """Export edilen ama hicbir yerde import edilmeyen fonksiyon/component."""
        exports = {}  # {name: file}
        imports = set()

        for f in self.src_files()[:200]:
            content = self.read(f)
            # Export'lari topla
            for m in re.finditer(r"export\s+(?:default\s+)?(?:function|class|const|let)\s+(\w+)", content):
                exports[m.group(1)] = f
            for m in re.finditer(r"export\s*\{([^}]+)\}", content):
                for name in m.group(1).split(","):
                    name = name.strip().split(" as ")[0].strip()
                    if name:
                        exports[name] = f
            # Import'lari topla
            for m in re.finditer(r"import\s+(?:\{[^}]*\}|\w+)\s+from", content):
                for name in re.findall(r"\b(\w+)\b", m.group()):
                    if name not in ("import", "from"):
                        imports.add(name)

        unused = {name: f for name, f in exports.items()
                  if name not in imports and not name.startswith("_") and name not in ("default", "App", "app")}

        if len(unused) > 10:
            first = list(unused.items())[0]
            return False, f"{len(unused)} export edilip kullanilmayan: {first[0]} in {first[1]}"
        return True, f"{len(unused)} kullanilmayan export" if unused else "Temiz"

    def check_duplicate_secrets(self, t: dict) -> Tuple[bool, str]:
        """Ayni secret/config degeri birden fazla dosyada tekrar ediyor."""
        values = {}  # {value_hash: [files]}
        pattern = r"""(?:api[_-]?key|secret|token|password)\s*[:=]\s*['"]([^'"]{10,})['"]"""

        for f in self.src_files()[:100]:
            if "test" in f.lower() or ".env" in f:
                continue
            content = self.read(f)
            for m in re.finditer(pattern, content, re.IGNORECASE):
                val = m.group(1)
                if val not in ("process.env", "os.environ"):
                    values.setdefault(val[:20], []).append(f)

        duplicates = {v: files for v, files in values.items() if len(set(files)) > 1}
        if duplicates:
            first_key = list(duplicates.keys())[0]
            first_files = duplicates[first_key]
            return False, f"{len(duplicates)} secret birden fazla dosyada: {', '.join(set(first_files)[:3])}"
        return True, "Temiz"

    def check_orphan_components(self, t: dict) -> Tuple[bool, str]:
        """Tanimlanmis ama hicbir yerde kullanilmayan component dosyalari."""
        component_files = []
        import_targets = set()

        for f in self.src_files()[:200]:
            # Component dosyalarini bul
            if any(x in f.lower() for x in ["component", "screen", "page", "view", "modal"]):
                component_files.append(f)

            # Import hedeflerini topla
            content = self.read(f)
            for m in re.finditer(r"""from\s+['"]([^'"]+)['"]""", content):
                import_targets.add(m.group(1))

        orphans = []
        for cf in component_files:
            basename = Path(cf).stem
            is_imported = any(basename in target for target in import_targets)
            if not is_imported and basename not in ("index", "App", "_layout", "layout"):
                orphans.append(cf)

        if len(orphans) > 3:
            return False, f"{len(orphans)} kullanilmayan component dosyasi: {orphans[0]}"
        return True, "Temiz"

    def check_env_var_mismatch(self, t: dict) -> Tuple[bool, str]:
        """Kodda kullanilan ama .env.example'da olmayan env variable'lar."""
        used_vars = set()
        for f in self.src_files()[:100]:
            content = self.read(f)
            used_vars.update(re.findall(r"process\.env\.(\w+)", content))
            used_vars.update(re.findall(r"os\.environ(?:\.get)?\(?['\"](\w+)", content))

        if not used_vars:
            return True, "Env var kullanilmiyor"

        documented_vars = set()
        for env_file in [".env.example", ".env.sample", ".env.template"]:
            content = self.read(env_file)
            if content:
                for line in content.splitlines():
                    if "=" in line and not line.strip().startswith("#"):
                        documented_vars.add(line.split("=")[0].strip())

        # Filter out common/obvious ones
        undocumented = used_vars - documented_vars - {"NODE_ENV", "HOME", "PATH", "USER"}
        if len(undocumented) > 3 and documented_vars:
            return False, f"{len(undocumented)} env var dokumante edilmemis: {', '.join(list(undocumented)[:5])}"
        return True, "Temiz"

    def check_circular_imports(self, t: dict) -> Tuple[bool, str]:
        """Dosyalar arasi dairesel import tespiti (derin)."""
        graph = {}
        for f in self.src_files()[:200]:
            content = self.read(f)
            imports = set()
            for m in re.finditer(r"""(?:import|from)\s+['"](\.[^'"]+)['"]""", content):
                imports.add(m.group(1))
            graph[f] = imports

        # DFS ile cycle bul
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            for imp in graph.get(node, []):
                # Resolve relative import
                resolved = None
                for candidate in graph:
                    if candidate.endswith(imp.lstrip("./") + ".ts") or candidate.endswith(imp.lstrip("./") + ".tsx") or candidate.endswith(imp.lstrip("./") + ".js"):
                        resolved = candidate
                        break
                if resolved:
                    if resolved in rec_stack:
                        cycles.append(f"{node} -> {resolved}")
                    elif resolved not in visited:
                        dfs(resolved, path + [node])
            rec_stack.discard(node)

        for node in graph:
            if node not in visited:
                dfs(node, [])

        if cycles:
            return False, f"{len(cycles)} dairesel import: {cycles[0]}"
        return True, "Temiz"

    def check_inconsistent_naming(self, t: dict) -> Tuple[bool, str]:
        """Dosya isimlendirme tutarsizligi (camelCase vs kebab-case vs snake_case)."""
        styles = {"camel": 0, "kebab": 0, "snake": 0, "pascal": 0}
        for f in self.src_files()[:200]:
            name = Path(f).stem
            if name.startswith("_") or name in ("index", "app", "main"):
                continue
            if "-" in name:
                styles["kebab"] += 1
            elif "_" in name:
                styles["snake"] += 1
            elif name[0].isupper():
                styles["pascal"] += 1
            elif any(c.isupper() for c in name[1:]):
                styles["camel"] += 1

        used_styles = {k: v for k, v in styles.items() if v > 0}
        if len(used_styles) > 2:
            detail = ", ".join(f"{k}:{v}" for k, v in sorted(used_styles.items(), key=lambda x: -x[1]))
            return False, f"Karisik dosya isimlendirme: {detail}"
        return True, "Tutarli"

    def check_api_auth_coverage(self, t: dict) -> Tuple[bool, str]:
        """API endpoint'lerinin auth middleware ile korunup korunmadigini kontrol et."""
        # Route tanimlari ve auth middleware'leri karsilastir
        routes_with_auth = 0
        routes_without_auth = 0

        for f in self.src_files()[:100]:
            content = self.read(f)
            lines = content.split("\n")
            for i, line in enumerate(lines):
                # Supabase edge function
                if "Deno.serve" in line or "serve(async" in line:
                    # Auth kontrolu var mi
                    fn_content = "\n".join(lines[max(0, i):min(len(lines), i+50)])
                    if "authorization" in fn_content.lower() or "getAuthUser" in fn_content or "auth" in fn_content.lower():
                        routes_with_auth += 1
                    else:
                        routes_without_auth += 1
                # Express/Fastify routes
                if re.search(r"(?:app|router)\.\s*(?:post|put|delete|patch)\s*\(", line):
                    context = "\n".join(lines[max(0, i-3):i+1])
                    if re.search(r"(?:auth|protect|guard|middleware|verify)", context, re.IGNORECASE):
                        routes_with_auth += 1
                    else:
                        routes_without_auth += 1

        if routes_without_auth > 0:
            total = routes_with_auth + routes_without_auth
            return False, f"{routes_without_auth}/{total} mutating route auth middleware eksik"
        return True, "Temiz"

    def get_all_checks(self) -> Dict[str, callable]:
        return {
            "unused_exports": self.check_unused_exports,
            "duplicate_secrets": self.check_duplicate_secrets,
            "orphan_components": self.check_orphan_components,
            "env_var_mismatch": self.check_env_var_mismatch,
            "circular_imports_deep": self.check_circular_imports,
            "inconsistent_naming": self.check_inconsistent_naming,
            "api_auth_coverage": self.check_api_auth_coverage,
        }

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = self.get_all_checks()
        fn = checks.get(subtype)
        return fn(test) if fn else (True, "SKIP")
