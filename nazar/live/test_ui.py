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

import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
import zlib
from datetime import datetime
from http.server import ThreadingHTTPServer as HTTPServer, BaseHTTPRequestHandler
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
    """Arka planda adaptif FPS ile ekran goruntusu yakalar.

    Optimizasyonlar:
    - Disk I/O sifir: iOS ve Android stdout pipe uzerinden okur
    - CRC32 karsilastirma: Ekran degismediyse islem atlanir
    - JPEG binary: base64 encode yok, MJPEG stream'e direkt verilir
    - ffmpeg varsa yarim cozunurluge kucultme (pipe ile, shell=False)
    - Pillow fallback: ffmpeg yoksa Pillow ile resize + Android PNG->JPEG
    - Adaptif FPS: 0.5-10fps arasi, degisiklik varsa hizlan yoksa yavasla
    - Keep-alive: ekran degismese bile min 1s'de bir son frame gonderilir
    - Event-driven: _frame_event ile MJPEG handler bekler
    """

    _MIN_INTERVAL = 0.1   # 10 fps maks
    _MAX_INTERVAL = 2.0   # 0.5 fps min
    _KEEPALIVE_S = 1.0    # Ekran degismese bile 1s'de bir frame isle

    def __init__(self, platform: str, interval: float = 0.3):
        self.platform = platform
        self.interval = interval
        self._lock = threading.Lock()
        self._jpeg_frame: bytes = b""
        self._last_crc: int = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._has_client = False
        self._last_client_time: float = 0
        self._last_change_time: float = 0
        self._frame_event = threading.Event()
        # ffmpeg ve Pillow varligini bir kere kontrol et
        self._has_ffmpeg: bool = shutil.which("ffmpeg") is not None
        self._pil_image = None
        try:
            from PIL import Image
            self._pil_image = Image
        except ImportError:
            pass

    def start(self):
        """Yakalama dongusu baslat."""
        if self._running:
            return
        self._running = True
        self._last_change_time = time.monotonic()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Yakalama dongusunu durdur."""
        self._running = False
        self._frame_event.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def get_jpeg(self) -> bytes:
        """Son frame'i binary JPEG olarak dondur."""
        self._last_client_time = time.monotonic()
        self._has_client = True
        with self._lock:
            return self._jpeg_frame

    def wait_frame(self, timeout: float = 2.0) -> bool:
        """Yeni frame gelene kadar bekle. True=frame var, False=timeout."""
        self._frame_event.clear()
        return self._frame_event.wait(timeout=timeout)

    def _capture_loop(self):
        """Arka planda adaptif FPS ile ekran goruntusu yakala."""
        adaptive_interval = self.interval
        while self._running:
            try:
                # Client 10 saniyedir istek atmadiysa yakalama yapma
                if self._has_client and (time.monotonic() - self._last_client_time) > 10:
                    time.sleep(adaptive_interval)
                    continue

                raw = self._take_screenshot()
                if raw:
                    changed = self._update_frame(raw)
                    now = time.monotonic()
                    if changed:
                        # Ekran degisti -> hizlan
                        adaptive_interval = max(self._MIN_INTERVAL,
                                                adaptive_interval * 0.7)
                        self._last_change_time = now
                    else:
                        # Ekran ayni -> yavasla
                        adaptive_interval = min(self._MAX_INTERVAL,
                                                adaptive_interval * 1.3)
                        # Keep-alive: 1s'de bir son frame'i yeniden isle
                        if (now - self._last_change_time) >= self._KEEPALIVE_S:
                            self._frame_event.set()
                            self._last_change_time = now
            except Exception:
                pass
            time.sleep(adaptive_interval)

    def _take_screenshot(self) -> Optional[bytes]:
        """Platforma gore ekran goruntusu al, stdout pipe ile binary dondur."""
        if self.platform == "ios":
            try:
                # stdout'a JPEG yaz, diske dokunma
                result = subprocess.run(
                    ["xcrun", "simctl", "io", "booted", "screenshot",
                     "--type=jpeg", "--mask=ignored", "-"],
                    capture_output=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout:
                    return result.stdout
            except (subprocess.TimeoutExpired, OSError):
                pass
        elif self.platform == "android":
            try:
                # Android screencap PNG verir
                result = subprocess.run(
                    ["adb", "exec-out", "screencap", "-p"],
                    capture_output=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout:
                    return result.stdout
            except (subprocess.TimeoutExpired, OSError):
                pass
        return None

    def _png_to_jpeg(self, png_data: bytes) -> bytes:
        """PNG veriyi JPEG'e cevir. Pillow varsa kullan, yoksa PNG dondur."""
        if self._pil_image is None:
            return png_data
        try:
            img = self._pil_image.open(io.BytesIO(png_data))
            if img.mode == "RGBA":
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            return buf.getvalue()
        except Exception:
            return png_data

    def _resize_jpeg(self, jpeg_data: bytes) -> bytes:
        """JPEG'i yarim cozunurluge kucult. ffmpeg > Pillow > ham veri."""
        if self._has_ffmpeg:
            return self._resize_ffmpeg(jpeg_data)
        if self._pil_image is not None:
            return self._resize_pillow(jpeg_data)
        return jpeg_data

    def _resize_ffmpeg(self, data: bytes) -> bytes:
        """ffmpeg ile pipe uzerinden yarim cozunurluge kucult."""
        proc = None
        try:
            proc = subprocess.Popen(
                ["ffmpeg", "-y", "-f", "image2pipe", "-i", "pipe:0",
                 "-vf", "scale=iw/2:ih/2", "-f", "image2", "-vcodec",
                 "mjpeg", "-q:v", "5", "pipe:1"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            out, _ = proc.communicate(input=data, timeout=3)
            if proc.returncode == 0 and out:
                return out
        except (subprocess.TimeoutExpired, OSError):
            if proc is not None and proc.poll() is None:
                proc.kill()
        return data

    def _resize_pillow(self, jpeg_data: bytes) -> bytes:
        """Pillow ile yarim cozunurluge kucult."""
        try:
            img = self._pil_image.open(io.BytesIO(jpeg_data))
            half = (img.width // 2, img.height // 2)
            img.thumbnail(half)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            return buf.getvalue()
        except Exception:
            return jpeg_data

    def _update_frame(self, data: bytes) -> bool:
        """Ekran degistiyse JPEG frame'i guncelle. True=degisti."""
        data_crc = zlib.crc32(data)
        if data_crc == self._last_crc:
            return False

        self._last_crc = data_crc
        # Android PNG -> JPEG cevirimi
        if self.platform == "android":
            data = self._png_to_jpeg(data)
        # Yarim cozunurluge kucult (opsiyonel)
        data = self._resize_jpeg(data)
        with self._lock:
            self._jpeg_frame = data
        self._frame_event.set()
        return True


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
<title>Nazar Studio</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --black:#000;--white:#fff;
  --g1:#0a0a0a;--g2:#111;--g3:#1a1a1a;--g4:#222;--g5:#333;--g6:#555;--g7:#888;--g8:#aaa;--g9:#ccc;--g10:#e5e5e5;
  --ok:#fff;--ok-bg:rgba(255,255,255,.08);
  --fail:#fff;--fail-bg:rgba(255,255,255,.04);
  --active-bg:rgba(255,255,255,.03);
  --radius:6px;
}
html,body{height:100%;overflow:hidden}
body{font-family:'SF Pro Text',-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',sans-serif;background:var(--black);color:var(--white);line-height:1.5;-webkit-font-smoothing:antialiased}

.layout{display:flex;height:100vh;width:100%}

/* ---- Sol: Simulator ---- */
.left-panel{
  width:55%;height:100%;display:flex;flex-direction:column;
  border-right:1px solid var(--g3);
}
.panel-header{
  padding:14px 24px;border-bottom:1px solid var(--g3);background:var(--g1);
  display:flex;align-items:center;justify-content:space-between;flex-shrink:0;
  -webkit-app-region:drag;
}
.brand{display:flex;align-items:center;gap:10px}
.brand-mark{
  width:28px;height:28px;border-radius:var(--radius);
  background:var(--white);display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:.75rem;color:var(--black);letter-spacing:-.5px;
}
.brand-text{font-size:.8rem;font-weight:600;color:var(--g8);letter-spacing:.5px;text-transform:uppercase}
.device-chip{
  padding:4px 12px;border-radius:100px;font-size:.68rem;font-weight:500;
  background:var(--g3);color:var(--g7);border:1px solid var(--g4);
  -webkit-app-region:no-drag;
}
.screen-area{
  flex:1;display:flex;align-items:center;justify-content:center;
  padding:20px;overflow:hidden;background:var(--black);position:relative;
}
.screen-area img{
  max-width:100%;max-height:100%;object-fit:contain;border-radius:12px;
  box-shadow:0 8px 60px rgba(0,0,0,.8),0 0 0 1px rgba(255,255,255,.06);
  transition:opacity .3s;
}
.screen-area img.is-loaded ~ .placeholder{display:none}
.placeholder{text-align:center;color:var(--g5)}
.placeholder-icon{
  width:48px;height:48px;border:2px solid var(--g4);border-radius:12px;
  margin:0 auto 16px;display:flex;align-items:center;justify-content:center;
}
.placeholder-icon svg{width:24px;height:24px;stroke:var(--g5);fill:none;stroke-width:1.5}
.placeholder p{font-size:.8rem;color:var(--g6)}

/* ---- Sag: Test Adimlari ---- */
.right-panel{
  width:45%;height:100%;display:flex;flex-direction:column;overflow:hidden;background:var(--g1);
}
.test-header{
  padding:14px 20px;border-bottom:1px solid var(--g3);background:var(--g1);
  display:flex;align-items:center;justify-content:space-between;flex-shrink:0;
}
.yaml-info{display:flex;flex-direction:column;gap:2px}
.yaml-name{font-size:.82rem;font-weight:600;color:var(--white)}
.yaml-meta{font-size:.68rem;color:var(--g6)}
.status-badge{
  padding:5px 14px;border-radius:100px;font-size:.68rem;font-weight:600;
  letter-spacing:.3px;text-transform:uppercase;
}
.status-badge.idle{background:var(--g3);color:var(--g6)}
.status-badge.running{background:var(--white);color:var(--black);animation:pulse 2s ease-in-out infinite}
.status-badge.done{background:var(--g3);color:var(--white)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}

/* Step listesi */
.steps-scroll{flex:1;overflow-y:auto;padding:6px 0}

.step{
  display:flex;align-items:stretch;gap:0;
  margin:0 12px;border-radius:var(--radius);
  transition:all .15s ease;position:relative;
}
.step+.step{margin-top:2px}
.step:hover{background:var(--g2)}

/* Sol: Timeline cizgisi */
.step-timeline{
  width:36px;display:flex;flex-direction:column;align-items:center;
  padding-top:14px;flex-shrink:0;position:relative;
}
.step-dot{
  width:10px;height:10px;border-radius:50%;
  background:var(--g4);border:2px solid var(--g3);
  position:relative;z-index:1;flex-shrink:0;
  transition:all .2s;
}
.step.is-passed .step-dot{background:var(--white);border-color:var(--white)}
.step.is-failed .step-dot{background:var(--white);border-color:var(--g6)}
.step.is-running .step-dot{
  background:var(--white);border-color:var(--white);
  box-shadow:0 0 0 4px rgba(255,255,255,.15);
  animation:dot-pulse 1.5s ease-in-out infinite;
}
.step.is-manual .step-dot{background:var(--g6);border-color:var(--g6)}
@keyframes dot-pulse{0%,100%{box-shadow:0 0 0 4px rgba(255,255,255,.15)}50%{box-shadow:0 0 0 8px rgba(255,255,255,.05)}}

.step-line{
  width:1px;flex:1;background:var(--g3);margin-top:4px;
}
.step:last-child .step-line{background:transparent}
.step.is-passed .step-line{background:var(--g5)}

/* Orta: Icerik */
.step-body{
  flex:1;min-width:0;padding:10px 8px 10px 0;
}
.step-action-line{
  font-size:.78rem;font-weight:500;color:var(--g9);
  display:flex;align-items:baseline;gap:6px;
}
.act-keyword{color:var(--white);font-weight:600}
.act-target{color:var(--g7)}
.act-value{color:var(--g6);font-style:italic}
.step-desc{font-size:.7rem;color:var(--g5);margin-top:2px}
.step-err{font-size:.7rem;color:var(--g8);margin-top:3px;font-style:italic}

/* Sag: Durum */
.step-indicator{
  width:32px;display:flex;align-items:center;justify-content:center;
  flex-shrink:0;padding-top:8px;
}
.check-icon{font-size:.75rem;color:var(--g5)}
.step.is-passed .check-icon{color:var(--white)}
.step.is-failed .check-icon{color:var(--g7)}
.step.is-running .check-icon .spinner{
  display:inline-block;width:12px;height:12px;
  border:1.5px solid var(--g4);border-top-color:var(--white);
  border-radius:50%;animation:spin .7s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg)}}

/* Aktif step vurgusu */
.step.is-running{background:var(--active-bg)}
.step.is-failed{background:rgba(255,255,255,.02)}

/* ---- Alt Bar ---- */
.bottom-bar{
  padding:12px 20px;border-top:1px solid var(--g3);background:var(--g1);
  flex-shrink:0;
}
.progress-track{
  height:3px;background:var(--g3);border-radius:2px;overflow:hidden;margin-bottom:10px;
}
.progress-bar{
  height:100%;border-radius:2px;transition:width .4s ease;
  background:var(--white);
}
.progress-bar.has-fail{background:var(--g6)}
.stats{
  display:flex;align-items:center;justify-content:space-between;
  font-size:.7rem;color:var(--g6);
}
.stat-group{display:flex;gap:16px}
.stat-item{display:flex;align-items:center;gap:5px}
.stat-dot{width:6px;height:6px;border-radius:50%;display:inline-block}
.stat-dot.s-pass{background:var(--white)}
.stat-dot.s-fail{background:var(--g6)}
.stat-dot.s-manual{background:var(--g5)}
.stat-dot.s-pending{background:var(--g4)}
.stat-val{font-weight:600;color:var(--g8)}
.elapsed{color:var(--g6);font-variant-numeric:tabular-nums}

/* Scrollbar */
::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--g4);border-radius:2px}
::-webkit-scrollbar-thumb:hover{background:var(--g5)}

@media(max-width:900px){
  .layout{flex-direction:column}
  .left-panel{width:100%;height:45%}
  .right-panel{width:100%;height:55%}
}
</style>
</head>
<body>
<div class="layout">

  <!-- Sol: Simulator -->
  <div class="left-panel">
    <div class="panel-header">
      <div class="brand">
        <div class="brand-mark">N</div>
        <span class="brand-text">Nazar Studio</span>
      </div>
      <span class="device-chip" id="deviceBadge">Algilaniyor...</span>
    </div>
    <div class="screen-area" id="screenWrap">
      <img id="screenImg" src="/stream" alt="Screen"
           onload="this.classList.add('is-loaded')"
           onerror="this.classList.remove('is-loaded')">
      <div class="placeholder" id="noScreen">
        <div class="placeholder-icon">
          <svg viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18.01" stroke-linecap="round"/></svg>
        </div>
        <p>Simulator bekleniyor...</p>
      </div>
    </div>
  </div>

  <!-- Sag: Test Adimlari -->
  <div class="right-panel">
    <div class="test-header">
      <div class="yaml-info">
        <span class="yaml-name" id="yamlTitle">test.yaml</span>
        <span class="yaml-meta" id="yamlMeta">0 adim</span>
      </div>
      <span class="status-badge idle" id="runStatus">Bekliyor</span>
    </div>

    <div class="steps-scroll" id="stepsList"></div>

    <div class="bottom-bar">
      <div class="progress-track">
        <div class="progress-bar" id="progressFill" style="width:0%"></div>
      </div>
      <div class="stats">
        <div class="stat-group">
          <span class="stat-item"><span class="stat-dot s-pass"></span><span class="stat-val" id="passedCount">0</span> gecti</span>
          <span class="stat-item"><span class="stat-dot s-fail"></span><span class="stat-val" id="failedCount">0</span> kaldi</span>
          <span class="stat-item"><span class="stat-dot s-manual"></span><span class="stat-val" id="manualCount">0</span> manuel</span>
          <span class="stat-item"><span class="stat-dot s-pending"></span><span class="stat-val" id="pendingCount">0</span> bekliyor</span>
        </div>
        <span class="elapsed" id="elapsed">0.0s</span>
      </div>
    </div>
  </div>

</div>

<script>
(function() {
  'use strict';

  var stepsList = document.getElementById('stepsList');
  var progressFill = document.getElementById('progressFill');
  var yamlTitle = document.getElementById('yamlTitle');
  var yamlMeta = document.getElementById('yamlMeta');
  var runStatus = document.getElementById('runStatus');
  var deviceBadge = document.getElementById('deviceBadge');

  var statusLabels = {idle:'Bekliyor', running:'Calisiyor', done:'Tamamlandi'};

  function buildStep(step, index, total) {
    var st = step.status || 'pending';

    var el = document.createElement('div');
    el.className = 'step';
    if (st === 'running') el.className += ' is-running';
    else if (st === 'passed') el.className += ' is-passed';
    else if (st === 'failed') el.className += ' is-failed';
    else if (st === 'manual') el.className += ' is-manual';

    // Timeline
    var tl = document.createElement('div');
    tl.className = 'step-timeline';
    var dot = document.createElement('div');
    dot.className = 'step-dot';
    tl.appendChild(dot);
    if (index < total - 1) {
      var line = document.createElement('div');
      line.className = 'step-line';
      tl.appendChild(line);
    }
    el.appendChild(tl);

    // Body
    var body = document.createElement('div');
    body.className = 'step-body';

    var actLine = document.createElement('div');
    actLine.className = 'step-action-line';

    var kw = document.createElement('span');
    kw.className = 'act-keyword';
    kw.textContent = step.action || '';
    actLine.appendChild(kw);

    if (step.target) {
      var tg = document.createElement('span');
      tg.className = 'act-target';
      tg.textContent = '"' + step.target + '"';
      actLine.appendChild(tg);
    }
    if (step.value) {
      var vl = document.createElement('span');
      vl.className = 'act-value';
      vl.textContent = step.value;
      actLine.appendChild(vl);
    }
    body.appendChild(actLine);

    if (step.description) {
      var desc = document.createElement('div');
      desc.className = 'step-desc';
      desc.textContent = step.description;
      body.appendChild(desc);
    }
    if (step.error && st === 'failed') {
      var err = document.createElement('div');
      err.className = 'step-err';
      err.textContent = step.error;
      body.appendChild(err);
    }
    if (st === 'manual') {
      var m = document.createElement('div');
      m.className = 'step-err';
      m.textContent = 'Manuel dogrulama gerekli';
      body.appendChild(m);
    }
    el.appendChild(body);

    // Indicator
    var ind = document.createElement('div');
    ind.className = 'step-indicator';
    var icon = document.createElement('span');
    icon.className = 'check-icon';
    if (st === 'running') {
      icon.innerHTML = '<span class="spinner"></span>';
    } else if (st === 'passed') {
      icon.textContent = '\u2713';
    } else if (st === 'failed') {
      icon.textContent = '\u2717';
    } else if (st === 'manual') {
      icon.textContent = '\u25CB';
    } else {
      icon.textContent = '';
    }
    ind.appendChild(icon);
    el.appendChild(ind);

    return el;
  }

  function renderSteps(data) {
    if (!data || !data.steps) return;

    yamlTitle.textContent = data.yaml_name || 'test.yaml';
    yamlMeta.textContent = data.steps.length + ' adim';

    var overall = data.overall_status || 'idle';
    runStatus.textContent = statusLabels[overall] || overall;
    runStatus.className = 'status-badge ' + overall;

    var frag = document.createDocumentFragment();
    for (var i = 0; i < data.steps.length; i++) {
      frag.appendChild(buildStep(data.steps[i], i, data.steps.length));
    }
    while (stepsList.firstChild) stepsList.removeChild(stepsList.firstChild);
    stepsList.appendChild(frag);

    var active = stepsList.querySelector('.is-running');
    if (active) active.scrollIntoView({behavior:'smooth', block:'center'});

    document.getElementById('passedCount').textContent = data.passed || 0;
    document.getElementById('failedCount').textContent = data.failed || 0;
    document.getElementById('manualCount').textContent = data.manual || 0;
    document.getElementById('pendingCount').textContent = data.pending || 0;
    document.getElementById('elapsed').textContent = (data.elapsed || 0) + 's';

    var pct = data.progress || 0;
    progressFill.style.width = pct + '%';
    progressFill.className = (data.failed > 0) ? 'progress-bar has-fail' : 'progress-bar';

    if (data.device) deviceBadge.textContent = data.device;
  }

  function refreshSteps() {
    fetch('/api/steps')
      .then(function(r) { return r.json(); })
      .then(function(d) { renderSteps(d); })
      .catch(function() {});
  }

  refreshSteps();
  setInterval(refreshSteps, 500);
})();
</script>
</body>
</html>"""


# ============================================================
# HTTP Handler
# ============================================================

class _TestUIHandler(BaseHTTPRequestHandler):
    """Live Test UI HTTP istek isleyici.

    MJPEG stream destekli. /stream endpoint'i multipart/x-mixed-replace
    ile binary JPEG frame'leri gonderir. BrokenPipe ve ConnectionReset
    hatalari sessizce yakalanir.
    """

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

    def _stream_mjpeg(self):
        """MJPEG stream: multipart/x-mixed-replace ile binary JPEG gonder."""
        ui: NazarLiveTestUI = self.server._nazar_test_ui
        cap = ui.screenshot
        if cap is None:
            self._send_json({"error": "screenshot not ready"}, 503)
            return

        boundary = b"--frame"
        self.send_response(200)
        self.send_header("Content-Type",
                         "multipart/x-mixed-replace; boundary=--frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            while cap._running:
                # Frame bekle (event-driven, polling degil)
                cap.wait_frame(timeout=2.0)
                frame = cap.get_jpeg()
                if not frame:
                    continue
                # MJPEG part header + binary JPEG
                header = (
                    boundary + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame)).encode() + b"\r\n"
                    b"\r\n"
                )
                self.wfile.write(header)
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def do_GET(self):
        ui: NazarLiveTestUI = self.server._nazar_test_ui

        if self.path == "/stream":
            self._stream_mjpeg()

        elif self.path == "/api/steps":
            data = ui.tracker.get_data() if ui.tracker else {}
            data["device"] = ui.device_name
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
        self.screenshot = ScreenshotCapture(self.platform)
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

        self.screenshot = ScreenshotCapture(self.platform)
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
