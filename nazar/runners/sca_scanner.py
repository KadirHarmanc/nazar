"""SCA Scanner - Software Composition Analysis (Snyk benzeri)."""
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from nazar.runners.base import BaseRunner

# Bilinen typosquatting paketleri (npm + pypi)
KNOWN_TYPOSQUATS = {
    # npm
    "crossenv": "cross-env",
    "cross-env.js": "cross-env",
    "d3.js": "d3",
    "fabric-js": "fabric",
    "ffmepg": "ffmpeg",
    "gruntcli": "grunt-cli",
    "http-proxy.js": "http-proxy",
    "jquery.js": "jquery",
    "mariadb": "mariasql",
    "mongose": "mongoose",
    "mssql.js": "mssql",
    "mssql-node": "mssql",
    "mysqljs": "mysql",
    "node-hierarchical-softmax": "node-hs",
    "node-opencv": "opencv",
    "node-opensl": "openssl",
    "node-openssl": "openssl",
    "nodecaffe": "node-caffe",
    "nodefabric": "fabric",
    "nodemailer-js": "nodemailer",
    "noderequest": "request",
    "nodesass": "node-sass",
    "nodesqlite": "sqlite3",
    "opencv.js": "opencv",
    "openssl.js": "openssl",
    "proxy.js": "proxy",
    "shadowsock": "shadowsocks",
    "smb": "samba",
    "sqliter": "sqlite3",
    "sqlserver": "mssql",
    "tkinter": "Tkinter",
    # pypi
    "colourama": "colorama",
    "dateutil": "python-dateutil",
    "djago": "django",
    "djanga": "django",
    "easyinstall": "setuptools",
    "free-net-vpn": "protonvpn-cli",
    "jeIlyfish": "jellyfish",
    "libpeshka": "python-chess",
    "maratlib": "maratlib",
    "noblesse": "noblesse",
    "openvc": "opencv-python",
    "pyaborern": "pyautogui",
    "pycrypto": "pycryptodome",
    "pygane": "pygame",
    "pyinstaler": "pyinstaller",
    "pyqt-5": "pyqt5",
    "python-binance": "python-binance",
    "python3-dateutil": "python-dateutil",
    "reqeusts": "requests",
    "resuests": "requests",
    "setuptool": "setuptools",
    "urllib": "urllib3",
}

# GPL ailesi lisanslari
GPL_LICENSES = {"GPL", "GPL-2.0", "GPL-3.0", "AGPL", "AGPL-3.0", "LGPL", "LGPL-2.1", "LGPL-3.0", "GPL-2.0-only", "GPL-3.0-only", "AGPL-3.0-only"}

# Deprecated paketler (bilinen)
DEPRECATED_NPM = {
    "request": "axios veya node-fetch kullanin",
    "node-uuid": "uuid paketine gecin",
    "nomnom": "commander veya yargs kullanin",
    "colors": "chalk kullanin",
    "istanbul": "nyc kullanin",
    "jade": "pug kullanin",
    "tslint": "eslint + @typescript-eslint kullanin",
    "node-sass": "sass (dart-sass) kullanin",
    "left-pad": "String.padStart() kullanin",
    "moment": "dayjs veya date-fns kullanin",
    "enzyme": "React Testing Library kullanin",
    "react-native-cli": "@react-native-community/cli kullanin",
    "popper.js": "@popperjs/core kullanin",
    "uglify-js": "terser kullanin",
    "querystring": "URLSearchParams kullanin (Node.js built-in)",
}

DEPRECATED_PIP = {
    "pycrypto": "pycryptodome kullanin",
    "distribute": "setuptools kullanin",
    "nose": "pytest kullanin",
    "optparse": "argparse kullanin (stdlib)",
    "imp": "importlib kullanin (stdlib)",
    "pipes": "subprocess kullanin",
    "formatter": "kaldirin (Python 3.10+ deprecated)",
}


class SCAScanner(BaseRunner):
    """Software Composition Analysis - Dependency guvenlik taramasi."""

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = {
            "npm_audit": self._npm_audit,
            "pip_audit": self._pip_audit,
            "go_vulncheck": self._go_vulncheck,
            "outdated_packages": self._outdated_packages,
            "license_compatibility": self._license_compatibility,
            "deprecated_packages": self._deprecated_packages,
            "typosquatting": self._typosquatting,
        }
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    def _npm_audit(self, t: dict) -> Tuple[bool, str]:
        """npm audit ile guvenlik acigi taramasi."""
        pkg = self.root / "package.json"
        if not pkg.exists():
            return True, "package.json yok, SKIP"
        lock = self.root / "package-lock.json"
        if not lock.exists():
            return True, "package-lock.json yok, npm audit atlandi"
        try:
            r = subprocess.run(
                ["npm", "audit", "--json"],
                capture_output=True, text=True,
                cwd=str(self.root), timeout=20,
            )
            data = json.loads(r.stdout)
            vulns = data.get("metadata", {}).get("vulnerabilities", {})
            critical = vulns.get("critical", 0)
            high = vulns.get("high", 0)
            moderate = vulns.get("moderate", 0)
            total = critical + high + moderate
            if critical > 0 or high > 0:
                return False, f"critical:{critical} high:{high} moderate:{moderate} - npm audit fix --force"
            if moderate > 0:
                return True, f"moderate:{moderate} (kabul edilebilir)"
            return True, f"Temiz - {vulns.get('total', 0)} paket tarandi"
        except FileNotFoundError:
            return True, "npm bulunamadi, SKIP"
        except subprocess.TimeoutExpired:
            return True, "npm audit timeout, SKIP"
        except (json.JSONDecodeError, KeyError):
            return True, "npm audit parse hatasi, SKIP"

    def _pip_audit(self, t: dict) -> Tuple[bool, str]:
        """pip-audit veya safety ile Python dependency taramasi."""
        reqs = self.root / "requirements.txt"
        pyproject = self.root / "pyproject.toml"
        pipfile = self.root / "Pipfile"
        if not (reqs.exists() or pyproject.exists() or pipfile.exists()):
            return True, "Python dependency dosyasi yok, SKIP"
        # pip-audit dene
        try:
            r = subprocess.run(
                ["pip-audit", "--format", "json", "-r", "requirements.txt"]
                if reqs.exists()
                else ["pip-audit", "--format", "json"],
                capture_output=True, text=True,
                cwd=str(self.root), timeout=30,
            )
            data = json.loads(r.stdout) if r.stdout.strip() else []
            if isinstance(data, list) and len(data) > 0:
                critical = [v for v in data if v.get("fix_versions")]
                return False, f"{len(data)} guvenlik acigi: {data[0].get('name', '?')} ({data[0].get('id', '?')})"
            return True, "Temiz - pip-audit ile tarandi"
        except FileNotFoundError:
            pass
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        # safety dene
        try:
            r = subprocess.run(
                ["safety", "check", "--json"],
                capture_output=True, text=True,
                cwd=str(self.root), timeout=20,
            )
            if r.returncode != 0 and r.stdout:
                data = json.loads(r.stdout)
                vulns = data if isinstance(data, list) else data.get("vulnerabilities", [])
                if vulns:
                    return False, f"{len(vulns)} guvenlik acigi bulundu"
            return True, "Temiz - safety ile tarandi"
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        # Fallback: requirements.txt'deki pinlenmemis paketleri kontrol et
        if reqs.exists():
            lines = reqs.read_text(errors="ignore").strip().split("\n")
            unpinned = [l.strip() for l in lines if l.strip() and not l.startswith("#") and "==" not in l and ">=" not in l]
            if unpinned:
                return True, f"pip-audit/safety yok, {len(unpinned)} pinlenmemis paket"
        return True, "pip-audit/safety bulunamadi, SKIP"

    def _go_vulncheck(self, t: dict) -> Tuple[bool, str]:
        """Go modulleri icin govulncheck."""
        gomod = self.root / "go.mod"
        if not gomod.exists():
            return True, "go.mod yok, SKIP"
        try:
            r = subprocess.run(
                ["govulncheck", "./..."],
                capture_output=True, text=True,
                cwd=str(self.root), timeout=30,
            )
            if "Vulnerability" in r.stdout or "found" in r.stdout.lower():
                lines = r.stdout.strip().split("\n")
                vuln_lines = [l for l in lines if "GO-" in l or "CVE-" in l]
                count = len(vuln_lines) or 1
                first = vuln_lines[0].strip() if vuln_lines else "Detay icin govulncheck ./... calistirin"
                return False, f"{count} guvenlik acigi: {first[:80]}"
            return True, "Temiz - govulncheck ile tarandi"
        except FileNotFoundError:
            return True, "govulncheck bulunamadi, SKIP"
        except subprocess.TimeoutExpired:
            return True, "govulncheck timeout, SKIP"

    def _outdated_packages(self, t: dict) -> Tuple[bool, str]:
        """Major versiyon gerideleri tespit et."""
        pkg = self.root / "package.json"
        if pkg.exists():
            return self._npm_outdated()
        reqs = self.root / "requirements.txt"
        if reqs.exists():
            return self._pip_outdated()
        gomod = self.root / "go.mod"
        if gomod.exists():
            return True, "Go modulleri icin go list -m -u kullanin"
        return True, "Dependency dosyasi yok, SKIP"

    def _npm_outdated(self) -> Tuple[bool, str]:
        try:
            r = subprocess.run(
                ["npm", "outdated", "--json"],
                capture_output=True, text=True,
                cwd=str(self.root), timeout=20,
            )
            data = json.loads(r.stdout) if r.stdout.strip() else {}
            major_outdated = []
            for name, info in data.items():
                current = info.get("current", "")
                latest = info.get("latest", "")
                if current and latest:
                    cur_major = current.split(".")[0] if "." in current else current
                    lat_major = latest.split(".")[0] if "." in latest else latest
                    try:
                        if int(lat_major) > int(cur_major):
                            major_outdated.append(f"{name} {current}->{latest}")
                    except ValueError:
                        pass
            if major_outdated:
                return False, f"{len(major_outdated)} major geride: {major_outdated[0]}"
            return True, f"Temiz - paketler guncel"
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return True, "npm outdated calistirilamadi, SKIP"

    def _pip_outdated(self) -> Tuple[bool, str]:
        try:
            r = subprocess.run(
                ["pip", "list", "--outdated", "--format", "json"],
                capture_output=True, text=True, timeout=20,
            )
            data = json.loads(r.stdout) if r.stdout.strip() else []
            major_outdated = []
            for pkg in data:
                current = pkg.get("version", "")
                latest = pkg.get("latest_version", "")
                if current and latest:
                    cur_major = current.split(".")[0]
                    lat_major = latest.split(".")[0]
                    try:
                        if int(lat_major) > int(cur_major):
                            major_outdated.append(f"{pkg['name']} {current}->{latest}")
                    except ValueError:
                        pass
            if major_outdated:
                return False, f"{len(major_outdated)} major geride: {major_outdated[0]}"
            return True, "Temiz - paketler guncel"
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return True, "pip list calistirilamadi, SKIP"

    def _license_compatibility(self, t: dict) -> Tuple[bool, str]:
        """GPL dependency MIT projede kontrolu."""
        pkg = self.root / "package.json"
        if not pkg.exists():
            return True, "package.json yok, SKIP"
        try:
            pkg_data = json.loads(pkg.read_text(errors="ignore"))
        except json.JSONDecodeError:
            return True, "package.json parse hatasi, SKIP"
        project_license = pkg_data.get("license", "").upper()
        if any(g in project_license for g in GPL_LICENSES):
            return True, "Proje zaten GPL, uyumluluk sorunu yok"
        # node_modules'daki GPL paketleri kontrol et
        nm = self.root / "node_modules"
        if not nm.exists():
            return True, "node_modules yok, SKIP"
        gpl_pkgs = []
        deps = list(pkg_data.get("dependencies", {}).keys()) + list(pkg_data.get("devDependencies", {}).keys())
        for dep in deps[:100]:
            dep_pkg = nm / dep / "package.json"
            if dep_pkg.exists():
                try:
                    dep_data = json.loads(dep_pkg.read_text(errors="ignore"))
                    dep_license = dep_data.get("license", "")
                    if isinstance(dep_license, dict):
                        dep_license = dep_license.get("type", "")
                    dep_license_upper = dep_license.upper()
                    if any(g in dep_license_upper for g in GPL_LICENSES) and "LGPL" not in dep_license_upper:
                        gpl_pkgs.append(f"{dep} ({dep_license})")
                except (json.JSONDecodeError, OSError):
                    pass
        if gpl_pkgs:
            return False, f"{len(gpl_pkgs)} GPL dependency: {gpl_pkgs[0]}"
        return True, "Lisans uyumlulugu temiz"

    def _deprecated_packages(self, t: dict) -> Tuple[bool, str]:
        """Deprecated paket tespiti."""
        found = []
        # npm
        pkg = self.root / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(errors="ignore"))
                all_deps = list(data.get("dependencies", {}).keys()) + list(data.get("devDependencies", {}).keys())
                for dep in all_deps:
                    if dep in DEPRECATED_NPM:
                        found.append(f"{dep} -> {DEPRECATED_NPM[dep]}")
            except json.JSONDecodeError:
                pass
        # pip
        reqs = self.root / "requirements.txt"
        if reqs.exists():
            lines = reqs.read_text(errors="ignore").strip().split("\n")
            for line in lines:
                name = re.split(r"[=<>!~]", line.strip())[0].strip().lower()
                if name in DEPRECATED_PIP:
                    found.append(f"{name} -> {DEPRECATED_PIP[name]}")
        if found:
            return False, f"{len(found)} deprecated: {found[0]}"
        return True, "Deprecated paket yok"

    def _typosquatting(self, t: dict) -> Tuple[bool, str]:
        """Bilinen typosquatting paket tespiti."""
        suspect = []
        # npm
        pkg = self.root / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(errors="ignore"))
                all_deps = list(data.get("dependencies", {}).keys()) + list(data.get("devDependencies", {}).keys())
                for dep in all_deps:
                    if dep.lower() in KNOWN_TYPOSQUATS:
                        suspect.append(f"{dep} (gercek: {KNOWN_TYPOSQUATS[dep.lower()]})")
            except json.JSONDecodeError:
                pass
        # pip
        reqs = self.root / "requirements.txt"
        if reqs.exists():
            lines = reqs.read_text(errors="ignore").strip().split("\n")
            for line in lines:
                name = re.split(r"[=<>!~]", line.strip())[0].strip().lower()
                if name in KNOWN_TYPOSQUATS:
                    suspect.append(f"{name} (gercek: {KNOWN_TYPOSQUATS[name]})")
        if suspect:
            return False, f"TEHLIKE: {len(suspect)} suphe: {suspect[0]}"
        return True, "Typosquatting yok"
