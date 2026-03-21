# Nazar Studio - Native Desktop UI Plan

## Ozet

Nazar'in canli test arayuzunu native macOS/Windows/Linux uygulamasi olarak gostermek icin pywebview entegrasyonu.

Mevcut `localhost:9998` web arayuzunu native pencerede acar. Tarayici gerektirmez, uygulama gibi calisir.

---

## Mimari

```
+--------------------------------------------------+
|  Nazar Studio (pywebview native pencere)          |
|                                                    |
|  +---------------------+  +---------------------+ |
|  |                     |  |  login-test.yml      | |
|  |   SIMULATOR         |  |  Status: Running     | |
|  |   EKRANI            |  |                      | |
|  |                     |  |  1. launchApp    [OK] | |
|  |   (3sn'de bir       |  |  2. assertVis   [OK] | |
|  |    xcrun simctl     |  |  3. tapOn       [>>] | |
|  |    screenshot)      |  |  4. inputText   [--] | |
|  |                     |  |  5. screenshot  [--] | |
|  |                     |  |                      | |
|  +---------------------+  +---------------------+ |
|                                                    |
|  [============================----]  85%  12.3s    |
|  5 passed  |  0 failed  |  1 running  |  1 manual  |
+--------------------------------------------------+
```

---

## Teknik Plan

### Faz 1: pywebview Entegrasyonu (30dk)

**Dosyalar:**
- `nazar/live/studio.py` - NazarStudio sinifi

**Gorevler:**
1. `pyproject.toml`'a optional dependency ekle: `studio = ["pywebview>=5.0"]`
2. `NazarStudio` sinifi olustur:
   - `__init__(title, width, height, port)`
   - `open(yaml_file)` - HTTP server + pywebview penceresi baslat
   - `close()` - temizlik
3. Mevcut `test_ui.py` HTTP server'ini arka planda calistir
4. pywebview'i main thread'de baslat (macOS Cocoa gerekliligi)
5. Fallback: pywebview yoksa `webbrowser.open()` ile tarayicida ac

**Kod yapisi:**
```python
class NazarStudio:
    def __init__(self, title="Nazar Studio", width=1200, height=800, port=9998):
        self.title = title
        self.width = width
        self.height = height
        self.port = port
        self._test_ui = None

    def open(self, yaml_file: str):
        # 1. HTTP server + screenshot + test runner baslat
        from nazar.live.test_ui import NazarLiveTestUI
        self._test_ui = NazarLiveTestUI(port=self.port)
        self._test_ui.start(yaml_file)

        # 2. Native pencere ac
        try:
            import webview
            window = webview.create_window(
                self.title,
                f"http://localhost:{self.port}",
                width=self.width,
                height=self.height,
                min_size=(800, 600),
            )
            webview.start()  # main thread'de calisir
        except ImportError:
            # Fallback: tarayici
            import webbrowser
            webbrowser.open(f"http://localhost:{self.port}")
            input("Kapatmak icin Enter basin...")

        # 3. Temizlik
        self._test_ui.stop()

    def close(self):
        if self._test_ui:
            self._test_ui.stop()
```

---

### Faz 2: Shell + CLI Entegrasyonu (15dk)

**Dosyalar:**
- `nazar/interactive/shell.py` - `_run_live_test()` guncelle
- `nazar/cli.py` - `nazar ui run` guncelle

**Gorevler:**
1. Shell'de canli test secildiginde `NazarStudio.open()` cagir
2. CLI'da `nazar ui run --studio` flag'i ekle
3. pywebview yoksa otomatik fallback (tarayici)
4. `nazar studio` komutu ekle (direkt studio ac)

**Kullanici akisi:**
```
nazar> ~/Desktop/BetterPlate
  Profil: [7] Mobil
  Canli test? [E]vet

  Nazar Studio aciliyor...
  [native macOS penceresi acilir]
  [sol: simulator ekrani, sag: test adimlari]
  [testler otomatik calisir]
  [bittikten sonra pencere acik kalir, kullanici inceleyebilir]
```

---

### Faz 3: UI Gelistirmeleri (30dk)

**Dosyalar:**
- `nazar/live/test_ui.py` - HTML sablonu iyilestir

**Gorevler:**
1. Pencere boyutuna responsive layout (pywebview resize destekler)
2. Ust bar: Nazar logosu + yaml dosya adi + durum gostergesi
3. Sol panel: Simulator ekrani + cihaz cercevesi (iPhone mockup CSS)
4. Sag panel: Adim listesi + syntax renklendirme + gecen sure
5. Alt bar: Progress + sayaclar + "Durdur" butonu
6. JS bridge ile Python'dan anlık durum guncellemesi
7. Tema: Dark tema varsayilan, mevcut HTML'i kullan

---

### Faz 4: Pencere Ozellikleri (15dk)

**Gorevler:**
1. Pencere basligi: "Nazar Studio - login-test.yml"
2. Min boyut: 800x600
3. Varsayilan boyut: 1200x800
4. `on_top=False` (varsayilan, istege bagli)
5. Pencere kapatildiginda `on_closing` callback ile server'i durdur
6. macOS menu bar: File > Close, View > Always on Top

---

### Faz 5: State Sync - Canli Guncelleme (20dk)

**pywebview v6.0 State Sync kullan:**

```python
# Python tarafinda
window.state["steps"] = tracker.get_data()
window.state["screenshot"] = screenshot.get_base64()

# JS tarafinda otomatik guncellenir
// pywebview.state.steps -> DOM guncelle
// pywebview.state.screenshot -> img src guncelle
```

**Avantaj:** Polling (setInterval) yerine state sync ile anlık guncelleme. CPU kullanimi duser.

**Alternatif (v5.x uyumluluk):**
```python
# Python -> JS
window.evaluate_js(f"updateSteps({json.dumps(data)})")
```

---

## Kurulum

```bash
# Temel kurulum (tarayici fallback)
pip install nazar

# Studio ile (native pencere)
pip install nazar[studio]

# Her sey dahil
pip install nazar[studio,turkish]
```

---

## Dosya Yapisi

```
nazar/
  live/
    __init__.py
    server.py          # mevcut web dashboard (port 5555)
    test_ui.py         # mevcut canli test HTTP + HTML (port 9998)
    studio.py          # YENi - pywebview native pencere wrapper
```

---

## Riskler ve Cozumler

| Risk | Cozum |
|------|-------|
| pywebview kurulu degil | `webbrowser.open()` fallback |
| Sistem Python klavye focus | Homebrew Python kullan notu goster |
| macOS Cocoa main thread | `webview.start()` her zaman main thread'de |
| Port cakismasi | Rastgele port sec, `find_free_port()` |
| Buyuk screenshot base64 | JPEG kalitesi dusur (quality=50), resize (max 800px) |

---

## Zaman Tahmini

| Faz | Sure | Oncelik |
|-----|------|---------|
| Faz 1: pywebview entegrasyon | 30dk | YUKSEK |
| Faz 2: Shell + CLI | 15dk | YUKSEK |
| Faz 3: UI gelistirme | 30dk | ORTA |
| Faz 4: Pencere ozellikleri | 15dk | DUSUK |
| Faz 5: State sync | 20dk | DUSUK |
| **TOPLAM** | **~2 saat** | |

---

## Basari Kriterleri

- [ ] `pip install nazar[studio]` ile kurulur
- [ ] `nazar` shell'de canli teste `E` dediginde native pencere acilir
- [ ] Sol panel: simulator ekrani 3sn'de bir yenilenir
- [ ] Sag panel: test adimlari canli durum gostergeleriyle gorunur
- [ ] Pencere kapatildiginda server ve screenshot thread'i durur
- [ ] pywebview yoksa tarayicida acilir (fallback)
- [ ] Donma/lag olmaz
