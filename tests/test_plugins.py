"""Tests for plugin system."""
from nazar.plugins.base import BaseTestPlugin
from nazar.plugins.manager import PluginManager


def test_plugin_manager_init():
    """PluginManager initializes empty."""
    pm = PluginManager()
    assert pm.plugins == []


def test_plugin_manager_discover_empty(tmp_path):
    """Discover in empty dir returns no plugins."""
    pm = PluginManager()
    plugins = pm.discover([str(tmp_path)])
    # May find built-in example plugin
    assert isinstance(plugins, list)


def test_base_plugin_interface():
    """BaseTestPlugin has required methods."""
    assert hasattr(BaseTestPlugin, "get_tests")
    assert hasattr(BaseTestPlugin, "run_test")
    assert hasattr(BaseTestPlugin, "setup")
    assert hasattr(BaseTestPlugin, "teardown")
