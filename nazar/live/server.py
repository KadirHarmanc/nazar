"""Nazar Live Server - stdlib HTTP sunucusu ile canli tarama goruntuleme.

Sadece Python stdlib (http.server, json, threading) kullanir.
Flask/FastAPI gibi harici bagimliliklara ihtiyac duymaz.

Kullanim:
    server = NazarLiveServer(port=5555)
    server.set_results(results, plan_data)
    server.start()   # arka planda baslatir
    ...
    server.stop()
"""

import json
import os
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================
# HTML sablonu - tamamen gomulu, harici dosya gerektirmez
# ============================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nazar Live Report</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0f1117;--bg2:#1a1d27;--bg3:#242836;--border:#2d3348;
  --text:#e2e8f0;--text2:#94a3b8;--text3:#64748b;
  --green:#22c55e;--green-bg:rgba(34,197,94,.12);
  --red:#ef4444;--red-bg:rgba(239,68,68,.12);
  --yellow:#eab308;--yellow-bg:rgba(234,179,8,.12);
  --cyan:#06b6d4;--cyan-bg:rgba(6,182,212,.12);
  --purple:#a855f7;--blue:#3b82f6;
}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;min-height:100vh}
.container{max-width:960px;margin:0 auto;padding:16px}
header{text-align:center;padding:24px 0 16px;border-bottom:1px solid var(--border);margin-bottom:24px}
header h1{font-size:1.5rem;color:var(--cyan);margin-bottom:4px;letter-spacing:2px}
header .sub{color:var(--text3);font-size:.8rem}
.status-badge{display:inline-block;padding:3px 12px;border-radius:12px;font-size:.75rem;font-weight:600;margin-left:8px}
.status-scanning{background:var(--yellow-bg);color:var(--yellow);animation:pulse 1.5s infinite}
.status-done{background:var(--green-bg);color:var(--green)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}

/* Grade */
.grade-card{text-align:center;padding:32px 16px;margin-bottom:24px;background:var(--bg2);border-radius:12px;border:1px solid var(--border)}
.grade-letter{font-size:4rem;font-weight:900;line-height:1}
.grade-A-plus,.grade-A,.grade-A-minus{color:var(--green)}
.grade-B-plus,.grade-B,.grade-B-minus{color:#4ade80}
.grade-C-plus,.grade-C,.grade-C-minus{color:var(--yellow)}
.grade-D-plus,.grade-D,.grade-D-minus{color:#f97316}
.grade-F{color:var(--red)}
.grade-sub{color:var(--text2);font-size:.9rem;margin-top:8px}

/* Stats row */
.stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:24px}
.stat-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center}
.stat-value{font-size:1.5rem;font-weight:700}
.stat-value.green{color:var(--green)}.stat-value.red{color:var(--red)}.stat-value.cyan{color:var(--cyan)}.stat-value.yellow{color:var(--yellow)}
.stat-label{color:var(--text3);font-size:.75rem;margin-top:2px}

/* Categories */
.section{margin-bottom:24px}
.section h2{font-size:1rem;color:var(--text2);margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.cat-row{display:flex;align-items:center;gap:10px;padding:8px 12px;margin-bottom:6px;background:var(--bg2);border-radius:8px;border:1px solid var(--border)}
.cat-name{width:140px;font-size:.85rem;font-weight:600;flex-shrink:0}
.cat-bar-wrap{flex:1;height:20px;background:var(--bg3);border-radius:4px;overflow:hidden;position:relative}
.cat-bar-fill{height:100%;border-radius:4px;transition:width .5s ease}
.cat-bar-fill.high{background:var(--green)}.cat-bar-fill.mid{background:var(--yellow)}.cat-bar-fill.low{background:var(--red)}
.cat-nums{width:80px;text-align:right;font-size:.8rem;color:var(--text2);flex-shrink:0}
.cat-pct{width:48px;text-align:right;font-size:.8rem;font-weight:600;flex-shrink:0}
.cat-pct.high{color:var(--green)}.cat-pct.mid{color:var(--yellow)}.cat-pct.low{color:var(--red)}

/* Failed tests */
.fail-card{background:var(--bg2);border:1px solid var(--border);border-left:3px solid var(--red);border-radius:8px;padding:14px 16px;margin-bottom:10px}
.fail-card.critical{border-left-color:var(--red)}.fail-card.high{border-left-color:#f97316}.fail-card.medium{border-left-color:var(--yellow)}.fail-card.low{border-left-color:var(--text3)}
.fail-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;flex-wrap:wrap;gap:6px}
.fail-name{font-weight:600;font-size:.9rem}
.fail-badges{display:flex;gap:6px;flex-wrap:wrap}
.badge{padding:2px 8px;border-radius:6px;font-size:.7rem;font-weight:600}
.badge-critical{background:var(--red-bg);color:var(--red)}.badge-high{background:rgba(249,115,22,.15);color:#f97316}
.badge-medium{background:var(--yellow-bg);color:var(--yellow)}.badge-low{background:rgba(100,116,139,.15);color:var(--text3)}
.badge-cat{background:var(--cyan-bg);color:var(--cyan)}
.fail-detail{color:var(--text2);font-size:.82rem;line-height:1.6}
.fail-fix{margin-top:6px;padding:8px 10px;background:rgba(34,197,94,.06);border-radius:6px;font-size:.82rem;color:var(--green)}

/* Footer */
footer{text-align:center;padding:20px 0;color:var(--text3);font-size:.75rem;border-top:1px solid var(--border);margin-top:24px}

/* Responsive */
@media(max-width:640px){
  .cat-row{flex-wrap:wrap;gap:6px}
  .cat-name{width:100%}
  .cat-bar-wrap{order:3;width:100%}
  .cat-nums{width:auto}.cat-pct{width:auto}
  .stats-row{grid-template-columns:repeat(2,1fr)}
  .grade-letter{font-size:3rem}
  .fail-header{flex-direction:column;align-items:flex-start}
}

/* Scrollbar */
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-track{background:var(--bg)}::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

/* No results */
.empty{text-align:center;padding:60px 20px;color:var(--text3)}
.empty h2{font-size:1.2rem;margin-bottom:8px;color:var(--text2)}
.spinner{display:inline-block;width:32px;height:32px;border:3px solid var(--border);border-top-color:var(--cyan);border-radius:50%;animation:spin 1s linear infinite;margin-bottom:16px}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>NAZAR</h1>
  <div class="sub">
    Otonom Guvenlik & Kalite Tarayici
    <span id="statusBadge" class="status-badge status-scanning">Tarama devam ediyor</span>
  </div>
</header>
<div id="content">
  <div class="empty">
    <div class="spinner"></div>
    <h2>Tarama baslatiliyor...</h2>
    <p>Sonuclar geldikce burada gorunecek.</p>
  </div>
</div>
<footer>
  Nazar Live Report &middot; <span id="timestamp">-</span> &middot; localhost:{{PORT}}
</footer>
</div>

<script>
const PORT = {{PORT}};
let autoRefresh = null;

function gradeClass(g) {
  return 'grade-' + g.replace('+','plus').replace('-','minus').replace(' ','');
}

function barLevel(pct) {
  return pct >= 80 ? 'high' : pct >= 50 ? 'mid' : 'low';
}

function priorityOrder(p) {
  return {critical:0,high:1,medium:2,low:3}[p] ?? 4;
}

function escH(s) {
  if (!s) return '';
  var d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function buildStatCard(val, label, color) {
  var card = document.createElement('div');
  card.className = 'stat-card';
  var valEl = document.createElement('div');
  valEl.className = 'stat-value ' + color;
  valEl.textContent = val;
  var labelEl = document.createElement('div');
  labelEl.className = 'stat-label';
  labelEl.textContent = label;
  card.appendChild(valEl);
  card.appendChild(labelEl);
  return card;
}

function buildCatRow(name, d) {
  var total = d.passed + d.failed;
  var pct = total > 0 ? (d.passed / total * 100) : 0;
  var lvl = barLevel(pct);

  var row = document.createElement('div');
  row.className = 'cat-row';

  var nameEl = document.createElement('span');
  nameEl.className = 'cat-name';
  nameEl.textContent = name.toUpperCase();
  row.appendChild(nameEl);

  var barWrap = document.createElement('div');
  barWrap.className = 'cat-bar-wrap';
  var barFill = document.createElement('div');
  barFill.className = 'cat-bar-fill ' + lvl;
  barFill.style.width = pct.toFixed(0) + '%';
  barWrap.appendChild(barFill);
  row.appendChild(barWrap);

  var nums = document.createElement('span');
  nums.className = 'cat-nums';
  nums.textContent = d.passed + '/' + total;
  row.appendChild(nums);

  var pctEl = document.createElement('span');
  pctEl.className = 'cat-pct ' + lvl;
  pctEl.textContent = pct.toFixed(0) + '%';
  row.appendChild(pctEl);

  return row;
}

function buildFailCard(t) {
  var pri = t.priority || 'medium';
  var card = document.createElement('div');
  card.className = 'fail-card ' + pri;

  var header = document.createElement('div');
  header.className = 'fail-header';

  var nameEl = document.createElement('span');
  nameEl.className = 'fail-name';
  nameEl.textContent = t.name;
  header.appendChild(nameEl);

  var badges = document.createElement('div');
  badges.className = 'fail-badges';

  var priBadge = document.createElement('span');
  priBadge.className = 'badge badge-' + pri;
  priBadge.textContent = pri.toUpperCase();
  badges.appendChild(priBadge);

  if (t.type) {
    var catBadge = document.createElement('span');
    catBadge.className = 'badge badge-cat';
    catBadge.textContent = t.type.toUpperCase();
    badges.appendChild(catBadge);
  }
  if (t.confidence) {
    var confBadge = document.createElement('span');
    confBadge.className = 'badge badge-cat';
    confBadge.textContent = 'Guven: ' + t.confidence + '%';
    badges.appendChild(confBadge);
  }

  header.appendChild(badges);
  card.appendChild(header);

  if (t.detail) {
    var detailEl = document.createElement('div');
    detailEl.className = 'fail-detail';
    detailEl.textContent = t.detail;
    card.appendChild(detailEl);
  }

  var fix = t.how_to_fix;
  if (fix && fix.quick_fix) {
    var fixEl = document.createElement('div');
    fixEl.className = 'fail-fix';
    fixEl.textContent = 'Fix: ' + fix.quick_fix;
    card.appendChild(fixEl);
  }

  return card;
}

function calcGrade(rate) {
  var grades = [[97,'A+'],[93,'A'],[90,'A-'],[87,'B+'],[83,'B'],[80,'B-'],[77,'C+'],[73,'C'],[70,'C-'],[67,'D+'],[63,'D'],[60,'D-'],[0,'F']];
  for (var i = 0; i < grades.length; i++) {
    if (rate >= grades[i][0]) return grades[i][1];
  }
  return 'F';
}

function renderResults(data) {
  if (!data || !data.results || data.results.length === 0) {
    return;
  }

  var r = data.results;
  var passed = r.filter(function(t){ return t.passed; }).length;
  var failed = r.length - passed;
  var rate = r.length > 0 ? (passed / r.length * 100) : 0;
  var grade = data.grade || calcGrade(rate);
  var dur = data.duration ? data.duration.toFixed(1) + 's' : '-';

  // Kategoriler
  var cats = {};
  r.forEach(function(t) {
    var c = t.type || 'other';
    if (!cats[c]) cats[c] = {passed:0, failed:0};
    cats[c][t.passed ? 'passed' : 'failed']++;
  });

  var container = document.getElementById('content');
  // DOM'u temizle
  while (container.firstChild) {
    container.removeChild(container.firstChild);
  }

  // Grade card
  var gradeCard = document.createElement('div');
  gradeCard.className = 'grade-card';
  var gradeLetter = document.createElement('div');
  gradeLetter.className = 'grade-letter ' + gradeClass(grade);
  gradeLetter.textContent = grade;
  gradeCard.appendChild(gradeLetter);
  var gradeSub = document.createElement('div');
  gradeSub.className = 'grade-sub';
  gradeSub.textContent = rate.toFixed(0) + '% basari orani \u00b7 ' + r.length + ' test \u00b7 ' + dur;
  gradeCard.appendChild(gradeSub);
  container.appendChild(gradeCard);

  // Stats row
  var statsRow = document.createElement('div');
  statsRow.className = 'stats-row';
  statsRow.appendChild(buildStatCard(passed, 'Gecti', 'green'));
  statsRow.appendChild(buildStatCard(failed, 'Kaldi', failed > 0 ? 'red' : 'green'));
  statsRow.appendChild(buildStatCard(r.length, 'Toplam', 'cyan'));
  statsRow.appendChild(buildStatCard(Object.keys(cats).length, 'Kategori', 'yellow'));
  container.appendChild(statsRow);

  // Categories section
  var catSection = document.createElement('div');
  catSection.className = 'section';
  var catTitle = document.createElement('h2');
  catTitle.textContent = 'Kategori Dagilimi';
  catSection.appendChild(catTitle);

  var sortedCats = Object.entries(cats).sort(function(a, b) {
    var ra = a[1].passed / (a[1].passed + a[1].failed) * 100;
    var rb = b[1].passed / (b[1].passed + b[1].failed) * 100;
    return ra - rb;
  });
  sortedCats.forEach(function(entry) {
    catSection.appendChild(buildCatRow(entry[0], entry[1]));
  });
  container.appendChild(catSection);

  // Failed tests
  var failedTests = r.filter(function(t){ return !t.passed; }).sort(function(a,b){
    return priorityOrder(a.priority) - priorityOrder(b.priority);
  });
  if (failedTests.length > 0) {
    var failSection = document.createElement('div');
    failSection.className = 'section';
    var failTitle = document.createElement('h2');
    failTitle.textContent = failedTests.length + ' Basarisiz Test';
    failSection.appendChild(failTitle);
    failedTests.forEach(function(t) {
      failSection.appendChild(buildFailCard(t));
    });
    container.appendChild(failSection);
  } else {
    var successSection = document.createElement('div');
    successSection.className = 'section';
    var successCard = document.createElement('div');
    successCard.className = 'grade-card';
    successCard.style.borderColor = 'var(--green)';
    var successMsg = document.createElement('div');
    successMsg.style.color = 'var(--green)';
    successMsg.style.fontSize = '2rem';
    successMsg.style.fontWeight = '700';
    successMsg.textContent = 'Tum testler gecti!';
    successCard.appendChild(successMsg);
    successSection.appendChild(successCard);
    container.appendChild(successSection);
  }
}

async function fetchData() {
  try {
    var statusRes = await fetch('/api/status');
    var resultsRes = await fetch('/api/results');
    var status = await statusRes.json();
    var results = await resultsRes.json();

    // Status badge guncelle
    var badge = document.getElementById('statusBadge');
    if (status.status === 'done') {
      badge.className = 'status-badge status-done';
      badge.textContent = 'Tamamlandi';
      // Tarama bittiyse refresh durdur
      if (autoRefresh) { clearInterval(autoRefresh); autoRefresh = null; }
    } else {
      badge.className = 'status-badge status-scanning';
      badge.textContent = 'Tarama devam ediyor...';
    }

    // Timestamp
    document.getElementById('timestamp').textContent = new Date().toLocaleTimeString('tr-TR');

    renderResults(results);
  } catch(e) {
    // Sunucu kapanmis olabilir
  }
}

// Ilk yukle
fetchData();
// Tarama sirasinda 5sn'de bir yenile
autoRefresh = setInterval(fetchData, 5000);
</script>
</body>
</html>"""


class _NazarHandler(BaseHTTPRequestHandler):
    """HTTP istek isleyici. server objesindeki verilere erisir."""

    def log_message(self, format, *args):
        """Konsol ciktisini bastir - sessiz calis."""
        pass

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        server_obj: NazarLiveServer = self.server._nazar_server

        if self.path == "/api/results":
            data = server_obj.get_results_data()
            self._send_json(data)

        elif self.path == "/api/status":
            self._send_json({
                "status": server_obj.status,
                "started_at": server_obj.started_at,
                "updated_at": server_obj.updated_at,
            })

        elif self.path == "/" or self.path == "/index.html":
            html = HTML_TEMPLATE.replace("{{PORT}}", str(server_obj.port))
            self._send_html(html)

        else:
            self._send_json({"error": "not found"}, 404)


class NazarLiveServer:
    """Nazar canli web sunucusu.

    Tarama sirasinda veya sonrasinda sonuclari localhost uzerinden gosterir.
    Sadece stdlib kullanir, ek bagimliligi yoktur.

    Kullanim:
        server = NazarLiveServer(port=5555)
        server.start()                  # arka planda baslatir
        server.set_status("scanning")
        ...
        server.set_results(results, plan_data)
        server.set_status("done")
        ...
        server.stop()

    Veya mevcut tarama sonuclarindan baslatmak icin:
        server = NazarLiveServer.from_cache(project_path, port=5555)
        server.start_blocking()         # on planda calisir (Ctrl+C ile durdurulur)
    """

    def __init__(self, port: int = 5555):
        self.port = port
        self.status = "idle"
        self.started_at = ""
        self.updated_at = ""
        self._results: List[dict] = []
        self._plan_data: dict = {}
        self._grade: str = ""
        self._duration: float = 0.0
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # --- Veri yonetimi ---

    def set_results(self, results: List[dict], plan_data: Optional[dict] = None,
                    grade: str = "", duration: float = 0.0):
        """Tarama sonuclarini ayarla."""
        with self._lock:
            self._results = list(results) if results else []
            self._plan_data = plan_data or {}
            self._grade = grade
            self._duration = duration
            self.updated_at = datetime.now().isoformat()

    def set_status(self, status: str):
        """Durum guncelle: 'idle', 'scanning', 'done'."""
        with self._lock:
            self.status = status
            self.updated_at = datetime.now().isoformat()

    def get_results_data(self) -> dict:
        """API'den donecek JSON verisini olustur."""
        with self._lock:
            results = list(self._results)
            plan_data = dict(self._plan_data)
            grade = self._grade
            duration = self._duration

        if not results:
            return {"results": [], "grade": "", "duration": 0, "categories": {}}

        passed = sum(1 for r in results if r.get("passed"))
        total = len(results)
        rate = (passed / total * 100) if total > 0 else 0

        if not grade:
            grade = self._calc_grade(rate)

        # Kategori ozeti
        categories = {}
        for r in results:
            cat = r.get("type", "other")
            if cat not in categories:
                categories[cat] = {"passed": 0, "failed": 0}
            if r.get("passed"):
                categories[cat]["passed"] += 1
            else:
                categories[cat]["failed"] += 1

        return {
            "results": results,
            "grade": grade,
            "pass_rate": round(rate, 1),
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "duration": duration,
            "categories": categories,
        }

    # --- Sunucu yasam dongusu ---

    def start(self):
        """Sunucuyu arka plan thread'inde baslat."""
        if self._server is not None:
            return  # Zaten calisiyor

        self.started_at = datetime.now().isoformat()
        try:
            self._server = HTTPServer(("127.0.0.1", self.port), _NazarHandler)
        except OSError as e:
            print(f"[Nazar] Port {self.port} kullanimda veya erisilemiyor: {e}")
            print(f"[Nazar] Farkli bir port deneyin: --live-port <port>")
            return
        self._server._nazar_server = self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        """Sunucuyu durdur."""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def start_blocking(self):
        """Sunucuyu on planda baslat (Ctrl+C ile durur)."""
        self.started_at = datetime.now().isoformat()
        self._server = HTTPServer(("127.0.0.1", self.port), _NazarHandler)
        self._server._nazar_server = self
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self._server.shutdown()
            self._server = None

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}"

    # --- Fabrika metotlari ---

    @classmethod
    def from_cache(cls, project_path: str, port: int = 5555) -> "NazarLiveServer":
        """Mevcut tarama sonuclarindan sunucu olustur.

        .nazar/last-scan.json dosyasini okur ve sonuclari yukler.
        """
        from nazar.cache.scan_cache import ScanCache

        server = cls(port=port)
        cache = ScanCache(project_path)

        if not cache.has_previous_scan():
            return server

        try:
            last_scan_file = cache.last_scan_file
            data = json.loads(last_scan_file.read_text())
            results = data.get("results", [])
            grade = data.get("grade", "")
            duration = data.get("duration", 0.0)
            server.set_results(results, {}, grade, duration)
            server.set_status("done")
        except (json.JSONDecodeError, OSError, KeyError):
            pass

        return server

    # --- Yardimcilar ---

    @staticmethod
    def _calc_grade(rate: float) -> str:
        for min_r, g in [(97, "A+"), (93, "A"), (90, "A-"), (87, "B+"), (83, "B"),
                         (80, "B-"), (77, "C+"), (73, "C"), (70, "C-"), (67, "D+"),
                         (63, "D"), (60, "D-"), (0, "F")]:
            if rate >= min_r:
                return g
        return "F"
