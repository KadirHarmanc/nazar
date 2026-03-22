"""Nazar Studio - Native desktop UI for live testing.

pywebview ile simulator ekranini ve test adimlarini native pencerede gosterir.
pywebview yoksa tarayicida acar (fallback).
"""
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional


class NazarStudio:
    """Nazar Live Test'i native desktop penceresinde gosterir."""

    def __init__(self, title="Nazar Studio", width=1200, height=800, port=9998):
        self.title = title
        self.width = width
        self.height = height
        self.port = port
        self._test_ui = None
        self._window = None

    def open(self, yaml_file: str, auto_run: bool = True):
        """Native pencerede canli test arayuzunu ac.

        Args:
            yaml_file: YAML test dosyasinin yolu.
            auto_run: True ise testleri otomatik baslat.
        """
        from nazar.live.test_ui import NazarLiveTestUI

        # 1. HTTP server + screenshot + test runner baslat
        self._test_ui = NazarLiveTestUI(port=self.port)
        ok = self._test_ui.start(yaml_file, auto_run=auto_run)
        if not ok:
            print("Hata: Live test baslatılamadi (simulator/emulator acik mi?)")
            return False

        # Pencere basligina YAML adini ekle
        yaml_name = Path(yaml_file).stem
        window_title = f"{self.title} - {yaml_name}"

        # 2. Native pencere ac
        try:
            import webview

            self._window = webview.create_window(
                window_title,
                f"http://localhost:{self.port}",
                width=self.width,
                height=self.height,
                min_size=(800, 600),
                background_color="#0f172a",
                text_select=False,
            )

            # Pencere kapatildiginda cleanup
            self._window.events.closing += self._on_closing

            # Main thread'de calistir (macOS Cocoa gerekliligi)
            webview.start(debug=False)

        except ImportError:
            # pywebview yok - tarayicida ac
            import webbrowser
            webbrowser.open(f"http://localhost:{self.port}")
            print(f"\nNazar Studio: http://localhost:{self.port}")
            print("pywebview kurulu degil - tarayicida acildi")
            print("Native pencere icin: pip install pywebview")
            try:
                input("\nKapatmak icin Enter basin...")
            except (KeyboardInterrupt, EOFError):
                pass

        # 3. Temizlik
        self._cleanup()
        return True

    def open_viewer_only(self):
        """Sadece simulator izleme modu (test calistirmadan)."""
        from nazar.live.test_ui import NazarLiveTestUI

        self._test_ui = NazarLiveTestUI(port=self.port)
        ok = self._test_ui.start_server_only()
        if not ok:
            print("Hata: Simulator bulunamadi")
            return False

        try:
            import webview
            self._window = webview.create_window(
                f"{self.title} - Viewer",
                f"http://localhost:{self.port}",
                width=self.width,
                height=self.height,
                min_size=(800, 600),
                background_color="#0f172a",
            )
            self._window.events.closing += self._on_closing
            webview.start(debug=False)
        except ImportError:
            import webbrowser
            webbrowser.open(f"http://localhost:{self.port}")
            try:
                input("\nKapatmak icin Enter basin...")
            except (KeyboardInterrupt, EOFError):
                pass

        self._cleanup()
        return True

    def _on_closing(self):
        """Pencere kapatildiginda cagrilir."""
        self._cleanup()

    def _cleanup(self):
        """Server ve screenshot thread'lerini durdur."""
        if self._test_ui:
            self._test_ui.stop()
            self._test_ui = None

    def close(self):
        """Studio'yu kapat."""
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
        self._cleanup()


def launch_studio(yaml_file: str, port: int = 9998):
    """Tek fonksiyonla studio baslat (kolaylik icin)."""
    studio = NazarStudio(port=port)
    return studio.open(yaml_file)
