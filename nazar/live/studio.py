"""Nazar Studio - Native desktop UI for live testing.

Simulator penceresi sola, test adimlari penceresi saga otomatik konumlanir.
Screenshot capture yoktur - sifir overhead.
pywebview yoksa tarayicida acar (fallback).
"""
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def _position_windows_side_by_side(studio_title: str):
    """macOS'ta Simulator ve NazarStudio pencerelerini yan yana konumla.

    Sol yari: Simulator.app
    Sag yari: NazarStudio penceresi
    """
    if sys.platform != "darwin":
        return

    script = f'''
    tell application "System Events"
        -- Ekran boyutunu al
        set screenSize to {{1440, 900}}
        try
            set screenSize to size of scroll area 1 of application process "Finder"
        end try
        try
            tell application process "Finder"
                set screenSize to size of window 1
            end tell
        end try

        set screenW to item 1 of screenSize
        set screenH to item 2 of screenSize
        set halfW to (screenW div 2)

        -- Simulator.app sola konumla
        try
            tell application process "Simulator"
                set position of window 1 to {{0, 0}}
                set size of window 1 to {{halfW, screenH}}
            end tell
        end try

        -- Nazar Studio saga konumla
        delay 0.5
        try
            tell application process "Nazar Studio"
                set position of window 1 to {{halfW, 0}}
                set size of window 1 to {{halfW, screenH}}
            end tell
        end try
        try
            tell application process "Python"
                repeat with w in windows
                    if name of w contains "{studio_title}" then
                        set position of w to {{halfW, 0}}
                        set size of w to {{halfW, screenH}}
                        exit repeat
                    end if
                end repeat
            end tell
        end try
    end tell
    '''
    try:
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, OSError):
        pass


class NazarStudio:
    """Nazar Live Test'i native desktop penceresinde gosterir.

    Simulator penceresi sol yarida, test adimlari sag yarida konumlanir.
    Screenshot capture yoktur - Simulator'u direkt kendi penceresinde gorursunuz.
    """

    def __init__(self, title="Nazar Studio", width=600, height=800, port=9998):
        self.title = title
        self.width = width
        self.height = height
        self.port = port
        self._test_ui = None
        self._window = None

    def open(self, yaml_file: str, auto_run: bool = True):
        """Test arayuzunu ac ve pencereleri yan yana konumla.

        Args:
            yaml_file: YAML test dosyasinin yolu.
            auto_run: True ise testleri otomatik baslat.
        """
        from nazar.live.test_ui import NazarLiveTestUI

        self._test_ui = NazarLiveTestUI(port=self.port)
        ok = self._test_ui.start(yaml_file, auto_run=auto_run)
        if not ok:
            print("Hata: Live test baslatılamadi (simulator/emulator acik mi?)")
            return False

        yaml_name = Path(yaml_file).stem
        window_title = f"{self.title} - {yaml_name}"

        try:
            import webview

            self._window = webview.create_window(
                window_title,
                f"http://localhost:{self.port}",
                width=self.width,
                height=self.height,
                min_size=(400, 600),
                background_color="#0d1117",
                text_select=False,
            )

            self._window.events.closing += self._on_closing

            # Pencere acildiktan sonra konumla
            self._window.events.shown += lambda: _position_windows_side_by_side(window_title)

            webview.start(debug=False)

        except ImportError:
            import webbrowser
            webbrowser.open(f"http://localhost:{self.port}")
            print(f"\nNazar Studio: http://localhost:{self.port}")
            print("Simulator'u yan tarafa konumlayin.")
            print("Native pencere icin: pip install pywebview")
            try:
                input("\nKapatmak icin Enter basin...")
            except (KeyboardInterrupt, EOFError):
                pass

        self._cleanup()
        return True

    def open_viewer_only(self):
        """Sadece test adimi izleme modu (test calistirmadan)."""
        from nazar.live.test_ui import NazarLiveTestUI

        self._test_ui = NazarLiveTestUI(port=self.port)
        ok = self._test_ui.start_server_only()
        if not ok:
            print("Hata: Simulator bulunamadi")
            return False

        window_title = f"{self.title} - Viewer"

        try:
            import webview
            self._window = webview.create_window(
                window_title,
                f"http://localhost:{self.port}",
                width=self.width,
                height=self.height,
                min_size=(400, 600),
                background_color="#0d1117",
            )
            self._window.events.closing += self._on_closing
            self._window.events.shown += lambda: _position_windows_side_by_side(window_title)
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
        """Server thread'lerini durdur."""
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
