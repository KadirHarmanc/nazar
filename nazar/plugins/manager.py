"""Plugin Manager - Plugin'leri kesfet, yukle, calistir."""
import importlib
import importlib.util
import os
from pathlib import Path
from typing import List, Dict, Tuple

from nazar.plugins.base import BaseTestPlugin


class PluginManager:
    """Plugin'leri yonetir."""

    def __init__(self, project_root: str = None):
        self.plugins: List[BaseTestPlugin] = []
        self._project_root = project_root

    def discover(self, plugin_dirs: List[str] = None) -> List[BaseTestPlugin]:
        """Plugin'leri kesfet ve yukle."""
        dirs = plugin_dirs or []

        # Built-in plugin dizini
        builtin_dir = Path(__file__).parent
        if str(builtin_dir) not in dirs:
            dirs.insert(0, str(builtin_dir))

        for plugin_dir in dirs:
            self._load_from_directory(plugin_dir)

        # Entry points
        self._load_from_entry_points()

        return self.plugins

    def _load_from_directory(self, directory: str) -> None:
        """Dizindeki plugin dosyalarini yukle."""
        plugin_path = Path(directory).resolve()
        builtin_dir = Path(__file__).parent.resolve()
        if not (str(plugin_path).startswith(str(builtin_dir)) or
                (hasattr(self, '_project_root') and
                 str(plugin_path).startswith(str(Path(self._project_root).resolve())))):
            return
        if not plugin_path.is_dir():
            return

        for py_file in plugin_path.glob("*.py"):
            if py_file.name.startswith("_") or py_file.name in ("base.py", "manager.py"):
                continue

            try:
                spec = importlib.util.spec_from_file_location(
                    f"nazar_plugin_{py_file.stem}", str(py_file)
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BaseTestPlugin)
                            and attr is not BaseTestPlugin
                        ):
                            plugin = attr()
                            plugin.setup()
                            self.plugins.append(plugin)
            except Exception:
                pass

    def _load_from_entry_points(self) -> None:
        """Entry points'ten plugin yukle."""
        try:
            if hasattr(importlib.metadata, "entry_points"):
                eps = importlib.metadata.entry_points()
                if hasattr(eps, "select"):
                    plugin_eps = eps.select(group="nazar.plugins")
                else:
                    plugin_eps = eps.get("nazar.plugins", [])

                for ep in plugin_eps:
                    try:
                        plugin_class = ep.load()
                        if issubclass(plugin_class, BaseTestPlugin):
                            plugin = plugin_class()
                            plugin.setup()
                            self.plugins.append(plugin)
                    except Exception:
                        pass
        except Exception:
            pass

    def get_all_tests(self, scan_result) -> List[Dict]:
        """Tum plugin'lerden test listesi topla."""
        tests = []
        for plugin in self.plugins:
            try:
                plugin_tests = plugin.get_tests(scan_result)
                for test in plugin_tests:
                    test["_plugin"] = plugin.name
                tests.extend(plugin_tests)
            except Exception:
                pass
        return tests

    def run_test(self, test: dict, project_path: str) -> Tuple[bool, str]:
        """Ilgili plugin ile testi calistir."""
        plugin_name = test.get("_plugin", "")
        for plugin in self.plugins:
            if plugin.name == plugin_name:
                try:
                    return plugin.run_test(test, project_path)
                except Exception as e:
                    return False, str(e)[:80]
        return True, "Plugin bulunamadi - SKIP"

    def teardown_all(self) -> None:
        """Tum plugin'lerin teardown'ini cagir."""
        for plugin in self.plugins:
            try:
                plugin.teardown()
            except Exception:
                pass
