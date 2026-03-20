"""Live TUI Runner - Testler calisirken canli guncellenen terminal arayuzu."""
import time
from typing import List, Dict
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich import box


PASS_ICON = "[bold green]PASSED[/bold green]"
FAIL_ICON = "[bold red]FAILED[/bold red]"
RUN_ICON = "[bold yellow]RUNNING[/bold yellow]"
WAIT_ICON = "[dim]WAITING[/dim]"
SKIP_ICON = "[dim cyan]SKIPPED[/dim cyan]"

PRIORITY_STYLE = {
    "critical": "[bold red]CRITICAL[/bold red]",
    "high": "[bold yellow]HIGH[/bold yellow]",
    "medium": "[cyan]MEDIUM[/cyan]",
    "low": "[dim]LOW[/dim]",
}

CATEGORY_ICONS = {
    "api": "API",
    "security": "SEC",
    "code_quality": "QUA",
    "type_safety": "TYP",
    "import_graph": "IMP",
    "error_handling": "ERR",
    "naming": "NAM",
    "git": "GIT",
    "dependency": "DEP",
    "license": "LIC",
    "env": "ENV",
    "config": "CFG",
    "documentation": "DOC",
    "accessibility": "A11",
    "structure": "STR",
    "performance": "PERF",
    "visual": "VIS",
    "docker": "DOC",
}


def _letter_grade(pass_rate: float) -> tuple:
    """Detayli letter grade hesapla. (grade, stars, message, style) dondurur."""
    grades = [
        (97, "A+", 5, "Mukemmel!", "bold green"),
        (93, "A", 5, "Harika!", "bold green"),
        (90, "A-", 4, "Cok Iyi!", "bold green"),
        (87, "B+", 4, "Iyi!", "green"),
        (83, "B", 3, "Iyi", "green"),
        (80, "B-", 3, "Fena Degil", "green"),
        (77, "C+", 2, "Orta", "yellow"),
        (73, "C", 2, "Orta", "yellow"),
        (70, "C-", 2, "Idare Eder", "yellow"),
        (67, "D+", 1, "Zayif", "red"),
        (63, "D", 1, "Zayif", "red"),
        (60, "D-", 1, "Cok Zayif", "red"),
        (0, "F", 0, "Basarisiz", "bold red"),
    ]
    for min_rate, grade, stars, msg, style in grades:
        if pass_rate >= min_rate:
            return grade, stars, msg, style
    return "F", 0, "Basarisiz", "bold red"


class LiveTestRunner:
    """Canli TUI ile test calistirici."""

    def __init__(self, console: Console = None):
        self.console = console or Console()
        self.results: List[Dict] = []
        self.current_test: str = ""
        self.current_file: str = ""
        self.current_category: str = ""
        self.files_scanned: int = 0
        self.start_time: float = 0
        self.total_tests: int = 0
        self.completed: int = 0
        self.passed: int = 0
        self.failed: int = 0
        self.skipped: int = 0
        self.category_stats: Dict[str, Dict] = {}
        self.error_log: List[Dict] = []

    def run_with_live_ui(self, orchestrator, plan_data: dict) -> List[Dict]:
        """Testleri canli TUI ile calistir."""
        tests = plan_data.get("tests", [])
        self.total_tests = len(tests)
        self.start_time = time.time()

        # Kategorileri hazirla
        for test in tests:
            cat = test.get("type", "other")
            if cat not in self.category_stats:
                self.category_stats[cat] = {"total": 0, "passed": 0, "failed": 0, "running": False}
            self.category_stats[cat]["total"] += 1

        with Live(self._render_dashboard(), console=self.console, refresh_per_second=8, screen=False) as live:
            for i, test in enumerate(tests):
                test_name = test.get("name", f"Test {i+1}")
                test_type = test.get("type", "other")
                self.current_test = test_name
                self.current_category = test_type.upper()
                self.category_stats[test_type]["running"] = True

                live.update(self._render_dashboard())

                # Testi calistir
                result = orchestrator._run_test(test)
                self.results.append(result)

                # Taranan dosya bilgisini sonuctan cikar
                detail = result.get("detail", "")
                import re as _re
                file_match = _re.search(r'([a-zA-Z0-9_/\-\.]+\.\w{1,5})(?::\d+)?', detail)
                if file_match:
                    self.current_file = file_match.group(1)
                self.files_scanned += 1

                # Sonucu guncelle
                self.completed += 1
                self.category_stats[test_type]["running"] = False
                if result["passed"]:
                    self.passed += 1
                    self.category_stats[test_type]["passed"] += 1
                else:
                    self.failed += 1
                    self.category_stats[test_type]["failed"] += 1
                    self.error_log.append({
                        "name": test_name,
                        "detail": result.get("detail", ""),
                        "type": test_type,
                        "priority": result.get("priority", "medium"),
                        "how_to_fix": result.get("how_to_fix"),
                    })

                self.current_test = ""
                live.update(self._render_dashboard())

                # Kisa bekleme (UI guncellemesi icin)
                time.sleep(0.05)

            # Son hali goster
            live.update(self._render_final())

        return self.results

    def _render_dashboard(self) -> Panel:
        """Ana dashboard'u renderla."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="stats", size=5),
            Layout(name="body"),
        )

        # Body'yi ikiye bol
        layout["body"].split_row(
            Layout(name="progress", ratio=3),
            Layout(name="errors", ratio=2),
        )

        # Header - aktif tarama bilgisi
        elapsed = time.time() - self.start_time if self.start_time else 0
        header_text = Text()
        header_text.append("  NAZAR ", style="bold white on blue")
        if self.current_test:
            header_text.append(f"  {self.current_category} ", style="bold yellow")
            if self.current_file:
                short_file = self.current_file
                if len(short_file) > 35:
                    short_file = "..." + short_file[-32:]
                header_text.append(f" {short_file} ", style="dim")
        else:
            header_text.append("  Otonom Test Motoru  ", style="bold")
        header_text.append(f"  {elapsed:.1f}s", style="dim")
        layout["header"].update(Align.center(header_text))

        # Stats row
        layout["stats"].update(self._render_stats())

        # Progress table
        layout["progress"].update(self._render_progress_table())

        # Error log
        layout["errors"].update(self._render_error_log())

        return Panel(
            layout,
            title="[bold cyan]NAZAR LIVE[/bold cyan]",
            border_style="cyan",
            box=box.DOUBLE,
        )

    def _render_stats(self) -> Columns:
        """Istatistik kartlarini renderla."""
        progress_pct = (self.completed / self.total_tests * 100) if self.total_tests > 0 else 0
        pass_rate = (self.passed / self.completed * 100) if self.completed > 0 else 0

        # Progress bar
        filled = int(progress_pct / 5)
        bar = "[green]" + "█" * filled + "[/green]" + "[dim]░[/dim]" * (20 - filled)

        cards = [
            Panel(
                f"[bold]{self.completed}[/bold][dim]/{self.total_tests}[/dim]\n{bar}",
                title="Ilerleme",
                border_style="blue",
                width=28,
            ),
            Panel(
                f"[bold green]{self.passed}[/bold green]",
                title="Passed",
                border_style="green",
                width=12,
            ),
            Panel(
                f"[bold red]{self.failed}[/bold red]",
                title="Failed",
                border_style="red" if self.failed > 0 else "dim",
                width=12,
            ),
            Panel(
                f"[bold]{'%.0f' % pass_rate}%[/bold]",
                title="Basari",
                border_style="green" if pass_rate >= 80 else "yellow" if pass_rate >= 50 else "red",
                width=12,
            ),
        ]
        return Columns(cards, padding=(0, 1))

    def _render_progress_table(self) -> Panel:
        """Test ilerleme tablosunu renderla."""
        table = Table(
            show_header=True,
            header_style="bold",
            box=box.SIMPLE_HEAVY,
            expand=True,
            padding=(0, 1),
        )
        table.add_column("Kategori", style="cyan", width=6)
        table.add_column("Test", ratio=3)
        table.add_column("Durum", justify="center", width=9)
        table.add_column("Sure", justify="right", width=7)

        # Kategori ozetleri
        for cat, stats in self.category_stats.items():
            icon = CATEGORY_ICONS.get(cat, cat[:4].upper())
            total = stats["total"]
            p = stats["passed"]
            f = stats["failed"]
            remaining = total - p - f

            if stats["running"]:
                status = RUN_ICON
            elif remaining == 0:
                status = PASS_ICON if f == 0 else FAIL_ICON
            else:
                status = f"[dim]{p}/{total}[/dim]"

            bar_width = 15
            if total > 0:
                green_len = int(bar_width * p / total)
                red_len = int(bar_width * f / total)
                gray_len = bar_width - green_len - red_len
                bar = f"[green]{'█' * green_len}[/green][red]{'█' * red_len}[/red][dim]{'░' * gray_len}[/dim]"
            else:
                bar = "[dim]" + "░" * bar_width + "[/dim]"

            table.add_row(
                f"[bold]{icon}[/bold]",
                bar,
                status,
                f"{p+f}/{total}",
            )

        # Aktif test + taranan dosya
        if self.current_test:
            table.add_row("", "", "", "")
            test_label = self.current_test[:45]
            if self.current_file:
                test_label += f" [dim]({self.current_file})[/dim]"
            table.add_row(
                "[yellow]>>>[/yellow]",
                f"[bold yellow]{test_label}[/bold yellow]",
                RUN_ICON,
                "[yellow]...[/yellow]",
            )

        # Son 5 tamamlanan test
        recent = self.results[-5:] if self.results else []
        if recent:
            table.add_row("", "", "", "")
            for r in reversed(recent):
                status = PASS_ICON if r["passed"] else FAIL_ICON
                name = r["name"]
                if len(name) > 45:
                    name = name[:42] + "..."
                table.add_row(
                    f"[dim]{CATEGORY_ICONS.get(r.get('type', ''), '?')}[/dim]",
                    name,
                    status,
                    f"[dim]{r.get('duration', 0):.2f}s[/dim]",
                )

        return Panel(table, title="[bold]Test Ilerlemesi[/bold]", border_style="blue")

    def _render_error_log(self) -> Panel:
        """Hata logunu renderla - SORUN + COZUM + QUICK FIX."""
        if not self.error_log:
            content = Align.center(
                Text("Hata yok", style="dim green"),
                vertical="middle",
            )
            return Panel(content, title="[bold]Hatalar[/bold]", border_style="green")

        table = Table(
            show_header=False,
            box=None,
            expand=True,
            padding=(0, 1),
        )
        table.add_column("", ratio=1)

        for err in self.error_log[-6:]:
            priority = PRIORITY_STYLE.get(err["priority"], "[dim]?[/dim]")
            name = err["name"]
            if len(name) > 35:
                name = name[:32] + "..."
            detail = err.get("detail", "")
            if len(detail) > 40:
                detail = detail[:37] + "..."

            table.add_row(f"[red]x[/red] {priority} {name}")
            if detail:
                table.add_row(f"  [dim]{detail}[/dim]")

            # How to Fix goster
            fix = err.get("how_to_fix")
            if fix:
                table.add_row(f"  [green]>> {fix['quick_fix'][:50]}[/green]")

        return Panel(
            table,
            title=f"[bold red]Hatalar ({len(self.error_log)})[/bold red]",
            border_style="red",
        )

    def _render_final(self) -> Panel:
        """Son raporu renderla - detayli letter grade ile."""
        elapsed = time.time() - self.start_time
        pass_rate = (self.passed / self.total_tests * 100) if self.total_tests > 0 else 0

        # Detayli grade
        grade, stars, grade_msg, grade_style = _letter_grade(pass_rate)
        star_display = "*" * stars + "." * (5 - stars)

        # Sonuc tablosu
        result_table = Table(
            show_header=True, header_style="bold",
            box=box.ROUNDED, expand=True,
        )
        result_table.add_column("#", style="dim", width=4)
        result_table.add_column("Test", ratio=3)
        result_table.add_column("Tur", width=6)
        result_table.add_column("Sonuc", justify="center", width=9)
        result_table.add_column("Sure", justify="right", width=8)
        result_table.add_column("Detay", ratio=2)

        for i, r in enumerate(self.results, 1):
            status = PASS_ICON if r["passed"] else FAIL_ICON
            cat = CATEGORY_ICONS.get(r.get("type", ""), "?")
            name = r["name"]
            if len(name) > 50:
                name = name[:47] + "..."
            detail = r.get("detail", "")
            if len(detail) > 40:
                detail = detail[:37] + "..."
            detail_style = "dim" if r["passed"] else "red"

            result_table.add_row(
                str(i), name, cat, status,
                f"{r.get('duration', 0):.2f}s",
                f"[{detail_style}]{detail}[/{detail_style}]",
            )

        # Summary
        summary = Text()
        summary.append("\n")
        summary.append(f"  Not: ", style="bold")
        summary.append(f"{grade}", style=grade_style)
        summary.append(f" ({pass_rate:.0f}%) - {grade_msg}  ", style="bold")
        summary.append(f"[{star_display}]", style="yellow")
        summary.append(f"\n  Toplam: {self.total_tests} | ", style="bold")
        summary.append(f"Passed: {self.passed} ", style="green")
        summary.append(f"| Failed: {self.failed} ", style="red")
        summary.append(f"| Sure: {elapsed:.1f}s\n", style="dim")

        # Kategori bazli ozet
        cat_table = Table(show_header=True, box=box.SIMPLE, expand=True)
        cat_table.add_column("Kategori", style="cyan")
        cat_table.add_column("Passed", style="green", justify="center")
        cat_table.add_column("Failed", style="red", justify="center")
        cat_table.add_column("Basari", justify="center")

        for cat, stats in self.category_stats.items():
            total = stats["total"]
            rate = (stats["passed"] / total * 100) if total > 0 else 0
            rate_style = "green" if rate >= 80 else "yellow" if rate >= 50 else "red"
            cat_table.add_row(
                cat.upper(),
                str(stats["passed"]),
                str(stats["failed"]),
                f"[{rate_style}]{rate:.0f}%[/{rate_style}]",
            )

        # How to Fix ozet (basarisiz testler icin)
        fix_lines = []
        for err in self.error_log[:5]:
            fix = err.get("how_to_fix")
            if fix:
                fix_lines.append(f"  [yellow]>>[/yellow] {err['name'][:40]}")
                fix_lines.append(f"    [green]COZUM: {fix['cozum'][:60]}[/green]")

        layout = Layout()
        parts = [
            Layout(Align.center(summary), size=5),
            Layout(cat_table, size=len(self.category_stats) + 4),
        ]
        if fix_lines:
            fix_text = Text.from_markup("\n".join(fix_lines))
            parts.append(Layout(Panel(fix_text, title="[bold yellow]Nasil Duzeltilir?[/bold yellow]", border_style="yellow"), size=len(fix_lines) + 3))
        parts.append(Layout(result_table))

        layout.split_column(*parts)

        return Panel(
            layout,
            title="[bold green]NAZAR - TEST TAMAMLANDI[/bold green]",
            border_style="green" if self.failed == 0 else "red",
            box=box.DOUBLE,
        )
