"""Device Manager - Bagli cihazlari ve emulatorleri tespit eder."""
import subprocess
import shutil
from typing import Dict, List, Optional


def _run_cmd(cmd: List[str], timeout: int = 10) -> Optional[str]:
    """Komutu calistir, hata durumunda None dondur."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def list_android_devices() -> List[Dict]:
    """ADB ile bagli Android cihazlari listele."""
    output = _run_cmd(["adb", "devices"])
    if not output:
        return []

    devices = []
    for line in output.splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            serial = parts[0].strip()
            state = parts[1].strip()
            # Cihaz model adini al
            model = _run_cmd(
                ["adb", "-s", serial, "shell", "getprop", "ro.product.model"]
            )
            devices.append({
                "name": model or serial,
                "serial": serial,
                "platform": "android",
                "status": "booted" if state == "device" else state,
            })
    return devices


def list_ios_devices() -> List[Dict]:
    """xcrun simctl ile iOS simulatorlerini listele."""
    output = _run_cmd(["xcrun", "simctl", "list", "devices", "--json"])
    if not output:
        return []

    import json
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return []

    devices = []
    for runtime, device_list in data.get("devices", {}).items():
        for device in device_list:
            # Sadece aktif runtime'lari al
            if not device.get("isAvailable", False):
                continue
            state = device.get("state", "Shutdown").lower()
            devices.append({
                "name": device.get("name", "Unknown"),
                "serial": device.get("udid", ""),
                "platform": "ios",
                "status": "booted" if state == "booted" else "shutdown",
                "runtime": runtime,
            })
    return devices


def list_devices() -> List[Dict]:
    """Tum bagli cihazlari ve emulatorleri listele.

    Returns:
        List[Dict]: Her dict icerir:
            - name: Cihaz adi
            - serial: Cihaz serial/UDID
            - platform: "ios" veya "android"
            - status: "booted", "shutdown", "offline" vs.
    """
    devices = []
    devices.extend(list_android_devices())
    devices.extend(list_ios_devices())
    return devices


def get_active_device() -> Optional[Dict]:
    """Ilk aktif (booted) cihazi dondur. Yoksa None."""
    for device in list_devices():
        if device.get("status") == "booted":
            return device
    return None


def is_maestro_installed() -> bool:
    """Maestro CLI'nin yuklu olup olmadigini kontrol et."""
    # Once PATH'te var mi bak
    if shutil.which("maestro") is not None:
        output = _run_cmd(["maestro", "--version"])
        return output is not None
    return False


def get_maestro_version() -> Optional[str]:
    """Maestro versiyonunu dondur. Yuklu degilse None."""
    output = _run_cmd(["maestro", "--version"])
    return output
