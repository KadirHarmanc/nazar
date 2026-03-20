# Nazar'a Katki Rehberi

Nazar'a katki saglamak istediginiz icin tesekkurler!

## Gelistirme Ortami

```bash
# Repo'yu fork edin ve klonlayin
git clone https://github.com/YOUR_USERNAME/nazar.git
cd nazar

# Virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Gelistirme bagimliliklari
pip install -e ".[dev]"

# Pre-commit hook'lari
pip install pre-commit
pre-commit install
```

## Commit Formati

[Conventional Commits](https://www.conventionalcommits.org/) kullaniyoruz:

```
<tip>(<kapsam>): <aciklama>

[opsiyonel govde]

[opsiyonel footer]
```

### Tipler

| Tip | Aciklama |
|-----|----------|
| `feat` | Yeni ozellik |
| `fix` | Bug duzeltme |
| `docs` | Dokumantasyon |
| `test` | Test ekleme/duzeltme |
| `chore` | Build, CI, dependency |
| `refactor` | Kod yeniden duzenleme |
| `perf` | Performans iyilestirme |
| `style` | Formatlama (davranis degismez) |

### Ornekler

```
feat(security): add 50+ secret detection patterns
fix(cli): handle missing project path gracefully
docs(readme): add Docker usage section
test(orchestrator): add security test coverage
```

## Pull Request Sureci

1. Feature branch olusturun: `git checkout -b feat/amazing-feature`
2. Degisikliklerinizi yapin
3. Testleri calistirin: `pytest tests/ -v`
4. Lint kontrolu: `black . && ruff check .`
5. Commit atin (conventional commit formati)
6. Push edin: `git push origin feat/amazing-feature`
7. Pull Request acin

## Kod Stili

- **Formatter**: Black (line-length: 120)
- **Linter**: Ruff
- **Type Checker**: mypy (opsiyonel)
- **Test**: pytest

## Test Yazma

```python
# tests/test_<modul>.py
def test_feature_description():
    """Test aciklamasi."""
    # Arrange
    ...
    # Act
    ...
    # Assert
    assert result == expected
```

## Plugin Gelistirme

Kendi test plugin'inizi yazabilirsiniz:

```python
from nazar.plugins.base import BaseTestPlugin

class MyPlugin(BaseTestPlugin):
    name = "my-plugin"
    version = "1.0.0"
    description = "Custom test rules"

    def get_tests(self, scan_result):
        return [{"name": "My Test", "type": "custom", "priority": "medium"}]

    def run_test(self, test, project_path):
        return True, "Passed"
```

## Raporlama

- Bug: [GitHub Issues](https://github.com/user/nazar/issues) uzerinden
- Guvenlik acigi: [SECURITY.md](SECURITY.md) talimatlarini izleyin
- Ozellik onerisi: Issue Template kullanin

## Lisans

Katkilariniz MIT lisansi altinda yayinlanir.
