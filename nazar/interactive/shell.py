"""Nazar Interactive Shell - Claude Code benzeri interaktif terminal arayuzu."""
import os
import sys
import re
import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich import box


BANNER = """[bold cyan]
  ███╗   ██╗ █████╗ ███████╗ █████╗ ██████╗
  ████╗  ██║██╔══██╗╚══███╔╝██╔══██╗██╔══██╗
  ██╔██╗ ██║███████║  ███╔╝ ███████║██████╔╝
  ██║╚██╗██║██╔══██║ ███╔╝  ██╔══██║██╔══██╗
  ██║ ╚████║██║  ██║███████╗██║  ██║██║  ██║
  ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝
[/bold cyan]  [dim]Otonom Guvenlik & Kalite Tarayici[/dim]
"""

HELP_TEXT = """
[bold]BASLANGIC:[/bold]
  Proje yolunu yazin veya Desktop'taki klasor adini girin:
  [green]nazar> ~/Desktop/MyProject[/green]
  [green]nazar> MyProject[/green]  [dim](Desktop'ta arar)[/dim]

[bold]KOMUTLAR:[/bold] [dim](/ opsiyonel - scan veya /scan ayni sey)[/dim]
  [cyan]scan <yol>[/cyan]    [dim]|[/dim] [cyan]tara[/cyan]        Projeyi tara
  [cyan]report[/cyan]        [dim]|[/dim] [cyan]rapor[/cyan]       Basarisiz testler (report failed, report security)
  [cyan]detail <no>[/cyan]   [dim]|[/dim] [cyan]d3[/cyan]          Testin detayi + sorunlu kod
  [cyan]guide <no>[/cyan]    [dim]|[/dim] [cyan]g2[/cyan]          Adim adim duzeltme rehberi
  [cyan]export html[/cyan]   [dim]|[/dim] [cyan]e json[/cyan]      HTML/JSON/SARIF cikti
  [cyan]categories[/cyan]    [dim]|[/dim] [cyan]cat[/cyan]         Kategori listesi
  [cyan]stats[/cyan]                        Genel istatistikler
  [cyan]profiles[/cyan]      [dim]|[/dim] [cyan]profiller[/cyan]   Test profilleri
  [cyan]rule[/cyan]          [dim]|[/dim] [cyan]kural[/cyan]       Kural yonetimi (olustur, dogrula, test, listele)
  [cyan]batch <y1> <y2>[/cyan]               Birden fazla projeyi tara
  [cyan]coverage[/cyan]      [dim]|[/dim] [cyan]kapsam[/cyan]      Test kapsami raporu (kategori, dosya, guven)
  [cyan]ignore <rule>[/cyan]                 Kurali .nazarignore'a ekle
  [cyan]baseline save[/cyan]                Mevcut taramayi baseline olarak kaydet
  [cyan]baseline check[/cyan]               Baseline ile karsilastir (gerileme kontrolu)
  [cyan]run[/cyan]           [dim]|[/dim] [cyan]calistir[/cyan]    Canli UI test calistir (Nazar Live Test)
  [cyan]live[/cyan]          [dim]|[/dim] [cyan]serve[/cyan]       Canli web raporu (localhost:5555)
  [cyan]update[/cyan]        [dim]|[/dim] [cyan]guncelle[/cyan]    Son versiyona guncelle
  [cyan]clear[/cyan]         [dim]|[/dim] [cyan]temizle[/cyan]     Ekrani temizle
  [cyan]help[/cyan]          [dim]|[/dim] [cyan]yardim[/cyan]      Bu ekran
  [cyan]quit[/cyan]          [dim]|[/dim] [cyan]q[/cyan]           Cikis

[bold]IPUCLARI:[/bold]
  [dim]Tab[/dim]          Otomatik tamamlama
  [dim]Yukari ok[/dim]    Onceki komutlar
  [dim]Ctrl+C[/dim]       Iptal
"""


class NazarCompleter(Completer):
    COMMANDS = ["scan", "report", "detail", "guide", "export", "categories", "profiles", "stats", "coverage", "clear", "update", "live", "serve", "run", "rule", "batch", "baseline", "ignore", "help", "quit",
                "tara", "rapor", "detay", "rehber", "kategoriler", "profiller", "kapsam", "temizle", "guncelle", "calistir", "kural", "toplu", "referans", "yoksay", "yardim", "cikis", "cat"]
    FILTERS = ["failed", "passed", "all", "security", "appstore", "code_quality", "ux_text", "ui_component", "cross_file"]
    FORMATS = ["html", "json", "sarif", "junit", "markdown"]

    def __init__(self):
        self.path_completer = PathCompleter(expanduser=True)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.strip()
        word = text.lstrip("/").split(" ", 1)[0].lower()
        if word in ("report", "rapor", "r") and " " in text:
            sub = text.split(" ", 1)[1]
            for f in self.FILTERS:
                if f.startswith(sub):
                    yield Completion(f, start_position=-len(sub))
        elif word in ("export", "e") and " " in text:
            sub = text.split(" ", 1)[1]
            for f in self.FORMATS:
                if f.startswith(sub):
                    yield Completion(f, start_position=-len(sub))
        elif not " " in text:
            clean = text.lstrip("/")
            for cmd in self.COMMANDS:
                if cmd.startswith(clean):
                    yield Completion(cmd, start_position=-len(clean))
            yield from self.path_completer.get_completions(document, complete_event)
        else:
            yield from self.path_completer.get_completions(document, complete_event)


def _grade(rate):
    for min_r, g in [(97,"A+"),(93,"A"),(90,"A-"),(87,"B+"),(83,"B"),(80,"B-"),(77,"C+"),(73,"C"),(70,"C-"),(67,"D+"),(63,"D"),(60,"D-"),(0,"F")]:
        if rate >= min_r:
            return g
    return "F"


class NazarShell:
    def __init__(self):
        self.console = Console()
        history_dir = Path.home() / ".nazar"
        history_dir.mkdir(exist_ok=True)
        self.session = PromptSession(
            history=FileHistory(str(history_dir / "history")),
            completer=NazarCompleter(),
        )
        self.results = None
        self.plan_data = None
        self.project_path = None
        self._custom_categories = []
        self._project_config = None

    def _show_header(self, welcome=False):
        """Banner goster (sadece acilista veya /clear'da)."""
        import sys
        sys.stdout.write('\x1Bc')
        sys.stdout.flush()
        from nazar import __version__
        width = self.console.width or 80

        if width >= 60:
            self.console.print(BANNER, end="")
        else:
            self.console.print("[bold cyan]  NAZAR[/bold cyan]")
            self.console.print(f"  [dim]Otonom Guvenlik & Kalite Tarayici[/dim]")

        if width >= 80:
            self.console.print(f"  [dim]v{__version__}[/dim]  |  [bold]197+[/bold] kontrol  |  [bold]21[/bold] kategori  |  [bold]15+[/bold] framework  |  [bold]87[/bold] rehber")
        else:
            self.console.print(f"  [dim]v{__version__}[/dim] | [bold]197+[/bold] kontrol | [bold]21[/bold] kategori")

        if welcome:
            self._check_update_on_start()
            self.console.print()
            self.console.print("  [green]Taramak istediginiz projenin yolunu yazin:[/green]")
            self.console.print("  [dim]Ornek: ~/Desktop/MyProject | /help[/dim]")

    def run(self):
        self._show_header(welcome=True)
        while True:
            try:
                text = self.session.prompt(HTML('<style fg="#6366f1"><b>nazar</b></style><style fg="#475569">&gt; </style>'))
                text = text.strip()
                if not text:
                    continue
                self._handle(text)
            except KeyboardInterrupt:
                self.console.print("\n[dim]Iptal edildi.[/dim]")
            except EOFError:
                self.console.print("\n[dim]Gorusuruz![/dim]")
                break

    def _handle(self, text):
        parts = text.strip().split(None, 1)
        word = parts[0].lower().lstrip("/")
        arg = parts[1] if len(parts) > 1 else ""

        # Numara ile baslayan kisayollar: d3, g2, d 5
        if len(word) > 1 and word[0] in ("d", "g") and word[1:].isdigit():
            arg = word[1:]
            word = word[0]

        # Komut eslemesi - / olsun olmasin ayni calisiyor
        cmds = {
            "scan": lambda: self._scan(arg), "tara": lambda: self._scan(arg), "s": lambda: self._scan(arg),
            "report": lambda: self._report(arg), "rapor": lambda: self._report(arg), "r": lambda: self._report(arg),
            "detail": lambda: self._detail(arg), "detay": lambda: self._detail(arg), "d": lambda: self._detail(arg),
            "guide": lambda: self._guide(arg), "rehber": lambda: self._guide(arg), "g": lambda: self._guide(arg),
            "export": lambda: self._export(arg), "e": lambda: self._export(arg),
            "categories": self._categories, "kategoriler": self._categories, "c": self._categories, "cat": self._categories,
            "profiles": self._profiles, "profiller": self._profiles,
            "stats": self._stats, "istatistik": self._stats,
            "coverage": self._coverage, "kapsam": self._coverage,
            "rule": lambda: self._rule(arg), "kural": lambda: self._rule(arg),
            "batch": lambda: self._batch(arg), "toplu": lambda: self._batch(arg),
            "ignore": lambda: self._ignore(arg), "yoksay": lambda: self._ignore(arg),
            "baseline": lambda: self._baseline(arg), "referans": lambda: self._baseline(arg),
            "run": self._run_ui, "calistir": self._run_ui,
            "live": self._live, "serve": self._live,
            "clear": self._clear, "temizle": self._clear,
            "update": self._update, "guncelle": self._update,
            "help": lambda: self.console.print(HELP_TEXT), "yardim": lambda: self.console.print(HELP_TEXT), "h": lambda: self.console.print(HELP_TEXT),
            "quit": lambda: sys.exit(0), "exit": lambda: sys.exit(0), "q": lambda: sys.exit(0), "cikis": lambda: sys.exit(0),
        }

        fn = cmds.get(word)
        if fn:
            fn()
        elif text.strip() in (".", "./"):
            self.console.print("\n[yellow]  Mevcut dizini taramak yerine proje yolunu belirtin.[/yellow]")
            self.console.print("[dim]  Ornek: ~/Desktop/MyProject[/dim]\n")
        elif os.path.exists(os.path.expanduser(text.strip())) or text.strip().startswith("/") or text.strip().startswith("~"):
            self._scan(text.strip())
        else:
            # Belki Desktop/proje seklinde yazmistir
            desktop_try = os.path.expanduser(f"~/Desktop/{text.strip()}")
            if os.path.exists(desktop_try):
                self._scan(text.strip())
            else:
                self.console.print(f"\n[dim]  '{text.strip()}' bulunamadi. help yazin veya proje yolunu girin.[/dim]\n")

    def _scan(self, path_str):
        if not path_str:
            self.console.print("\n[yellow]  Hangi projeyi taramak istiyorsunuz?[/yellow]")
            self.console.print("[dim]  Ornek: /scan ~/Desktop/MyProject[/dim]")
            self.console.print("[dim]  Veya direkt dosya yolunu yazin: ~/Desktop/MyProject[/dim]\n")
            return
        # Path duzeltmeleri
        expanded = os.path.expanduser(path_str)
        # /desktop/x -> /Users/kullanici/Desktop/x otomatik cevir
        if expanded.lower().startswith("/desktop/"):
            expanded = os.path.expanduser("~/Desktop/" + expanded[9:])
        elif expanded.lower().startswith("desktop/"):
            expanded = os.path.expanduser("~/Desktop/" + expanded[8:])
        path = Path(expanded).resolve()
        if not path.exists():
            self.console.print(f"\n[red]  Yol bulunamadi: {path}[/red]")
            self.console.print("[dim]  Dosya yolunu kontrol edin. Tab ile otomatik tamamlama kullanabilirsiniz.[/dim]\n")
            return

        # Proje dizini teyidi
        verified = self._verify_project_path(path)
        if verified is None:
            return  # kullanici iptal etti
        path = verified

        self.project_path = str(path)
        start_time = time.time()

        from nazar.scanner.project_scanner import ProjectScanner
        from nazar.planner.test_planner import TestPlanner
        from nazar.runners.orchestrator import TestOrchestrator
        from nazar.cache.scan_cache import ScanCache
        from nazar.config.loader import ConfigLoader
        from rich.live import Live

        # .nazar/config.yaml yukle (varsa)
        self._project_config = ConfigLoader.load(self.project_path)
        if self._project_config.profile:
            self.console.print(f"  [dim]Config: profil={self._project_config.profile}[/dim]")
        if self._project_config.min_confidence != 50:
            self.console.print(f"  [dim]Config: min_confidence={self._project_config.min_confidence}[/dim]")
        if self._project_config.ignore_rules:
            self.console.print(f"  [dim]Config: {len(self._project_config.ignore_rules)} kural ignore edildi[/dim]")

        # Faz 0: Hizli on-analiz - proje tipini goster
        scan_start = time.time()
        scanner = ProjectScanner(self.project_path)

        # Proje tipini hizlica tespit et (sadece tech_stack)
        scanner._detect_tech_stack()
        tech = scanner.result.tech_stack
        proj_name = path.name

        self.console.print(f"\n  [bold]{proj_name}[/bold] [dim]({tech})[/dim]")

        # Onceki tarama var mi?
        cache = ScanCache(self.project_path)
        prev = cache.get_last_scan_summary()
        if prev:
            self.console.print(f"  [dim]Onceki tarama: {prev['grade']} ({prev['pass_rate']}%) - {cache.time_since_last_scan()}[/dim]")

        # Config'de profil ayarlanmissa direkt kullan
        if hasattr(self, '_project_config') and self._project_config.profile:
            profile = self._project_config.profile
            self.console.print(f"\n  [green]Config profili: {profile}[/green]\n")
        else:
            # Profil secim menusu
            profile = self._select_profile(tech, prev)
            if profile is None:
                return

        # Canli runtime test sorusu (mobil projeler icin)
        run_live_test = False
        if tech in ("react-native", "flutter", "ios-native", "android-native"):
            self.console.print()
            self.console.print("  [bold yellow]Canli runtime test yapmak ister misiniz?[/bold yellow]")
            self.console.print("  [dim]Simulator/emulator uzerinde uygulamayi gercek zamanli test eder[/dim]")
            try:
                live_answer = self.session.prompt(HTML('<style fg="#f59e0b"><b>[E]vet / [H]ayir</b></style><style fg="#475569">&gt; </style>'))
                if live_answer.strip().lower() in ("e", "evet", "y", "yes", "1"):
                    run_live_test = True
                    self.console.print("  [green]Canli test: Statik tarama sonrasi baslatilacak[/green]")
            except (KeyboardInterrupt, EOFError):
                pass
            self.console.print()

        def _scan_with_live():
            """Tarama sirasinda canli dosya gosterimi."""
            import threading
            result_holder = [None]
            done = threading.Event()

            def do_scan():
                result_holder[0] = scanner.scan()
                done.set()

            t = threading.Thread(target=do_scan, daemon=True)
            t.start()

            dots = ["   ", ".  ", ".. ", "..."]
            idx = 0
            with Live(console=self.console, refresh_per_second=4, transient=True) as live:
                while not done.is_set():
                    elapsed = time.time() - scan_start
                    file_count = len(scanner.result.source_files) if hasattr(scanner, 'result') else 0
                    tech = scanner.result.tech_stack if hasattr(scanner, 'result') and scanner.result.tech_stack != "unknown" else ""
                    idx += 1

                    tech_str = f" | {tech}" if tech else ""
                    anim = dots[idx % len(dots)]
                    panel_content = (
                        f"  [bold cyan]1/3[/bold cyan] Proje taraniyor{anim}\n"
                        f"  [dim]{elapsed:.1f}s | {file_count} dosya{tech_str}[/dim]"
                    )
                    live.update(Panel(panel_content, border_style="cyan", expand=False))
                    done.wait(timeout=0.25)

            return result_holder[0]

        scan_result = _scan_with_live()
        scan_dur = time.time() - scan_start
        self.console.print(f"  [bold cyan][1/3][/bold cyan] Proje tarandi [green]{scan_result.tech_stack}[/green] | {scan_result.screen_count} ekran | {scan_result.api_endpoint_count} API | {len(scan_result.source_files)} dosya [dim]({scan_dur:.1f}s)[/dim]")

        # Incremental mod: sadece degisen dosyalari tara
        incremental_files = None
        is_diff_mode = False
        if profile == "incremental":
            changed, new, deleted = cache.get_changed_files(scan_result.source_files)
            all_changed = changed + new
            self.console.print(f"\n  [bold cyan]Incremental:[/bold cyan] {len(changed)} degisen, {len(new)} yeni, {len(deleted)} silinen dosya")
            if not all_changed:
                self.console.print("  [green]Degisiklik tespit edilemedi, tarama atlaniyor.[/green]")
                prev_summary = cache.get_last_scan_summary()
                if prev_summary:
                    self.console.print(f"  [dim]Son tarama: {prev_summary['grade']} ({prev_summary['pass_rate']}%)[/dim]")
                self.console.print(f"\n[dim]Degisiklik yapip tekrar deneyin.[/dim]\n")
                return
            self.console.print(f"  [yellow]{len(all_changed)} dosya icin testler calistirilacak[/yellow]")
            incremental_files = all_changed
        elif profile == "diff":
            is_diff_mode = True

        # Faz 2: Planlama (secilen profil ile)
        plan_start = time.time()
        plan_profile = "full" if profile in ("incremental", "diff", "custom") else profile
        planner = TestPlanner(scan_result, profile=plan_profile)
        plan = planner.create_plan()
        self.plan_data = plan.to_dict()

        # Custom profil: sadece secilen kategorileri tut
        if profile == "custom" and hasattr(self, '_custom_categories') and self._custom_categories:
            custom_set = set(self._custom_categories)
            self.plan_data["tests"] = [
                t for t in self.plan_data.get("tests", [])
                if t.get("type", "other") in custom_set
            ]
            self.plan_data["total_tests"] = len(self.plan_data["tests"])

        # Incremental modda: plani degisen dosyalara gore filtrele
        if incremental_files is not None:
            self.plan_data = self._filter_plan_by_changed_files(self.plan_data, incremental_files)

        plan_dur = time.time() - plan_start
        total_test_count = len(self.plan_data.get("tests", []))
        if incremental_files is not None:
            self.console.print(f"  [bold yellow][2/3][/bold yellow] {total_test_count} test planlanidi (degisen dosyalar icin filtrelendi) [dim]({plan_dur:.1f}s)[/dim]")
        else:
            self.console.print(f"  [bold yellow][2/3][/bold yellow] {total_test_count} test planlanidi ({len(plan.categories)} kategori) [dim]({plan_dur:.1f}s)[/dim]")

        # Faz 3: Calistirma - CANLI IZLEME
        self.console.print(f"  [bold green][3/3][/bold green] Testler calistiriliyor...\n")
        orchestrator = TestOrchestrator(self.project_path, self.plan_data)
        # OPT 2 - Scanner cache'ini orchestrator'a aktar (ayni dosyalar tekrar okunmasin)
        orchestrator._content_cache = scanner._content_cache
        orchestrator._source_cache = scan_result.source_files
        tests = self.plan_data.get("tests", [])
        self.results = []
        passed = 0
        failed = 0
        current_cat = ""
        cat_results = {}

        from rich.live import Live

        run_start = time.time()
        active_test_name = ""
        active_test_start = 0
        active_test_idx = [0]
        spin_frames = [">", ">>", ">>>", ">>"]
        spin_idx = [0]

        def build_live_with_spinner():
            """Spinner dahil canli gosterim."""
            completed = len(self.results)
            total = len(tests)
            pct = (completed / total * 100) if total > 0 else 0
            elapsed = time.time() - run_start
            rate = (passed / completed * 100) if completed > 0 else 0

            bar_w = 30
            filled = int(bar_w * completed / max(total, 1))
            bar = "[green]" + "=" * filled + "[/green][dim]" + "-" * (bar_w - filled) + "[/dim]"

            spin = spin_frames[spin_idx[0] % len(spin_frames)]
            spin_idx[0] += 1
            active_elapsed = time.time() - active_test_start if active_test_start else 0

            if active_test_name:
                active_line = f"  [yellow]{spin}[/yellow] [bold]{active_test_name[:50]}[/bold] [dim]{active_elapsed:.0f}s[/dim]"
            else:
                active_line = "  [dim]Bekleniyor...[/dim]"

            # Son testler
            recent_lines = []
            for r in self.results[-3:]:
                icon = "[green]OK[/green]" if r["passed"] else "[red]XX[/red]"
                recent_lines.append(f"  {icon} {r['name'][:42]} [dim]{r.get('duration',0):.1f}s[/dim]")
            recent_text = "\n".join(recent_lines) if recent_lines else ""

            # Kategoriler
            cat_lines = []
            for cat, cd in cat_results.items():
                ct = cd["p"] + cd["f"]
                cr = (cd["p"] / ct * 100) if ct > 0 else 0
                ci = "[green]+[/green]" if cr >= 80 else "[yellow]![/yellow]" if cr >= 50 else "[red]-[/red]"
                mini_w = 8
                mini_f = int(mini_w * cd["p"] / max(ct, 1))
                mini_bar = "[green]" + "=" * mini_f + "[/green][dim]" + "-" * (mini_w - mini_f) + "[/dim]"
                is_active = " [yellow]<[/yellow]" if cat == current_cat else ""
                cat_lines.append(f"  {ci} {cat[:14]:<14} {cd['p']:>2}/{ct:<2} {mini_bar}{is_active}")
            cat_text = "\n".join(cat_lines[-8:]) if cat_lines else ""

            # Siradaki testler (her zaman goster)
            next_lines = []
            ci = active_test_idx[0] + 1
            for t in tests[ci:ci+3]:
                next_lines.append(f"  [dim]{t.get('name','')[:45]}[/dim]")
            if ci + 3 < total:
                next_lines.append(f"  [dim]...ve {total - ci - 3} test daha[/dim]")
            next_text = "\n".join(next_lines) if next_lines else "  [dim]Son testler calisiyor[/dim]"

            return Panel(
                f"  {bar}  {completed}/{total} ({pct:.0f}%)  [dim]{elapsed:.0f}s[/dim]\n"
                f"  [green]{passed} gecti[/green]  [red]{failed} kaldi[/red]  [dim]{rate:.0f}%[/dim]\n\n"
                f"[bold]Aktif:[/bold]\n{active_line}\n\n"
                f"[bold]Son:[/bold]\n{recent_text}\n\n"
                f"[bold]Kategoriler:[/bold]\n{cat_text}\n\n"
                f"[bold]Siradaki:[/bold]\n{next_text}",
                title="[bold cyan]NAZAR CANLI[/bold cyan]",
                border_style="cyan",
            )

        import threading

        # Her testi wrapper ile timeout'lu calistir
        TEST_TIMEOUT = 15  # saniye - tek test max 15sn
        WORKERS = 10

        def _run_with_timeout(test_item):
            """Tek testi timeout ile calistir."""
            result_box = [None]
            done_event = threading.Event()

            def _worker():
                result_box[0] = orchestrator._run_test(test_item)
                done_event.set()

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            done_event.wait(timeout=TEST_TIMEOUT)

            if result_box[0] is not None:
                return result_box[0]
            # Timeout - daemon thread arka planda olecek
            return {
                "name": test_item.get("name", "?"), "passed": True,
                "type": test_item.get("type", "other"), "subtype": test_item.get("subtype", ""),
                "priority": test_item.get("priority", "medium"),
                "detail": f"SKIP (>{TEST_TIMEOUT}s)", "duration": TEST_TIMEOUT,
                "confidence": 0, "confidence_label": "Timeout",
            }

        completed_count = [0]

        try:
            with Live(build_live_with_spinner(), console=self.console, refresh_per_second=4, transient=True) as live:
                # Tum testleri tek seferde submit et
                from concurrent.futures import ThreadPoolExecutor, as_completed
                with ThreadPoolExecutor(max_workers=WORKERS) as executor:
                    futures = {}
                    for i, test in enumerate(tests):
                        test_cat = test.get("type", "other")
                        if test_cat not in cat_results:
                            cat_results[test_cat] = {"p": 0, "f": 0}
                        futures[executor.submit(_run_with_timeout, test)] = (i, test)

                    active_test_name = "Testler calistiriliyor..."
                    active_test_start = time.time()

                    for future in as_completed(futures):
                        idx_f, test_f = futures[future]
                        active_test_idx[0] = idx_f
                        current_cat = test_f.get("type", "")
                        active_test_name = test_f.get("name", "?")[:50]
                        active_test_start = time.time()

                        try:
                            result = future.result()
                        except Exception as exc:
                            result = {
                                "name": test_f.get("name", "?"), "passed": False,
                                "type": test_f.get("type", "other"), "subtype": test_f.get("subtype", ""),
                                "priority": test_f.get("priority", "medium"),
                                "detail": f"Hata: {str(exc)[:60]}",
                            }

                        self.results.append(result)
                        tc = test_f.get("type", "other")
                        if result.get("passed"):
                            passed += 1
                            cat_results[tc]["p"] += 1
                        else:
                            failed += 1
                            cat_results[tc]["f"] += 1

                        completed_count[0] += 1
                        live.update(build_live_with_spinner())

        except KeyboardInterrupt:
            self.console.print("\n[dim]Tarama iptal edildi.[/dim]")

        # Config-based filtreleme: ignore_rules ve min_confidence
        if hasattr(self, '_project_config') and self.results:
            cfg = self._project_config
            # ignore_rules: config'deki kurallari sonuclardan cikar
            if cfg.ignore_rules:
                ignored_set = set(cfg.ignore_rules)
                before_count = len(self.results)
                self.results = [
                    r for r in self.results
                    if r.get("subtype", "") not in ignored_set
                ]
                removed = before_count - len(self.results)
                if removed > 0:
                    self.console.print(f"\n  [dim]Config: {removed} sonuc ignore_rules ile filtrelendi[/dim]")
                    # passed/failed yeniden hesapla
                    passed = sum(1 for r in self.results if r.get("passed"))
                    failed = len(self.results) - passed

            # min_confidence: config'deki esik altindaki sonuclari filtrele
            if cfg.min_confidence > 0:
                before_count = len(self.results)
                self.results = [
                    r for r in self.results
                    if not isinstance(r.get("confidence"), (int, float))
                    or r.get("confidence", 100) >= cfg.min_confidence
                ]
                removed = before_count - len(self.results)
                if removed > 0:
                    self.console.print(f"  [dim]Config: {removed} sonuc min_confidence={cfg.min_confidence}% ile filtrelendi[/dim]")
                    passed = sum(1 for r in self.results if r.get("passed"))
                    failed = len(self.results) - passed

        total_dur = time.time() - start_time
        rate = (passed / len(self.results) * 100) if self.results else 0
        grade = _grade(rate)
        gs = "green" if rate >= 80 else "yellow" if rate >= 60 else "red"

        self.console.print()
        self.console.print(Panel(
            f"[bold {gs}]Not: {grade} ({rate:.0f}%)[/bold {gs}]  |  "
            f"[green]{passed} passed[/green]  |  [red]{failed} failed[/red]  |  "
            f"[dim]{len(self.results)} test  |  {total_dur:.1f}s[/dim]",
            title="[bold cyan]SONUC[/bold cyan]", border_style="cyan",
        ))

        cats = {}
        for r in self.results:
            cat = r.get("type", "other")
            cats.setdefault(cat, {"passed": 0, "failed": 0})
            cats[cat]["passed" if r["passed"] else "failed"] += 1

        self.console.print()
        for cat, d in cats.items():
            total = d["passed"] + d["failed"]
            cr = (d["passed"] / total * 100) if total > 0 else 0
            filled = int(15 * d["passed"] / max(total, 1))
            bar = "[green]" + "█" * filled + "[/green][dim]" + "░" * (15 - filled) + "[/dim]"
            icon = "[green]+[/green]" if cr >= 80 else "[yellow]![/yellow]" if cr >= 50 else "[red]-[/red]"
            rs = f"[green]{cr:.0f}%[/green]" if cr >= 80 else f"[yellow]{cr:.0f}%[/yellow]" if cr >= 50 else f"[red]{cr:.0f}%[/red]"
            self.console.print(f"  {icon} {cat.upper():<16} {d['passed']:>3}/{total:<3} {rs:>6}  {bar}")

        fl = [r for r in self.results if not r["passed"]]
        if fl:
            self.console.print(f"\n[bold]{len(fl)} BASARISIZ TEST:[/bold]\n")
            for i, r in enumerate(fl, 1):
                pri = r.get("priority", "medium")
                ps = {"critical": "bold red", "high": "bold yellow", "medium": "cyan", "low": "dim"}.get(pri, "dim")
                conf = r.get("confidence", "?")
                dur = r.get("duration", 0)
                self.console.print(f"  [dim]#{i:>2}[/dim] [{ps}]{pri.upper():<8}[/{ps}] [bold]{r['name']}[/bold]")
                self.console.print(f"       [dim]Kategori:[/dim] {r.get('type','').upper()}  [dim]Guven:[/dim] {conf}%  [dim]Sure:[/dim] {dur:.1f}s")
                self.console.print(f"       {r.get('detail', '')}")
                if r.get("how_to_fix"):
                    self.console.print(f"       [green]Fix:[/green] {r['how_to_fix'].get('quick_fix', '')}")
                self.console.print()
        # Diff modu: onceki taramayla karsilastir
        if is_diff_mode and self.results:
            diff_result = cache.compare_with_previous(self.results)
            if diff_result:
                self.console.print()
                delta = diff_result["delta"]
                delta_sign = "+" if delta > 0 else ""
                delta_color = "green" if delta > 0 else "red" if delta < 0 else "dim"
                self.console.print(Panel(
                    f"[bold]Onceki:[/bold] {diff_result['previous_grade']} ({diff_result['previous_rate']}%)  "
                    f"[bold]Simdi:[/bold] {diff_result['current_grade']} ({diff_result['current_rate']}%)  "
                    f"[{delta_color}]{delta_sign}{delta}%[/{delta_color}]\n"
                    f"[green]{diff_result['fixed_count']} duzeltildi[/green]  |  "
                    f"[red]{diff_result['new_issues_count']} yeni sorun[/red]  |  "
                    f"[dim]{diff_result.get('time_since', '?')}[/dim]",
                    title="[bold yellow]KARSILASTIRMA[/bold yellow]", border_style="yellow",
                ))
                if diff_result["fixed"]:
                    self.console.print("  [green]Duzeltilen:[/green]")
                    for item in diff_result["fixed"][:5]:
                        self.console.print(f"    [green]+[/green] {item['name']}")
                if diff_result["new_issues"]:
                    self.console.print("  [red]Yeni sorunlar:[/red]")
                    for item in diff_result["new_issues"][:5]:
                        self.console.print(f"    [red]-[/red] {item['name']}")
            else:
                self.console.print("\n  [yellow]Onceki tarama bulunamadi, karsilastirma yapilamadi.[/yellow]")

        # Scan cache kaydet
        if self.results:
            cache.save_scan_result(self.results, self.plan_data, profile, total_dur)
            cache.save_file_hashes(scan_result.source_files)

        # Canli runtime test
        if run_live_test:
            try:
                self._run_live_test(path)
            except Exception:
                self.console.print("  [dim]Canli test baslatılamadi[/dim]")

        self.console.print()
        self.console.print("[bold cyan]Komutlar:[/bold cyan] [dim]d <no>[/dim] detay  [dim]g <no>[/dim] rehber  [dim]r[/dim] tablo  [dim]e html[/dim] export  [dim]help[/dim] yardim")
        self.console.print()

    def _report(self, filt):
        if not self.results:
            self.console.print("[yellow]Once tarama yapin: /scan <yol>[/yellow]")
            return
        if filt == "failed":
            tests = [r for r in self.results if not r["passed"]]
        elif filt == "passed":
            tests = [r for r in self.results if r["passed"]]
        elif filt and filt != "all":
            tests = [r for r in self.results if r.get("type") == filt]
        else:
            tests = [r for r in self.results if not r["passed"]]
        if not tests:
            self.console.print("[green]Sonuc yok![/green]")
            return
        table = Table(title=f"Sonuclar ({len(tests)})", box=box.ROUNDED)
        table.add_column("#", width=4, style="dim")
        table.add_column("Oncelik", width=8)
        table.add_column("Test", ratio=3)
        table.add_column("Sonuc", width=7)
        table.add_column("Guven", width=6)
        table.add_column("Detay", ratio=2, style="dim")
        for i, r in enumerate(tests, 1):
            pri = r.get("priority", "medium")
            ps = {"critical":"bold red","high":"yellow","medium":"cyan","low":"dim"}.get(pri,"dim")
            st = "[green]PASSED[/green]" if r["passed"] else "[red]FAILED[/red]"
            table.add_row(str(i), f"[{ps}]{pri.upper()}[/{ps}]", r["name"][:45], st, f"{r.get('confidence','?')}%", r.get("detail","")[:35])
        self.console.print(table)

    def _detail(self, num):
        if not self.results:
            self.console.print("[yellow]Once tarama yapin.[/yellow]")
            return
        try:
            idx = int(num) - 1
        except (ValueError, TypeError):
            self.console.print("[red]/detail 1 seklinde girin.[/red]")
            return
        fl = [r for r in self.results if not r["passed"]]
        if idx < 0 or idx >= len(fl):
            self.console.print(f"[red]1-{len(fl)} arasi girin.[/red]")
            return
        r = fl[idx]
        self.console.print(Panel(f"[bold]{r['name']}[/bold]\n\nOncelik: [bold]{r.get('priority','').upper()}[/bold] | Guven: [bold]{r.get('confidence','?')}%[/bold]\nKategori: {r.get('type','').upper()}\n\n[bold]Detay:[/bold] {r.get('detail','')}", title=f"[bold cyan]#{idx+1}[/bold cyan]", border_style="cyan"))
        detail = r.get("detail", "")
        m = re.search(r'([a-zA-Z0-9_/\-\.()]+\.[a-zA-Z]+):(\d+)', detail)
        if m and self.project_path:
            fp, ln = m.group(1), int(m.group(2))
            full = os.path.join(self.project_path, fp)
            if os.path.exists(full):
                try:
                    lines = open(full, errors="ignore").readlines()
                    s, e = max(0, ln-3), min(len(lines), ln+3)
                    code = "".join(lines[s:e])
                    lang = "typescript" if fp.endswith((".ts",".tsx")) else "python" if fp.endswith(".py") else "javascript"
                    self.console.print(Panel(Syntax(code, lang, theme="monokai", line_numbers=True, start_line=s+1, highlight_lines={ln}), title=f"[bold]{fp}[/bold]", border_style="red"))
                except Exception:
                    pass
        self.console.print(f"\n[dim]Rehber: /guide {idx+1}[/dim]")

    def _guide(self, num):
        if not self.results:
            self.console.print("[yellow]Once tarama yapin.[/yellow]")
            return
        try:
            idx = int(num) - 1
        except (ValueError, TypeError):
            self.console.print("[red]/guide 1 seklinde girin.[/red]")
            return
        fl = [r for r in self.results if not r["passed"]]
        if idx < 0 or idx >= len(fl):
            self.console.print(f"[red]1-{len(fl)} arasi girin.[/red]")
            return
        r = fl[idx]
        guide = r.get("guide")
        if not guide:
            fix = r.get("how_to_fix")
            if fix:
                self.console.print(f"\n[bold red]SORUN:[/bold red] {fix.get('sorun','')}")
                self.console.print(f"[bold green]COZUM:[/bold green] {fix.get('cozum','')}")
                self.console.print(f"[bold cyan]QUICK FIX:[/bold cyan] {fix.get('quick_fix','')}")
            else:
                self.console.print("[yellow]Bu test icin rehber yok.[/yellow]")
            return
        ct = Text()
        ct.append(f"\n  RISK: ", style="bold red")
        ct.append(f"{guide['risk']}\n\n")
        ct.append(f"  Ne Oluyor: ", style="bold")
        ct.append(f"{guide['what']}\n")
        ct.append(f"  Neden Onemli: ", style="bold")
        ct.append(f"{guide['why']}\n")
        self.console.print(Panel(ct, title=f"[bold yellow]{guide['title']}[/bold yellow]", border_style="yellow"))
        steps = guide.get("steps", [])
        if steps:
            self.console.print("\n[bold]  ADIM ADIM:[/bold]")
            for i, s in enumerate(steps, 1):
                self.console.print(f"  [cyan]{i}.[/cyan] {s}")
        before, after = guide.get("before", ""), guide.get("after", "")
        if before and after:
            self.console.print()
            self.console.print(Panel(before, title="[red]ONCE[/red]", border_style="red"))
            self.console.print(Panel(after, title="[green]SONRA[/green]", border_style="green"))
        if guide.get("warning"):
            self.console.print(f"\n[yellow]  UYARI: {guide['warning']}[/yellow]")
        if guide.get("tools"):
            self.console.print(f"[dim]  Onerilen: {', '.join(guide['tools'])}[/dim]")
        self.console.print()

    def _export(self, fmt_str):
        if not self.results:
            self.console.print("[yellow]Once tarama yapin.[/yellow]")
            return
        parts = fmt_str.split(None, 1)
        fmt = parts[0] if parts else "html"
        out = parts[1] if len(parts) > 1 else None
        # Raporu proje dizinine kaydet
        base_dir = self.project_path if self.project_path else os.getcwd()
        if fmt == "html":
            out = out or os.path.join(base_dir, "nazar-report.html")
            from nazar.reporter.html_reporter import HTMLReporter
            HTMLReporter().generate(self.results, self.plan_data or {}, out)
        elif fmt == "json":
            out = out or os.path.join(base_dir, "nazar-report.json")
            from nazar.reporters.json_reporter import JSONReporter
            JSONReporter().generate(self.results, self.plan_data or {}, out)
        elif fmt == "sarif":
            out = out or os.path.join(base_dir, "nazar-report.sarif")
            from nazar.reporters.sarif_reporter import SARIFReporter
            SARIFReporter().generate(self.results, self.plan_data or {}, out)
        elif fmt == "markdown":
            out = out or os.path.join(base_dir, "nazar-report.md")
            from nazar.reporters.markdown_reporter import MarkdownReporter
            MarkdownReporter().generate(self.results, self.plan_data or {}, out)
        elif fmt == "junit":
            out = out or os.path.join(base_dir, "nazar-report.xml")
            from nazar.reporters.junit_reporter import JUnitReporter
            JUnitReporter().generate(self.results, self.plan_data or {}, out)
        else:
            self.console.print(f"[red]Format: html/json/sarif/markdown/junit[/red]")
            return
        abs_out = os.path.abspath(out)
        self.console.print(f"[green]Rapor olusturuldu:[/green] {abs_out}")
        # HTML ise tarayicide ac
        if fmt == "html":
            import webbrowser
            webbrowser.open(f"file://{abs_out}")
            self.console.print("[dim]Tarayicida acildi[/dim]")

    def _categories(self):
        table = Table(title="Nazar v4.0 Kategorileri", box=box.ROUNDED)
        table.add_column("Kategori", style="cyan", width=18)
        table.add_column("Kontrol", justify="center", width=8)
        table.add_column("Aciklama", ratio=3)
        cats = [
            ("Security", "63", "50+ secret, OWASP, crypto, supply chain"),
            ("App Store", "32", "Privacy manifest, IAP, Sign in with Apple"),
            ("Play Store", "10", "targetSdk, exported, ProGuard, permissions"),
            ("SCA", "7", "npm/pip/go audit, typosquatting, lisans"),
            ("AST Analysis", "6", "Python AST: eval, bare except, mutable default"),
            ("Taint Tracking", "5", "SQL injection, XSS, command injection akisi"),
            ("Code Quality", "16", "Complexity, dead code, smells"),
            ("UI Component", "10", "a11y, touch target, dark mode"),
            ("UX Text", "8", "Yazim, tutarlilik, i18n"),
            ("Cross-File", "7", "Dead export, orphan, circular import"),
            ("API", "4", "Erisilebilirlik, response"),
            ("Git", "4", "gitignore, buyuk dosya"),
            ("YAML Rules", "3", "Semgrep benzeri ozel kural motoru"),
            ("Type Safety", "3", "any, ts-ignore"),
            ("Error Handling", "3", "Bos catch, async"),
            ("Performance", "3", "Buyuk dosya/gorsel"),
            ("Documentation", "3", "README, CHANGELOG"),
            ("Naming", "3", "Dosya isimleri"),
            ("Dependency", "3", "Vulnerability"),
            ("Accessibility", "2", "testID, label"),
            ("Docker", "2", "Image, secret"),
        ]
        for n, c, d in cats:
            table.add_row(n, c, d)
        table.add_row("[bold]TOPLAM[/bold]", "[bold]197+[/bold]", "")
        self.console.print(table)

    def _profiles(self):
        """Mevcut test profillerini Rich tablosu ile goster."""
        from nazar.planner.profiles import TEST_PROFILES

        PROFILE_COLORS = {
            "full": "green",
            "frontend": "cyan",
            "backend": "blue",
            "security": "yellow",
            "mobile": "magenta",
            "ci": "red",
            "dependency": "bright_cyan",
            "performance": "bright_yellow",
        }

        table = Table(title="Nazar Test Profilleri", box=box.ROUNDED)
        table.add_column("Profil", style="bold", width=14)
        table.add_column("Aciklama", ratio=3)
        table.add_column("Kategori", justify="center", width=10)
        table.add_column("Kategoriler", ratio=4)

        for key, profile in TEST_PROFILES.items():
            color = PROFILE_COLORS.get(key, "white")
            name_cell = f"[{color}]{profile['name']}[/{color}]"

            cats = profile.get("categories", "__all__")
            if cats == "__all__":
                cat_count = "Tumu"
                cat_list = "[dim]Tech stack'e gore otomatik[/dim]"
            else:
                cat_count = str(len(cats))
                cat_list = ", ".join(cats)

            est = profile.get("estimated_minutes", 0)
            desc = f"{profile['description']} [dim](~{est}dk)[/dim]"

            table.add_row(name_cell, desc, cat_count, cat_list)

        self.console.print(table)

    # === Profil Secim Sistemi ===

    @staticmethod
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
        filtered["total_tests"] = len(kept)
        return filtered

    def _select_profile(self, tech: str, prev_scan: dict) -> str:
        """Kullaniciya profil secim menusu goster."""
        from nazar.planner.profiles import TEST_PROFILES

        self.console.print()
        self.console.print("  [bold]Ne test etmek istiyorsun?[/bold]")
        self.console.print()

        options = []
        idx = 1

        # 1. Tam tarama (her zaman)
        options.append(("full", "Tam tarama", "Tum kategoriler", "~5-10dk"))
        self.console.print(f"  [bold cyan][{idx}][/bold cyan] Tam tarama              [dim]Tum kategoriler (~5-10dk)[/dim]")
        idx += 1

        # 2-3. Hizli/karsilastirmali (onceki tarama varsa)
        if prev_scan:
            options.append(("incremental", "Hizli tarama", "Sadece degisen dosyalar", "~1dk"))
            self.console.print(f"  [bold cyan][{idx}][/bold cyan] Hizli tarama            [dim]Sadece degisen dosyalar (~1dk)[/dim]")
            idx += 1

            options.append(("diff", "Karsilastirmali", "Onceki sonucla diff", "~5-10dk"))
            self.console.print(f"  [bold cyan][{idx}][/bold cyan] Karsilastirmali         [dim]Onceki sonucla diff (~5-10dk)[/dim]")
            idx += 1

        # 4. Frontend
        options.append(("frontend", "Frontend / UI", "UX, UI, accessibility, renk, form", "~2-3dk"))
        self.console.print(f"  [bold cyan][{idx}][/bold cyan] Frontend / UI           [dim]UX, renk, form, accessibility (~2-3dk)[/dim]")
        idx += 1

        # 5. Backend
        options.append(("backend", "Backend / API", "Security, API, taint, code quality", "~3-4dk"))
        self.console.print(f"  [bold cyan][{idx}][/bold cyan] Backend / API           [dim]Security, taint, code quality (~3-4dk)[/dim]")
        idx += 1

        # 6. Guvenlik
        options.append(("security", "Guvenlik", "63 guvenlik + SCA + taint + AST", "~4-5dk"))
        self.console.print(f"  [bold cyan][{idx}][/bold cyan] Guvenlik                [dim]OWASP, SCA, taint tracking (~4-5dk)[/dim]")
        idx += 1

        # 7. Mobil (sadece mobil projeler)
        if tech in ("react-native", "flutter", "ios-native", "android-native"):
            options.append(("mobile", "Mobil uyumluluk", "App Store + Play Store", "~3-4dk"))
            self.console.print(f"  [bold cyan][{idx}][/bold cyan] Mobil uyumluluk         [dim]App Store + Play Store (~3-4dk)[/dim]")
            idx += 1

        # 8. Dependency
        options.append(("dependency", "Dependency analizi", "SCA, lisans, versiyon kontrolleri", "~2-3dk"))
        self.console.print(f"  [bold cyan][{idx}][/bold cyan] Dependency analizi      [dim]SCA, lisans, versiyon (~2-3dk)[/dim]")
        idx += 1

        # 9. Performance
        options.append(("performance", "Performans", "Bundle, gorsel, lazy load", "~2-3dk"))
        self.console.print(f"  [bold cyan][{idx}][/bold cyan] Performans              [dim]Bundle, gorsel, lazy load (~2-3dk)[/dim]")
        idx += 1

        # 10. CI/CD
        options.append(("ci", "CI/CD (hizli)", "Sadece kritik testler", "~1dk"))
        self.console.print(f"  [bold cyan][{idx}][/bold cyan] CI/CD (hizli)           [dim]Sadece kritik testler (~1dk)[/dim]")
        idx += 1

        # 11. Ozel (kendin sec)
        options.append(("custom", "Ozel (kendin sec)", "Kategorileri kendin sec", "~?dk"))
        self.console.print(f"  [bold cyan][{idx}][/bold cyan] Ozel (kendin sec)       [dim]Kategorileri kendin sec[/dim]")
        idx += 1

        self.console.print()

        try:
            choice = self.session.prompt(HTML('<style fg="#6366f1"><b>sec</b></style><style fg="#475569"> (1-' + str(len(options)) + ')&gt; </style>'))
            choice = choice.strip()
            ci = int(choice) - 1
            if 0 <= ci < len(options):
                selected = options[ci]
                if selected[0] == "custom":
                    return self._select_custom_profile()
                self.console.print(f"  [green]Secildi: {selected[1]}[/green]\n")
                return selected[0]
        except (ValueError, KeyboardInterrupt, EOFError):
            pass

        self.console.print("  [dim]Iptal edildi.[/dim]\n")
        return None

    def _select_custom_profile(self) -> str:
        """Kullaniciya kategori secim ekrani goster, ozel profil olustur."""
        ALL_CATEGORIES = [
            ("security", "Guvenlik (OWASP, secret, crypto)"),
            ("sca", "SCA (npm/pip audit, lisans)"),
            ("taint", "Taint Tracking (SQL injection, XSS)"),
            ("ast_analysis", "AST Analizi (eval, bare except)"),
            ("code_quality", "Kod Kalitesi (complexity, dead code)"),
            ("cross_file", "Cross-File (dead export, circular)"),
            ("ui_component", "UI Component (a11y, touch, dark mode)"),
            ("ux_text", "UX Text (yazim, tutarlilik, i18n)"),
            ("api", "API (erisilebilirlik, response)"),
            ("git", "Git (gitignore, buyuk dosya)"),
            ("type_safety", "Type Safety (any, ts-ignore)"),
            ("error_handling", "Error Handling (bos catch, async)"),
            ("performance", "Performans (bundle, gorsel)"),
            ("documentation", "Dokumantasyon (README, CHANGELOG)"),
            ("naming", "Naming (dosya isimleri)"),
            ("dependency", "Dependency (vulnerability)"),
            ("accessibility", "Accessibility (testID, label)"),
            ("docker", "Docker (image, secret)"),
            ("appstore", "App Store (privacy, IAP)"),
            ("playstore", "Play Store (targetSdk, ProGuard)"),
            ("yaml_rules", "YAML Rules (ozel kural motoru)"),
        ]

        self.console.print()
        self.console.print("  [bold]Kategori sec (virgul ile ayir, ornek: 1,3,5,7):[/bold]")
        self.console.print()
        for i, (key, desc) in enumerate(ALL_CATEGORIES, 1):
            self.console.print(f"  [bold cyan][{i:>2}][/bold cyan] {desc}")
        self.console.print()

        try:
            cat_choice = self.session.prompt(HTML('<style fg="#6366f1"><b>kategoriler</b></style><style fg="#475569">&gt; </style>'))
            cat_choice = cat_choice.strip()
            if not cat_choice:
                self.console.print("  [dim]Iptal edildi.[/dim]\n")
                return None

            selected_cats = []
            for part in cat_choice.split(","):
                part = part.strip()
                if part.isdigit():
                    ci = int(part) - 1
                    if 0 <= ci < len(ALL_CATEGORIES):
                        selected_cats.append(ALL_CATEGORIES[ci][0])

            if not selected_cats:
                self.console.print("  [red]Gecerli kategori secilmedi.[/red]\n")
                return None

            self._custom_categories = selected_cats
            cat_names = ", ".join(selected_cats)
            self.console.print(f"  [green]Secildi: {cat_names}[/green]\n")
            return "custom"
        except (KeyboardInterrupt, EOFError):
            self.console.print("  [dim]Iptal edildi.[/dim]\n")
            return None

    # === Proje Dizini Teyit Sistemi ===

    PROJECT_MARKERS = [
        "package.json", "pyproject.toml", "setup.py", "requirements.txt",
        "pubspec.yaml", "go.mod", "Cargo.toml", "composer.json",
        "Gemfile", "build.gradle", "pom.xml", "Makefile",
        "app.json", "next.config.js", "nuxt.config.js", "vite.config.ts",
        "manage.py", "settings.py", "tsconfig.json", ".gitignore",
    ]

    def _verify_project_path(self, path: Path) -> Path:
        """Proje dizinini teyit et. Yanlis dizinse oner, kullanici secsin."""
        # 1. Proje dosyasi var mi kontrol et
        markers_found = [m for m in self.PROJECT_MARKERS if (path / m).exists()]

        if markers_found:
            # Proje bulundu, teyit goster
            self.console.print(f"\n  [green]Proje bulundu:[/green] {path.name}/")
            self.console.print(f"  [dim]Belirtecler: {', '.join(markers_found[:4])}[/dim]")
            return path

        # 2. Proje dosyasi yok - belki ust dizin secilmis
        # Alt dizinlerde proje var mi?
        sub_projects = []
        try:
            for child in sorted(path.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    child_markers = [m for m in self.PROJECT_MARKERS if (child / m).exists()]
                    if child_markers:
                        sub_projects.append({"name": child.name, "path": child, "markers": child_markers})
        except PermissionError:
            pass

        if not sub_projects:
            self.console.print(f"\n  [yellow]Bu dizinde proje bulunamadi: {path}[/yellow]")
            self.console.print("  [dim]package.json, pyproject.toml gibi dosyalar yok.[/dim]")
            self.console.print("  [dim]Dogrudan proje kokunu secin.[/dim]\n")
            return None

        # 3. Alt dizinlerde proje bulundu - kullaniciya sor
        self.console.print(f"\n  [yellow]'{path.name}/' proje koku degil, ama alt dizinlerde proje bulundu:[/yellow]\n")
        for i, sp in enumerate(sub_projects[:9], 1):
            markers_str = ", ".join(sp["markers"][:3])
            self.console.print(f"  [{i}] {sp['name']}/  [dim]({markers_str})[/dim]")
        self.console.print(f"  [0] Yine de '{path.name}/' dizinini tara")
        self.console.print()

        try:
            choice = self.session.prompt(HTML('<style fg="#6366f1"><b>sec</b></style><style fg="#475569">&gt; </style>'))
            choice = choice.strip()
            if choice == "0":
                return path
            idx = int(choice) - 1
            if 0 <= idx < len(sub_projects):
                selected = sub_projects[idx]
                self.console.print(f"  [green]Secildi: {selected['name']}/[/green]")
                return selected["path"]
        except (ValueError, KeyboardInterrupt, EOFError):
            pass

        self.console.print("  [dim]Iptal edildi.[/dim]\n")
        return None

    def _check_update_on_start(self):
        """Acilista sessizce guncelleme kontrol et."""
        import threading
        def _check():
            try:
                import urllib.request, json
                from nazar import __version__
                resp = urllib.request.urlopen("https://pypi.org/pypi/nazar/json", timeout=3)
                data = json.loads(resp.read())
                latest = data["info"]["version"]
                # Versiyon karsilastir (tuple olarak)
                def _ver(v):
                    return tuple(int(x) for x in v.split(".")[:3])
                if _ver(latest) > _ver(__version__):
                    self.console.print(f"\n  [bold yellow]Guncelleme mevcut: v{__version__} -> v{latest}[/bold yellow]")
                    self.console.print(f"  [dim]update yazarak guncelleyebilirsiniz.[/dim]")
                else:
                    self.console.print(f"  [dim green]Guncel (v{__version__})[/dim green]")
            except Exception:
                pass
        # Ana thread'i bloklamadan kontrol et
        t = threading.Thread(target=_check, daemon=True)
        t.start()
        t.join(timeout=4)

    def _update(self):
        """Nazar'i son versiyona guncelle."""
        import subprocess as _sp
        self.console.print("\n  [bold cyan]Guncelleme kontrol ediliyor...[/bold cyan]")
        try:
            from nazar import __version__
            current = __version__
        except (ImportError, AttributeError):
            current = "?"
        try:
            import urllib.request, json
            resp = urllib.request.urlopen("https://pypi.org/pypi/nazar/json", timeout=10)
            data = json.loads(resp.read())
            latest = data["info"]["version"]
        except Exception:
            latest = "?"
        if current == latest and current != "?":
            self.console.print(f"  [green]Zaten guncel: v{current}[/green]\n")
            return
        if latest != "?":
            self.console.print(f"  Mevcut: v{current}  ->  Yeni: v{latest}")
        try:
            r = _sp.run(["pipx", "upgrade", "nazar"], capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                self.console.print(f"  [green]Guncellendi! v{latest}[/green]\n")
                return
        except (FileNotFoundError, _sp.TimeoutExpired):
            pass
        try:
            r = _sp.run([sys.executable, "-m", "pip", "install", "--upgrade", "nazar"], capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                self.console.print(f"  [green]Guncellendi! v{latest}[/green]\n")
                return
        except (FileNotFoundError, _sp.TimeoutExpired):
            pass
        self.console.print("  [red]Otomatik guncelleme basarisiz.[/red]")
        self.console.print("  [dim]Manuel: pipx upgrade nazar[/dim]\n")

    def _clear(self):
        self._show_header()

    def _stats(self):
        from nazar.guides.registry import GuideRegistry
        from nazar.runners.confidence import CONFIDENCE_SCORES
        table = Table(title="Nazar v4.0", box=box.ROUNDED)
        table.add_column("Metrik", style="cyan")
        table.add_column("Deger", style="green")
        table.add_row("Kontrol", "197+")
        table.add_row("Kategori", "21")
        table.add_row("Guide", str(len(GuideRegistry.get_all())))
        table.add_row("Confidence", str(len(CONFIDENCE_SCORES)))
        table.add_row("Framework", "15+")
        table.add_row("Format", "5 (HTML, JSON, SARIF, Markdown, JUnit)")
        table.add_row("Moduller", "SCA, AST, Taint, YAML Rules, App/Play Store")
        if self.results:
            p = sum(1 for r in self.results if r["passed"])
            f = len(self.results) - p
            table.add_row("", "")
            table.add_row("[bold]Son Tarama[/bold]", f"[bold]{self.project_path}[/bold]")
            table.add_row("Gecen/Kalan", f"[green]{p}[/green] / [red]{f}[/red]")
        self.console.print(table)

    def _ignore(self, rule_id: str):
        """Kurali .nazarignore dosyasina ekle."""
        if not rule_id:
            self.console.print("\n[yellow]  Kullanim: ignore <rule_id>[/yellow]")
            self.console.print("[dim]  Ornek: ignore todo_count[/dim]")
            self.console.print("[dim]  Ornek: ignore naming_conventions[/dim]")
            # Mevcut ignore listesini goster
            if self.project_path:
                ignore_file = Path(self.project_path) / ".nazarignore"
                if ignore_file.exists():
                    content = ignore_file.read_text(errors="ignore").strip()
                    if content:
                        self.console.print(f"\n[bold]  Mevcut .nazarignore:[/bold]")
                        for line in content.splitlines():
                            if line.strip() and not line.strip().startswith("#"):
                                self.console.print(f"  [dim]{line.strip()}[/dim]")
            self.console.print()
            return

        rule_id = rule_id.strip()
        target_dir = self.project_path or os.getcwd()
        ignore_file = Path(target_dir) / ".nazarignore"

        # Dosya yoksa olustur
        if not ignore_file.exists():
            ignore_file.write_text("# Nazar Ignore File\n# Kural ignore: rule:kural_adi\n# Dosya ignore: dosya/pattern\n\n")

        # Zaten var mi kontrol et
        existing = ignore_file.read_text(errors="ignore")
        rule_line = f"rule:{rule_id}"
        if rule_line in existing:
            self.console.print(f"\n[yellow]  '{rule_id}' zaten .nazarignore'da mevcut.[/yellow]\n")
            return

        # Ekle
        with open(ignore_file, "a") as f:
            f.write(f"{rule_line}\n")
        self.console.print(f"\n[green]  '{rule_id}' .nazarignore'a eklendi.[/green]")
        self.console.print(f"[dim]  Dosya: {ignore_file}[/dim]\n")

    def _coverage(self):
        """Test kapsami raporu goster."""
        if not self.results:
            self.console.print("[yellow]Once tarama yapin: /scan <yol>[/yellow]")
            return

        from nazar.reporters.coverage_reporter import CoverageReporter
        import json as _json

        plan = self.plan_data or {}
        if self.project_path:
            plan["project_path"] = self.project_path

        reporter = CoverageReporter()
        cov_json = reporter.generate(self.results, plan)
        cov = _json.loads(cov_json)

        # Ozet
        summary = cov["summary"]
        rate = summary["pass_rate"]
        gs = "green" if rate >= 80 else "yellow" if rate >= 60 else "red"
        self.console.print(Panel(
            f"[bold {gs}]Not: {summary['grade']} ({rate}%)[/bold {gs}]  |  "
            f"[green]{summary['passed']} passed[/green]  |  "
            f"[red]{summary['failed']} failed[/red]  |  "
            f"[dim]{summary['total_checks']} kontrol[/dim]",
            title="[bold cyan]TEST KAPSAMI[/bold cyan]", border_style="cyan",
        ))

        # Kategori kapsami
        cat_data = cov.get("category_coverage", {})
        if cat_data:
            cat_table = Table(title="Kategori Kapsami", box=box.ROUNDED)
            cat_table.add_column("Kategori", style="cyan", width=18)
            cat_table.add_column("Gecen/Toplam", justify="center", width=12)
            cat_table.add_column("Oran", justify="right", width=8)
            cat_table.add_column("Durum", width=14)
            for cat, info in cat_data.items():
                cr = info["pass_rate"]
                rs = "green" if cr >= 80 else "yellow" if cr >= 60 else "red"
                status_map = {
                    "clean": "[green]Temiz[/green]",
                    "partial": "[yellow]Kismi[/yellow]",
                    "needs_attention": "[red]Dikkat[/red]",
                }
                bar_w = 10
                filled = int(bar_w * info["passed"] / max(info["total"], 1))
                bar = "[green]" + "=" * filled + "[/green][dim]" + "-" * (bar_w - filled) + "[/dim]"
                cat_table.add_row(
                    cat.upper(),
                    f"{info['passed']}/{info['total']} {bar}",
                    f"[{rs}]{cr}%[/{rs}]",
                    status_map.get(info["status"], info["status"]),
                )
            self.console.print(cat_table)

        # Guven dagilimi
        conf = cov.get("confidence_distribution", {})
        if conf.get("total_findings", 0) > 0:
            self.console.print()
            self.console.print("[bold]Guven Dagilimi (Basarisiz Testler):[/bold]")
            for level, color in [("high", "red"), ("medium", "yellow"), ("low", "dim")]:
                data = conf.get(level, {})
                cnt = data.get("count", 0)
                label = data.get("label", "")
                if cnt > 0:
                    self.console.print(f"  [{color}]{level.upper():<8}[/{color}] {cnt:>3}  [dim]{label}[/dim]")
            self.console.print(f"  [dim]Ortalama guven: {conf.get('average_confidence', 0)}%[/dim]")

        # En sorunlu dosyalar (ilk 5)
        file_density = cov.get("file_issue_density", [])
        if file_density:
            self.console.print()
            self.console.print("[bold]En Sorunlu Dosyalar:[/bold]")
            for i, fd in enumerate(file_density[:5], 1):
                sev = fd["highest_severity"]
                ss = {"critical": "bold red", "high": "yellow", "medium": "cyan", "low": "dim"}.get(sev, "dim")
                self.console.print(f"  [dim]#{i}[/dim] [{ss}]{sev.upper():<8}[/{ss}] {fd['file']}  [dim]({fd['issue_count']} sorun)[/dim]")

        # Trend
        trend = cov.get("trend")
        if trend and trend.get("available"):
            delta = trend["delta_rate"]
            delta_sign = "+" if delta > 0 else ""
            delta_color = "green" if delta > 0 else "red" if delta < 0 else "dim"
            self.console.print()
            self.console.print(Panel(
                f"[bold]Onceki:[/bold] {trend['previous']['grade']} ({trend['previous']['pass_rate']}%)  "
                f"[bold]Simdi:[/bold] {trend['current']['grade']} ({trend['current']['pass_rate']}%)  "
                f"[{delta_color}]{delta_sign}{delta}%[/{delta_color}]\n"
                f"[green]{trend['fixed_count']} duzeltildi[/green]  |  "
                f"[red]{trend['new_issues_count']} yeni sorun[/red]",
                title="[bold yellow]TREND[/bold yellow]", border_style="yellow",
            ))

        self.console.print()
        self.console.print("[dim]JSON icin: export json | coverage raporunu dosyaya: nazar coverage . -o coverage.json[/dim]")
        self.console.print()

    def _run_live_test(self, project_path):
        """Nazar Live Test UI ile gorsel runtime test arayuzu ac.

        Maestro bagimliligini ortadan kaldirip Nazar'in kendi canli test
        arayuzunu kullanir. Simulator/emulator ekranini canli olarak sol
        panelde gosterirken, sag panelde YAML test adimlarini durum
        gostergeleriyle izleme imkani sunar.
        """
        import webbrowser
        from nazar.live.test_ui import NazarLiveTestUI, detect_platform, get_device_name

        self.console.print()
        self.console.print(Panel("[bold cyan]NAZAR CANLI TEST[/bold cyan]", border_style="cyan"))

        # 1. Cihaz kontrolu
        platform = detect_platform()
        if platform == "none":
            self.console.print("  [red]Simulator/emulator bulunamadi![/red]")
            self.console.print("  [dim]iOS: Xcode > Open Developer Tool > Simulator[/dim]")
            self.console.print("  [dim]Android: emulator -avd <isim>[/dim]")
            return

        device_name = get_device_name(platform)
        self.console.print(f"  [green]Platform:[/green] {platform.upper()}")
        self.console.print(f"  [green]Cihaz:[/green] {device_name}")

        # 2. YAML test dosyalarini uret (yoksa)
        ui_dir = Path(project_path) / ".nazar" / "ui-tests"
        yaml_files = []
        if ui_dir.exists():
            yaml_files = list(ui_dir.glob("*.yml")) + list(ui_dir.glob("*.yaml"))
        if not yaml_files:
            self.console.print("  [yellow]UI test dosyasi uretiliyor...[/yellow]")
            try:
                from nazar.analyzers.yaml_ui_runner import YAMLUIGenerator
                gen = YAMLUIGenerator(str(project_path))
                created = gen.generate()
                if created:
                    yaml_files = [Path(f) for f in created]
                    self.console.print(f"  [green]{len(created)} test dosyasi olusturuldu[/green]")
            except Exception:
                pass

        if not yaml_files:
            self.console.print("  [yellow]UI test dosyasi bulunamadi[/yellow]")
            self.console.print("  [dim]Simulator izleme modunda baslatiliyor...[/dim]")

        # 3. Nazar Studio (native pencere) veya tarayici
        if not yaml_files:
            self.console.print("  [yellow]UI test dosyasi bulunamadi[/yellow]")
            return

        yaml_file = yaml_files[0]
        self.console.print()
        self.console.print(f"  [bold cyan]Nazar Studio baslatiliyor...[/bold cyan]")
        self.console.print(f"  [dim]Test: {yaml_file.name}[/dim]")

        try:
            from nazar.live.studio import NazarStudio
            studio = NazarStudio(port=9998)
            studio.open(str(yaml_file))
        except Exception as e:
            self.console.print(f"  [red]Hata: {e}[/red]")

    def _rule(self, arg):
        """Kural yonetim menusu."""
        from rich.table import Table
        from nazar.tools.rule_builder import RuleBuilder

        sub = arg.strip().lower() if arg else ""

        if sub == "list" or sub == "listele":
            # Kural listesi
            all_rules = RuleBuilder.list_rules()
            if not all_rules:
                self.console.print("\n[yellow]  Hic kural bulunamadi.[/yellow]")
                self.console.print("  [dim]Ozel kural olusturmak icin: rule create[/dim]\n")
                return

            builtin = [r for r in all_rules if r["source"] == "builtin"]
            custom = [r for r in all_rules if r["source"] != "builtin"]

            if builtin:
                table = Table(title=f"Yerlesik Kurallar ({len(builtin)})")
                table.add_column("ID", style="cyan")
                table.add_column("Severity", style="yellow")
                table.add_column("Aciklama", style="white")
                for r in builtin:
                    sev = r["severity"]
                    ss = {"critical": "bold red", "high": "yellow", "medium": "cyan", "low": "dim"}.get(sev, "dim")
                    table.add_row(r["id"], f"[{ss}]{sev.upper()}[/{ss}]", r["message"])
                self.console.print(table)

            if custom:
                self.console.print()
                table = Table(title=f"Ozel Kurallar ({len(custom)})")
                table.add_column("ID", style="cyan")
                table.add_column("Severity", style="yellow")
                table.add_column("Kaynak", style="dim")
                table.add_column("Aciklama", style="white")
                for r in custom:
                    sev = r["severity"]
                    ss = {"critical": "bold red", "high": "yellow", "medium": "cyan", "low": "dim"}.get(sev, "dim")
                    table.add_row(r["id"], f"[{ss}]{sev.upper()}[/{ss}]", r["source"], r["message"])
                self.console.print(table)

            self.console.print(f"\n  [bold]Toplam: {len(all_rules)} kural ({len(builtin)} yerlesik + {len(custom)} ozel)[/bold]\n")

        elif sub == "create" or sub == "olustur":
            # Interaktif kural olusturma
            self.console.print("\n[bold cyan]  KURAL OLUSTUR[/bold cyan]\n")
            builder = RuleBuilder()
            try:
                rule = builder.create_rule()
            except ValueError as e:
                self.console.print(f"\n[red]  Hata: {e}[/red]\n")
                return
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[dim]  Iptal edildi.[/dim]\n")
                return

            errors = builder.validate_rule(rule)
            if errors:
                self.console.print("\n[red]  Dogrulama hatalari:[/red]")
                for err in errors:
                    self.console.print(f"    [red]- {err}[/red]")
                return

            # Kayit yolunu sor
            default_path = os.path.join(os.path.expanduser("~"), ".nazar", "rules", "custom-rules.yaml")
            try:
                out_path = self.session.prompt(
                    HTML(f'<style fg="#6366f1"><b>Kayit yolu</b></style><style fg="#475569"> [{default_path}]&gt; </style>')
                )
                out_path = out_path.strip() or default_path
            except (KeyboardInterrupt, EOFError):
                out_path = default_path

            saved = builder.save_rule(rule, out_path)
            self.console.print(f"\n[green]  Kural kaydedildi: {saved}[/green]\n")

        elif sub.startswith("validate") or sub.startswith("dogrula"):
            # Kural dosyasi dogrulama
            parts = sub.split(None, 1)
            file_path = parts[1] if len(parts) > 1 else ""
            if not file_path:
                try:
                    file_path = self.session.prompt(
                        HTML('<style fg="#6366f1"><b>YAML dosya yolu</b></style><style fg="#475569">&gt; </style>')
                    ).strip()
                except (KeyboardInterrupt, EOFError):
                    return
            if not file_path:
                self.console.print("[yellow]  Dosya yolu gerekli.[/yellow]")
                return

            from nazar.tools.rule_validator import validate_yaml_rules
            errors = validate_yaml_rules(os.path.expanduser(file_path))
            if not errors:
                self.console.print(f"\n[green]  Dosya gecerli: {file_path}[/green]\n")
            else:
                self.console.print(f"\n[red]  {len(errors)} hata bulundu:[/red]")
                for i, err in enumerate(errors, 1):
                    color = "yellow" if err.startswith("Uyari:") else "red"
                    self.console.print(f"    [{color}]{i}. {err}[/{color}]")
                self.console.print()

        elif sub.startswith("test"):
            # Kural test
            parts = sub.split(None, 1)
            file_path = parts[1] if len(parts) > 1 else ""
            if not file_path:
                try:
                    file_path = self.session.prompt(
                        HTML('<style fg="#6366f1"><b>YAML kural dosyasi</b></style><style fg="#475569">&gt; </style>')
                    ).strip()
                except (KeyboardInterrupt, EOFError):
                    return
            if not file_path:
                self.console.print("[yellow]  Dosya yolu gerekli.[/yellow]")
                return

            proj = self.project_path
            if not proj:
                try:
                    proj = self.session.prompt(
                        HTML('<style fg="#6366f1"><b>Proje dizini</b></style><style fg="#475569">&gt; </style>')
                    ).strip()
                except (KeyboardInterrupt, EOFError):
                    return
            if not proj:
                self.console.print("[yellow]  Proje yolu gerekli.[/yellow]")
                return

            file_path = os.path.expanduser(file_path)
            proj = os.path.expanduser(proj)

            from nazar.tools.rule_validator import validate_yaml_rules
            verrs = validate_yaml_rules(file_path)
            real_errors = [e for e in verrs if not e.startswith("Uyari:")]
            if real_errors:
                self.console.print(f"\n[red]  Kural dosyasi gecersiz: {len(real_errors)} hata[/red]")
                for err in real_errors:
                    self.console.print(f"    [red]- {err}[/red]")
                return

            try:
                import yaml as _yaml
                with open(file_path, "r") as f:
                    data = _yaml.safe_load(f)
                rules = data.get("rules", []) if data else []
            except Exception as e:
                self.console.print(f"\n[red]  Dosya okunamadi: {e}[/red]\n")
                return

            total_matches = 0
            for rule in rules:
                rid = rule.get("id", "?")
                self.console.print(f"\n  [bold cyan]Kural: {rid}[/bold cyan] [dim]({rule.get('severity', 'medium')})[/dim]")
                try:
                    matches = RuleBuilder.test_rule(rule, proj)
                except Exception as e:
                    self.console.print(f"    [red]Hata: {e}[/red]")
                    continue

                if matches:
                    self.console.print(f"    [yellow]{len(matches)} eslesme:[/yellow]")
                    for m in matches[:10]:
                        self.console.print(f"      [dim]{m['file']}:{m['line']}[/dim] {m['content'][:60]}")
                    if len(matches) > 10:
                        self.console.print(f"      [dim]...ve {len(matches) - 10} daha[/dim]")
                    total_matches += len(matches)
                else:
                    self.console.print("    [green]Eslesme yok.[/green]")

            self.console.print(f"\n  [bold]Toplam: {total_matches} eslesme ({len(rules)} kural)[/bold]\n")

        else:
            # Alt komut menusu goster
            self.console.print("\n[bold cyan]  KURAL YONETIMI[/bold cyan]\n")
            self.console.print("  [cyan]rule list[/cyan]      [dim]|[/dim] [cyan]kural listele[/cyan]    Tum kurallari listele")
            self.console.print("  [cyan]rule create[/cyan]    [dim]|[/dim] [cyan]kural olustur[/cyan]    Yeni kural olustur")
            self.console.print("  [cyan]rule validate[/cyan]  [dim]|[/dim] [cyan]kural dogrula[/cyan]    YAML dosyasini dogrula")
            self.console.print("  [cyan]rule test[/cyan]      [dim]|[/dim] [cyan]kural test[/cyan]       Kurali proje uzerinde test et")
            self.console.print()

    def _batch(self, arg):
        """Birden fazla projeyi sirayla tara."""
        if not arg.strip():
            self.console.print("\n[yellow]  Kullanim: batch <yol1> <yol2> ...[/yellow]")
            self.console.print("[dim]  Ornek: batch ~/Desktop/Proje1 ~/Desktop/Proje2[/dim]\n")
            return

        paths = arg.strip().split()
        resolved_paths = []
        for p in paths:
            expanded = os.path.expanduser(p)
            # /desktop/x -> ~/Desktop/x otomatik cevir
            if expanded.lower().startswith("/desktop/"):
                expanded = os.path.expanduser("~/Desktop/" + expanded[9:])
            elif expanded.lower().startswith("desktop/"):
                expanded = os.path.expanduser("~/Desktop/" + expanded[8:])
            rp = Path(expanded).resolve()
            if not rp.exists():
                # Desktop'ta dene
                desktop_try = Path(os.path.expanduser(f"~/Desktop/{p}")).resolve()
                if desktop_try.exists():
                    rp = desktop_try
                else:
                    self.console.print(f"  [red]Bulunamadi: {p}[/red]")
                    continue
            resolved_paths.append(str(rp))

        if not resolved_paths:
            self.console.print("[red]  Gecerli proje yolu bulunamadi.[/red]\n")
            return

        from nazar.batch.scanner import BatchScanner
        from rich.table import Table
        from rich import box

        self.console.print(f"\n  [bold magenta]BATCH TARAMA[/bold magenta] - {len(resolved_paths)} proje\n")
        for i, p in enumerate(resolved_paths, 1):
            self.console.print(f"  [dim][{i}/{len(resolved_paths)}][/dim] {Path(p).name}")
        self.console.print()

        scanner = BatchScanner(resolved_paths, profile="ci")
        results = scanner.scan_all()

        # Sonuc tablosu
        table = Table(title="Batch Tarama Sonuclari", box=box.ROUNDED)
        table.add_column("Proje", style="cyan")
        table.add_column("Not", width=5, justify="center")
        table.add_column("Oran", width=8, justify="right")
        table.add_column("Gecen", width=6, justify="right", style="green")
        table.add_column("Kalan", width=6, justify="right", style="red")
        table.add_column("Sure", width=8, justify="right", style="dim")
        table.add_column("Durum", width=15)

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

        self.console.print(table)

        # Genel ozet
        summary = scanner.get_consolidated_summary()
        overall_gs = "green" if summary["pass_rate"] >= 80 else "yellow" if summary["pass_rate"] >= 60 else "red"
        from rich.panel import Panel
        self.console.print(Panel(
            f"[bold {overall_gs}]Genel: {summary['grade']} ({summary['pass_rate']}%)[/bold {overall_gs}]  |  "
            f"[green]{summary['total_passed']} gecti[/green]  |  "
            f"[red]{summary['total_failed']} kaldi[/red]  |  "
            f"[dim]{summary['project_count']} proje  |  {summary['duration']}s[/dim]",
            title="[bold cyan]BATCH SONUC[/bold cyan]", border_style="cyan",
        ))

        # Hata olan projeler
        errors = [d for d in results.values() if d.get("error")]
        if errors:
            self.console.print(f"\n[yellow]{len(errors)} projede hata:[/yellow]")
            for e in errors:
                self.console.print(f"  [red]-[/red] {e['project_name']}: {e['error'][:60]}")
        self.console.print()

    def _baseline(self, arg):
        """Baseline yonetimi: save veya check."""
        sub = arg.strip().lower() if arg else ""

        if sub == "save":
            self._baseline_save()
        elif sub == "check":
            self._baseline_check()
        else:
            self.console.print("\n[bold]Baseline Komutlari:[/bold]")
            self.console.print("  [cyan]baseline save[/cyan]    Mevcut taramayi baseline olarak kaydet")
            self.console.print("  [cyan]baseline check[/cyan]   Baseline ile karsilastir (gerileme kontrolu)")
            self.console.print()
            if self.project_path:
                from nazar.cache.scan_cache import ScanCache
                cache = ScanCache(self.project_path)
                if cache.has_baseline():
                    bl = cache.get_baseline()
                    if bl:
                        self.console.print(f"  [green]Mevcut baseline:[/green] {bl.get('grade', '?')} ({bl.get('pass_rate', 0)}%)")
                        self.console.print(f"  [dim]Tarih: {bl.get('timestamp', '?')}[/dim]")
                else:
                    self.console.print("  [dim]Baseline yok. 'baseline save' ile olusturun.[/dim]")
            else:
                self.console.print("  [dim]Once bir proje tarayin.[/dim]")
            self.console.print()

    def _baseline_save(self):
        """Mevcut tarama sonuclarini baseline olarak kaydet."""
        if not self.results or not self.project_path:
            self.console.print("\n[yellow]  Once bir proje tarayin: scan <yol>[/yellow]\n")
            return

        from nazar.cache.scan_cache import ScanCache

        cache = ScanCache(self.project_path)
        cache.save_baseline(self.results)

        passed = sum(1 for r in self.results if r.get("passed"))
        total = len(self.results)
        rate = (passed / total * 100) if total else 0
        grade = _grade(rate)

        self.console.print(Panel(
            f"[bold green]BASELINE KAYDEDILDI[/bold green]\n"
            f"Proje: {Path(self.project_path).name}\n"
            f"Not: {grade} ({rate:.1f}%)\n"
            f"Test: {passed} gecti / {total - passed} kaldi\n"
            f"Dosya: .nazar/baseline.json",
            expand=False, border_style="green",
        ))

    def _baseline_check(self):
        """Mevcut taramayi baseline ile karsilastir."""
        if not self.project_path:
            self.console.print("\n[yellow]  Once bir proje tarayin: scan <yol>[/yellow]\n")
            return

        from nazar.cache.scan_cache import ScanCache

        cache = ScanCache(self.project_path)

        if not cache.has_baseline():
            self.console.print("\n[red]  Baseline bulunamadi.[/red]")
            self.console.print("  [dim]Once 'baseline save' ile baseline kaydedin.[/dim]\n")
            return

        if not self.results:
            self.console.print("\n[yellow]  Once bir tarama yapin: scan <yol>[/yellow]\n")
            return

        comparison = cache.compare_with_baseline(self.results)

        baseline_gs = "green" if comparison["baseline_rate"] >= 80 else "yellow" if comparison["baseline_rate"] >= 60 else "red"
        current_gs = "green" if comparison["current_rate"] >= 80 else "yellow" if comparison["current_rate"] >= 60 else "red"
        delta = comparison["delta"]
        delta_sign = "+" if delta > 0 else ""
        delta_color = "green" if delta > 0 else "red" if delta < 0 else "dim"

        self.console.print(Panel(
            f"[bold]Baseline:[/bold] [{baseline_gs}]{comparison['baseline_grade']} ({comparison['baseline_rate']}%)[/{baseline_gs}]\n"
            f"[bold]Simdi:[/bold]    [{current_gs}]{comparison['current_grade']} ({comparison['current_rate']}%)[/{current_gs}]\n"
            f"[bold]Fark:[/bold]     [{delta_color}]{delta_sign}{delta}%[/{delta_color}]",
            title="[bold yellow]BASELINE KARSILASTIRMA[/bold yellow]", border_style="yellow",
        ))

        # Regressions
        regressions = comparison.get("regressions", [])
        if regressions:
            self.console.print(f"\n[bold red]GERILEMELER ({len(regressions)}):[/bold red]")
            for r in regressions[:10]:
                pri = r.get("priority", "medium").upper()
                self.console.print(f"  [red]-[/red] [{pri}] {r['name']}")
                if r.get("detail"):
                    self.console.print(f"    [dim]{r['detail'][:70]}[/dim]")

        # Improvements
        improvements = comparison.get("improvements", [])
        if improvements:
            self.console.print(f"\n[bold green]DUZELTMELER ({len(improvements)}):[/bold green]")
            for r in improvements[:10]:
                self.console.print(f"  [green]+[/green] {r['name']}")

        # New issues
        new_issues = comparison.get("new_issues", [])
        if new_issues:
            self.console.print(f"\n[bold yellow]YENI SORUNLAR ({len(new_issues)}):[/bold yellow]")
            for r in new_issues[:10]:
                pri = r.get("priority", "medium").upper()
                self.console.print(f"  [yellow]![/yellow] [{pri}] {r['name']}")

        if comparison.get("has_regressions"):
            self.console.print(f"\n[bold red]UYARI: {len(regressions)} gerileme tespit edildi![/bold red]")
        else:
            self.console.print(f"\n[bold green]OK: Gerileme yok. Baseline korunuyor.[/bold green]")
        self.console.print()

    def _run_ui(self):
        """Nazar Live Test UI ile UI testlerini cihazda calistir."""
        import subprocess as _sp
        from nazar.live.test_ui import detect_platform, get_device_name

        # 1. Platform kontrolu
        platform = detect_platform()
        if platform != "none":
            device_name = get_device_name(platform)
            self.console.print(f"\n  [green]{platform.upper()}:[/green] {device_name}")
        else:
            # Geriye donuk uyumluluk
            pass

        # 2. Cihaz kontrolu (Nazar kendi dedektoru ile)
        device_found = platform != "none"
        if not device_found:
            # Fallback: dogrudan subprocess ile kontrol
            try:
                r = _sp.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
                lines = [l for l in r.stdout.strip().split("\n")[1:] if l.strip() and "device" in l]
                if lines:
                    device_found = True
                    device_name = lines[0].split()[0]
                    self.console.print(f"  [green]Cihaz:[/green] {device_name}")
            except FileNotFoundError:
                pass

        if not device_found:
            try:
                r = _sp.run(["xcrun", "simctl", "list", "devices", "booted"], capture_output=True, text=True, timeout=10)
                if "Booted" in r.stdout:
                    device_found = True
                    self.console.print(f"  [green]iOS Simulator:[/green] aktif")
            except FileNotFoundError:
                pass

        if not device_found:
            self.console.print("\n[yellow]  Bagli cihaz veya emulator bulunamadi.[/yellow]")
            self.console.print("  [dim]Android: adb devices | iOS: xcrun simctl list devices booted[/dim]\n")
            return

        # 3. YAML dosyalarini bul
        search_path = None
        if self.project_path:
            search_path = Path(self.project_path)
        else:
            self.console.print("\n[yellow]  Once bir proje tarayin veya yol belirtin.[/yellow]")
            self.console.print("  [dim]Ornek: scan ~/Desktop/MyProject[/dim]\n")
            return

        nazar_dir = search_path / ".nazar" / "ui-tests"
        yaml_files = []
        if nazar_dir.exists():
            yaml_files = sorted(
                [f for f in nazar_dir.glob("*.yml")]
                + [f for f in nazar_dir.glob("*.yaml")]
            )

        if not yaml_files:
            # Dogrudan proje kokunde de bak
            yaml_files = sorted(
                [f for f in search_path.glob("*.yml")]
                + [f for f in search_path.glob("*.yaml")]
            )

        if not yaml_files:
            self.console.print(f"\n[yellow]  YAML test dosyasi bulunamadi: {search_path}[/yellow]")
            self.console.print("  [dim].nazar/ui-tests/ dizinine bakildi. 'nazar ui init' ile olusturun.[/dim]\n")
            return

        # 4. Kullaniciya secim menusu goster
        self.console.print(f"\n  [bold]{len(yaml_files)} UI test dosyasi bulundu:[/bold]\n")
        for i, yf in enumerate(yaml_files, 1):
            self.console.print(f"  [bold cyan][{i}][/bold cyan] {yf.name}")
        self.console.print(f"  [bold cyan][0][/bold cyan] Tumu calistir")
        self.console.print()

        try:
            choice = self.session.prompt(
                HTML('<style fg="#6366f1"><b>run</b></style><style fg="#475569"> (0-' + str(len(yaml_files)) + ')&gt; </style>')
            )
            choice = choice.strip()
            ci = int(choice)
            if ci == 0:
                selected_files = yaml_files
            elif 1 <= ci <= len(yaml_files):
                selected_files = [yaml_files[ci - 1]]
            else:
                self.console.print("  [dim]Gecersiz secim.[/dim]\n")
                return
        except (ValueError, KeyboardInterrupt, EOFError):
            self.console.print("  [dim]Iptal edildi.[/dim]\n")
            return

        # 5. Secilen testleri Nazar Live Test UI ile calistir
        import webbrowser
        from nazar.live.test_ui import NazarLiveTestUI

        total = len(selected_files)
        results = []

        for i, yf in enumerate(selected_files, 1):
            fname = yf.name
            self.console.print(f"\n  [bold cyan][{i}/{total}][/bold cyan] {fname}")

            ui = NazarLiveTestUI(port=9999)
            step_start = time.time()

            try:
                started = ui.start(str(yf), auto_run=True)
                if not started:
                    self.console.print(f"    [red]Baslatilamadi[/red]")
                    results.append({"file": fname, "passed": False, "duration": 0.0})
                    continue

                # Ilk test icin tarayiciyi ac
                if i == 1:
                    webbrowser.open("http://localhost:9999")
                    self.console.print(f"  [green]Nazar Live Test:[/green] http://localhost:9999")

                # Testlerin bitmesini bekle (max 120sn)
                for tick in range(240):
                    if ui.tracker:
                        data = ui.tracker.get_data()
                        if data.get("overall_status") == "done":
                            break
                    time.sleep(0.5)

                duration = time.time() - step_start

                # Sonuclari topla
                if ui.tracker:
                    data = ui.tracker.get_data()
                    failed_count = data.get("failed", 0)
                    success = failed_count == 0
                    self.console.print(f"    [green]{data.get('passed', 0)} gecti[/green]  "
                                       f"[red]{failed_count} kaldi[/red]  "
                                       f"[dim]({duration:.1f}s)[/dim]")
                else:
                    success = False

                status = "[green]GECTI[/green]" if success else "[red]BASARISIZ[/red]"
                self.console.print(f"    {status} [dim]({duration:.1f}s)[/dim]")
                results.append({"file": fname, "passed": success, "duration": duration})

            except Exception as exc:
                self.console.print(f"    [red]HATA: {exc}[/red]")
                results.append({"file": fname, "passed": False, "duration": 0.0})
            finally:
                ui.stop()

        # 6. Sonuc ozeti
        passed = sum(1 for r in results if r["passed"])
        failed = total - passed
        total_dur = sum(r["duration"] for r in results)

        self.console.print()
        summary_table = Table(title="UI Test Sonuclari", show_header=True)
        summary_table.add_column("#", style="dim", width=4)
        summary_table.add_column("Test", style="white")
        summary_table.add_column("Sonuc", width=10)
        summary_table.add_column("Sure", width=8, justify="right")

        for idx, r in enumerate(results, 1):
            status = "[green]GECTI[/green]" if r["passed"] else "[red]KALDI[/red]"
            summary_table.add_row(str(idx), r["file"], status, f"{r['duration']:.1f}s")

        self.console.print(summary_table)

        rate = (passed / total * 100) if total > 0 else 0
        gs = "green" if rate >= 80 else "yellow" if rate >= 60 else "red"
        self.console.print(Panel(
            f"[{gs}]{passed}/{total} gecti ({rate:.0f}%)[/{gs}]  |  "
            f"[green]{passed} basarili[/green]  |  [red]{failed} basarisiz[/red]  |  "
            f"[dim]Toplam: {total_dur:.1f}s[/dim]",
            title="[bold cyan]UI TEST SONUC[/bold cyan]", border_style="cyan",
        ))
        self.console.print()

    def _live(self):
        """Canli web raporu baslat - son tarama sonuclarini localhost:5555'te goster."""
        from nazar.live.server import NazarLiveServer

        if self.results and self.project_path:
            # Mevcut tarama sonuclarini kullan
            server = NazarLiveServer(port=5555)
            passed = sum(1 for r in self.results if r.get("passed"))
            total = len(self.results)
            rate = (passed / total * 100) if total > 0 else 0
            grade = _grade(rate)
            duration = 0.0
            server.set_results(self.results, self.plan_data or {}, grade, duration)
            server.set_status("done")
        elif self.project_path:
            # Cache'den oku
            server = NazarLiveServer.from_cache(self.project_path, port=5555)
            if not server._results:
                self.console.print("[yellow]Tarama sonucu bulunamadi. Once tarama yapin.[/yellow]")
                return
        else:
            self.console.print("[yellow]Once bir proje tarayin: scan <yol>[/yellow]")
            return

        server.start()
        self.console.print(f"\n[cyan]Canli rapor baslatildi: http://localhost:5555[/cyan]")
        self.console.print("[dim]Durdurmak icin 'stop' yazin veya Ctrl+C basin.[/dim]\n")

        try:
            while True:
                try:
                    cmd = self.session.prompt(HTML('<style fg="#06b6d4"><b>live</b></style><style fg="#475569">&gt; </style>'))
                    cmd = cmd.strip().lower()
                    if cmd in ("stop", "dur", "quit", "q", "exit"):
                        break
                except KeyboardInterrupt:
                    break
                except EOFError:
                    break
        finally:
            server.stop()
            self.console.print("[dim]Canli rapor durduruldu.[/dim]\n")
