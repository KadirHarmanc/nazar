# Nazar - Mimari Genel Bakis

Nazar, projeleri otonom olarak tarayan, test plani olusturan, testleri calistiran ve raporlayan bir guvenlik ve kalite tarayicisidir.

## Ana Pipeline

```
Scanner -> Planner -> Orchestrator -> Reporter
```

1. **Scanner** projeyi analiz eder, teknoloji yigini/dil/framework/ekran/API bilgisini cikarir.
2. **Planner** scan sonucuna gore hangi testlerin calistirilacagini planlar (profil destegi ile).
3. **Orchestrator** plani alir, ilgili runner ve analyzer'lara delege ederek paralel calistirir.
4. **Reporter** sonuclari HTML, JSON, SARIF, Markdown, JUnit veya Coverage formatlarinda sunar.

## Modul Aciklamalari

| Modul | Konum | Gorev |
|-------|-------|-------|
| **ProjectScanner** | `scanner/project_scanner.py` | Proje dizinini tarar, tech stack/dil/framework/ekran/API bilgisini cikarir. |
| **TestPlanner** | `planner/test_planner.py` | Scan sonucuna ve profil secimene gore test plani olusturur. |
| **TestOrchestrator** | `runners/orchestrator.py` | Plani alir, runner/analyzer'lara delege eder, paralel calistirir. |
| **DeepSecurityScanner** | `runners/security_scanner.py` | 50+ guvenlik kontrolu: secret, OWASP, crypto, injection. |
| **UXTextAnalyzer** | `runners/ux_text_analyzer.py` | Yazim, tutarlilik, i18n metin kontrolleri. |
| **UIComponentTester** | `runners/ui_component_tester.py` | Erisebilirlik, touch target, dark mode kontrolleri. |
| **CrossFileAnalyzer** | `runners/cross_analyzer.py` | Dead export, orphan dosya, circular import tespiti. |
| **AppStoreChecker** | `runners/appstore_checker.py` | Apple App Store uyumluluk kontrolleri (privacy manifest, IAP vb.). |
| **PlayStoreChecker** | `runners/playstore_checker.py` | Google Play Store uyumluluk kontrolleri. |
| **SCAScanner** | `runners/sca_scanner.py` | npm/pip/go audit, typosquatting, lisans taramasi. |
| **ComplianceChecker** | `runners/compliance_checker.py` | Uyumluluk ve standart kontrolleri. |
| **PythonASTAnalyzer** | `analyzers/ast_python.py` | Python AST analizi: eval, bare except, mutable default. |
| **TaintTracker** | `analyzers/taint_tracker.py` | SQL injection, XSS, command injection akis analizi. |
| **YAMLRuleEngine** | `analyzers/pattern_engine.py` | Semgrep benzeri YAML tabanli ozel kural motoru. |
| **UIAnalyzer** | `analyzers/ui_analyzer.py` | UI bilesenlerini analiz eder. |
| **SpellChecker** | `analyzers/spell_checker.py` | Kod icerisinde yazim hatasi kontrolu. |
| **UIQualityAnalyzer** | `analyzers/ui_quality.py` | UI kalite metrikleri. |
| **I18nAnalyzer** | `analyzers/i18n_analyzer.py` | Uluslararasilastirma uyumluluk kontrolu. |
| **ResponsiveAnalyzer** | `analyzers/responsive_analyzer.py` | Responsive tasarim kontrolleri. |
| **PerformanceStaticAnalyzer** | `analyzers/performance_analyzer.py` | Statik performans analizi (buyuk dosya, gorsel vb.). |
| **VisualRegressionAnalyzer** | `analyzers/visual_regression.py` | Gorsel regresyon tespiti. |
| **ConfidenceScorer** | `runners/confidence.py` | Her bulguya 0-100 arasi guven puani verir. |
| **HTMLReporter** | `reporter/html_reporter.py` | Interaktif HTML rapor olusturur. |
| **JSONReporter** | `reporters/json_reporter.py` | JSON formati rapor ciktisi. |
| **SARIFReporter** | `reporters/sarif_reporter.py` | SARIF formati (GitHub Code Scanning uyumlu). |
| **MarkdownReporter** | `reporters/markdown_reporter.py` | Markdown formati rapor. |
| **JUnitReporter** | `reporters/junit_reporter.py` | JUnit XML formati (CI/CD uyumlu). |
| **CoverageReporter** | `reporters/coverage_reporter.py` | Test kapsami raporu: kategori/dosya/guven/trend verileri. |
| **NazarShell** | `interactive/shell.py` | Interaktif terminal arayuzu (prompt_toolkit tabanli). |
| **CLI** | `cli.py` | Typer tabanli komut satiri arayuzu. |
| **ScanCache** | `cache/scan_cache.py` | Incremental tarama icin dosya hash hafizasi ve tarama gecmisi. |
| **ConfigLoader** | `config/loader.py` | nazar.yaml yapilandirma dosyasi yukleyici. |
| **PluginManager** | `plugins/manager.py` | Harici plugin yukleme ve yonetimi. |
| **GuideRegistry** | `guides/registry.py` | Her bulgu icin adim adim duzeltme rehberleri. |
| **BatchScanner** | `batch/scanner.py` | Birden fazla projeyi sirayla tarar. |
| **NazarLiveServer** | `live/server.py` | Tarama sirasinda canli web raporu sunucusu. |
| **GitHubPRReporter** | `integrations/github_pr.py` | GitHub PR comment ve SARIF entegrasyonu. |
| **MaestroExecutor** | `executors/maestro_executor.py` | Maestro ile mobil UI testlerini cihazda calistirir. |
| **DeviceManager** | `executors/device_manager.py` | Simulator/emulator cihaz yonetimi. |
| **RuleBuilder** | `tools/rule_builder.py` | Interaktif YAML kural olusturucu. |
| **RuleValidator** | `tools/rule_validator.py` | YAML kurallarini dogrular ve test eder. |

## Yeni Kontrol Ekleme

1. `runners/` veya `analyzers/` altinda uygun dosyayi bulun (veya yeni dosya olusturun).
2. Kontrol fonksiyonunu yazin. Donus: `(passed: bool, detail: str)` tuple'i.
3. `runners/orchestrator.py` icindeki `_run_test` metoduna yeni subtype eslemesi ekleyin.
4. `runners/confidence.py` icindeki `CONFIDENCE_SCORES` sozlugune yeni subtype icin guven puani ekleyin.
5. `guides/registry.py` icine opsiyonel bir duzeltme rehberi ekleyin.

Ornek:

```python
# runners/orchestrator.py icinde
elif subtype == "my_new_check":
    passed, detail = self._check_my_new_thing(test, project_path)
```

## Plugin Olusturma

1. `nazar.plugins.base.BaseTestPlugin` sinifini extend edin:

```python
from nazar.plugins.base import BaseTestPlugin

class MyPlugin(BaseTestPlugin):
    name = "my-plugin"
    version = "1.0.0"
    description = "Ozel kontrol plugini"

    def get_tests(self, scan_result):
        """Plugin'in calistiracagi testlerin listesini dondur."""
        return [
            {
                "name": "Ozel kontrol",
                "type": "custom",
                "subtype": "my_check",
                "priority": "medium",
            }
        ]

    def run_test(self, test, project_path):
        """Tek testi calistir. (passed, detail) dondur."""
        # Kontrol mantigi
        return True, "Sorun yok"
```

2. Plugin'i proje dizininde `.nazar/plugins/` altina yerlestirin veya `nazar.yaml` icerisinde `plugins` alaninda belirtin.

3. Plugin'ler otomatik olarak `PluginManager` tarafindan yuklenir ve test planina eklenir.

## Dizin Yapisi

```
nazar/
  cli.py                  # Typer CLI giris noktasi
  interactive/
    shell.py              # Interaktif terminal arayuzu
  scanner/
    project_scanner.py    # Proje tarayici
    patterns.py           # Regex pattern'leri
  planner/
    test_planner.py       # Test planlayici
    profiles.py           # Test profilleri (full, ci, security vb.)
  runners/
    orchestrator.py       # Test orkestratoru
    base.py               # BaseRunner sinifi
    security_scanner.py   # Guvenlik tarayici
    ...                   # Diger runner'lar
  analyzers/
    ast_python.py         # Python AST analizi
    taint_tracker.py      # Taint tracking
    pattern_engine.py     # YAML kural motoru
    ...                   # Diger analyzer'lar
  reporters/
    json_reporter.py      # JSON cikti
    sarif_reporter.py     # SARIF cikti
    coverage_reporter.py  # Kapsam raporu
    ...                   # Diger formatlar
  reporter/
    html_reporter.py      # HTML rapor
  cache/
    scan_cache.py         # Tarama hafizasi
  config/
    loader.py             # Yapilandirma yukleyici
  plugins/
    base.py               # Plugin base class
    manager.py            # Plugin yonetimi
  guides/
    registry.py           # Rehber kayitlari
  integrations/
    github_pr.py          # GitHub entegrasyonu
  executors/
    maestro_executor.py   # Maestro runner
    device_manager.py     # Cihaz yonetimi
  live/
    server.py             # Canli web sunucusu
  batch/
    scanner.py            # Coklu proje tarayici
  tui/
    live_runner.py        # Canli TUI gosterimi
  tools/
    rule_builder.py       # Kural olusturucu
    rule_validator.py     # Kural dogrulayici
```
