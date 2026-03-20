"""Tests for config system."""
from nazar.config.loader import ConfigLoader, NazarConfig
from pathlib import Path


def test_default_config():
    """Default config has sane values."""
    config = NazarConfig()
    assert "node_modules" in config.exclude_dirs
    assert config.cache_enabled is True
    assert config.parallel_workers == 4


def test_load_missing_config(tmp_path):
    """Loading from dir without config returns defaults."""
    config = ConfigLoader.load(str(tmp_path))
    assert isinstance(config, NazarConfig)
    assert config.output_format == "html"


def test_generate_template(tmp_path):
    """Template generation creates a file."""
    output = str(tmp_path / "nazar.yaml")
    ConfigLoader.generate_template(output)
    assert Path(output).exists()
    content = Path(output).read_text()
    assert "exclude" in content
    assert "severity" in content


def test_load_custom_config(tmp_path):
    """Custom config is loaded correctly."""
    config_content = """
exclude:
  dirs:
    - custom_dir
    - another_dir
parallel: 8
cache: false
output: json
"""
    (tmp_path / "nazar.yaml").write_text(config_content)
    config = ConfigLoader.load(str(tmp_path))
    assert "custom_dir" in config.exclude_dirs
    assert config.parallel_workers == 8
    assert config.cache_enabled is False
    assert config.output_format == "json"
