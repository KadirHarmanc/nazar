"""Nazar CLI - Ana giris noktasi."""
import sys
import typer
import random
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Optional, List
import json
import time

from nazar.scanner.project_scanner import ProjectScanner
from nazar.planner.test_planner import TestPlanner
from nazar.runners.orchestrator import TestOrchestrator
from nazar.reporter.html_reporter import HTMLReporter
from nazar.tui.live_runner import LiveTestRunner
from nazar.planner.profiles import get_profile_priority_filter

# Severity seviyeleri: critical > high > medium > low
SEVERITY_LEVELS = {"critical": 4, "high": 3, "medium": 2, "low": 1}

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
    "nazar auto . --ci ile hizli CI/CD taramasi yapin (exit 0/1)",
    "nazar auto . --ci --fail-on critical ile sadece critical bulgularda fail verin",
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

rule_app = typer.Typer(
    name="rule",
    help="Kural olustur, dogrula, test et ve listele.",
)
app.add_typer(rule_app, name="rule")
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


def _filter_plan_by_changed_files(plan_dict: dict, changed_files: list) -> dict:
    """Test planini degisen dosyalara gore filtrele.

    Target alani degisen dosyalardan biriyle eslesen testleri tut.
    Target alani olmayan (genel) testleri de dahil et.
    """
    filtered = dict(plan_dict)
    tests = plan_dict.get("tests", [])
    changed_set = set(changed_files)

    kept = []
    for test in tests:
        target = test.get("target", "")
        # Target yoksa veya bossa -> genel test, her zaman dahil et
        if not target:
            kept.append(test)
            continue
        # Target degisen dosyalardan biriyse dahil et
        if target in changed_set:
            kept.append(test)
            continue
        # Target bir dizin veya partial path olabilir, prefix eslestirme yap
        for cf in changed_files:
            if cf.startswith(target) or target.startswith(cf):
                kept.append(test)
                break

    filtered["tests"] = kept
    # Toplam test sayisini guncelle
    filtered["total_tests"] = len(kept)
    return filtered


def _has_findings_at_level(results: list, fail_on: str) -> bool:
    """Belirtilen seviye ve ustunde basarisiz test var mi kontrol et.

    fail_on="critical" -> sadece critical failed varsa True
    fail_on="high"     -> critical veya high failed varsa True
    fail_on="medium"   -> critical, high veya medium failed varsa True
    fail_on="low"      -> herhangi bir failed varsa True
    """
    threshold = SEVERITY_LEVELS.get(fail_on, 2)  # varsayilan medium
    for r in results:
        if not r.get("passed", True):
            result_priority = r.get("priority", "medium").lower()
            result_level = SEVERITY_LEVELS.get(result_priority, 2)
            if result_level >= threshold:
                return True
    return False


def _run_auto(path: Path, report: str, opts: dict) -> list:
    """Auto komutu mantigi. Sonuclari dondurur (CI exit code icin)."""
    quiet, json_output = opts.get("quiet", False), opts.get("json_output", False)
    profile = opts.get("profile", "full")
    incremental = opts.get("incremental", False)
    show_ui = not quiet and not json_output

    from nazar.cache.scan_cache import ScanCache
    cache = ScanCache(str(path))

    if show_ui:
        profile_text = f" | Profil: {profile}" if profile != "full" else ""
        inc_text = " | Incremental" if incremental else ""
        console.print(Panel(
            f"[bold magenta]NAZAR AUTO[/bold magenta] - Tam Otonom Test{profile_text}{inc_text}\n"
            "Tara > Planla > Calistir > Raporla", expand=False))
    start = time.time()
    scan_result = _phase_scan(path, show_ui)

    # Incremental mod: sadece degisen dosyalari tara
    if incremental and cache.has_previous_scan():
        changed, new, deleted = cache.get_changed_files(scan_result.source_files)
        all_changed = changed + new
        if show_ui:
            console.print(f"\n  [bold cyan]Incremental:[/bold cyan] {len(changed)} degisen, {len(new)} yeni, {len(deleted)} silinen dosya")
        if not all_changed:
            if show_ui:
                console.print("  [green]Degisiklik yok, tarama atlaniyor.[/green]")
                prev = cache.get_last_scan_summary()
                if prev:
                    console.print(f"  [dim]Son tarama: {prev['grade']} ({prev['pass_rate']}%)[/dim]")
            elif not quiet:
                console.print("Degisiklik tespit edilemedi, tarama atlaniyor.")
            return []
        if show_ui:
            console.print(f"  [yellow]{len(all_changed)} dosya icin testler calistirilacak[/yellow]")
        # Plan olustur ve testleri changed dosyalara gore filtrele
        _test_plan, plan_dict = _phase_plan(scan_result, show_ui, profile=profile)
        plan_dict = _filter_plan_by_changed_files(plan_dict, all_changed)
        if show_ui:
            filtered_count = len(plan_dict.get("tests", []))
            console.print(f"  [dim]{filtered_count} test filtrelendi (degisen dosyalar icin)[/dim]")
    elif incremental and not cache.has_previous_scan():
        if show_ui:
            console.print("\n  [yellow]Onceki tarama bulunamadi, tam tarama yapiliyor...[/yellow]")
        _test_plan, plan_dict = _phase_plan(scan_result, show_ui, profile=profile)
    else:
        _test_plan, plan_dict = _phase_plan(scan_result, show_ui, profile=profile)

    orchestrator = TestOrchestrator(str(path), plan_dict)
    results = _phase_execute(orchestrator, plan_dict, json_output, quiet, show_ui)

    # --min-confidence filtreleme
    min_conf = opts.get("min_confidence", 50)
    show_ignored = opts.get("show_ignored", False)
    if min_conf > 0:
        filtered_results = []
        ignored_results = []
        for r in results:
            conf = r.get("confidence", 100)
            if isinstance(conf, (int, float)) and conf < min_conf:
                ignored_results.append(r)
            else:
                filtered_results.append(r)
        if ignored_results and show_ui:
            console.print(f"\n  [dim]{len(ignored_results)} sonuc guven esigi altinda (min_confidence={min_conf}%) filtrelendi[/dim]")
        if show_ignored and ignored_results and show_ui:
            console.print(f"\n  [yellow]Filtrelenen sonuclar (guven < {min_conf}%):[/yellow]")
            for ir in ignored_results[:20]:
                icon = "[green]OK[/green]" if ir.get("passed") else "[red]XX[/red]"
                console.print(f"    {icon} {ir.get('name', '?')[:50]}  [dim]guven: {ir.get('confidence', '?')}%[/dim]")
            if len(ignored_results) > 20:
                console.print(f"    [dim]...ve {len(ignored_results) - 20} sonuc daha[/dim]")
        results = filtered_results

    _phase_report(results, plan_dict, report, json_output, quiet, show_ui, start)

    # Scan cache kaydet
    cache.save_scan_result(results, plan_dict, profile, time.time() - start)
    cache.save_file_hashes(scan_result.source_files)

    return results


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
    ci: bool = typer.Option(False, "--ci", help="CI modu kisayolu: profile=ci, json=true, quiet=true, fail-on=high"),
    fail_on: Optional[str] = typer.Option(None, "--fail-on", help="Exit code 1 esigi: critical, high, medium, low"),
    incremental: bool = typer.Option(False, "--incremental", help="Sadece degisen dosyalari tara"),
    github_pr: bool = typer.Option(False, "--github-pr", help="Sonuclari GitHub PR comment olarak gonder"),
    sarif: Optional[str] = typer.Option(None, "--sarif", help="SARIF cikti dosyasi (GitHub Code Scanning)"),
    live: bool = typer.Option(False, "--live", help="Canli web raporu baslat (localhost:5555)"),
    live_port: int = typer.Option(5555, "--live-port", help="Canli web raporu portu"),
    min_confidence: int = typer.Option(50, "--min-confidence", help="Minimum guven esigi (0-100, varsayilan 50). Alttaki sonuclar filtrelenir."),
    show_ignored: bool = typer.Option(False, "--show-ignored", help="Ignore edilen sonuclari da goster"),
):
    """Tek komutla her seyi yap: tara, planla, calistir, raporla.

    CI/CD kullanimi:
      nazar auto . --ci                    # critical+high bulursa exit 1
      nazar auto . --ci --fail-on critical # sadece critical bulursa exit 1
      nazar auto . --profile ci --fail-on high --json --quiet

    Canli web raporu:
      nazar auto . --live                  # localhost:5555'te canli rapor
      nazar auto . --live --live-port 8080 # farkli port
    """
    opts = ctx.obj or {}

    # --ci kisayolu: profile=ci, json=true, quiet=true, fail-on=high (varsayilan)
    if ci:
        opts["profile"] = "ci"
        opts["json_output"] = True
        opts["quiet"] = True
        if fail_on is None:
            fail_on = "high"  # --ci varsayilani: critical + high = fail
    else:
        opts["profile"] = profile or "full"

    opts["incremental"] = incremental
    opts["min_confidence"] = min_confidence
    opts["show_ignored"] = show_ignored

    # Port dogrulama
    if live and not (1024 <= live_port <= 65535):
        console.print(f"[red]Gecersiz port: {live_port}. Port 1024-65535 araliginda olmalidir.[/red]")
        raise SystemExit(1)

    # --live: tarama sirasinda canli web sunucusu baslat
    live_server = None
    if live:
        from nazar.live.server import NazarLiveServer
        live_server = NazarLiveServer(port=live_port)
        live_server.set_status("scanning")
        live_server.start()
        console.print(f"[cyan]Canli rapor: http://localhost:{live_port}[/cyan]")

    results = _run_auto(path, report, opts)

    # Live sunucuya son sonuclari yukle
    if live_server:
        live_server.set_results(results, {})
        live_server.set_status("done")
        console.print(f"[cyan]Canli rapor hazir: http://localhost:{live_port}[/cyan]")
        console.print(f"[dim]Kapatmak icin Ctrl+C[/dim]")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            live_server.stop()
            console.print("[dim]Canli rapor durduruldu.[/dim]")

    if github_pr or sarif:
        # Sonuclari tekrar uret (hafif)
        scan_result = _phase_scan(path, False)
        _test_plan, plan_dict = _phase_plan(scan_result, False)
        orchestrator = TestOrchestrator(str(path), plan_dict)
        results_for_integrations = orchestrator.run_all()

        from nazar.integrations.github_pr import GitHubPRReporter
        reporter = GitHubPRReporter()

        if github_pr:
            if reporter.post_comment(results_for_integrations, plan_dict):
                console.print("[green]GitHub PR comment gonderildi[/green]")
            else:
                console.print("[yellow]PR comment gonderilemedi (token/repo/PR bilgisi eksik)[/yellow]")

        if sarif:
            sarif_content = reporter.generate_sarif(results_for_integrations)
            Path(sarif).write_text(sarif_content)
            console.print(f"[green]SARIF cikti: {sarif}[/green]")

    # --fail-on: belirtilen seviyede veya ustunde basarisiz test varsa exit 1
    if fail_on and results:
        fail_on_lower = fail_on.lower()
        if fail_on_lower not in SEVERITY_LEVELS:
            console.print(f"[red]Gecersiz --fail-on degeri: {fail_on}. Gecerli: critical, high, medium, low[/red]")
            raise SystemExit(2)
        if _has_findings_at_level(results, fail_on_lower):
            failed_at_level = [
                r for r in results
                if not r.get("passed", True)
                and SEVERITY_LEVELS.get(r.get("priority", "medium").lower(), 2) >= SEVERITY_LEVELS[fail_on_lower]
            ]
            if not opts.get("json_output"):
                console.print(
                    f"[red]FAIL: {len(failed_at_level)} bulgu ({fail_on_lower}+ seviye)[/red]"
                )
            raise SystemExit(1)


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


@ui_app.command("run")
def ui_run(
    path: str = typer.Argument(..., help="Proje veya YAML dosya yolu"),
    device: str = typer.Option(None, "--device", "-d", help="Cihaz ID"),
    live: bool = typer.Option(True, "--live/--no-live", help="Canli TUI gosterimi"),
    convert: bool = typer.Option(False, "--convert", help="Nazar YAML'i Maestro formatina cevir"),
):
    """YAML UI testlerini Maestro ile cihazda calistir."""
    import tempfile
    import yaml as _yaml

    from nazar.executors.device_manager import (
        is_maestro_installed,
        list_devices,
        get_active_device,
    )
    from nazar.executors.maestro_executor import MaestroExecutor
    from nazar.executors.flow_converter import convert_nazar_to_maestro
    from nazar.tui.runtime_viewer import RuntimeViewer, run_with_viewer

    console.print(Panel("[bold green]NAZAR UI RUN[/bold green] - Maestro ile UI Test", expand=False))

    # 1. Maestro kurulu mu?
    if not is_maestro_installed():
        console.print("[red]Maestro kurulu degil.[/red]")
        console.print()
        console.print("[bold]Kurmak icin:[/bold]")
        console.print("  [cyan]brew install maestro[/cyan]  [dim](macOS)[/dim]")
        console.print('  [cyan]curl -Ls "https://get.maestro.mobile.dev" | bash[/cyan]  [dim](Linux/macOS)[/dim]')
        raise typer.Exit(1)

    console.print("  [green]Maestro:[/green] kurulu")

    # 2. Bagli cihaz/emulator var mi?
    devices = list_devices()
    active_device = get_active_device()
    device_name = device or ""
    device_info = {}

    if device:
        # Kullanici belirli bir cihaz belirtti
        matched = [d for d in devices if d.get("serial") == device]
        if matched:
            device_info = matched[0]
            device_name = device
        else:
            device_name = device
            device_info = {"name": device, "platform": "?", "status": "?"}
        console.print(f"  [green]Cihaz:[/green] {device_name}")
    elif active_device:
        device_name = active_device.get("serial", "")
        device_info = active_device
        console.print(f"  [green]Cihaz:[/green] {device_info.get('name', device_name)}")
    else:
        console.print("[yellow]Bagli cihaz veya emulator bulunamadi.[/yellow]")
        console.print("[dim]Android: adb devices | iOS: xcrun simctl list devices booted[/dim]")
        raise typer.Exit(1)

    # 3. YAML dosyalarini bul
    resolved = Path(path).resolve()
    yaml_files = []

    if resolved.is_file() and resolved.suffix in (".yml", ".yaml"):
        yaml_files = [str(resolved)]
    elif resolved.is_dir():
        nazar_dir = resolved / ".nazar" / "ui-tests"
        if nazar_dir.exists():
            yaml_files = sorted(
                [str(f) for f in nazar_dir.glob("*.yml")]
                + [str(f) for f in nazar_dir.glob("*.yaml")]
            )
        if not yaml_files:
            yaml_files = sorted(
                [str(f) for f in resolved.glob("*.yml")]
                + [str(f) for f in resolved.glob("*.yaml")]
            )

    if not yaml_files:
        console.print(f"[red]YAML test dosyasi bulunamadi: {resolved}[/red]")
        console.print("[dim].nazar/ui-tests/ dizinine bakildi. 'nazar ui init' ile olusturun.[/dim]")
        raise typer.Exit(1)

    console.print(f"\n  [bold]{len(yaml_files)} test dosyasi bulundu[/bold]")

    # 4. Proje dizinini belirle
    if resolved.is_file():
        project_path = str(resolved.parent)
    else:
        project_path = str(resolved)

    # 5. Testleri calistir
    total = len(yaml_files)
    results = []

    for i, yf in enumerate(yaml_files, 1):
        fname = Path(yf).name
        console.print(f"\n  [bold cyan][{i}/{total}][/bold cyan] {fname}")

        run_file = yf
        tmp_file = None

        if convert:
            try:
                maestro_content = convert_nazar_to_maestro(yf)
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yml", prefix="maestro_",
                    delete=False, dir=str(Path(yf).parent),
                )
                tmp.write(maestro_content)
                tmp.close()
                tmp_file = tmp.name
                run_file = tmp.name
                console.print("    [dim]Maestro formatina cevirildi[/dim]")
            except Exception as exc:
                console.print(f"    [yellow]Ceviri hatasi: {exc}[/yellow]")

        step_start = time.time()
        try:
            executor = MaestroExecutor(
                project_path=project_path,
                yaml_file=run_file,
                device=device_name or None,
            )

            if live:
                # Nazar adimlarini oku (viewer icin)
                try:
                    with open(yf, "r", encoding="utf-8") as f:
                        nazar_data = _yaml.safe_load(f)
                    steps = nazar_data.get("steps", []) if isinstance(nazar_data, dict) else []
                except Exception:
                    steps = []

                if steps:
                    run_with_viewer(
                        executor=executor,
                        steps=steps,
                        device_info=device_info,
                        console=console,
                    )
                else:
                    executor.run()
            else:
                executor.run()

            summary = executor.get_summary()
            duration = summary.get("duration", time.time() - step_start)
            success = summary.get("success", True)

            status = "[green]GECTI[/green]" if success else "[red]BASARISIZ[/red]"
            console.print(f"    {status} [dim]({duration:.1f}s)[/dim]")
            results.append({"file": fname, "passed": success, "duration": duration})

        except Exception as exc:
            duration = time.time() - step_start
            console.print(f"    [red]HATA: {exc}[/red]")
            results.append({"file": fname, "passed": False, "duration": duration})
        finally:
            if tmp_file and Path(tmp_file).exists():
                try:
                    Path(tmp_file).unlink()
                except OSError:
                    pass

    # 6. Ozet
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    total_dur = sum(r["duration"] for r in results)

    console.print()
    summary_table = Table(title="UI Test Sonuclari", show_header=True)
    summary_table.add_column("#", style="dim", width=4)
    summary_table.add_column("Test", style="white")
    summary_table.add_column("Sonuc", width=10)
    summary_table.add_column("Sure", width=8, justify="right")

    for i, r in enumerate(results, 1):
        status = "[green]GECTI[/green]" if r["passed"] else "[red]KALDI[/red]"
        summary_table.add_row(str(i), r["file"], status, f"{r['duration']:.1f}s")

    console.print(summary_table)
    rate = (passed / total * 100) if total > 0 else 0
    gs = "green" if rate >= 80 else "yellow" if rate >= 60 else "red"
    console.print(Panel(
        f"[{gs}]{passed}/{total} gecti ({rate:.0f}%)[/{gs}]  |  "
        f"[green]{passed} basarili[/green]  |  [red]{failed} basarisiz[/red]  |  "
        f"[dim]Toplam: {total_dur:.1f}s[/dim]",
        title="[bold cyan]SONUC[/bold cyan]", border_style="cyan",
    ))

    if failed > 0:
        raise typer.Exit(1)


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


@app.command()
def serve(
    path: Path = typer.Argument(".", help="Proje dizini (son tarama sonuclarini kullanir)"),
    port: int = typer.Option(5555, "--port", "-p", help="Sunucu portu"),
):
    """Son tarama sonuclarini canli web sayfasinda goster.

    Onceki taramada kaydedilen .nazar/last-scan.json dosyasini okur
    ve localhost uzerinden gorsel rapor sunar.

    Kullanim:
      nazar serve                     # localhost:5555
      nazar serve ~/MyProject -p 8080 # farkli proje ve port
    """
    from nazar.live.server import NazarLiveServer
    from nazar.cache.scan_cache import ScanCache

    resolved_path = Path(path).resolve()
    cache = ScanCache(str(resolved_path))

    if not cache.has_previous_scan():
        console.print(f"[red]Tarama sonucu bulunamadi: {resolved_path}[/red]")
        console.print("[dim]Once 'nazar auto <yol>' ile tarama yapin.[/dim]")
        raise typer.Exit(1)

    summary = cache.get_last_scan_summary()
    console.print(Panel(
        f"[bold cyan]NAZAR SERVE[/bold cyan] - Canli Web Raporu\n"
        f"Proje: {resolved_path.name}  |  Son tarama: {summary.get('grade', '?')} ({summary.get('pass_rate', 0)}%)\n"
        f"http://localhost:{port}", expand=False))

    server = NazarLiveServer.from_cache(str(resolved_path), port=port)
    console.print(f"[green]Sunucu baslatildi: http://localhost:{port}[/green]")
    console.print("[dim]Durdurmak icin Ctrl+C[/dim]")

    try:
        server.start_blocking()
    except KeyboardInterrupt:
        pass
    console.print("[dim]Sunucu durduruldu.[/dim]")


# === Rule (Kural) Komutlari ===


@rule_app.command("create")
def rule_create(
    output: str = typer.Option("custom-rules.yaml", "--output", "-o", help="Cikti YAML dosyasi"),
):
    """Interaktif kural olusturucu. Adim adim yeni kural tanimlayin."""
    from nazar.tools.rule_builder import RuleBuilder

    console.print(Panel("[bold cyan]NAZAR RULE CREATE[/bold cyan] - Yeni Kural Olustur", expand=False))
    console.print("[dim]Kural bilgilerini adim adim girin.[/dim]\n")

    builder = RuleBuilder()

    try:
        rule = builder.create_rule()
    except ValueError as e:
        console.print(f"\n[red]Hata: {e}[/red]")
        raise typer.Exit(1)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Iptal edildi.[/dim]")
        raise typer.Exit(0)

    # Dogrula
    errors = builder.validate_rule(rule)
    if errors:
        console.print("\n[red]Kural dogrulama hatalari:[/red]")
        for err in errors:
            console.print(f"  [red]- {err}[/red]")
        raise typer.Exit(1)

    console.print("\n[green]Kural gecerli![/green]")

    # Onizleme
    table = Table(title="Kural Onizleme")
    table.add_column("Alan", style="cyan")
    table.add_column("Deger", style="white")
    table.add_row("ID", rule["id"])
    table.add_row("Pattern", rule["pattern"])
    table.add_row("Mesaj", rule["message"])
    table.add_row("Severity", rule["severity"])
    table.add_row("Diller", ", ".join(rule.get("languages", [])) or "Tumu")
    table.add_row("Dosya Kaliplari", ", ".join(rule.get("file_patterns", [])) or "Tumu")
    if rule.get("description"):
        table.add_row("Aciklama", rule["description"])
    if rule.get("fix"):
        table.add_row("Fix", rule["fix"])
    console.print(table)

    # Kaydet
    saved = builder.save_rule(rule, output)
    console.print(f"\n[green]Kural kaydedildi: {saved}[/green]")


@rule_app.command("validate")
def rule_validate(
    path: str = typer.Argument(..., help="YAML kural dosyasi yolu"),
):
    """YAML kural dosyasini dogrula: regex, zorunlu alanlar, tekrar eden ID'ler."""
    from nazar.tools.rule_validator import validate_yaml_rules

    console.print(Panel("[bold yellow]NAZAR RULE VALIDATE[/bold yellow] - Kural Dosyasi Dogrulama", expand=False))

    errors = validate_yaml_rules(path)

    if not errors:
        console.print(f"\n[bold green]Dosya gecerli: {path}[/bold green]")
        # Kural sayisini goster
        try:
            import yaml as _yaml
            with open(path, "r") as f:
                data = _yaml.safe_load(f)
            count = len(data.get("rules", [])) if data else 0
            console.print(f"[dim]{count} kural bulundu.[/dim]")
        except Exception:
            pass
    else:
        console.print(f"\n[bold red]{len(errors)} hata bulundu: {path}[/bold red]\n")
        for i, err in enumerate(errors, 1):
            if err.startswith("Uyari:"):
                console.print(f"  [yellow]{i}. {err}[/yellow]")
            else:
                console.print(f"  [red]{i}. {err}[/red]")
        raise typer.Exit(1)


@rule_app.command("test")
def rule_test(
    rule_file: str = typer.Argument(..., help="YAML kural dosyasi"),
    project_path: Path = typer.Argument(".", help="Test edilecek proje dizini"),
    rule_id: Optional[str] = typer.Option(None, "--rule", "-r", help="Sadece belirli bir kural ID'sini test et"),
):
    """Kural dosyasini bir proje uzerinde test et, eslesmeleri goster."""
    from nazar.tools.rule_builder import RuleBuilder
    from nazar.tools.rule_validator import validate_yaml_rules

    console.print(Panel("[bold green]NAZAR RULE TEST[/bold green] - Kural Test", expand=False))

    # Once dogrula
    errors = validate_yaml_rules(rule_file)
    if errors:
        real_errors = [e for e in errors if not e.startswith("Uyari:")]
        if real_errors:
            console.print(f"[red]Kural dosyasi gecersiz: {len(real_errors)} hata[/red]")
            for err in real_errors:
                console.print(f"  [red]- {err}[/red]")
            raise typer.Exit(1)

    # Kurallari yukle
    try:
        import yaml as _yaml
        with open(rule_file, "r") as f:
            data = _yaml.safe_load(f)
        rules = data.get("rules", []) if data else []
    except Exception as e:
        console.print(f"[red]Dosya okunamadi: {e}[/red]")
        raise typer.Exit(1)

    if not rules:
        console.print("[yellow]Kural bulunamadi.[/yellow]")
        raise typer.Exit(0)

    # Belirli bir kural secildiyse filtrele
    if rule_id:
        rules = [r for r in rules if r.get("id") == rule_id]
        if not rules:
            console.print(f"[red]Kural bulunamadi: {rule_id}[/red]")
            raise typer.Exit(1)

    total_matches = 0
    for rule in rules:
        rid = rule.get("id", "?")
        console.print(f"\n[bold cyan]Kural: {rid}[/bold cyan] [dim]({rule.get('severity', 'medium')})[/dim]")
        console.print(f"  [dim]Pattern: {rule.get('pattern', '')}[/dim]")

        try:
            matches = RuleBuilder.test_rule(rule, str(project_path))
        except Exception as e:
            console.print(f"  [red]Hata: {e}[/red]")
            continue

        if matches:
            console.print(f"  [yellow]{len(matches)} eslesme bulundu:[/yellow]\n")
            table = Table(show_header=True)
            table.add_column("#", style="dim", width=4)
            table.add_column("Dosya", style="white")
            table.add_column("Satir", style="cyan", width=6)
            table.add_column("Eslesme", style="yellow")
            table.add_column("Icerik", style="dim")

            for i, m in enumerate(matches[:20], 1):
                table.add_row(
                    str(i),
                    m["file"],
                    str(m["line"]),
                    m["match"][:30],
                    m["content"][:50],
                )
            console.print(table)

            if len(matches) > 20:
                console.print(f"  [dim]...ve {len(matches) - 20} eslesme daha[/dim]")

            total_matches += len(matches)
        else:
            console.print("  [green]Eslesme yok - kural bu projede tetiklenmiyor.[/green]")

    console.print(f"\n[bold]Toplam: {total_matches} eslesme ({len(rules)} kural)[/bold]")


@rule_app.command("list")
def rule_list(
    rules_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Ozel kural dizini"),
):
    """Tum kurallari listele: yerlesik + ozel YAML kurallar."""
    from nazar.tools.rule_builder import RuleBuilder

    console.print(Panel("[bold magenta]NAZAR RULE LIST[/bold magenta] - Kural Listesi", expand=False))

    all_rules = RuleBuilder.list_rules(rules_dir)

    if not all_rules:
        console.print("[yellow]Hic kural bulunamadi.[/yellow]")
        console.print("[dim]Ozel kural olusturmak icin: nazar rule create[/dim]")
        return

    # Kaynaklara gore grupla
    builtin = [r for r in all_rules if r["source"] == "builtin"]
    custom = [r for r in all_rules if r["source"] != "builtin"]

    if builtin:
        table = Table(title=f"Yerlesik Kurallar ({len(builtin)})")
        table.add_column("ID", style="cyan")
        table.add_column("Severity", style="yellow")
        table.add_column("Aciklama", style="white")
        for r in builtin:
            sev = r["severity"]
            sev_style = {"critical": "bold red", "high": "yellow", "medium": "cyan", "low": "dim"}.get(sev, "dim")
            table.add_row(r["id"], f"[{sev_style}]{sev.upper()}[/{sev_style}]", r["message"])
        console.print(table)

    if custom:
        console.print()
        table = Table(title=f"Ozel Kurallar ({len(custom)})")
        table.add_column("ID", style="cyan")
        table.add_column("Severity", style="yellow")
        table.add_column("Kaynak", style="dim")
        table.add_column("Aciklama", style="white")
        table.add_column("Diller", style="green")
        for r in custom:
            sev = r["severity"]
            sev_style = {"critical": "bold red", "high": "yellow", "medium": "cyan", "low": "dim"}.get(sev, "dim")
            langs = ", ".join(r.get("languages", [])) or "Tumu"
            table.add_row(r["id"], f"[{sev_style}]{sev.upper()}[/{sev_style}]", r["source"], r["message"], langs)
        console.print(table)

    console.print(f"\n[bold]Toplam: {len(all_rules)} kural ({len(builtin)} yerlesik + {len(custom)} ozel)[/bold]")
    if not custom:
        console.print("[dim]Ozel kural olusturmak icin: nazar rule create[/dim]")


# === Batch Komutlari ===

@app.command()
def batch(
    ctx: typer.Context,
    paths: List[Path] = typer.Argument(..., help="Taranacak proje dizinleri"),
    profile: str = typer.Option("ci", "--profile", "-p", help="Test profili"),
    report: Optional[str] = typer.Option(None, "--report", "-r", help="Markdown rapor dosyasi"),
    json_output: bool = typer.Option(False, "--json", help="JSON formatinda cikti"),
):
    """Birden fazla projeyi sirayla tara, konsolide rapor uret.

    Kullanim:
      nazar batch ~/proje1 ~/proje2 ~/proje3
      nazar batch ~/proje1 ~/proje2 --profile security
      nazar batch ~/proje1 ~/proje2 --report batch-report.md
    """
    from nazar.batch.scanner import BatchScanner

    project_paths = [str(p) for p in paths]

    if not json_output:
        console.print(Panel(
            f"[bold magenta]NAZAR BATCH[/bold magenta] - Coklu Proje Taramasi\n"
            f"Profil: {profile}  |  {len(project_paths)} proje", expand=False))

    scanner = BatchScanner(project_paths, profile=profile)

    if not json_output:
        console.print()
        for i, p in enumerate(project_paths, 1):
            console.print(f"  [dim][{i}/{len(project_paths)}][/dim] {Path(p).name}")
        console.print()

    results = scanner.scan_all()

    if json_output:
        summary = scanner.get_consolidated_summary()
        sys.stdout.write(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
        return

    # Sonuc tablosu
    table = Table(title="Batch Tarama Sonuclari", show_header=True)
    table.add_column("Proje", style="cyan")
    table.add_column("Not", width=5, justify="center")
    table.add_column("Oran", width=8, justify="right")
    table.add_column("Gecen", width=6, justify="right", style="green")
    table.add_column("Kalan", width=6, justify="right", style="red")
    table.add_column("Sure", width=8, justify="right", style="dim")
    table.add_column("Durum", width=20)

    for path_key, data in results.items():
        grade = data["grade"]
        gs = "green" if data["pass_rate"] >= 80 else "yellow" if data["pass_rate"] >= 60 else "red"
        if data.get("error"):
            status = "[red]HATA[/red]"
        else:
            status = f"[{gs}]OK[/{gs}]"
        table.add_row(
            data["project_name"],
            f"[{gs}]{grade}[/{gs}]",
            f"[{gs}]{data['pass_rate']}%[/{gs}]",
            str(data["passed"]),
            str(data["failed"]),
            f"{data['duration']}s",
            status,
        )

    console.print(table)

    # Genel ozet
    summary = scanner.get_consolidated_summary()
    overall_gs = "green" if summary["pass_rate"] >= 80 else "yellow" if summary["pass_rate"] >= 60 else "red"
    console.print(Panel(
        f"[bold {overall_gs}]Genel Not: {summary['grade']} ({summary['pass_rate']}%)[/bold {overall_gs}]  |  "
        f"[green]{summary['total_passed']} gecti[/green]  |  "
        f"[red]{summary['total_failed']} kaldi[/red]  |  "
        f"[dim]{summary['project_count']} proje  |  {summary['duration']}s[/dim]",
        title="[bold cyan]BATCH SONUC[/bold cyan]", border_style="cyan",
    ))

    # Markdown rapor
    if report:
        md = scanner.generate_report()
        Path(report).write_text(md, encoding="utf-8")
        console.print(f"\n[green]Rapor kaydedildi: {report}[/green]")

    # Hata olan projeler
    errors = [d for d in results.values() if d.get("error")]
    if errors:
        console.print(f"\n[yellow]{len(errors)} projede hata olustu:[/yellow]")
        for e in errors:
            console.print(f"  [red]-[/red] {e['project_name']}: {e['error'][:60]}")


# === Coverage Komutu ===


@app.command()
def coverage(
    ctx: typer.Context,
    path: Path = typer.Argument(".", help="Proje dizini"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="JSON cikti dosyasi"),
    profile: str = typer.Option("full", "--profile", "-p", help="Test profili"),
):
    """Projeyi tara ve test kapsami raporu olustur.

    Kategori bazli kapsam, dosya bazli sorun yogunlugu,
    guven dagilimi ve onceki taramayla trend verisi gosterir.

    Kullanim:
      nazar coverage                         # mevcut dizin
      nazar coverage ~/MyProject             # belirli proje
      nazar coverage . -o coverage.json      # JSON dosyaya kaydet
    """
    from nazar.reporters.coverage_reporter import CoverageReporter
    from nazar.cache.scan_cache import ScanCache

    opts = ctx.obj or {}
    json_output = opts.get("json_output", False)
    quiet = opts.get("quiet", False)
    show_ui = not quiet and not json_output

    if show_ui:
        console.print(Panel("[bold cyan]NAZAR COVERAGE[/bold cyan] - Test Kapsami Raporu", expand=False))

    # Tarama yap
    start = time.time()
    scan_result = _phase_scan(path, show_ui)
    _test_plan, plan_dict = _phase_plan(scan_result, show_ui, profile=profile)
    plan_dict["project_path"] = str(Path(path).resolve())
    orchestrator = TestOrchestrator(str(path), plan_dict)
    results = _phase_execute(orchestrator, plan_dict, json_output, quiet, show_ui)

    # Coverage raporu olustur
    reporter = CoverageReporter()
    cov_json = reporter.generate(results, plan_dict, output)
    cov_data = json.loads(cov_json)

    if json_output:
        sys.stdout.write(cov_json + "\n")
        return

    # Ozet
    summary = cov_data["summary"]
    gs = "green" if summary["pass_rate"] >= 80 else "yellow" if summary["pass_rate"] >= 60 else "red"
    console.print(Panel(
        f"[bold {gs}]Not: {summary['grade']} ({summary['pass_rate']}%)[/bold {gs}]  |  "
        f"[green]{summary['passed']} passed[/green]  |  "
        f"[red]{summary['failed']} failed[/red]  |  "
        f"[dim]{summary['total_checks']} kontrol[/dim]",
        title="[bold cyan]KAPSAM OZETI[/bold cyan]", border_style="cyan",
    ))

    # Kategori tablosu
    cat_data = cov_data.get("category_coverage", {})
    if cat_data:
        cat_table = Table(title="Kategori Kapsami", show_header=True)
        cat_table.add_column("Kategori", style="cyan", width=20)
        cat_table.add_column("Toplam", justify="center", width=8)
        cat_table.add_column("Gecen", justify="center", width=8, style="green")
        cat_table.add_column("Kalan", justify="center", width=8, style="red")
        cat_table.add_column("Oran", justify="right", width=8)
        cat_table.add_column("Durum", width=16)
        for cat, info in cat_data.items():
            rate = info["pass_rate"]
            rs = "green" if rate >= 80 else "yellow" if rate >= 60 else "red"
            status_map = {"clean": "[green]Temiz[/green]", "partial": "[yellow]Kismi[/yellow]", "needs_attention": "[red]Dikkat[/red]"}
            cat_table.add_row(
                cat.upper(), str(info["total"]), str(info["passed"]), str(info["failed"]),
                f"[{rs}]{rate}%[/{rs}]", status_map.get(info["status"], info["status"]),
            )
        console.print(cat_table)

    # Guven dagilimi
    conf = cov_data.get("confidence_distribution", {})
    if conf.get("total_findings", 0) > 0:
        conf_table = Table(title="Guven Dagilimi (Basarisiz Testler)", show_header=True)
        conf_table.add_column("Seviye", style="cyan", width=20)
        conf_table.add_column("Sayi", justify="center", width=10)
        conf_table.add_column("Aciklama", width=30)
        for level in ("high", "medium", "low"):
            data = conf.get(level, {})
            conf_table.add_row(
                level.upper(), str(data.get("count", 0)), data.get("label", ""),
            )
        conf_table.add_row("", "", "")
        conf_table.add_row("[bold]Ortalama Guven[/bold]", f"[bold]{conf.get('average_confidence', 0)}%[/bold]", "")
        console.print(conf_table)

    # Dosya yogunlugu (en sorunlu 10 dosya)
    file_density = cov_data.get("file_issue_density", [])
    if file_density:
        file_table = Table(title="En Sorunlu Dosyalar", show_header=True)
        file_table.add_column("#", style="dim", width=4)
        file_table.add_column("Dosya", ratio=3)
        file_table.add_column("Sorun", justify="center", width=8)
        file_table.add_column("En Yuksek", width=10)
        for i, fd in enumerate(file_density[:10], 1):
            sev = fd["highest_severity"]
            ss = {"critical": "bold red", "high": "yellow", "medium": "cyan", "low": "dim"}.get(sev, "dim")
            file_table.add_row(str(i), fd["file"], str(fd["issue_count"]), f"[{ss}]{sev.upper()}[/{ss}]")
        console.print(file_table)

    # Trend
    trend = cov_data.get("trend")
    if trend and trend.get("available"):
        delta = trend["delta_rate"]
        delta_sign = "+" if delta > 0 else ""
        delta_color = "green" if delta > 0 else "red" if delta < 0 else "dim"
        direction_map = {"improving": "Yukseliyor", "regressing": "Dusuyor", "stable": "Sabit"}
        console.print(Panel(
            f"[bold]Onceki:[/bold] {trend['previous']['grade']} ({trend['previous']['pass_rate']}%)  "
            f"[bold]Simdi:[/bold] {trend['current']['grade']} ({trend['current']['pass_rate']}%)  "
            f"[{delta_color}]{delta_sign}{delta}%[/{delta_color}]  "
            f"| {direction_map.get(trend['direction'], trend['direction'])}\n"
            f"[green]{trend['fixed_count']} duzeltildi[/green]  |  "
            f"[red]{trend['new_issues_count']} yeni sorun[/red]",
            title="[bold yellow]TREND[/bold yellow]", border_style="yellow",
        ))

    duration = time.time() - start
    console.print(f"\n[dim]Sure: {duration:.1f}s[/dim]")

    if output:
        console.print(f"[green]Rapor kaydedildi: {output}[/green]")

    _show_tip()


# === Baseline Komutlari ===

baseline_app = typer.Typer(
    name="baseline",
    help="Baseline yonetimi: kaydet, karsilastir, kontrol et.",
)
app.add_typer(baseline_app, name="baseline")


@baseline_app.command("save")
def baseline_save(
    path: Path = typer.Argument(".", help="Proje dizini"),
    profile: str = typer.Option("full", "--profile", "-p", help="Test profili"),
):
    """Mevcut tarama sonuclarini baseline olarak kaydet.

    Baseline, projenin kabul edilen referans durumunu belirler.
    Sonraki 'nazar baseline check' komutlari bu baseline ile karsilastirma yapar.

    Kullanim:
      nazar baseline save                  # mevcut dizin
      nazar baseline save ~/MyProject      # belirli proje
    """
    from nazar.cache.scan_cache import ScanCache

    resolved = Path(path).resolve()
    cache = ScanCache(str(resolved))

    # Onceki tarama var mi?
    if cache.has_previous_scan():
        results = cache.get_last_scan_results()
        if results:
            cache.save_baseline(results)
            summary = cache.get_last_scan_summary()
            console.print(Panel(
                f"[bold green]BASELINE KAYDEDILDI[/bold green]\n"
                f"Proje: {resolved.name}\n"
                f"Not: {summary.get('grade', '?')} ({summary.get('pass_rate', 0)}%)\n"
                f"Test: {summary.get('passed', 0)} gecti / {summary.get('failed', 0)} kaldi\n"
                f"Dosya: .nazar/baseline.json",
                expand=False, border_style="green",
            ))
            return

    # Onceki tarama yoksa yeni tarama yap
    console.print("[yellow]Onceki tarama bulunamadi, yeni tarama yapiliyor...[/yellow]")

    from nazar.scanner.project_scanner import ProjectScanner as _PS
    from nazar.planner.test_planner import TestPlanner as _TP
    from nazar.runners.orchestrator import TestOrchestrator as _TO

    scanner = _PS(str(resolved))
    scan_result = scanner.scan()
    planner = _TP(scan_result, profile=profile)
    test_plan = planner.create_plan()
    plan_dict = test_plan.to_dict()
    orchestrator = _TO(str(resolved), plan_dict)
    results = orchestrator.run_all()

    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    rate = (passed / total * 100) if total else 0

    cache.save_scan_result(results, plan_dict, profile, 0)
    cache.save_baseline(results)

    console.print(Panel(
        f"[bold green]BASELINE KAYDEDILDI[/bold green]\n"
        f"Proje: {resolved.name}\n"
        f"Not: {cache._grade(rate)} ({rate:.1f}%)\n"
        f"Test: {passed} gecti / {total - passed} kaldi\n"
        f"Dosya: .nazar/baseline.json",
        expand=False, border_style="green",
    ))


@baseline_app.command("check")
def baseline_check(
    path: Path = typer.Argument(".", help="Proje dizini"),
    profile: str = typer.Option("full", "--profile", "-p", help="Test profili"),
    json_out: bool = typer.Option(False, "--json", help="JSON formatinda cikti"),
):
    """Mevcut taramayi baseline ile karsilastir.

    Gerileme (regression) varsa exit code 1 dondurur.
    CI/CD pipeline'da baseline kalitesini korumak icin kullanin.

    Kullanim:
      nazar baseline check                 # mevcut dizin
      nazar baseline check ~/MyProject     # belirli proje
      nazar baseline check --json          # JSON cikti (CI icin)
    """
    from nazar.cache.scan_cache import ScanCache

    resolved = Path(path).resolve()
    cache = ScanCache(str(resolved))

    if not cache.has_baseline():
        if json_out:
            sys.stdout.write(json.dumps({"error": "Baseline bulunamadi"}) + "\n")
        else:
            console.print("[red]Baseline bulunamadi.[/red]")
            console.print("[dim]Once 'nazar baseline save' ile baseline kaydedin.[/dim]")
        raise SystemExit(1)

    # Yeni tarama yap
    if not json_out:
        console.print(Panel(
            f"[bold cyan]NAZAR BASELINE CHECK[/bold cyan]\n"
            f"Proje: {resolved.name}  |  Profil: {profile}", expand=False))
        console.print("\n[dim]Tarama yapiliyor...[/dim]")

    scanner = ProjectScanner(str(resolved))
    scan_result = scanner.scan()
    planner = TestPlanner(scan_result, profile=profile)
    test_plan = planner.create_plan()
    plan_dict = test_plan.to_dict()
    orchestrator = TestOrchestrator(str(resolved), plan_dict)
    current_results = orchestrator.run_all()

    # Baseline ile karsilastir
    comparison = cache.compare_with_baseline(current_results)

    if json_out:
        sys.stdout.write(json.dumps(comparison, indent=2, ensure_ascii=False) + "\n")
    else:
        baseline_gs = "green" if comparison["baseline_rate"] >= 80 else "yellow" if comparison["baseline_rate"] >= 60 else "red"
        current_gs = "green" if comparison["current_rate"] >= 80 else "yellow" if comparison["current_rate"] >= 60 else "red"
        delta = comparison["delta"]
        delta_sign = "+" if delta > 0 else ""
        delta_color = "green" if delta > 0 else "red" if delta < 0 else "dim"

        console.print(Panel(
            f"[bold]Baseline:[/bold] [{baseline_gs}]{comparison['baseline_grade']} ({comparison['baseline_rate']}%)[/{baseline_gs}]\n"
            f"[bold]Simdi:[/bold]    [{current_gs}]{comparison['current_grade']} ({comparison['current_rate']}%)[/{current_gs}]\n"
            f"[bold]Fark:[/bold]     [{delta_color}]{delta_sign}{delta}%[/{delta_color}]",
            title="[bold yellow]BASELINE KARSILASTIRMA[/bold yellow]", border_style="yellow",
        ))

        # Regressions
        regressions = comparison.get("regressions", [])
        if regressions:
            console.print(f"\n[bold red]GERILEMELER ({len(regressions)}):[/bold red]")
            for r in regressions[:15]:
                pri = r.get("priority", "medium").upper()
                console.print(f"  [red]-[/red] [{pri}] {r['name']}")
                if r.get("detail"):
                    console.print(f"    [dim]{r['detail'][:70]}[/dim]")

        # Improvements
        improvements = comparison.get("improvements", [])
        if improvements:
            console.print(f"\n[bold green]DUZELTMELER ({len(improvements)}):[/bold green]")
            for r in improvements[:15]:
                console.print(f"  [green]+[/green] {r['name']}")

        # New issues
        new_issues = comparison.get("new_issues", [])
        if new_issues:
            console.print(f"\n[bold yellow]YENI SORUNLAR ({len(new_issues)}):[/bold yellow]")
            for r in new_issues[:15]:
                pri = r.get("priority", "medium").upper()
                console.print(f"  [yellow]![/yellow] [{pri}] {r['name']}")

    # Regression varsa exit 1
    if comparison.get("has_regressions"):
        if not json_out:
            console.print(f"\n[bold red]FAIL: {len(comparison['regressions'])} gerileme tespit edildi.[/bold red]")
        raise SystemExit(1)
    else:
        if not json_out:
            console.print(f"\n[bold green]OK: Gerileme yok. Baseline korunuyor.[/bold green]")


@app.command()
def studio(
    yaml_file: str = typer.Argument(..., help="YAML test dosyasi yolu"),
    port: int = typer.Option(9998, "--port", "-p", help="HTTP sunucu portu"),
):
    """Nazar Studio - Native pencerede canli test arayuzu.

    Simulator ekranini ve YAML test adimlarini native desktop penceresinde gosterir.
    pywebview kurulu degilse tarayicida acar.

    Ornek: nazar studio .nazar/ui-tests/login-test.yml
    """
    from nazar.live.studio import NazarStudio
    s = NazarStudio(port=port)
    s.open(yaml_file)


if __name__ == "__main__":
    app()
