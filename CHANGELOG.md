# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.0.0] - 2026-03-20

### Added
- YAML UI Testing: `nazar ui init`, `nazar ui generate`, `nazar ui check`
- Interactive shell with natural language commands (no `/` prefix needed)
- Turkish command aliases (`tara`, `rapor`, `detay`, `rehber`, `temizle`)
- Desktop path auto-detection (type project name, Nazar finds it)
- `profiles` command to list all test profiles
- JUnit export format
- `dependency` and `performance` profiles in interactive menu
- Turkish spell checking as optional dependency (`pip install nazar[turkish]`)

### Security
- Path traversal protection in file reader (root boundary check)
- SSRF protection in API endpoint testing (internal IP blocking)
- Plugin directory restricted to project root
- pip upgrade uses `sys.executable` instead of PATH-dependent `pip3`

### Fixed
- npm audit parse errors no longer silently pass (now correctly fail)
- Consistent test counts across UI (197+ tests, 21 categories)
- Removed unused `jinja2` dependency
- Removed phantom `templates/` package-data reference

### Changed
- Parallel test execution (6 concurrent workers)
- Subprocess timeouts reduced (120s -> 30s)
- Shared source cache across all runners (single `os.walk`)
- `typer[all]` simplified to `typer` (rich already separate dependency)

## [4.0.0] - 2026-03-19

### Added
- Scan cache with mtime+hash hybrid detection
- 8 test profiles (full, frontend, backend, security, mobile, ci, dependency, performance)
- UI Analysis motor (element extraction, page discovery, dead routes)
- Spell checker (Zeyrek + pyspellchecker + custom dictionary)
- UI quality analyzer (color consistency, WCAG contrast, font consistency, form validation)
- i18n deep analysis with coverage percentage
- Responsive design analyzer
- Performance static analyzer
- YAML UI test runner with syntax/target/coverage validation
- Live spinner during test execution
- Profile selection menu in interactive shell
- Project path verification with sub-project detection
- Update checker on startup
- `/update` command

### Changed
- Interactive shell rewritten with live UI feedback
- Thread-based test execution (non-blocking UI)

## [3.0.0] - 2026-03-18

### Added
- SCA Scanner (npm audit, pip-audit, govulncheck, typosquatting, license check)
- Python AST Analyzer (6 checks, 80% false positive reduction)
- Taint Tracking (SQL injection, XSS, command injection data flow)
- YAML Rule Engine (Semgrep-like custom rules)
- App Store compliance (32 checks)
- Play Store compliance (10 checks)
- GitHub PR integration (comments, SARIF, check status)
- VS Code Extension scaffolding
- 87 fix guides

## [2.0.0] - 2026-03-18

### Added
- Interactive shell with Rich TUI
- HTML report generation
- 22 test categories
- Plugin system
- Docker support
- GitHub Actions integration

## [1.0.0] - 2026-03-18

### Added
- Initial release
- Project scanner (15+ technology support)
- Security scanner (secrets, OWASP Top 10)
- Code quality checks
- CLI commands: scan, plan, run, auto
