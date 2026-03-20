"""Maestro Executor - Maestro UI testlerini calistirir ve ciktisini parse eder."""
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from nazar.executors.device_manager import (
    get_active_device,
    is_maestro_installed,
)

# Cihaz ID'si icin izin verilen karakter deseni
_DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9:._-]+$")


class MaestroError(Exception):
    """Maestro ile ilgili hatalar."""
    pass


class MaestroNotInstalledError(MaestroError):
    """Maestro yuklu degil."""
    pass


class NoDeviceError(MaestroError):
    """Bagli cihaz bulunamadi."""
    pass


class TestFailedError(MaestroError):
    """Test basarisiz oldu."""
    pass


# Maestro ciktisindan adim bilgilerini parse etmek icin kaliplar
STEP_RUNNING_PATTERN = re.compile(
    r"(?:Running|Executing)\s*(?:step\s*)?(\d+)?[:\s]*(.+)",
    re.IGNORECASE,
)
STEP_PASSED_PATTERN = re.compile(
    r"(?:Completed|Passed|OK|SUCCESS)[:\s]*(.+)?",
    re.IGNORECASE,
)
STEP_FAILED_PATTERN = re.compile(
    r"(?:FAILED|ERROR|FAIL)[:\s]*(.+)?",
    re.IGNORECASE,
)
SCREENSHOT_PATTERN = re.compile(
    r"(?:Screenshot|Captured)\s*(?:saved\s*(?:to|at))?\s*[:\s]*(.+\.png)",
    re.IGNORECASE,
)
FLOW_COMPLETE_PATTERN = re.compile(
    r"(?:Flow|Test)\s+(?:completed|finished|done)",
    re.IGNORECASE,
)


class MaestroExecutor:
    """Maestro test dosyalarini calistirir.

    Args:
        project_path: Projenin kok dizini.
        yaml_file: Calistirilacak Maestro YAML dosyasinin yolu.
        device: Belirli bir cihaz serial/UDID'si. None ise otomatik sec.
    """

    def __init__(
        self,
        project_path: str,
        yaml_file: str,
        device: Optional[str] = None,
    ):
        self.project_path = Path(project_path).resolve()
        self.yaml_file = Path(yaml_file).resolve()
        self.device = device
        self._results: List[Dict] = []
        self._output_lines: List[str] = []
        self._start_time: float = 0
        self._end_time: float = 0

        if not self.yaml_file.exists():
            raise FileNotFoundError(
                "YAML dosyasi bulunamadi: {}".format(self.yaml_file)
            )

        # YAML dosyasinin proje dizini icinde oldugunu dogrula
        try:
            self.yaml_file.relative_to(self.project_path)
        except ValueError:
            raise ValueError(
                "YAML dosyasi proje dizini disinda: {} (proje: {})".format(
                    self.yaml_file, self.project_path
                )
            )

        # Device ID dogrulamasi
        if self.device is not None:
            if self.device.startswith("-"):
                raise ValueError(
                    "Gecersiz cihaz ID'si ('-' ile baslayamaz): {}".format(
                        self.device
                    )
                )
            if not _DEVICE_ID_PATTERN.match(self.device):
                raise ValueError(
                    "Gecersiz cihaz ID'si (sadece A-Z, a-z, 0-9, :, ., _, - karakterleri): {}".format(
                        self.device
                    )
                )

    def _build_command(self) -> List[str]:
        """Maestro komutunu olustur."""
        cmd = ["maestro", "test"]
        if self.device:
            # Komutu olusturmadan once device degerini tekrar dogrula
            if self.device.startswith("-"):
                raise ValueError(
                    "Gecersiz cihaz ID'si ('-' ile baslayamaz): {}".format(
                        self.device
                    )
                )
            if not _DEVICE_ID_PATTERN.match(self.device):
                raise ValueError(
                    "Gecersiz cihaz ID'si (sadece A-Z, a-z, 0-9, :, ., _, - karakterleri): {}".format(
                        self.device
                    )
                )
            cmd.extend(["--device", self.device])
        cmd.append(str(self.yaml_file))
        return cmd

    def _check_prerequisites(self) -> None:
        """Calisma kosullarini kontrol et."""
        if not is_maestro_installed():
            raise MaestroNotInstalledError(
                "Maestro yuklu degil. "
                "Kurmak icin: curl -Ls 'https://get.maestro.mobile.dev' | bash"
            )

        if not self.device:
            active = get_active_device()
            if active is None:
                raise NoDeviceError(
                    "Bagli veya aktif cihaz bulunamadi. "
                    "Emulator baslatip tekrar deneyin."
                )
            self.device = active.get("serial")

    def _parse_line(self, line: str) -> Optional[Dict]:
        """Tek bir Maestro cikti satirini parse et.

        Returns:
            Dict veya None. Dict icerigi:
                - event: "step_running", "step_passed", "step_failed",
                         "screenshot", "flow_complete"
                - step_index: Adim numarasi (varsa)
                - detail: Ek bilgi
        """
        stripped = line.strip()
        if not stripped:
            return None

        # Akis tamamlandi (diger kaliplardan once kontrol et,
        # "completed" kelimesi step_passed ile de eslestigi icin)
        if FLOW_COMPLETE_PATTERN.search(stripped):
            return {
                "event": "flow_complete",
                "detail": stripped,
            }

        # Adim calisiyor
        m = STEP_RUNNING_PATTERN.search(stripped)
        if m:
            idx = int(m.group(1)) if m.group(1) else None
            return {
                "event": "step_running",
                "step_index": idx,
                "detail": (m.group(2) or "").strip(),
            }

        # Adim basarisiz (basarilidan once kontrol et)
        m = STEP_FAILED_PATTERN.search(stripped)
        if m:
            return {
                "event": "step_failed",
                "detail": (m.group(1) or "").strip(),
            }

        # Adim basarili
        m = STEP_PASSED_PATTERN.search(stripped)
        if m:
            return {
                "event": "step_passed",
                "detail": (m.group(1) or "").strip(),
            }

        # Ekran goruntusu
        m = SCREENSHOT_PATTERN.search(stripped)
        if m:
            return {
                "event": "screenshot",
                "detail": m.group(1).strip(),
            }

        return None

    def run(self) -> List[Dict]:
        """Maestro testini calistir ve ciktiyi topla.

        Returns:
            List[Dict]: Adim sonuclari.

        Raises:
            MaestroNotInstalledError: Maestro yuklu degilse.
            NoDeviceError: Aktif cihaz yoksa.
            TestFailedError: Test basarisiz olduysa.
        """
        self._check_prerequisites()
        cmd = self._build_command()
        self._results = []
        self._output_lines = []
        self._start_time = time.time()

        current_step_index = 0
        process = None

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(self.project_path),
                env={**os.environ, "MAESTRO_CLI_NO_ANALYTICS": "true"},
            )

            for line in iter(process.stdout.readline, ""):
                self._output_lines.append(line.rstrip())
                event = self._parse_line(line)
                if event is None:
                    continue

                if event["event"] == "step_running":
                    current_step_index += 1
                    self._results.append({
                        "step_index": current_step_index,
                        "action": event["detail"],
                        "status": "running",
                        "screenshot": None,
                        "error": None,
                    })
                elif event["event"] == "step_passed":
                    if self._results:
                        self._results[-1]["status"] = "passed"
                elif event["event"] == "step_failed":
                    if self._results:
                        self._results[-1]["status"] = "failed"
                        self._results[-1]["error"] = event["detail"]
                elif event["event"] == "screenshot":
                    if self._results:
                        self._results[-1]["screenshot"] = event["detail"]

            process.wait()
            self._end_time = time.time()

            # Henuz "running" durumunda kalan adimlari bitir
            for r in self._results:
                if r["status"] == "running":
                    r["status"] = (
                        "passed" if process.returncode == 0 else "failed"
                    )

            if process.returncode != 0:
                failed_steps = [
                    r for r in self._results if r["status"] == "failed"
                ]
                if failed_steps:
                    msg = "Test basarisiz: {} adim hata verdi".format(
                        len(failed_steps)
                    )
                else:
                    msg = "Maestro hata koduyla cikti: {}".format(
                        process.returncode
                    )
                raise TestFailedError(msg)

        except FileNotFoundError:
            self._end_time = time.time()
            raise MaestroNotInstalledError(
                "Maestro komutu bulunamadi. Yukleyin: "
                "curl -Ls 'https://get.maestro.mobile.dev' | bash"
            )
        finally:
            if process is not None:
                try:
                    if process.stdout:
                        process.stdout.close()
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                except OSError:
                    pass

        return self._results

    def run_with_callback(
        self,
        on_step: Callable[[Dict], None],
    ) -> List[Dict]:
        """Maestro testini callback ile calistir.

        Her adim degisikligi oldugunda on_step callback'i cagirilir.

        Args:
            on_step: Her olay icin cagrilacak fonksiyon.
                     Dict icerigi: event, step_index, status, detail

        Returns:
            List[Dict]: Adim sonuclari.

        Raises:
            MaestroNotInstalledError: Maestro yuklu degilse.
            NoDeviceError: Aktif cihaz yoksa.
            TestFailedError: Test basarisiz olduysa.
        """
        self._check_prerequisites()
        cmd = self._build_command()
        self._results = []
        self._output_lines = []
        self._start_time = time.time()

        current_step_index = 0
        process = None

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(self.project_path),
                env={**os.environ, "MAESTRO_CLI_NO_ANALYTICS": "true"},
            )

            for line in iter(process.stdout.readline, ""):
                self._output_lines.append(line.rstrip())
                event = self._parse_line(line)
                if event is None:
                    continue

                if event["event"] == "step_running":
                    current_step_index += 1
                    step_data = {
                        "step_index": current_step_index,
                        "action": event["detail"],
                        "status": "running",
                        "screenshot": None,
                        "error": None,
                    }
                    self._results.append(step_data)
                    on_step({
                        "event": "step_running",
                        "step_index": current_step_index,
                        "status": "running",
                        "detail": event["detail"],
                    })

                elif event["event"] == "step_passed":
                    if self._results:
                        self._results[-1]["status"] = "passed"
                        on_step({
                            "event": "step_passed",
                            "step_index": len(self._results),
                            "status": "passed",
                            "detail": event["detail"],
                        })

                elif event["event"] == "step_failed":
                    if self._results:
                        self._results[-1]["status"] = "failed"
                        self._results[-1]["error"] = event["detail"]
                        on_step({
                            "event": "step_failed",
                            "step_index": len(self._results),
                            "status": "failed",
                            "detail": event["detail"],
                        })

                elif event["event"] == "screenshot":
                    if self._results:
                        self._results[-1]["screenshot"] = event["detail"]
                        on_step({
                            "event": "screenshot",
                            "step_index": len(self._results),
                            "status": self._results[-1]["status"],
                            "detail": event["detail"],
                        })

                elif event["event"] == "flow_complete":
                    on_step({
                        "event": "flow_complete",
                        "step_index": len(self._results),
                        "status": "complete",
                        "detail": event["detail"],
                    })

            process.wait()
            self._end_time = time.time()

            # Henuz "running" durumunda kalan adimlari bitir
            for r in self._results:
                if r["status"] == "running":
                    r["status"] = (
                        "passed" if process.returncode == 0 else "failed"
                    )

            # Non-zero return code kontrolu
            if process.returncode != 0:
                failed_steps = [
                    r for r in self._results if r["status"] == "failed"
                ]
                if failed_steps:
                    msg = "Test basarisiz: {} adim hata verdi".format(
                        len(failed_steps)
                    )
                else:
                    msg = "Maestro hata koduyla cikti: {}".format(
                        process.returncode
                    )
                raise TestFailedError(msg)

        except FileNotFoundError:
            self._end_time = time.time()
            raise MaestroNotInstalledError(
                "Maestro komutu bulunamadi. Yukleyin: "
                "curl -Ls 'https://get.maestro.mobile.dev' | bash"
            )
        finally:
            if process is not None:
                try:
                    if process.stdout:
                        process.stdout.close()
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                except OSError:
                    pass

        return self._results

    def get_results(self) -> List[Dict]:
        """Son calistirma sonuclarini dondur.

        Returns:
            List[Dict]: Her dict icerir:
                - step_index: Adim numarasi
                - action: Ne yapildi
                - status: "passed", "failed", "running"
                - screenshot: Ekran goruntusu yolu (varsa)
                - error: Hata mesaji (varsa)
        """
        return list(self._results)

    def get_output(self) -> str:
        """Ham Maestro ciktisini dondur."""
        return "\n".join(self._output_lines)

    def get_duration(self) -> float:
        """Calisma suresini saniye olarak dondur."""
        if self._end_time and self._start_time:
            return self._end_time - self._start_time
        return 0.0

    def get_summary(self) -> Dict:
        """Ozet bilgileri dondur."""
        passed = sum(1 for r in self._results if r["status"] == "passed")
        failed = sum(1 for r in self._results if r["status"] == "failed")
        return {
            "total_steps": len(self._results),
            "passed": passed,
            "failed": failed,
            "duration": self.get_duration(),
            "yaml_file": str(self.yaml_file),
            "device": self.device,
            "success": failed == 0 and len(self._results) > 0,
        }
