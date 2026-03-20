"""Runtime Viewer - Maestro test calistirmasini canli gosteren TUI."""
import threading
import time
from typing import Dict, List, Optional

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.align import Align
from rich import box


# Durum ikonlari
STATUS_ICONS = {
    "passed": "[bold green]OK[/bold green]",
    "failed": "[bold red]FAIL[/bold red]",
    "running": "[bold yellow]>>>[/bold yellow]",
    "pending": "[dim]---[/dim]",
    "skipped": "[dim cyan]SKIP[/dim cyan]",
}

# Adim durum renkleri
STATUS_STYLES = {
    "passed": "green",
    "failed": "red",
    "running": "bold yellow",
    "pending": "dim",
    "skipped": "dim cyan",
}


class RuntimeViewer:
    """Maestro testlerinin canli calismasini gosteren TUI.

    Sol panel: Test adimlari ve durumlari
    Sag panel: Cihaz bilgisi, gecen sure, basari/basarisiz sayisi

    Args:
        yaml_file: Test YAML dosyasinin adi.
        steps: Test adimlarinin listesi. Her adim bir dict:
               {action: str, target: str, ...}
        device_info: Cihaz bilgileri dict. (Opsiyonel)
        console: Rich Console nesnesi. (Opsiyonel)
    """

    def __init__(
        self,
        yaml_file: str,
        steps: List[Dict],
        device_info: Optional[Dict] = None,
        console: Optional[Console] = None,
    ):
        self.yaml_file = yaml_file
        self.steps = steps
        self.device_info = device_info or {}
        self.console = console or Console()
        self._step_statuses: List[str] = ["pending"] * len(steps)
        self._step_errors: List[str] = [""] * len(steps)
        self._start_time: float = 0
        self._passed: int = 0
        self._failed: int = 0
        self._current_index: int = -1
        self._live: Optional[Live] = None
        self._finished: bool = False
        self._lock: threading.Lock = threading.Lock()

    def update_step(self, index: int, status: str, error: str = "") -> None:
        """Bir adimin durumunu guncelle.

        Thread-safe: _passed, _failed, _current_index guncellemeleri
        threading.Lock ile korunur.

        Args:
            index: Adim indeksi (0-based).
            status: "running", "passed", "failed", "skipped"
            error: Hata mesaji (sadece failed icin).
        """
        with self._lock:
            if 0 <= index < len(self._step_statuses):
                old_status = self._step_statuses[index]
                self._step_statuses[index] = status
                self._step_errors[index] = error

                # Sayaclari guncelle
                if status == "passed" and old_status != "passed":
                    self._passed += 1
                elif status == "failed" and old_status != "failed":
                    self._failed += 1

                if status == "running":
                    self._current_index = index

                if self._live:
                    self._live.update(self._render())

    def show_result(
        self, passed: int, failed: int, duration: float
    ) -> None:
        """Son sonucu goster.

        Thread-safe: _passed, _failed, _finished guncellemeleri
        threading.Lock ile korunur.

        Args:
            passed: Basarili adim sayisi.
            failed: Basarisiz adim sayisi.
            duration: Toplam sure (saniye).
        """
        with self._lock:
            self._passed = passed
            self._failed = failed
            self._finished = True
            if self._live:
                self._live.update(self._render())

    def display_screenshot(self, path: str) -> None:
        """Screenshot'i terminalde goster (varsa term-image, yoksa dosya yolu)."""
        console = Console()
        try:
            from term_image.image import from_file
            img = from_file(path)
            img.draw()
            return
        except (ImportError, Exception):
            pass
        # Fallback: dosya yolu + boyut
        import os
        size = ""
        if os.path.exists(path):
            size = f" ({os.path.getsize(path) // 1024}KB)"
        console.print(Panel(
            f"[dim]Screenshot kaydedildi{size}[/dim]\n"
            f"[bold]{path}[/bold]\n"
            f"[dim]Gormek icin: open {path}[/dim]",
            title="[cyan]Screenshot[/cyan]", border_style="cyan",
        ))

    def start(self) -> Live:
        """Canli gosterimi baslat. Context manager olarak kullanilabilir.

        Returns:
            Rich Live nesnesi.
        """
        self._start_time = time.time()
        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=8,
            screen=False,
        )
        return self._live

    def _elapsed(self) -> float:
        """Gecen sureyi dondur."""
        if self._start_time:
            return time.time() - self._start_time
        return 0.0

    def _render(self) -> Panel:
        """Ana layout'u renderla."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        layout["body"].split_row(
            Layout(name="steps", ratio=3),
            Layout(name="info", ratio=2),
        )

        # Header
        layout["header"].update(self._render_header())

        # Sol panel: adimlar
        layout["steps"].update(self._render_steps())

        # Sag panel: bilgiler
        layout["info"].update(self._render_info())

        # Footer
        layout["footer"].update(self._render_footer())

        border_style = "green" if self._finished and self._failed == 0 else (
            "red" if self._finished and self._failed > 0 else "cyan"
        )

        return Panel(
            layout,
            title="[bold cyan]NAZAR RUNTIME[/bold cyan]",
            border_style=border_style,
            box=box.DOUBLE,
        )

    def _render_header(self) -> Panel:
        """Ust baslik."""
        header = Text()
        header.append("  NAZAR ", style="bold white on blue")
        header.append("  Maestro Runtime  ", style="bold")
        header.append(str(self.yaml_file), style="cyan")
        return Panel(header, box=box.SIMPLE)

    def _render_steps(self) -> Panel:
        """Sol panel: test adimlari tablosu."""
        table = Table(
            show_header=True,
            header_style="bold",
            box=box.SIMPLE_HEAVY,
            expand=True,
            padding=(0, 1),
        )
        table.add_column("#", style="dim", width=4)
        table.add_column("", width=6)
        table.add_column("Adim", ratio=3)
        table.add_column("Hedef", ratio=2)

        for i, step in enumerate(self.steps):
            status = self._step_statuses[i]
            icon = STATUS_ICONS.get(status, STATUS_ICONS["pending"])
            style = STATUS_STYLES.get(status, "dim")

            action = step.get("action", "?")
            target = step.get("target", "")
            if len(target) > 35:
                target = target[:32] + "..."

            # Aktif adimi vurgula
            if i == self._current_index and status == "running":
                row_num = "[bold yellow]{}[/bold yellow]".format(i + 1)
                row_action = "[bold yellow]{}[/bold yellow]".format(action)
                row_target = "[bold yellow]{}[/bold yellow]".format(target)
            elif status == "failed":
                row_num = "[red]{}[/red]".format(i + 1)
                row_action = "[red]{}[/red]".format(action)
                error = self._step_errors[i]
                if error:
                    row_target = "[red]{} ({})[/red]".format(target, error[:25])
                else:
                    row_target = "[red]{}[/red]".format(target)
            elif status == "passed":
                row_num = "[green]{}[/green]".format(i + 1)
                row_action = "[green]{}[/green]".format(action)
                row_target = "[green]{}[/green]".format(target)
            else:
                row_num = "[dim]{}[/dim]".format(i + 1)
                row_action = "[dim]{}[/dim]".format(action)
                row_target = "[dim]{}[/dim]".format(target)

            table.add_row(row_num, icon, row_action, row_target)

        return Panel(
            table,
            title="[bold]Test Adimlari[/bold]",
            border_style="blue",
        )

    def _render_info(self) -> Panel:
        """Sag panel: cihaz bilgisi ve istatistikler."""
        info_layout = Layout()
        info_layout.split_column(
            Layout(name="device", size=8),
            Layout(name="stats", size=8),
            Layout(name="progress"),
        )

        # Cihaz bilgisi
        device_text = Text()
        device_name = self.device_info.get("name", "Bilinmiyor")
        device_platform = self.device_info.get("platform", "?")
        device_status = self.device_info.get("status", "?")

        device_text.append("Cihaz: ", style="bold")
        device_text.append("{}\n".format(device_name))
        device_text.append("Platform: ", style="bold")
        device_text.append("{}\n".format(device_platform.upper()))
        device_text.append("Durum: ", style="bold")
        status_style = "green" if device_status == "booted" else "yellow"
        device_text.append(
            "{}\n".format(device_status), style=status_style
        )

        info_layout["device"].update(
            Panel(device_text, title="[bold]Cihaz[/bold]", border_style="dim")
        )

        # Istatistikler
        stats_text = Text()
        elapsed = self._elapsed()
        total = len(self.steps)
        completed = self._passed + self._failed

        stats_text.append("Sure: ", style="bold")
        stats_text.append("{:.1f}s\n".format(elapsed))
        stats_text.append("Toplam: ", style="bold")
        stats_text.append("{}\n".format(total))
        stats_text.append("Basarili: ", style="bold")
        stats_text.append("{}\n".format(self._passed), style="green")
        stats_text.append("Basarisiz: ", style="bold")
        fail_style = "red" if self._failed > 0 else "dim"
        stats_text.append("{}\n".format(self._failed), style=fail_style)

        info_layout["stats"].update(
            Panel(
                stats_text,
                title="[bold]Istatistik[/bold]",
                border_style="dim",
            )
        )

        # Ilerleme cubugu
        if total > 0:
            pct = completed / total * 100
            filled = int(pct / 5)
            bar = (
                "[green]" + "=" * filled + "[/green]"
                + "[dim]" + "-" * (20 - filled) + "[/dim]"
            )
            progress_text = Text.from_markup(
                "\n {} [{}/{}] {:.0f}%\n".format(bar, completed, total, pct)
            )
        else:
            progress_text = Text("\n Bekleniyor...\n", style="dim")

        info_layout["progress"].update(
            Panel(
                Align.center(progress_text, vertical="middle"),
                title="[bold]Ilerleme[/bold]",
                border_style="dim",
            )
        )

        return Panel(
            info_layout,
            title="[bold]Bilgiler[/bold]",
            border_style="blue",
        )

    def _render_footer(self) -> Panel:
        """Alt bilgi cubugu."""
        footer = Text()
        if self._finished:
            if self._failed == 0:
                footer.append(
                    "  BASARILI  ",
                    style="bold white on green",
                )
                footer.append(
                    "  Tum adimlar basariyla tamamlandi!",
                    style="green",
                )
            else:
                footer.append(
                    "  BASARISIZ  ",
                    style="bold white on red",
                )
                footer.append(
                    "  {} adim basarisiz oldu.".format(self._failed),
                    style="red",
                )
        else:
            if self._current_index >= 0:
                step = self.steps[self._current_index]
                footer.append("  Calisiyor: ", style="bold yellow")
                footer.append(
                    "{} -> {}".format(
                        step.get("action", "?"),
                        step.get("target", "?"),
                    ),
                    style="yellow",
                )
            else:
                footer.append("  Baslatiliyor...", style="dim")

        return Panel(footer, box=box.SIMPLE)


def run_with_viewer(
    executor,
    steps: List[Dict],
    device_info: Optional[Dict] = None,
    console: Optional[Console] = None,
) -> List[Dict]:
    """MaestroExecutor'u RuntimeViewer ile birlikte calistir.

    Bu yardimci fonksiyon executor ve viewer'i birbirine baglar.

    Args:
        executor: MaestroExecutor nesnesi.
        steps: Nazar formatindaki test adimlari.
        device_info: Cihaz bilgileri.
        console: Rich Console nesnesi.

    Returns:
        Test sonuclari listesi.
    """
    viewer = RuntimeViewer(
        yaml_file=str(executor.yaml_file),
        steps=steps,
        device_info=device_info or {},
        console=console,
    )

    live = viewer.start()
    results = []

    def on_step(event: Dict) -> None:
        """Her adim olayinda viewer'i guncelle."""
        idx = event.get("step_index", 1) - 1  # 1-based -> 0-based
        status = event.get("status", "running")
        detail = event.get("detail", "")

        if event["event"] == "step_running":
            viewer.update_step(idx, "running")
        elif event["event"] == "step_passed":
            viewer.update_step(idx, "passed")
        elif event["event"] == "step_failed":
            viewer.update_step(idx, "failed", error=detail)

    try:
        with live:
            results = executor.run_with_callback(on_step)
            summary = executor.get_summary()
            viewer.show_result(
                passed=summary["passed"],
                failed=summary["failed"],
                duration=summary["duration"],
            )
    except Exception as e:
        viewer._finished = True
        if viewer._live:
            viewer._live.update(viewer._render())
        raise

    return results
