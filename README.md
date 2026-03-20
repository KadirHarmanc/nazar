<p align="center">
  <br>
  <span style="font-size: 80px">🧿</span>
  <br>
</p>

<h1 align="center">Nazar</h1>
<h3 align="center">Autonomous Security & Quality Scanner</h3>

<p align="center">
  <em>Zero-config. Framework-aware. 197+ automated checks.</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/nazar/"><img src="https://img.shields.io/pypi/v/nazar?color=%2334D058&label=PyPI" alt="PyPI"></a>
  <a href="https://pypi.org/project/nazar/"><img src="https://img.shields.io/pypi/pyversions/nazar" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License"></a>
  <a href="https://pypi.org/project/nazar/"><img src="https://img.shields.io/pypi/dm/nazar?color=orange" alt="Downloads"></a>
</p>

---

**Nazar** scans your project, understands its architecture, generates a tailored test plan, and runs 197+ security & quality checks -- all without any configuration. Just type `nazar` and let it do the rest.

```bash
pip install nazar
nazar
```

That's it. Nazar detects your tech stack (React Native, Flutter, Django, FastAPI, Go, Rust, and 15+ more), selects the right tests, and gives you a full report with fix guides.

---

## Why Nazar?

Most scanners need config files, plugins, or framework-specific setup. Nazar takes a different approach:

- **Zero config** -- point it at any project, it figures out the rest
- **Architecture-aware** -- React Native project? You get App Store checks. Django? You get SQL injection taint tracking. Go? You get `govulncheck`
- **Fix guides** -- not just "you have a problem" but "here's exactly how to fix it, step by step" (87 built-in guides)
- **Interactive shell** -- live progress, detailed results, code snippets, all in your terminal
- **Fast** -- parallel test execution, incremental scanning, smart caching

---

## Quick Start

### Install

```bash
# Recommended
pipx install nazar

# Or with pip
pip install nazar

# Turkish spell checking support (optional)
pip install nazar[turkish]

# Live runtime testing on simulator/emulator (optional)
curl -Ls "https://get.maestro.mobile.dev" | bash
```

### Run

```bash
# Interactive mode (recommended)
nazar

# One-shot full scan
nazar auto ~/MyProject

# Scan with specific profile
nazar auto ~/MyProject --profile security
nazar auto ~/MyProject --profile frontend
nazar auto ~/MyProject --profile mobile

# CI/CD mode
nazar auto . --json --quiet
```

### Interactive Shell

The interactive shell is where Nazar shines. No need to remember flags -- just type naturally:

```
nazar> ~/Desktop/MyProject
  MyProject (react-native)
  Select profile: [1] Full  [2] Frontend  [3] Security  ...

  [1/3] Project scanned: react-native | 24 screens | 8 API | 156 files (1.2s)
  [2/3] 87 tests planned (12 categories) (0.1s)
  [3/3] Running tests...

  Grade: B+ (84%)  |  73 passed  |  14 failed  |  87 tests  |  32.4s

nazar> d 3              # show detail for failed test #3
nazar> g 3              # step-by-step fix guide
nazar> report security  # filter by category
nazar> export html      # generate HTML report
nazar> profiles         # list all test profiles
nazar> help             # all commands
```

Commands work with or without `/` prefix. Turkish aliases supported (`tara`, `rapor`, `detay`, `rehber`).

---

## What It Checks (197+ Tests, 21 Categories)

### Security (63 tests)
| Check | What it catches |
|-------|----------------|
| Secret Detection | 50+ patterns: AWS keys, JWT tokens, private keys, database URLs, API keys |
| OWASP Top 10 | SQL injection, XSS, CSRF, CORS misconfiguration, insecure crypto |
| Supply Chain | Typosquatting detection (60+ known malicious packages), dependency confusion |
| Taint Tracking | Source-to-sink data flow analysis for injection vulnerabilities |

### Code Quality (16 tests)
Cyclomatic complexity, dead code, code smells, debug statements, naming conventions, long functions, deep nesting, bare except, TODO count, maintainability index.

### SCA - Software Composition Analysis (7 tests)
| Tool | Coverage |
|------|----------|
| `npm audit` | Node.js vulnerabilities |
| `pip-audit` | Python vulnerabilities |
| `govulncheck` | Go vulnerabilities |
| License check | GPL compatibility, license conflicts |
| Outdated deps | Major version lag detection |
| Typosquatting | 60+ known malicious package names |
| Deprecated | Abandoned package detection |

### App Store Compliance (32 tests)
Privacy manifest, App Tracking Transparency, Sign in with Apple, IAP validation, minimum deployment target, IPv6 compatibility, IDFA usage, push notification setup, and more.

### Play Store Compliance (10 tests)
Target SDK version, exported components, ProGuard/R8 configuration, dangerous permissions, backup rules, cleartext traffic.

### Python AST Analysis (6 tests)
Real code understanding via AST -- not regex. Catches mutable default arguments, bare `*` imports, unused variables, shadowed builtins, unreachable code, assert in production.

### And More...
| Category | Tests | Highlights |
|----------|-------|------------|
| UI Components | 10 | Accessibility, touch targets, dark mode, loading states |
| UX Text | 8 | Spelling, consistency, i18n readiness, alt text |
| Cross-File | 7 | Dead exports, orphan components, circular imports |
| YAML Rules | 3 | Write your own Semgrep-like rules in YAML |
| API | 4 | Endpoint reachability, response validation |
| i18n | 3 | Translation coverage, hardcoded strings |
| Responsive | 3 | Fixed dimensions, scroll issues |
| Performance | 6 | Bundle size, large assets, render performance |
| Git | 4 | .gitignore, large files, sensitive files |
| Type Safety | 3 | `any` usage, `ts-ignore`, unsafe casts |
| Error Handling | 3 | Empty catch, swallowed errors, async |
| Docker | 2 | Base image, secrets in Dockerfile |

---

## Test Profiles

Not every project needs every test. Nazar has 8 built-in profiles:

| Profile | Focus | Best for |
|---------|-------|----------|
| `full` | All 197+ tests | Comprehensive audit |
| `frontend` | UI, UX, accessibility, responsive | React, Vue, Flutter |
| `backend` | Security, API, code quality | Django, FastAPI, Express |
| `security` | All security-related tests | Security audit |
| `mobile` | App Store + Play Store + UI | React Native, Flutter |
| `ci` | Fast critical-only checks | CI/CD pipelines |
| `dependency` | SCA, licenses, versions | Dependency audit |
| `performance` | Bundle, assets, rendering | Performance optimization |

```bash
nazar auto . --profile security
```

---

## YAML UI Testing

Define UI tests in YAML, Nazar validates them statically:

```yaml
# .nazar/ui-tests/login-screen.yml
apiVersion: nazar/v1
name: Login Screen Test
platform: all
priority: high

steps:
  - action: navigate
    target: "LoginScreen"

  - action: assertVisible
    target: "Email"

  - action: inputText
    target: "email_input"
    value: "test@example.com"

  - action: tapOn
    target: "Login Button"

  - action: assertVisible
    target: "Welcome"
```

```bash
# Generate YAML tests from your screens
nazar ui generate ~/MyProject

# Validate YAML test files
nazar ui check ~/MyProject
```

Nazar checks syntax, verifies targets exist in your codebase, and measures screen coverage.

---

## Custom Rules (YAML Rule Engine)

Write Semgrep-like rules in YAML:

```yaml
# .nazar/rules/my-rules.yml
rules:
  - id: no-console-log
    pattern: "console\\.log\\("
    message: "Remove console.log before production"
    severity: warning
    languages: [javascript, typescript]

  - id: no-hardcoded-url
    pattern: "https?://[a-zA-Z0-9]"
    message: "Use environment variables for URLs"
    severity: error
    languages: [javascript, typescript, python]
```

---

## Output Formats

```bash
# Interactive HTML report
nazar auto . --report report.html

# JSON (for CI/CD)
nazar --json auto .

# From interactive shell
nazar> export html
nazar> export json
nazar> export sarif    # GitHub Code Scanning
nazar> export junit    # CI/CD test results
nazar> export markdown # Markdown summary
```

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/nazar.yml
name: Nazar Security Scan
on: [push, pull_request]

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install nazar
      - run: nazar auto . --json --quiet --profile ci
```

### With PR Comments & SARIF

```yaml
      - run: |
          nazar auto . --sarif nazar.sarif --github-pr
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: nazar.sarif
```

---

## Plugin System

Extend Nazar with custom test plugins:

```python
from nazar.plugins.base import BaseTestPlugin

class MyPlugin(BaseTestPlugin):
    name = "my-plugin"
    version = "1.0.0"
    description = "Custom security checks"

    def get_tests(self, scan_result):
        return [
            {
                "name": "Check for admin backdoor",
                "type": "custom",
                "subtype": "admin_backdoor",
                "priority": "critical",
            }
        ]

    def run_test(self, test, project_path):
        # Your custom logic here
        return True, "No backdoor found"
```

Place in `.nazar/plugins/` or configure in `nazar.yaml`:

```yaml
plugin_dirs:
  - .nazar/plugins
```

---

## Configuration

Nazar works without any config, but you can customize it:

```yaml
# nazar.yaml
profile: security
ignore_rules:
  - todo_count
  - naming_conventions
custom_dict:
  - myapp
  - signup
  - onboarding
```

### .nazarignore

Skip specific files or rules:

```
# Skip test files
tests/
__tests__/

# Skip specific rules
!rule:deprecated_packages
!rule:todo_count
```

---

## Supported Technologies

| Category | Frameworks |
|----------|-----------|
| **Frontend** | React, React Native, Vue, Angular, Svelte |
| **Mobile** | React Native, Flutter, Swift, Kotlin |
| **Backend** | Django, FastAPI, Flask, Express, NestJS |
| **Languages** | Python, JavaScript, TypeScript, Go, Rust, Dart, Swift, Kotlin, Java, Ruby, PHP, C# |
| **Infrastructure** | Docker, GitHub Actions, Terraform |

---

## Architecture

```
nazar/
  scanner/        # Project analysis & tech detection
  planner/        # Test plan generation & profiles
  runners/        # Test execution (35 runner types)
  analyzers/      # Deep analysis (AST, taint, UI, spell, i18n)
  cache/          # Incremental scan cache
  reporters/      # Output formats (HTML, JSON, SARIF, JUnit)
  interactive/    # Terminal shell & live UI
  plugins/        # Plugin system
  guides/         # 87 fix guides
  rules/          # Built-in YAML rules
```

---

## Development

```bash
git clone https://github.com/KadirHarmanc/nazar.git
cd nazar
pip install -e ".[dev]"
pytest
```

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

MIT -- see [LICENSE](LICENSE) for details.
