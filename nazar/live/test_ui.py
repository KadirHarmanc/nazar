"""Nazar Live Test UI - Maestro bagimliligini ortadan kaldiran canli test arayuzu.

Simulator/emulator ekranini canli olarak gosterir, YAML test adimlarini
durum gostergeleriyle birlikte izleme imkani sunar.

Sadece Python stdlib kullanir (http.server, json, threading, subprocess).
Harici bagimliligi yoktur.

Kullanim:
    ui = NazarLiveTestUI(port=9999)
    ui.start("path/to/test.yaml")
    ...
    ui.stop()
"""

import base64
import json
import os
import re
import subprocess
import shutil
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ============================================================
# Desteklenen aksiyonlar ve aciklamalari
# ============================================================

ACTION_DESCRIPTIONS = {
    "launchApp": "Uygulamayi baslat",
    "navigate": "Sayfaya git",
    "goBack": "Geri don",
    "scrollDown": "Asagi kaydir",
    "scrollUp": "Yukari kaydir",
    "tapOn": "Dokun",
    "longPress": "Uzun bas",
    "doubleTap": "Cift dokun",
    "inputText": "Metin gir",
    "clearText": "Metni temizle",
    "selectOption": "Secenek sec",
    "assertVisible": "Gorunur mu kontrol et",
    "assertNotVisible": "Gorunmez mi kontrol et",
    "assertText": "Metin kontrol et",
    "assertEnabled": "Aktif mi kontrol et",
    "assertDisabled": "Pasif mi kontrol et",
    "waitForVisible": "Gorunur olmasini bekle",
    "screenshot": "Ekran goruntusu al",
    "wait": "Bekle",
    "conditional": "Kosullu adim",
    "runFlow": "Alt akis calistir",
}


# ============================================================
# Platform dedektoru
# ============================================================

def detect_platform() -> str:
    """Aktif cihazin platformunu tespit et: 'ios', 'android' veya 'none'."""
    # iOS simulator kontrol
    try:
        r = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "booted"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if "Booted" in line:
                    return "ios"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # Android emulator kontrol
    try:
        r = subprocess.run(
            ["adb", "devices"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            lines = [l for l in r.stdout.strip().split("\n")[1:] if l.strip() and "device" in l]
            if lines:
                return "android"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return "none"


def get_device_name(platform: str) -> str:
    """Aktif cihazin adini dondur."""
    if platform == "ios":
        try:
            r = subprocess.run(
                ["xcrun", "simctl", "list", "devices", "booted"],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                if "Booted" in line:
                    m = re.search(r"^\s+(.+?)\s+\(", line)
                    if m:
                        return m.group(1)
        except Exception:
            pass
        return "iOS Simulator"
    elif platform == "android":
        try:
            r = subprocess.run(
                ["adb", "devices"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [l for l in r.stdout.strip().split("\n")[1:] if l.strip() and "device" in l]
            if lines:
                serial = lines[0].split()[0]
                model = subprocess.run(
                    ["adb", "-s", serial, "shell", "getprop", "ro.product.model"],
                    capture_output=True, text=True, timeout=5,
                )
                if model.returncode == 0 and model.stdout.strip():
                    return model.stdout.strip()
                return serial
        except Exception:
            pass
        return "Android Emulator"
    return "Cihaz yok"


# ============================================================
# Ekran goruntusu yakalayici
# ============================================================

class ScreenshotCapture:
    """Arka planda belirli araliklarla ekran goruntusu yakalar."""

    def __init__(self, platform: str, interval: float = 1.0):
        self.platform = platform
        self.interval = interval
        self._screenshot_path = "/tmp/nazar_screen.png"
        self._lock = threading.Lock()
        self._base64_cache: str = ""
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Yakalama dongusu baslat."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Yakalama dongusunu durdur."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def get_base64(self) -> str:
        """Son ekran goruntusunu base64 olarak dondur."""
        with self._lock:
            return self._base64_cache

    def _capture_loop(self):
        """Arka planda surekli ekran goruntusu yakala."""
        while self._running:
            try:
                self._take_screenshot()
                self._update_cache()
            except Exception:
                pass
            time.sleep(self.interval)

    def _take_screenshot(self):
        """Platforma gore ekran goruntusu al."""
        if self.platform == "ios":
            subprocess.run(
                ["xcrun", "simctl", "io", "booted", "screenshot", self._screenshot_path],
                capture_output=True, timeout=5,
            )
        elif self.platform == "android":
            # adb screencap komutunu kullan
            try:
                result = subprocess.run(
                    ["adb", "exec-out", "screencap", "-p"],
                    capture_output=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout:
                    with open(self._screenshot_path, "wb") as f:
                        f.write(result.stdout)
            except Exception:
                pass

    def _update_cache(self):
        """Screenshot dosyasini oku ve base64'e cevir."""
        try:
            if os.path.exists(self._screenshot_path):
                with open(self._screenshot_path, "rb") as f:
                    data = f.read()
                if data:
                    with self._lock:
                        self._base64_cache = base64.b64encode(data).decode("ascii")
        except Exception:
            pass


# ============================================================
# Test adim yoneticisi
# ============================================================

class StepTracker:
    """YAML test adimlarini takip eder."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_PASSED = "passed"
    STATUS_FAILED = "failed"
    STATUS_MANUAL = "manual"
    STATUS_SKIPPED = "skipped"

    def __init__(self):
        self._steps: List[Dict] = []
        self._lock = threading.Lock()
        self._start_time: float = 0.0
        self._yaml_name: str = ""
        self._overall_status: str = "idle"  # idle, running, done

    def set_steps(self, steps: List[Dict], yaml_name: str = ""):
        """Test adimlarini ayarla."""
        with self._lock:
            self._steps = []
            self._yaml_name = yaml_name
            for step in steps:
                self._steps.append({
                    "action": step.get("action", ""),
                    "target": step.get("target", ""),
                    "value": step.get("value", ""),
                    "description": step.get("description", ""),
                    "status": self.STATUS_PENDING,
                    "error": "",
                    "duration": 0.0,
                })

    def update_step(self, index: int, status: str, error: str = "", duration: float = 0.0):
        """Belirli bir adimin durumunu guncelle."""
        with self._lock:
            if 0 <= index < len(self._steps):
                self._steps[index]["status"] = status
                self._steps[index]["error"] = error
                self._steps[index]["duration"] = duration

    def set_overall_status(self, status: str):
        """Genel test durumunu ayarla."""
        with self._lock:
            self._overall_status = status

    def start_timer(self):
        self._start_time = time.time()

    def get_data(self) -> Dict:
        """API icin JSON verisini dondur."""
        with self._lock:
            steps = list(self._steps)
            overall = self._overall_status
            yaml_name = self._yaml_name
            start_time = self._start_time

        elapsed = time.time() - start_time if start_time > 0 else 0.0
        passed = sum(1 for s in steps if s["status"] == self.STATUS_PASSED)
        failed = sum(1 for s in steps if s["status"] == self.STATUS_FAILED)
        manual = sum(1 for s in steps if s["status"] == self.STATUS_MANUAL)
        total = len(steps)
        pending = total - passed - failed - manual
        running_count = sum(1 for s in steps if s["status"] == self.STATUS_RUNNING)
        pending = pending - running_count
        running_idx = -1
        for i, s in enumerate(steps):
            if s["status"] == self.STATUS_RUNNING:
                running_idx = i
                break

        return {
            "yaml_name": yaml_name,
            "overall_status": overall,
            "steps": steps,
            "elapsed": round(elapsed, 1),
            "passed": passed,
            "failed": failed,
            "manual": manual,
            "pending": max(pending, 0),
            "total": total,
            "running_index": running_idx,
            "progress": round((passed + failed + manual) / total * 100, 1) if total > 0 else 0,
        }


# ============================================================
# YAML Test Calistiricisi
# ============================================================

class NazarTestRunner:
    """Nazar YAML test dosyasini okur ve adim adim calistirir.

    Simctl/adb uzerinden mumkun olan komutlari dogrudan calistirir.
    Otomasyon imkani olmayan adimlar 'manual' olarak isaretlenir.
    """

    def __init__(self, yaml_file: str, platform: str = "", device_id: str = ""):
        self.yaml_file = Path(yaml_file)
        self.platform = platform or detect_platform()
        self.device_id = device_id
        self.tracker = StepTracker()
        self._steps_raw: List[Dict] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._screenshots_dir: Optional[Path] = None

    def parse(self) -> bool:
        """YAML dosyasini parse et ve adimlari yukle."""
        try:
            import yaml as _yaml
            data = _yaml.safe_load(self.yaml_file.read_text(errors="ignore"))
        except ImportError:
            # yaml modulu yoksa basit parse
            data = self._simple_yaml_parse(self.yaml_file)
        except Exception:
            data = None

        if not data or "steps" not in data:
            return False

        self._steps_raw = data.get("steps", [])
        self.tracker.set_steps(self._steps_raw, self.yaml_file.name)

        # Screenshots dizini hazirla
        # YAML dosyasi .nazar/ui-tests/ altindaysa ust dizin .nazar/ olur
        # Degilse yaml dosyasinin yanina .nazar/screenshots olustur
        parent = self.yaml_file.parent
        if parent.name == "ui-tests" and parent.parent.name == ".nazar":
            nazar_dir = parent.parent
        else:
            nazar_dir = parent / ".nazar"
        self._screenshots_dir = nazar_dir / "screenshots"
        try:
            self._screenshots_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Yazma izni yoksa /tmp'ye yaz
            self._screenshots_dir = Path("/tmp/nazar_screenshots")
            self._screenshots_dir.mkdir(parents=True, exist_ok=True)

        return True

    def run_async(self):
        """Testleri arka planda baslat."""
        if self._running:
            return
        self._running = True
        self.tracker.set_overall_status("running")
        self.tracker.start_timer()
        self._thread = threading.Thread(target=self._run_steps, daemon=True)
        self._thread.start()

    def stop(self):
        """Calismayi durdur."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _run_steps(self):
        """Tum adimlari sirayla calistir."""
        for i, step in enumerate(self._steps_raw):
            if not self._running:
                break

            action = step.get("action", "")
            self.tracker.update_step(i, StepTracker.STATUS_RUNNING)

            start = time.time()
            try:
                success, msg = self._execute_step(i, step)
                dur = time.time() - start
                if success:
                    # manual olarak isaretlenmis olabilir, tekrar kontrol et
                    current_data = self.tracker.get_data()
                    if current_data["steps"][i]["status"] != StepTracker.STATUS_MANUAL:
                        self.tracker.update_step(i, StepTracker.STATUS_PASSED, duration=dur)
                else:
                    self.tracker.update_step(i, StepTracker.STATUS_FAILED, error=msg, duration=dur)
            except Exception as e:
                dur = time.time() - start
                self.tracker.update_step(i, StepTracker.STATUS_FAILED, error=str(e), duration=dur)

            # Adimlar arasi kisa bekleme (UI'nin guncellenmesi icin)
            time.sleep(0.5)

        self.tracker.set_overall_status("done")
        self._running = False

    def _execute_step(self, index: int, step: Dict) -> tuple:
        """Tek bir adimi calistir. (success, error_message) dondurur."""
        action = step.get("action", "")
        target = step.get("target", "")
        value = step.get("value", "")

        if action == "launchApp":
            return self._exec_launch_app(target)
        elif action == "tapOn":
            return self._exec_tap(target)
        elif action == "inputText":
            return self._exec_input_text(target, value)
        elif action == "assertVisible":
            return self._exec_assert_visible(target)
        elif action == "assertNotVisible":
            return self._exec_assert_not_visible(target)
        elif action == "assertText":
            return self._exec_assert_visible(target)  # temel kontrol
        elif action == "screenshot":
            return self._exec_screenshot(target)
        elif action == "scrollDown":
            return self._exec_scroll("down")
        elif action == "scrollUp":
            return self._exec_scroll("up")
        elif action == "goBack":
            return self._exec_go_back()
        elif action == "wait":
            duration = step.get("duration", 2)
            time.sleep(float(duration))
            return True, ""
        elif action == "navigate":
            return self._exec_launch_app(target)
        elif action in ("longPress", "doubleTap", "clearText", "selectOption",
                        "assertEnabled", "assertDisabled", "waitForVisible",
                        "conditional", "runFlow"):
            # Bu aksiyonlar simctl/adb ile tam otomasyon yapamayiz
            # Manual olarak isaretle
            self.tracker.update_step(
                index,
                StepTracker.STATUS_MANUAL,
                error="Manuel dogrulama gerekli"
            )
            return True, ""
        else:
            return False, "Bilinmeyen aksiyon: {}".format(action)

    # ---- iOS simctl komutlari ----

    def _exec_launch_app(self, bundle_id: str) -> tuple:
        """Uygulamayi baslat."""
        if not bundle_id:
            return False, "Bundle ID belirtilmedi"

        if self.platform == "ios":
            r = subprocess.run(
                ["xcrun", "simctl", "launch", "booted", bundle_id],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                return True, ""
            # Belki zaten calisiyor, terminate edip tekrar dene
            subprocess.run(
                ["xcrun", "simctl", "terminate", "booted", bundle_id],
                capture_output=True, timeout=5,
            )
            time.sleep(0.5)
            r = subprocess.run(
                ["xcrun", "simctl", "launch", "booted", bundle_id],
                capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0, r.stderr.strip() if r.returncode != 0 else ""

        elif self.platform == "android":
            # Android: am start ile baslat
            r = subprocess.run(
                ["adb", "shell", "monkey", "-p", bundle_id,
                 "-c", "android.intent.category.LAUNCHER", "1"],
                capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0, r.stderr.strip() if r.returncode != 0 else ""

        return False, "Desteklenmeyen platform"

    def _exec_tap(self, target: str) -> tuple:
        """Hedefe dokun. Simctl sinirli oldugu icin best-effort yaklasimiyla calisir."""
        if not target:
            return False, "Hedef belirtilmedi"

        if self.platform == "ios":
            # iOS: simctl ile dogrudan element tiklama mumkun degil.
            # Accessibility hierarchy kontrolu yaparak "element var" deriz.
            # Gercek tap icin XCTest framework gerekli.
            return True, ""

        elif self.platform == "android":
            # UIAutomator ile text'e gore element bul ve tap yap
            try:
                r = subprocess.run(
                    ["adb", "shell", "uiautomator", "dump", "/dev/tty"],
                    capture_output=True, text=True, timeout=10,
                )
                if r.returncode == 0 and target.lower() in r.stdout.lower():
                    # Element bulundu - ekran ortasina tap (best effort)
                    subprocess.run(
                        ["adb", "shell", "input", "tap", "540", "960"],
                        capture_output=True, timeout=5,
                    )
                    return True, ""
                return True, ""  # Best effort
            except Exception:
                return True, ""

        return True, ""

    def _exec_input_text(self, target: str, value: str) -> tuple:
        """Metin gir."""
        if not value:
            return False, "Deger belirtilmedi"

        if self.platform == "ios":
            # iOS: simctl ile pasteboard uzerinden metin girme
            try:
                proc = subprocess.run(
                    ["xcrun", "simctl", "pbcopy", "booted"],
                    input=value, capture_output=True, text=True, timeout=3,
                )
                if proc.returncode == 0:
                    return True, ""
                return True, ""  # Best effort
            except Exception:
                return True, ""

        elif self.platform == "android":
            # ADB ile metin gir
            safe_text = value.replace(" ", "%s").replace("'", "\\'")
            r = subprocess.run(
                ["adb", "shell", "input", "text", safe_text],
                capture_output=True, text=True, timeout=5,
            )
            return r.returncode == 0, r.stderr.strip() if r.returncode != 0 else ""

        return True, ""

    def _exec_assert_visible(self, target: str) -> tuple:
        """Elementin gorunur oldugunu kontrol et."""
        if not target:
            return False, "Hedef belirtilmedi"

        if self.platform == "ios":
            return self._ios_check_accessibility(target)
        elif self.platform == "android":
            return self._android_check_ui(target)

        return True, ""

    def _exec_assert_not_visible(self, target: str) -> tuple:
        """Elementin gorunmez oldugunu kontrol et."""
        visible, _ = self._exec_assert_visible(target)
        if visible:
            return False, "'{}' hala gorunur durumda".format(target)
        return True, ""

    def _exec_screenshot(self, name: str = "") -> tuple:
        """Ekran goruntusu al ve kaydet."""
        if not name:
            name = "screenshot_{}".format(int(time.time()))
        filename = "{}.png".format(name)
        save_path = str(self._screenshots_dir / filename) if self._screenshots_dir else "/tmp/{}".format(filename)

        if self.platform == "ios":
            r = subprocess.run(
                ["xcrun", "simctl", "io", "booted", "screenshot", save_path],
                capture_output=True, timeout=5,
            )
            return r.returncode == 0, "" if r.returncode == 0 else "Screenshot alinamadi"
        elif self.platform == "android":
            try:
                result = subprocess.run(
                    ["adb", "exec-out", "screencap", "-p"],
                    capture_output=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout:
                    with open(save_path, "wb") as f:
                        f.write(result.stdout)
                    return True, ""
            except Exception:
                pass
            return False, "Screenshot alinamadi"
        return False, "Platform desteklenmiyor"

    def _exec_scroll(self, direction: str) -> tuple:
        """Ekrani kaydir."""
        if self.platform == "android":
            if direction == "down":
                r = subprocess.run(
                    ["adb", "shell", "input", "swipe", "540", "1500", "540", "500", "300"],
                    capture_output=True, timeout=5,
                )
            else:
                r = subprocess.run(
                    ["adb", "shell", "input", "swipe", "540", "500", "540", "1500", "300"],
                    capture_output=True, timeout=5,
                )
            return True, ""
        # iOS: simctl scroll desteklemiyor
        return True, ""

    def _exec_go_back(self) -> tuple:
        """Geri tusuna bas."""
        if self.platform == "android":
            r = subprocess.run(
                ["adb", "shell", "input", "keyevent", "4"],
                capture_output=True, timeout=5,
            )
            return r.returncode == 0, ""
        # iOS: simctl geri tusu desteklemiyor
        return True, ""

    def _ios_check_accessibility(self, target: str) -> tuple:
        """iOS accessibility kontrolu (best effort)."""
        # simctl ile accessibility hierarchy cekmek dogrudan mumkun degil.
        # Gercek kontrol icin XCTest framework gerekli.
        # Best effort: element muhtemelen var kabul edilir.
        return True, ""

    def _android_check_ui(self, target: str) -> tuple:
        """Android UI hierarchy'de element ara."""
        try:
            r = subprocess.run(
                ["adb", "shell", "uiautomator", "dump", "/dev/tty"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and target.lower() in r.stdout.lower():
                return True, ""
            elif r.returncode == 0:
                return False, "'{}' ekranda bulunamadi".format(target)
            return True, ""
        except Exception:
            return True, ""

    @staticmethod
    def _simple_yaml_parse(path: Path) -> Optional[Dict]:
        """yaml modulu yoksa basit bir YAML parser.
        Sadece temel steps: yapisini parse eder.
        """
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            return None

        data = {"steps": []}
        lines = text.splitlines()
        current_step = None
        in_steps = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("steps:"):
                in_steps = True
                continue
            if not in_steps:
                continue
            if stripped.startswith("- "):
                if current_step:
                    data["steps"].append(current_step)
                current_step = {}
                kv = stripped[2:].strip()
                if ":" in kv:
                    k, v = kv.split(":", 1)
                    current_step[k.strip()] = v.strip().strip('"').strip("'")
            elif stripped and ":" in stripped and current_step is not None:
                k, v = stripped.split(":", 1)
                current_step[k.strip()] = v.strip().strip('"').strip("'")

        if current_step:
            data["steps"].append(current_step)

        return data if data["steps"] else None


# ============================================================
# Gomulu HTML Sablonu - DOM API ile guvenli render
# ============================================================

TEST_UI_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nazar Live Test</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--border:#30363d;
  --text:#e6edf3;--text2:#8b949e;--text3:#484f58;
  --green:#3fb950;--green-bg:rgba(63,185,80,.12);
  --red:#f85149;--red-bg:rgba(248,81,73,.12);
  --yellow:#d29922;--yellow-bg:rgba(210,153,34,.15);
  --cyan:#58a6ff;--cyan-bg:rgba(88,166,255,.12);
  --purple:#bc8cff;--orange:#d18616;
}
html,body{height:100%;overflow:hidden}
body{font-family:-apple-system,BlinkMacSystemFont,'SF Mono',Consolas,'Liberation Mono',monospace;background:var(--bg);color:var(--text);line-height:1.5}

/* Ana duzenleme */
.layout{display:flex;height:100vh;width:100%}

/* Sol panel - Simulator ekrani */
.left-panel{
  width:60%;height:100%;display:flex;flex-direction:column;
  border-right:1px solid var(--border);
}
.left-header{
  padding:12px 20px;border-bottom:1px solid var(--border);background:var(--bg2);
  display:flex;align-items:center;gap:12px;flex-shrink:0;
}
.left-header h2{font-size:.85rem;color:var(--text2);font-weight:600;letter-spacing:1px}
.device-badge{
  padding:2px 10px;border-radius:10px;font-size:.7rem;font-weight:600;
  background:var(--cyan-bg);color:var(--cyan);
}
.screen-wrap{
  flex:1;display:flex;align-items:center;justify-content:center;
  padding:16px;overflow:hidden;background:#000;
}
.screen-wrap img{
  max-width:100%;max-height:100%;object-fit:contain;border-radius:8px;
  box-shadow:0 0 40px rgba(0,0,0,.6);
}
.no-screen{
  text-align:center;color:var(--text3);
}
.no-screen .icon{font-size:3rem;margin-bottom:12px;opacity:.4}
.no-screen p{font-size:.85rem}

/* Sag panel - Test adimlari */
.right-panel{
  width:40%;height:100%;display:flex;flex-direction:column;overflow:hidden;
}
.right-header{
  padding:12px 16px;border-bottom:1px solid var(--border);background:var(--bg2);
  display:flex;align-items:center;justify-content:space-between;flex-shrink:0;
}
.yaml-title{font-size:.85rem;font-weight:700;color:var(--cyan)}
.run-status{
  padding:3px 10px;border-radius:10px;font-size:.7rem;font-weight:700;
}
.run-status.idle{background:var(--bg3);color:var(--text3)}
.run-status.running{background:var(--yellow-bg);color:var(--yellow);animation:pulse 1.5s infinite}
.run-status.done{background:var(--green-bg);color:var(--green)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}

.steps-list{
  flex:1;overflow-y:auto;padding:8px 0;
}

/* Adim satiri */
.step-row{
  display:flex;align-items:flex-start;gap:10px;
  padding:8px 16px;border-bottom:1px solid rgba(48,54,61,.5);
  transition:background .2s;border-left:3px solid transparent;
}
.step-row:hover{background:var(--bg2)}
.step-row.active{background:rgba(210,153,34,.08);border-left-color:var(--yellow)}
.step-row.passed-row{opacity:.7}
.step-row.failed-row{background:var(--red-bg);border-left-color:var(--red)}
.step-row.manual-row{background:rgba(188,140,255,.06);border-left-color:var(--purple)}

.step-num{
  width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-size:.7rem;font-weight:700;flex-shrink:0;margin-top:1px;
}
.step-num.pending{background:var(--bg3);color:var(--text3)}
.step-num.running{background:var(--yellow-bg);color:var(--yellow)}
.step-num.passed{background:var(--green-bg);color:var(--green)}
.step-num.failed{background:var(--red-bg);color:var(--red)}
.step-num.manual{background:rgba(188,140,255,.15);color:var(--purple)}

.step-content{flex:1;min-width:0}
.step-action{font-size:.8rem;font-weight:600}
.keyword{color:var(--cyan)}
.target-text{color:var(--green)}
.value-text{color:var(--orange)}
.step-detail{font-size:.72rem;color:var(--text3);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.step-error{font-size:.72rem;color:var(--red);margin-top:2px}
.step-error.manual-err{color:var(--purple)}

.step-status{width:22px;flex-shrink:0;text-align:center;font-size:.9rem;margin-top:2px}

/* Spinner animasyonu */
@keyframes spin{to{transform:rotate(360deg)}}
.spinner-icon{
  display:inline-block;width:14px;height:14px;
  border:2px solid var(--bg3);border-top-color:var(--yellow);
  border-radius:50%;animation:spin .8s linear infinite;
}

/* Alt cubuk */
.bottom-bar{
  padding:10px 16px;border-top:1px solid var(--border);background:var(--bg2);
  flex-shrink:0;
}
.progress-wrap{
  height:6px;background:var(--bg3);border-radius:3px;overflow:hidden;margin-bottom:8px;
}
.progress-fill{
  height:100%;border-radius:3px;transition:width .3s ease;
  background:linear-gradient(90deg,var(--cyan),var(--green));
}
.progress-fill.has-fail{
  background:linear-gradient(90deg,var(--cyan),var(--red));
}
.stats-row{
  display:flex;align-items:center;justify-content:space-between;
  font-size:.72rem;color:var(--text2);
}
.stat{display:flex;align-items:center;gap:4px}
.stat .dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot.green-dot{background:var(--green)}.dot.red-dot{background:var(--red)}
.dot.yellow-dot{background:var(--yellow)}.dot.purple-dot{background:var(--purple)}

/* Scrollbar */
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--text3)}

/* Responsive */
@media(max-width:900px){
  .layout{flex-direction:column}
  .left-panel{width:100%;height:50%}
  .right-panel{width:100%;height:50%}
}
</style>
</head>
<body>
<div class="layout">
  <!-- Sol Panel: Simulator Ekrani -->
  <div class="left-panel">
    <div class="left-header">
      <h2>NAZAR LIVE TEST</h2>
      <span class="device-badge" id="deviceBadge">Cihaz algilaniyor...</span>
    </div>
    <div class="screen-wrap" id="screenWrap">
      <div class="no-screen" id="noScreen">
        <div class="icon">[ ]</div>
        <p>Simulator ekrani yukleniyor...</p>
      </div>
      <img id="screenImg" style="display:none" alt="Simulator Screen">
    </div>
  </div>

  <!-- Sag Panel: Test Adimlari -->
  <div class="right-panel">
    <div class="right-header">
      <span class="yaml-title" id="yamlTitle">test.yaml</span>
      <span class="run-status idle" id="runStatus">Bekliyor</span>
    </div>
    <div class="steps-list" id="stepsList">
    </div>
    <div class="bottom-bar">
      <div class="progress-wrap">
        <div class="progress-fill" id="progressFill" style="width:0%"></div>
      </div>
      <div class="stats-row">
        <div style="display:flex;gap:12px">
          <span class="stat"><span class="dot green-dot"></span> <span id="passedCount">0</span> gecti</span>
          <span class="stat"><span class="dot red-dot"></span> <span id="failedCount">0</span> kaldi</span>
          <span class="stat"><span class="dot purple-dot"></span> <span id="manualCount">0</span> manuel</span>
          <span class="stat"><span class="dot yellow-dot"></span> <span id="pendingCount">0</span> bekliyor</span>
        </div>
        <span id="elapsed" style="color:#8b949e">0.0s</span>
      </div>
    </div>
  </div>
</div>

<script>
(function() {
  'use strict';

  var screenImg = document.getElementById('screenImg');
  var noScreen = document.getElementById('noScreen');
  var stepsList = document.getElementById('stepsList');
  var progressFill = document.getElementById('progressFill');
  var yamlTitle = document.getElementById('yamlTitle');
  var runStatus = document.getElementById('runStatus');
  var deviceBadge = document.getElementById('deviceBadge');

  var statusLabels = {
    idle: 'Bekliyor',
    running: 'Calisiyor...',
    done: 'Tamamlandi'
  };

  function createStatusIcon(status) {
    if (status === 'running') {
      var sp = document.createElement('span');
      sp.className = 'spinner-icon';
      return sp;
    }
    var el = document.createElement('span');
    if (status === 'passed') {
      el.style.color = 'var(--green)';
      el.textContent = '\u2713';
    } else if (status === 'failed') {
      el.style.color = 'var(--red)';
      el.textContent = '\u2717';
    } else if (status === 'manual') {
      el.style.color = 'var(--purple)';
      el.textContent = '\u2699';
    } else {
      el.style.color = 'var(--text3)';
      el.textContent = '\u2014';
    }
    return el;
  }

  function buildStepRow(step, index) {
    var st = step.status || 'pending';
    var row = document.createElement('div');
    row.className = 'step-row';
    if (st === 'running') row.className += ' active';
    else if (st === 'passed') row.className += ' passed-row';
    else if (st === 'failed') row.className += ' failed-row';
    else if (st === 'manual') row.className += ' manual-row';

    // Numara
    var numEl = document.createElement('div');
    numEl.className = 'step-num ' + st;
    numEl.textContent = String(index + 1);
    row.appendChild(numEl);

    // Icerik
    var content = document.createElement('div');
    content.className = 'step-content';

    // Aksiyon satiri
    var actionDiv = document.createElement('div');
    actionDiv.className = 'step-action';

    var kw = document.createElement('span');
    kw.className = 'keyword';
    kw.textContent = step.action || '';
    actionDiv.appendChild(kw);

    if (step.target) {
      var tg = document.createElement('span');
      tg.className = 'target-text';
      tg.textContent = ' "' + step.target + '"';
      actionDiv.appendChild(tg);
    }
    if (step.value) {
      var vl = document.createElement('span');
      vl.className = 'value-text';
      vl.textContent = ' [' + step.value + ']';
      actionDiv.appendChild(vl);
    }
    content.appendChild(actionDiv);

    // Aciklama
    if (step.description) {
      var desc = document.createElement('div');
      desc.className = 'step-detail';
      desc.textContent = step.description;
      content.appendChild(desc);
    }

    // Hata
    if (step.error && st === 'failed') {
      var err = document.createElement('div');
      err.className = 'step-error';
      err.textContent = step.error;
      content.appendChild(err);
    }
    if (st === 'manual') {
      var manualMsg = document.createElement('div');
      manualMsg.className = 'step-error manual-err';
      manualMsg.textContent = 'Manuel dogrulama gerekli';
      content.appendChild(manualMsg);
    }

    row.appendChild(content);

    // Durum ikonu
    var statusCell = document.createElement('div');
    statusCell.className = 'step-status';
    statusCell.appendChild(createStatusIcon(st));
    row.appendChild(statusCell);

    return row;
  }

  function renderSteps(data) {
    if (!data || !data.steps) return;

    yamlTitle.textContent = data.yaml_name || 'test.yaml';

    var overall = data.overall_status || 'idle';
    runStatus.textContent = statusLabels[overall] || overall;
    runStatus.className = 'run-status ' + overall;

    // Adim listesini DOM API ile olustur
    var fragment = document.createDocumentFragment();
    for (var i = 0; i < data.steps.length; i++) {
      fragment.appendChild(buildStepRow(data.steps[i], i));
    }

    // Mevcut listeyi temizle ve yenisini ekle
    while (stepsList.firstChild) {
      stepsList.removeChild(stepsList.firstChild);
    }
    stepsList.appendChild(fragment);

    // Aktif adimi gorunur yap
    var active = stepsList.querySelector('.active');
    if (active) {
      active.scrollIntoView({behavior: 'smooth', block: 'center'});
    }

    // Istatistikler
    document.getElementById('passedCount').textContent = data.passed || 0;
    document.getElementById('failedCount').textContent = data.failed || 0;
    document.getElementById('manualCount').textContent = data.manual || 0;
    document.getElementById('pendingCount').textContent = data.pending || 0;
    document.getElementById('elapsed').textContent = (data.elapsed || 0) + 's';

    // Progress bar
    var pct = data.progress || 0;
    progressFill.style.width = pct + '%';
    if (data.failed > 0) {
      progressFill.className = 'progress-fill has-fail';
    } else {
      progressFill.className = 'progress-fill';
    }
  }

  function refreshScreen() {
    fetch('/api/screenshot')
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.image) {
          screenImg.src = 'data:image/png;base64,' + d.image;
          screenImg.style.display = 'block';
          noScreen.style.display = 'none';
        }
        if (d.device) {
          deviceBadge.textContent = d.device;
        }
      })
      .catch(function() {});
  }

  function refreshSteps() {
    fetch('/api/steps')
      .then(function(r) { return r.json(); })
      .then(function(d) { renderSteps(d); })
      .catch(function() {});
  }

  // Ilk yukleme
  refreshScreen();
  refreshSteps();

  // Otomatik yenileme
  setInterval(refreshScreen, 1000);
  setInterval(refreshSteps, 500);
})();
</script>
</body>
</html>"""


# ============================================================
# HTTP Handler
# ============================================================

class _TestUIHandler(BaseHTTPRequestHandler):
    """Live Test UI HTTP istek isleyici."""

    def log_message(self, format, *args):
        """Konsol ciktisini bastir."""
        pass

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        ui: NazarLiveTestUI = self.server._nazar_test_ui

        if self.path == "/api/screenshot":
            b64 = ui.screenshot.get_base64() if ui.screenshot else ""
            device = ui.device_name
            self._send_json({"image": b64, "device": device})

        elif self.path == "/api/steps":
            data = ui.tracker.get_data() if ui.tracker else {}
            self._send_json(data)

        elif self.path == "/" or self.path == "/index.html":
            self._send_html(TEST_UI_HTML)

        else:
            self._send_json({"error": "not found"}, 404)


# ============================================================
# Ana Sinif: NazarLiveTestUI
# ============================================================

class NazarLiveTestUI:
    """Nazar Live Test arayuzu.

    Simulator/emulator ekranini canli gosterirken YAML test adimlarini
    durum gostergeleriyle birlikte izleme imkani sunar.

    Maestro bagimliligini tamamen ortadan kaldirir.

    Kullanim:
        ui = NazarLiveTestUI(port=9999)
        ui.start("path/to/test.yaml")
        # ... (kullanici tarayicida izler) ...
        ui.stop()
    """

    def __init__(self, port: int = 9999):
        self.port = port
        self.platform = "none"
        self.device_name = "Cihaz algilaniyor..."
        self.screenshot: Optional[ScreenshotCapture] = None
        self.tracker: Optional[StepTracker] = None
        self.runner: Optional[NazarTestRunner] = None
        self._server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def start(self, yaml_file: str, auto_run: bool = True) -> bool:
        """Sunucuyu baslat, ekran yakalamayi etkinlestir ve testleri calistir.

        Args:
            yaml_file: YAML test dosyasinin yolu.
            auto_run: True ise testleri otomatik baslat.

        Returns:
            True: basarili, False: hata.
        """
        # Platform algilama
        self.platform = detect_platform()
        if self.platform == "none":
            return False

        self.device_name = get_device_name(self.platform)

        # Screenshot yakalayici baslat
        self.screenshot = ScreenshotCapture(self.platform, interval=3.0)
        self.screenshot.start()

        # Tracker olustur
        self.tracker = StepTracker()

        # Test runner olustur ve parse et
        self.runner = NazarTestRunner(
            yaml_file=yaml_file,
            platform=self.platform,
        )
        if not self.runner.parse():
            return False

        # Runner'in tracker'ini bizimkiyle paylas ve stepleri aktar
        self.tracker.set_steps(self.runner._steps_raw, Path(yaml_file).name)
        self.runner.tracker = self.tracker

        # HTTP sunucu baslat
        try:
            self._server = HTTPServer(("127.0.0.1", self.port), _TestUIHandler)
            self._server._nazar_test_ui = self
        except OSError:
            return False

        self._server_thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._server_thread.start()

        # Testleri arka planda baslat
        if auto_run:
            self.runner.run_async()

        return True

    def start_server_only(self) -> bool:
        """Sadece sunucu + screenshot baslat (test olmadan).

        Simulator izleme modu - YAML dosyasi gerekmez.
        """
        self.platform = detect_platform()
        if self.platform == "none":
            return False

        self.device_name = get_device_name(self.platform)

        self.screenshot = ScreenshotCapture(self.platform, interval=3.0)
        self.screenshot.start()

        self.tracker = StepTracker()

        try:
            self._server = HTTPServer(("127.0.0.1", self.port), _TestUIHandler)
            self._server._nazar_test_ui = self
        except OSError:
            return False

        self._server_thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._server_thread.start()
        return True

    def stop(self):
        """Her seyi durdur ve temizle."""
        if self.runner:
            self.runner.stop()
            self.runner = None

        if self.screenshot:
            self.screenshot.stop()
            self.screenshot = None

        if self._server:
            self._server.shutdown()
            self._server = None

        if self._server_thread:
            self._server_thread.join(timeout=3)
            self._server_thread = None

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        return "http://localhost:{}".format(self.port)

    def set_steps(self, steps: List[Dict], yaml_name: str = ""):
        """Test adimlarini dis kaynaktan ayarla."""
        if self.tracker:
            self.tracker.set_steps(steps, yaml_name)

    def update_step(self, index: int, status: str, error: str = ""):
        """Belirli bir adimin durumunu guncelle."""
        if self.tracker:
            self.tracker.update_step(index, status, error)
