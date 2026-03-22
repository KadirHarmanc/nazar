# Nazar Studio - Screenshot Optimizasyon Raporu

> 2 tur arastirma + 2 agent dogrulama + cakisma analizi sonucu olusturulmustur.

---

## 1. Mevcut Durum

### Akis
```
iOS:  xcrun simctl io booted screenshot --type=jpeg /tmp/nazar_screen.jpg
      -> dosyaya yaz -> dosyadan oku -> base64 encode -> HTTP JSON -> JS fetch -> img.src

Android: adb exec-out screencap -p
         -> stdout PNG -> dosyaya yaz -> dosyadan oku -> base64 encode -> HTTP JSON -> JS fetch -> img.src
```

### Sorunlar
| # | Sorun | Etki | Oncelik |
|---|-------|------|---------|
| 1 | Disk I/O (her karede yaz + oku) | ~5-10ms gereksiz gecikme | Yuksek |
| 2 | base64 encoding | Veriyi %33 sisiriyor (DOGRULANDI) | Yuksek |
| 3 | HTTP polling (2s aralik) | Minimum 2s gecikme + gereksiz istek | Yuksek |
| 4 | Android PNG formati | JPEG'e gore 3-5x buyuk | Orta |
| 5 | Tam cozunurluk (1170x2532) | Preview icin gereksiz buyuk | Orta |
| 6 | JavaScript fetch dongusu | CPU + network overhead | Dusuk |

### Boyut Analizi (Tek Frame)
```
PNG tam cozunurluk:     ~3.5 MB
JPEG kalite 85 tam:     ~800 KB   (xcrun varsayilan)
JPEG kalite 60 tam:     ~500 KB
JPEG kalite 60 yarim:   ~150 KB
base64 overhead:        +33%      (DOGRULANDI - matematiksel kesinlik)

Mevcut: ~800KB * 1.33 = ~1064KB per frame
Hedef:  ~150KB binary JPEG
Kazanc: ~7x kucuk
```

---

## 2. Dogrulanmis Arastirma Bulgulari

Her madde iki agent tarafindan dogrulanmis, sonuc etiketi eklenmistir.

### 2.1 iOS Simulator - Stdout Modu [DOGRULANDI]

```bash
# Mevcut (dosyaya yazar):
xcrun simctl io booted screenshot --type=jpeg /tmp/nazar_screen.jpg

# Optimize (stdout'a yazar, disk I/O sifir):
xcrun simctl io booted screenshot --type=jpeg -
```

Tire (`-`) parametresi JPEG'i dogrudan stdout'a basar.

**Dogrulanan parametreler:**
```bash
xcrun simctl io <device> screenshot [--type=<type>] [--display=<display>] [--mask=<mask>] <file or ->
# --type: png, tiff, bmp, gif, jpeg
# --display: internal, external
# --mask: ignored (en hizli), alpha, black
```

**Dogrulanan davranislar:**
- Simulator minimize edilse bile calisiyor (render buffer'dan okur)
- `--quality` parametresi YOK - JPEG varsayilan ~85-90 kalitede uretilir
- `--scale` parametresi YOK - her zaman tam cozunurluk
- `recordVideo` stdout'a stream VEREMIYOR (sadece dosyaya)
- Birden fazla simulator aciksa `booted` ILK'ini hedefler, UDID kullanmak guvenli

**Gecikme rakamlari:** Bagimsiz benchmark ile dogrulanamadi. Asagidaki degerler tahminidir:

| Islemci | JPEG stdout | PNG stdout |
|---------|------------|------------|
| M1 | ~100-180ms | ~200-400ms |
| M2 | ~70-150ms | ~180-350ms |
| M3 | ~60-130ms | ~160-300ms |

### 2.2 Android Emulator [DOGRULANDI]

`adb exec-out screencap -p` PNG verir, JPEG secenegi YOK.

| Yontem | Hiz | Bagimsizlik | Durum |
|--------|-----|-------------|-------|
| `adb exec-out screencap -p` | ~2-3 fps | Yok | Mevcut, calisiyor |
| `adb shell screenrecord --output-format=h264 -` | ~15-30 fps | ffmpeg (decode) | DOGRULANDI |
| adbblitz | ~30 fps | numpy, av | Agir bagimsizlik |

**Android screencap gizli bayraklar:**
- `-p`: PNG (tek format)
- `-d <display_id>`: Belirli ekran (Android 10+)
- JPEG destegi YOK

**screenrecord H264 stream [DOGRULANDI]:**
```bash
adb shell screenrecord --output-format=h264 --size=540x960 --bit-rate=2000000 -
```
- stdout'a raw H264 stream verir
- `--size` ile cozunurluk dusurulur
- 3 dakika hard limit (Android OS kisitlamasi, bypass edilemez)

### 2.3 base64 Overhead [DOGRULANDI]

```
Her 3 byte girdi -> 4 byte cikti = %33.33 artis (matematiksel kesinlik)
100KB binary -> 133KB base64 + encode CPU + decode CPU + JS JSON parse
```

MJPEG stream ile base64 tamamen ortadan kalkar. Binary JPEG icin HTTP Content-Type: `image/jpeg`.

### 2.4 MJPEG Stream [KISMI DOGRU]

**Calisiyor, ama nüanslar var:**

```python
# Sunucu
self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=--frame')
# Her frame:
self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\n')
self.wfile.write(f'Content-Length: {len(jpeg_bytes)}\r\n\r\n'.encode())
self.wfile.write(jpeg_bytes)
self.wfile.write(b'\r\n')
```

```html
<!-- Istemci - JS sifir -->
<img src="/stream" />
```

**Tarayici destegi (dogrulama sonrasi duzeltme):**
- Chrome: Dokuman seviyesinde `multipart/x-mixed-replace` destegi Chrome 29'da kaldirildi. AMA `<img>` icinde MJPEG **hala calisiyor**.
- Firefox: Tam destek.
- Safari/WKWebView: Calisiyor ama uzun sure frame gelmezse baglanti koparabilir.
- pywebview WKWebView: MJPEG destekliyor. `debug=False` modu etkilemiyor.

**Kritik uygulama detaylari:**
- `BrokenPipeError` ve `ConnectionResetError` yakalanmali
- Chunked transfer encoding KULLANILMAMALI
- Boundary: `--frame` en uyumlu
- Yavas client icin `deque(maxlen=2)` ile frame atlama

**Performans karsilastirmasi [DOGRULANDI]:**

| Yontem | Overhead/frame | Gecikme | JS kodu |
|--------|---------------|---------|---------|
| MJPEG multipart | ~60 byte | ~5ms | Sifir |
| WebSocket binary | ~10 byte | ~2ms | Gerekli |
| HTTP polling + base64 | ~300 byte + %33 | ~20-50ms | Gerekli |

### 2.5 Goruntu Kucultme [DUZELTILMIS]

**xcrun kalite/cozunurluk kontrolu YOK.** Kucultme icin sonradan isleme zorunlu.

| Yontem | Hiz | Platform | Bagimsizlik | Dogrulama |
|--------|-----|----------|-------------|-----------|
| ffmpeg pipe | ~30ms | Cross-platform | ffmpeg (sistem) | DOGRULANDI |
| Pillow | ~20ms | Cross-platform | pip install pillow | DOGRULANDI |
| CoreImage/PyObjC | ~5-15ms | Sadece macOS | pip install pyobjc | DUZELTILDI |
| sips | Yavas | Sadece macOS | Yok | stdin/stdout YOK |

**ONEMLI DUZELTME - CoreImage/PyObjC:**
Onceki raporda "Harici Bagimsizlik: Yok" yaziyordu. Bu **YANLIS**.
macOS Monterey 12.3+ sonrasi Apple sistem Python'u ve PyObjC'yi kaldirdi.
`pip install pyobjc` ile kurulmasi GEREKIYOR.

**ffmpeg pipeline [DOGRULANDI]:**
```bash
xcrun simctl io booted screenshot --type=jpeg - | \
  ffmpeg -hide_banner -loglevel error -i pipe:0 \
  -vf "scale=iw/2:ih/2" -q:v 8 -f image2pipe -vcodec mjpeg pipe:1
```

ffmpeg -q:v degerleri (MJPEG): 2-5 yuksek, 6-10 dengeli, 11-20 dusuk.
Toplam gecikme: xcrun ~100ms + ffmpeg ~30-50ms = ~135-155ms.

**GUVENLIK NOTU:** `shell=True` yerine iki ayri `subprocess.Popen` ile pipe baglanmali.

### 2.6 Adaptif Frame Rate [KISMI DOGRU]

**CRC32 performansi [DOGRULANDI]:**
- 500KB: ~0.03ms, 1MB: ~0.07ms (ihmal edilebilir)
- Mevcut kodda `hash()` kullaniliyor, `zlib.crc32` degil (tutarsizlik)

**JPEG non-determinism riski:**
- xcrun'un JPEG encoder'i genellikle deterministik sonuc verir
- AMA garanti degil. Ayni ekran farkli byte'lar uretebilir
- Worst case: gereksiz frame encode edilir (fonksiyonel hata degil, performans kaybi)
- CRC32 yine de en uygun secim (pHash/SSIM overkill ve 100x yavas)

**Adaptif algoritma:**
```
Idle (degisiklik yok): 0.5 fps (2s aralik)
3+ ayni frame: yavasla
Degisiklik var: hizlan, max 10 fps (100ms aralik)
```

### 2.7 Bellek Optimizasyonu [KISMI DOGRU]

**Lock overhead [DOGRULANDI]:** ~50-100ns, ihmal edilebilir.
**Threading vs Multiprocessing:** Threading tercih edilmeli (I/O-bound is).

**Ring Buffer [KISMI DOGRU]:**
- Pattern teknik olarak dogru
- AMA `read()` methodu `bytes()` ile yeni nesne olusturuyor, on-tahsisin amacini kisitliyor
- CPython'da 3-10fps icin anlamli performans farki yaratmaz
- Sonuc: Overengineering. Basit `bytes` degiskeni yeterli.

### 2.8 scrcpy Mimarisi [DOGRULANDI - REFERANS]

1. `adb push scrcpy-server.jar /data/local/tmp/` (~50KB)
2. `adb forward tcp:27183 localabstract:scrcpy`
3. `adb shell CLASSPATH=... app_process / com.genymobile.scrcpy.Server ...`
4. Socket: ilk 68 byte device info, sonra H264 NAL paketleri
5. Root gerektirmez (`shell` kullanici + `SurfaceControl` gizli API)

Python'dan kullanilabilir ama H264 decode icin ffmpeg/av zorunlu.

### 2.9 Edge Case ve Guvenilirlik [DOGRULANDI]

- Eszamanli xcrun: calisiyor ama %20-30 yavaslar. Tekil thread ile onlenmeli.
- Simulator cokme: `returncode != 0` kontrolu + JPEG header dogrulama (`\xff\xd8`)
- ADB kopma: `adb kill-server && adb start-server`, max 3 deneme
- macOS izinleri: `xcrun simctl io` icin ekran izni GEREKMEZ

---

## 3. Cakisma Analizi

Iki agent cakisma kontrolu yapti. Sonuclar:

### CAKISMA YOK (4 madde)

| # | Konu | Aciklama |
|---|------|----------|
| 1 | MJPEG vs Mevcut API | `/stream` eklenir, `/api/screenshot` ve `/api/steps` aynen kalir |
| 7 | Ring Buffer vs Lock | Ring buffer kendi lock'unu yonetiyor, mevcut ile cakismaz |
| 8 | Temp dosya temizleme | `except OSError: pass` zaten handle ediyor |
| 6 | Hash non-determinism | Worst case: gereksiz encode. Fonksiyonel hata yok |

### POTANSIYEL RISK (3 madde)

| # | Konu | Risk | Cozum |
|---|------|------|-------|
| 2 | MJPEG + WKWebView | Uzun sure frame gelmezse timeout | Keep-alive: idle'da bile 1s'de bir son frame'i tekrar gonder |
| 5 | Adaptif fps + MJPEG | 2s frame araligi WKWebView'i koparabilir | Yakalama ve gonderme ayrilmali. Stream'de min 1fps keep-alive |
| 10 | Faz siralama | Faz 1'de base64 kaldirilirsa Faz 2 olmadan frontend bozulur | base64 kaldirma Faz 2 ile birlikte yapilmali |

### CAKISMA VAR (3 madde)

| # | Konu | Sorun | Cozum |
|---|------|-------|-------|
| 3 | ffmpeg bagimsizlik | Sistem bagimsiligi, pip ile kurulmaz | Opsiyonel: ffmpeg > Pillow > ham JPEG. `shutil.which("ffmpeg")` kontrolu |
| 4 | iOS JPEG vs Android PNG | MJPEG `image/jpeg` gonderir, Android PNG verir = bozuk goruntu | Android PNG -> JPEG cevirimi zorunlu (Pillow veya ffmpeg) |
| 9 | Android 3dk limit | Uzun testlerde screenrecord durur | Watchdog: 170s'de yeni process baslat. Sadece Faz 5 icin gecerli |

---

## 4. Uygulama Plani (Cakisma Analizine Gore Yeniden Siralanmis)

### Faz 1: Stdout Gecisi [BAGIMSIZ, RISKSIZ]
> base64'e DOKUNMA, sadece disk I/O'yu kaldir.

- [x] Hash karsilastirma - TAMAMLANDI
- [x] Client yoksa yakalama durdurma - TAMAMLANDI
- [x] JPEG format gecisi - TAMAMLANDI
- [ ] iOS: `xcrun simctl io booted screenshot --type=jpeg --mask=ignored -`
- [ ] Android: stdout'u direkt bellek'e al (dosyaya yazma)
- [ ] `hash()` yerine `zlib.crc32()` gecisi

**Kazanc:** Disk I/O sifir, hash tutarliligi.
**Risk:** Sifir. Mevcut frontend aynen calismaya devam eder.

### Faz 2: Goruntu Kucultme [BAGIMSIZ, OPSIYONEL]
> Faz 1'den sonra veya paralel yapilabilir.

- [ ] Fallback zinciri: `shutil.which("ffmpeg")` kontrolu
  1. ffmpeg varsa: `subprocess.Popen` pipeline (shell=True KULLANMA)
  2. ffmpeg yoksa + Pillow varsa: `Image.thumbnail()` ile resize
  3. Hicbiri yoksa: tam boyut JPEG gonder
- [ ] JPEG kalite: ffmpeg `-q:v 8` veya Pillow `quality=60`
- [ ] Yarim cozunurluk (1170x2532 -> 585x1266)

**Kazanc:** Frame boyutu ~500KB -> ~150KB.
**Risk:** ffmpeg/Pillow yoksa etkisiz (ama calismaya devam eder).

**ffmpeg pipeline (shell=True OLMADAN):**
```python
import shutil, subprocess

def capture_resized():
    if shutil.which("ffmpeg"):
        xcrun = subprocess.Popen(
            ['xcrun', 'simctl', 'io', 'booted', 'screenshot', '--type=jpeg', '-'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        ffmpeg = subprocess.Popen(
            ['ffmpeg', '-hide_banner', '-loglevel', 'error',
             '-i', 'pipe:0', '-vf', 'scale=iw/2:ih/2',
             '-q:v', '8', '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'],
            stdin=xcrun.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        xcrun.stdout.close()
        data = ffmpeg.communicate()[0]
        return data if data and data[:2] == b'\xff\xd8' else None
    else:
        # Fallback: tam boyut
        result = subprocess.run(
            ['xcrun', 'simctl', 'io', 'booted', 'screenshot', '--type=jpeg', '-'],
            capture_output=True, timeout=10
        )
        return result.stdout if result.returncode == 0 else None
```

### Faz 3: MJPEG Stream + base64 Kaldirma + Adaptif fps [BIRLIKTE YAPILMALI]
> Bu uc degisiklik birbirine bagimli. Ayri uygulanirsa frontend bozulur.

- [ ] `/stream` MJPEG endpoint'i ekle
- [ ] base64 encode'u kaldir, binary JPEG kullan
- [ ] Frontend: `<img src="/stream">` ile degistir, `refreshScreen()` ve `setInterval` kaldir
- [ ] Steps polling (`/api/steps`) aynen kalsin (JSON, fetch ile)
- [ ] `BrokenPipeError` / `ConnectionResetError` yakalama
- [ ] Adaptif yakalama: CRC32 degisiklik kontrolu, 0.5-10 fps arasi
- [ ] Keep-alive frame: ekran degismese bile min 1s'de bir son frame'i tekrar gonder
- [ ] Android PNG -> JPEG cevirimi (CAKISMA #4 cozumu):
  ```python
  # Android PNG'yi JPEG'e cevir (Pillow ile)
  try:
      from PIL import Image
      import io
      img = Image.open(io.BytesIO(png_data))
      buf = io.BytesIO()
      img.save(buf, 'JPEG', quality=60)
      jpeg_data = buf.getvalue()
  except ImportError:
      # Pillow yoksa PNG'yi oldufu gibi gonder (Content-Type: image/png)
      jpeg_data = png_data
  ```
- [ ] `deque(maxlen=2)` ile yavas client frame atlama

**Kazanc:** Gecikme 2-3s -> ~300ms, base64 sifir, idle CPU sifir.
**Risk:** WKWebView timeout (keep-alive ile cozuldu), Android format (cevirim ile cozuldu).

**MJPEG stream handler ornegi:**
```python
def handle_stream(self):
    self.send_response(200)
    self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=--frame')
    self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
    self.send_header('Connection', 'close')
    self.end_headers()

    last_send = 0
    while self._running:
        frame = self.capture.get_jpeg()  # binary bytes
        if frame is None:
            time.sleep(0.1)
            continue

        now = time.monotonic()

        # Keep-alive: frame degismese bile 1s'de bir gonder
        if now - last_send < 0.1 and not self.capture.has_new_frame():
            time.sleep(0.05)
            continue

        try:
            self.wfile.write(b'--frame\r\n')
            self.wfile.write(b'Content-Type: image/jpeg\r\n')
            self.wfile.write(f'Content-Length: {len(frame)}\r\n'.encode())
            self.wfile.write(b'\r\n')
            self.wfile.write(frame)
            self.wfile.write(b'\r\n')
            self.wfile.flush()
            last_send = now
        except (BrokenPipeError, ConnectionResetError):
            break
```

### Faz 4: Ileri Seviye [OPSIYONEL, EN RISKLI]
> Agir bagimsizliklar, 3dk limit gibi sorunlar var. Sadece gerektiginde.

- [ ] Android screenrecord H264 stream + ffmpeg decode
  - 3dk limit cozumu: Watchdog thread, 170s'de yeniden baslat
  - Frame kaybi: ~0.5-1s (eski process olur, yenisi baslar)
- [ ] scrcpy-server.jar entegrasyonu (H264 decode zorunlu)
- [ ] WebSocket binary frame alternatifi (daha az overhead ama JS gerekli)
- [ ] Birden fazla simulator destegi (UDID secimi)

---

## 5. Dogrulama Ozet Tablosu

| Madde | Dogrulama Sonucu | Kritik Not |
|-------|-----------------|------------|
| xcrun stdout (`-`) | DOGRULANDI | Calisiyor, gecikme rakamlari dogrulanamadi |
| MJPEG Stream | KISMI DOGRU | Chrome `<img>` icinde destekliyor, dokuman seviyesinde degil |
| ffmpeg pipeline | DOGRULANDI | Komut calisiyor, `shell=True` kullanilmamali |
| CoreImage/PyObjC | DUZELTILDI | PyObjC macOS 12.3+ sonrasi kurulu GELMIYOR |
| Android H264 stream | DOGRULANDI | stdout, 3dk limit, --size hepsi dogru |
| Adaptif fps CRC32 | KISMI DOGRU | Calisiyor, JPEG non-determinism riski dusuk |
| base64 %33 overhead | DOGRULANDI | Matematiksel kesinlik |
| Ring Buffer | GEREKSIZ | CPython'da 3-10fps icin anlamli fark yok |
| scrcpy mimarisi | DOGRULANDI | Referans bilgi, entegrasyon opsiyonel |
| Edge case'ler | DOGRULANDI | Mevcut kod cogu durumu handle ediyor |

---

## 6. Cakisma Ozet Tablosu

| # | Cakisma | Durum | Cozum | Hangi Fazda |
|---|---------|-------|-------|-------------|
| 1 | MJPEG vs API | YOK | `/stream` eklenir, eski API kalir | Faz 3 |
| 2 | MJPEG + WKWebView | RISK | Keep-alive frame (min 1fps) | Faz 3 |
| 3 | ffmpeg bagimsizlik | VAR | Opsiyonel: ffmpeg > Pillow > ham JPEG | Faz 2 |
| 4 | iOS JPEG vs Android PNG | VAR | Android PNG -> JPEG cevirimi | Faz 3 |
| 5 | Adaptif fps + MJPEG | RISK | Yakalama/gonderme ayrilmali | Faz 3 |
| 6 | Hash non-determinism | RISK (dusuk) | Gereksiz encode, fonksiyonel hata yok | - |
| 7 | Ring Buffer vs Lock | YOK | Birlikte calisiyor | - |
| 8 | Temp dosya | YOK | except OSError zaten var | - |
| 9 | Android 3dk limit | VAR | Watchdog yeniden baslatma | Faz 4 |
| 10 | Faz siralama | RISK | base64 kaldirma = Faz 3 ile birlikte | Faz 3 |

---

## 7. Beklenen Sonuc

| Metrik | Simdiki | Faz 1 | Faz 2 | Faz 3 | Faz 4 |
|--------|---------|-------|-------|-------|-------|
| Frame boyutu | ~1064 KB | ~800 KB | ~150 KB | ~150 KB | ~150 KB |
| Gecikme | 2-3s | 2-3s | 2-3s | ~300ms | ~100ms |
| Disk I/O | Her frame | Sifir | Sifir | Sifir | Sifir |
| CPU (encode) | Yuksek | Orta | Dusuk | Dusuk | Minimal |
| JS overhead | Polling | Polling | Polling | Sifir | Sifir |
| base64 | +33% | +33% | +33% | Sifir | Sifir |
| Bellek/frame | ~1.4 MB | ~1.1 MB | ~200 KB | ~200 KB | ~200 KB |
| Idle CPU | Sabit | Sabit | Sabit | ~Sifir | ~Sifir |

**Faz 1 + 2:** Frame boyutu 7x kucuk, disk I/O sifir.
**Faz 3:** Gecikme 10x azalma, JS overhead sifir, base64 sifir.
**Faz 4:** Android'de surekli stream, idle CPU sifir.

---

## 8. Optimal Pipeline (Hedef - Faz 3 Sonrasi)

### iOS
```
xcrun simctl io <UDID> screenshot --type=jpeg --mask=ignored -
  -> subprocess stdout (disk I/O sifir)
  -> CRC32 degisiklik kontrolu (~0.03ms)
  -> ffmpeg/Pillow resize + kalite (opsiyonel, ~30ms)
  -> MJPEG stream (binary, ~60 byte overhead)
  -> <img src="/stream"> (JS sifir)
```

### Android
```
adb exec-out screencap -p
  -> subprocess stdout (PNG)
  -> Pillow/ffmpeg PNG->JPEG cevirimi + resize
  -> CRC32 degisiklik kontrolu
  -> MJPEG stream (binary)
  -> <img src="/stream">
```

### Android Ileri Seviye (Faz 4)
```
adb shell screenrecord --output-format=h264 --size=540x960 -
  -> ffmpeg H264->MJPEG decode + resize
  -> JPEG frame parse (SOI/EOI marker)
  -> MJPEG stream
  -> <img src="/stream">
  -> Watchdog: 170s'de yeniden baslat
```
