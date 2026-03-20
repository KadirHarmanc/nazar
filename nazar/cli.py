"""Nazar CLI - Ana giris noktasi."""
import typer
import random
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Optional
import json
import time

from nazar.scanner.project_scanner import ProjectScanner
from nazar.planner.test_planner import TestPlanner
from nazar.runners.orchestrator import TestOrchestrator
from nazar.reporter.html_reporter import HTMLReporter
from nazar.tui.live_runner import LiveTestRunner

DID_YOU_KNOW = [
    "nazar --json ile CI/CD pipeline'iniza entegre edin",
    "nazar.yaml ile kurallarinizi ozellestirin",
    "nazar run --category security ile sadece guvenlik testlerini calistirin",
    "Pre-commit hook ile her commit'te otomatik tarama yapin",
    "nazar --quiet ile sadece sonucu gorun",
    "SARIF ciktisiyla GitHub Code Scanning'e entegre edin",
    "Plugin yazarak kendi test kurallarinizi ekleyin",
    "nazar auto --report rapor.html ile ozel rapor adi verin",
    "nazar init ile proje yapilandirma dosyasi olusturun",
    "Docker ile nazar'i container icinde calistirabilirsiniz",
]

app = typer.Typer(
    name="nazar",
    help="Nazar - Projeyi tarar, mimariyi anlar, test plani yapar, calistirir.",
    invoke_without_command=True,
)
ui_app = typer.Typer(
    name="ui",
    help="YAML UI test dosyalarini yonet: olustur, tara, kontrol et.",
)
app.add_typer(ui_app, name="ui")
console = Console()


@app.callback()
def main(
    ctx: typer.Context,
    no_color: bool = typer.Option(False, "--no-color", help="Renksiz cikti"),
    json_output: bool = typer.Option(False, "--json", help="JSON formatinda cikti"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal cikti"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Detayli cikti"),
):
    """Nazar - Otonom Test Araci."""
    ctx.ensure_object(dict)
    ctx.obj["no_color"] = no_color
    ctx.obj["json_output"] = json_output
    ctx.obj["quiet"] = quiet
    ctx.obj["verbose"] = verbose

    if no_color:
        console._force_terminal = False

    # Argumansiz calistirma = interaktif mod
    if ctx.invoked_subcommand is None:
        from nazar.interactive.shell import NazarShell
        NazarShell().run()


def _show_tip():
    """Rastgele ipucu goster."""
    console.print(f"\n[dim]Did You Know? {random.choice(DID_YOU_KNOW)}[/dim]")


def _phase_scan(path: Path, show_ui: bool):
    """Faz 1: Projeyi tara."""
    if show_ui:
        console.print("\n[bold cyan][1/4][/bold cyan] Proje taraniyor...")
    scanner = ProjectScanner(str(path))
    result = scanner.scan()
    if show_ui:
        console.print(f"  Teknoloji: [green]{result.tech_stack}[/green]")
        console.print(f"  {result.screen_count} ekran, {result.api_endpoint_count} API, {result.existing_test_count} mevcut test")
    return result


def _phase_plan(scan_result, show_ui: bool, profile: str = "full"):
    """Faz 2: Test plani olustur."""
    if show_ui:
        profile_label = f" ({profile})" if profile != "full" else ""
        console.print(f"\n[bold yellow][2/4][/bold yellow] Test plani olusturuluyor...{profile_label}")
    planner = TestPlanner(scan_result, profile=profile)
    test_plan = planner.create_plan()
    if show_ui:
        console.print(f"  {test_plan.total_tests} test planlanidi")
    return test_plan, test_plan.to_dict()


def _phase_execute(orchestrator, plan_dict, json_output, quiet, show_ui):
    """Faz 3: Testleri calistir."""
    if json_output or quiet:
        return orchestrator.run_all()
    if show_ui:
        console.print("\n[bold green][3/4][/bold green] Testler calistiriliyor...\n")
    return LiveTestRunner(console).run_with_live_ui(orchestrator, plan_dict)


def _phase_report(results, plan_dict, report, json_output, quiet, show_ui, start):
    """Faz 4: Sonuclari raporla."""
    passed = sum(1 for r in results if r["passed"])
    if json_output:
        import sys
        from nazar.reporters.json_reporter import JSONReporter
        sys.stdout.write(JSONReporter().generate(results, plan_dict) + "\n")
        return
    if not quiet:
        console.print("\n[bold magenta][4/4][/bold magenta] Rapor olusturuluyor...")
    HTMLReporter().generate(results, plan_dict, report)
    if not quiet:
        console.print(f"\n[bold]Toplam sure: {time.time() - start:.1f}s[/bold]")
        console.print(f"[green]Rapor: {report}[/green]")
        _show_tip()
    else:
        pass_rate = (passed / len(results) * 100) if results else 0
        console.print(f"Nazar: {passed}/{len(results)} passed ({pass_rate:.0f}%) - {report}")


def _run_auto(path: Path, report: str, opts: dict):
    """Auto komutu mantigi."""
    quiet, json_output = opts.get("quiet", False), opts.get("json_output", False)
    profile = opts.get("profile", "full")
    show_ui = not quiet and not json_output
    if show_ui:
        profile_text = f" | Profil: {profile}" if profile != "full" else ""
        console.print(Panel(
            f"[bold magenta]NAZAR AUTO[/bold magenta] - Tam Otonom Test{profile_text}\n"
            "Tara > Planla > Calistir > Raporla", expand=False))
    start = time.time()
    scan_result = _phase_scan(path, show_ui)
    _test_plan, plan_dict = _phase_plan(scan_result, show_ui, profile=profile)
    orchestrator = TestOrchestrator(str(path), plan_dict)
    results = _phase_execute(orchestrator, plan_dict, json_output, quiet, show_ui)
    _phase_report(results, plan_dict, report, json_output, quiet, show_ui, start)

    # Scan cache kaydet
    from nazar.cache.scan_cache import ScanCache
    cache = ScanCache(str(path))
    cache.save_scan_result(results, plan_dict, profile, time.time() - start)
    cache.save_file_hashes(scan_result.source_files)


@app.command()
def scan(
    path: Path = typer.Argument(".", help="Proje dizini"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Sonuc dosyasi (JSON)"),
):
    """Projeyi tara, teknik mimariyi analiz et."""
    console.print(Panel("[bold cyan]NAZAR SCAN[/bold cyan] - Proje Analizi", expand=False))
    scanner = ProjectScanner(str(path))
    result = scanner.scan()
    table = Table(title="Proje Analizi", show_header=True)
    table.add_column("Ozellik", style="cyan")
    table.add_column("Deger", style="green")

    table.add_row("Proje Adi", result.project_name)
    table.add_row("Teknoloji", result.tech_stack)
    table.add_row("Dil", ", ".join(result.languages))
    table.add_row("Framework", result.framework or "-")
    table.add_row("Ekran/Component Sayisi", str(result.screen_count))
    table.add_row("API Endpoint Sayisi", str(result.api_endpoint_count))
    table.add_row("Mevcut Test Sayisi", str(result.existing_test_count))
    table.add_row("Config Dosyalari", ", ".join(result.config_files) or "-")

    console.print(table)
    if result.api_endpoints:
        api_table = Table(title="Bulunan API Endpoint'leri")
        api_table.add_column("Method", style="yellow")
        api_table.add_column("URL", style="white")
        api_table.add_column("Dosya", style="dim")
        for ep in result.api_endpoints[:20]:
            api_table.add_row(ep.get("method", "GET"), ep["url"], ep.get("file", ""))
        console.print(api_table)
    if result.screens:
        screen_table = Table(title="Bulunan Ekranlar/Component'ler")
        screen_table.add_column("Adi", style="magenta")
        screen_table.add_column("Dosya", style="dim")
        screen_table.add_column("Tur", style="cyan")
        for s in result.screens[:30]:
            screen_table.add_row(s["name"], s["file"], s.get("type", "component"))
        console.print(screen_table)
    if output:
        Path(output).write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        console.print(f"\n[green]Sonuc kaydedildi: {output}[/green]")
    return result


@app.command()
def plan(
    path: Path = typer.Argument(".", help="Proje dizini"),
    output: Optional[str] = typer.Option("nazar-plan.json", "--output", "-o"),
):
    """Proje analizine dayanarak test plani olustur."""
    console.print(Panel("[bold yellow]NAZAR PLAN[/bold yellow] - Test Plani Olustur", expand=False))
    scanner = ProjectScanner(str(path))
    scan_result = scanner.scan()
    planner = TestPlanner(scan_result)
    test_plan = planner.create_plan()
    table = Table(title="Test Plani")
    table.add_column("Kategori", style="cyan")
    table.add_column("Test Sayisi", style="green")
    table.add_column("Oncelik", style="yellow")

    for category in test_plan.categories:
        table.add_row(
            category["name"],
            str(category["test_count"]),
            category["priority"],
        )
    console.print(table)

    console.print(f"\n[bold]Toplam Test:[/bold] {test_plan.total_tests}")
    console.print(f"[bold]Tahmini Sure:[/bold] {test_plan.estimated_duration}")
    if test_plan.tests:
        detail_table = Table(title="Test Detaylari")
        detail_table.add_column("#", style="dim")
        detail_table.add_column("Test", style="white")
        detail_table.add_column("Tur", style="cyan")
        detail_table.add_column("Hedef", style="green")
        for i, test in enumerate(test_plan.tests[:30], 1):
            detail_table.add_row(
                str(i), test["name"], test["type"], test.get("target", "")
            )
        console.print(detail_table)

    Path(output).write_text(json.dumps(test_plan.to_dict(), indent=2, ensure_ascii=False))
    console.print(f"\n[green]Plan kaydedildi: {output}[/green]")


@app.command()
def run(
    path: Path = typer.Argument(".", help="Proje dizini"),
    plan_file: Optional[str] = typer.Option(None, "--plan", "-p", help="Plan dosyasi"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Sadece bu kategoriyi calistir"),
    report: str = typer.Option("nazar-report.html", "--report", "-r", help="Rapor dosyasi"),
):
    """Test planini calistir."""
    console.print(Panel("[bold green]NAZAR RUN[/bold green] - Testleri Calistir", expand=False))
    if plan_file and Path(plan_file).exists():
        plan_data = json.loads(Path(plan_file).read_text())
    else:
        console.print("[yellow]Plan bulunamadi, otomatik olusturuluyor...[/yellow]")
        scanner = ProjectScanner(str(path))
        scan_result = scanner.scan()
        planner = TestPlanner(scan_result)
        test_plan = planner.create_plan()
        plan_data = test_plan.to_dict()
    orchestrator = TestOrchestrator(str(path), plan_data)
    if category:
        filtered_plan = dict(plan_data)
        filtered_plan["tests"] = [t for t in plan_data.get("tests", []) if t.get("type", "").lower() == category.lower()]
        orchestrator = TestOrchestrator(str(path), filtered_plan)
        plan_data = filtered_plan
    live_runner = LiveTestRunner(console)
    results = live_runner.run_with_live_ui(orchestrator, plan_data)

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    HTMLReporter().generate(results, plan_data, report)
    console.print(f"[green]Rapor olusturuldu: {report}[/green]")


@app.command()
def auto(
    ctx: typer.Context,
    path: Path = typer.Argument(".", help="Proje dizini"),
    report: str = typer.Option("nazar-report.html", "--report", "-r"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Test profili (full/frontend/backend/security/mobile/ci)"),
    incremental: bool = typer.Option(False, "--incremental", help="Sadece degisen dosyalari tara"),
    github_pr: bool = typer.Option(False, "--github-pr", help="Sonuclari GitHub PR comment olarak gonder"),
    sarif: Optional[str] = typer.Option(None, "--sarif", help="SARIF cikti dosyasi (GitHub Code Scanning)"),
):
    """Tek komutla her seyi yap: tara, planla, calistir, raporla."""
    opts = ctx.obj or {}
    opts["profile"] = profile or "full"
    opts["incremental"] = incremental
    _run_auto(path, report, opts)

    if github_pr or sarif:
        # Sonuclari tekrar uret (hafif)
        scan_result = _phase_scan(path, False)
        _test_plan, plan_dict = _phase_plan(scan_result, False)
        orchestrator = TestOrchestrator(str(path), plan_dict)
        results = orchestrator.run_all()

        from nazar.integrations.github_pr import GitHubPRReporter
        reporter = GitHubPRReporter()

        if github_pr:
            if reporter.post_comment(results, plan_dict):
                console.print("[green]GitHub PR comment gonderildi[/green]")
            else:
                console.print("[yellow]PR comment gonderilemedi (token/repo/PR bilgisi eksik)[/yellow]")

        if sarif:
            sarif_content = reporter.generate_sarif(results)
            Path(sarif).write_text(sarif_content)
            console.print(f"[green]SARIF cikti: {sarif}[/green]")


@app.command()
def init(
    path: Path = typer.Argument(".", help="Proje dizini"),
):
    """nazar.yaml yapilandirma dosyasi olustur."""
    from nazar.config.loader import ConfigLoader
    output = str(Path(path) / "nazar.yaml")
    if Path(output).exists():
        console.print(f"[yellow]nazar.yaml zaten mevcut: {output}[/yellow]")
        raise typer.Abort()
    ConfigLoader.generate_template(output)
    console.print(f"[green]nazar.yaml olusturuldu: {output}[/green]")
    console.print("[dim]Dosyayi duzenleyerek Nazar'i yapilandiriniz.[/dim]")


@app.command()
def update():
    """Nazar'i son versiyona guncelle."""
    import subprocess as _sp

    console.print("[bold cyan]Nazar guncelleniyor...[/bold cyan]")

    # Mevcut versiyon
    try:
        from nazar import __version__
        current = __version__
    except (ImportError, AttributeError):
        current = "?"

    # PyPI'dan son versiyonu kontrol et
    try:
        import urllib.request, json
        resp = urllib.request.urlopen("https://pypi.org/pypi/nazar/json", timeout=10)
        data = json.loads(resp.read())
        latest = data["info"]["version"]
    except Exception:
        latest = "?"

    if current == latest and current != "?":
        console.print(f"[green]Zaten guncel: v{current}[/green]")
        return

    if latest != "?":
        console.print(f"  Mevcut: v{current}  ->  Yeni: v{latest}")

    # pipx ile guncelle (oncelikli)
    try:
        r = _sp.run(["pipx", "upgrade", "nazar"], capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            console.print(f"[green]Guncellendi! (pipx)[/green]")
            return
    except (FileNotFoundError, _sp.TimeoutExpired):
        pass

    # pip ile guncelle (fallback)
    try:
        import sys as _sys
        r = _sp.run([_sys.executable, "-m", "pip", "install", "--upgrade", "nazar"], capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            console.print(f"[green]Guncellendi! (pip)[/green]")
            return
        # --user ile dene
        r = _sp.run([_sys.executable, "-m", "pip", "install", "--upgrade", "--user", "nazar"], capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            console.print(f"[green]Guncellendi! (pip --user)[/green]")
            return
    except (FileNotFoundError, _sp.TimeoutExpired):
        pass

    console.print("[red]Otomatik guncelleme basarisiz.[/red]")
    console.print("[dim]Manuel: pipx upgrade nazar  veya  pip3 install --upgrade nazar[/dim]")


@ui_app.command("init")
def ui_init(
    path: Path = typer.Argument(".", help="Proje dizini"),
):
    """Ornek YAML UI test dosyalari olustur (.nazar/ui-tests/)."""
    from nazar.analyzers.yaml_ui_runner import YAMLUIGenerator

    console.print(Panel("[bold cyan]NAZAR UI INIT[/bold cyan] - Ornek UI Test Sablonu", expand=False))
    generator = YAMLUIGenerator(str(path))
    created = generator.generate()

    if created:
        table = Table(title="Olusturulan UI Test Dosyalari")
        table.add_column("#", style="dim")
        table.add_column("Dosya", style="green")
        for i, f in enumerate(created, 1):
            table.add_row(str(i), f)
        console.print(table)
        console.print(f"\n[green]{len(created)} dosya olusturuldu.[/green]")
    else:
        console.print("[yellow]Yeni dosya olusturulmadi (tum ekranlar icin dosya zaten mevcut veya ekran bulunamadi).[/yellow]")


@ui_app.command("generate")
def ui_generate(
    path: Path = typer.Argument(".", help="Proje dizini"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Cikti dizini (varsayilan: .nazar/ui-tests/)"),
):
    """Projedeki ekranlardan otomatik YAML UI test dosyasi uret."""
    from nazar.analyzers.yaml_ui_runner import YAMLUIGenerator

    console.print(Panel("[bold yellow]NAZAR UI GENERATE[/bold yellow] - Otomatik UI Test Uretimi", expand=False))
    generator = YAMLUIGenerator(str(path))
    created = generator.generate(output_dir=output)

    if created:
        table = Table(title="Uretilen UI Test Dosyalari")
        table.add_column("#", style="dim")
        table.add_column("Dosya", style="green")
        for i, f in enumerate(created, 1):
            table.add_row(str(i), f)
        console.print(table)
        console.print(f"\n[green]{len(created)} dosya uretildi.[/green]")
    else:
        console.print("[yellow]Yeni dosya uretilmedi (tum ekranlar icin dosya zaten mevcut veya ekran bulunamadi).[/yellow]")


@ui_app.command("check")
def ui_check(
    path: Path = typer.Argument(".", help="Proje dizini"),
):
    """YAML UI test dosyalarini kontrol et: syntax, hedefler, kapsam."""
    from nazar.analyzers.yaml_ui_runner import YAMLUITestRunner

    console.print(Panel("[bold green]NAZAR UI CHECK[/bold green] - UI Test Kontrolu", expand=False))
    runner = YAMLUITestRunner(str(path))

    checks = [
        ("Syntax Kontrolu", "yaml_ui_syntax"),
        ("Hedef Kontrolu", "yaml_ui_targets"),
        ("Kapsam Kontrolu", "yaml_ui_coverage"),
    ]

    table = Table(title="UI Test Kontrol Sonuclari")
    table.add_column("Kontrol", style="cyan")
    table.add_column("Sonuc", style="bold")
    table.add_column("Detay", style="white")

    all_passed = True
    for label, subtype in checks:
        passed, detail = runner.run_check(subtype, {})
        status = "[green]GECTI[/green]" if passed else "[red]BASARISIZ[/red]"
        if not passed:
            all_passed = False
        table.add_row(label, status, detail)

    console.print(table)
    if all_passed:
        console.print("\n[bold green]Tum kontroller basarili.[/bold green]")
    else:
        console.print("\n[bold red]Bazi kontroller basarisiz oldu.[/bold red]")


if __name__ == "__main__":
    app()
