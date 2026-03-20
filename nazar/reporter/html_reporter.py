"""HTML Reporter - Test sonuclarini interaktif HTML raporuna donusturur."""
from pathlib import Path
from datetime import datetime
from typing import List, Dict


def _letter_grade(rate: float) -> tuple:
    """(grade, stars, color) dondurur."""
    grades = [
        (97, "A+", 5, "#22c55e"), (93, "A", 5, "#22c55e"), (90, "A-", 4, "#22c55e"),
        (87, "B+", 4, "#84cc16"), (83, "B", 3, "#84cc16"), (80, "B-", 3, "#84cc16"),
        (77, "C+", 2, "#eab308"), (73, "C", 2, "#eab308"), (70, "C-", 2, "#eab308"),
        (67, "D+", 1, "#f97316"), (63, "D", 1, "#f97316"), (60, "D-", 1, "#f97316"),
        (0, "F", 0, "#ef4444"),
    ]
    for min_rate, grade, stars, color in grades:
        if rate >= min_rate:
            return grade, stars, color
    return "F", 0, "#ef4444"


class HTMLReporter:
    def generate(self, results: List[Dict], plan: dict, output_path: str):
        total = len(results)
        passed = sum(1 for r in results if r["passed"])
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0
        total_duration = sum(r.get("duration", 0) for r in results)

        # Kategorilere ayir
        categories = {}
        for r in results:
            cat = r.get("type", "other")
            if cat not in categories:
                categories[cat] = {"passed": 0, "failed": 0, "tests": []}
            if r["passed"]:
                categories[cat]["passed"] += 1
            else:
                categories[cat]["failed"] += 1
            categories[cat]["tests"].append(r)

        grade, stars, color = _letter_grade(pass_rate)
        star_html = "".join(f'<span class="star active">*</span>' for _ in range(stars)) + \
                    "".join(f'<span class="star">*</span>' for _ in range(5 - stars))

        # SVG score gauge
        circumference = 2 * 3.14159 * 54
        offset = circumference - (pass_rate / 100) * circumference

        # Category kartlari HTML
        cat_cards = ""
        for cat_name, cat_data in categories.items():
            cat_total = cat_data["passed"] + cat_data["failed"]
            cat_rate = (cat_data["passed"] / cat_total * 100) if cat_total > 0 else 0
            cat_color = "#22c55e" if cat_rate >= 80 else "#eab308" if cat_rate >= 50 else "#ef4444"

            # Kategori testleri
            cat_tests_html = ""
            for ct in cat_data["tests"]:
                status_class = "passed" if ct["passed"] else "failed"
                status_text = "PASSED" if ct["passed"] else "FAILED"
                priority = ct.get("priority", "medium")
                detail = ct.get("detail", "")

                # Guide + How to Fix
                fix_html = ""
                guide = ct.get("guide")
                if guide and not ct["passed"]:
                    steps_html = "".join(f"<li>{s}</li>" for s in guide.get("steps", []))
                    warn_html = f'<div class="guide-warn">{guide["warning"]}</div>' if guide.get("warning") else ""
                    tools_html = ""
                    if guide.get("tools"):
                        tools_html = '<div class="guide-tools">Onerilen: ' + ", ".join(guide["tools"]) + "</div>"
                    before = guide.get("before", "").replace("<", "&lt;").replace(">", "&gt;")
                    after = guide.get("after", "").replace("<", "&lt;").replace(">", "&gt;")
                    fix_html = f"""
                    <div class="guide-box">
                        <div class="guide-title">{guide['title']}</div>
                        <div class="guide-risk">{guide['risk']}</div>
                        <div class="guide-what"><b>Ne Oluyor:</b> {guide['what']}</div>
                        <div class="guide-why"><b>Neden Onemli:</b> {guide['why']}</div>
                        <div class="guide-steps"><b>Adim Adim:</b><ol>{steps_html}</ol></div>
                        <div class="guide-code"><div class="guide-before"><div class="guide-label">ONCE (yanlis)</div><pre>{before}</pre></div><div class="guide-after"><div class="guide-label">SONRA (dogru)</div><pre>{after}</pre></div></div>
                        {warn_html}{tools_html}
                    </div>"""
                elif ct.get("how_to_fix") and not ct["passed"]:
                    fix = ct["how_to_fix"]
                    fix_html = f"""
                    <div class="how-to-fix">
                        <div class="fix-title">Nasil Duzeltilir?</div>
                        <div class="fix-item"><b>SORUN:</b> {fix['sorun']}</div>
                        <div class="fix-item"><b>COZUM:</b> {fix['cozum']}</div>
                        <div class="fix-item fix-quick"><b>QUICK FIX:</b> {fix['quick_fix']}</div>
                    </div>"""

                cat_tests_html += f"""
                <div class="test-row {status_class}" data-name="{ct['name'].lower()}" data-status="{status_class}" data-priority="{priority}">
                    <span class="test-name">{ct['name']}</span>
                    <span class="badge {status_class}">{status_text}</span>
                    <span class="badge priority-{priority}">{priority}</span>
                    <span class="test-duration">{ct.get('duration', 0):.2f}s</span>
                    <span class="test-detail">{detail}</span>
                    {fix_html}
                </div>"""

            cat_cards += f"""
            <div class="category-section">
                <div class="category-header" onclick="toggleCategory(this)">
                    <span class="category-toggle">+</span>
                    <span class="category-name">{cat_name.upper()}</span>
                    <span class="category-stats">
                        <span class="badge passed">{cat_data['passed']}</span>
                        <span class="badge failed">{cat_data['failed']}</span>
                    </span>
                    <div class="category-bar">
                        <div class="category-bar-fill" style="width:{cat_rate:.0f}%;background:{cat_color}"></div>
                    </div>
                    <span class="category-rate" style="color:{cat_color}">{cat_rate:.0f}%</span>
                </div>
                <div class="category-body" style="display:none">
                    {cat_tests_html}
                </div>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nazar Test Report</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
.header {{ text-align: center; padding: 40px 0 20px; }}
.header h1 {{ font-size: 2.5em; background: linear-gradient(135deg, #6366f1, #8b5cf6, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
.header .subtitle {{ color: #94a3b8; margin-top: 8px; }}
.score-section {{ text-align: center; margin: 30px 0; }}
.score-gauge {{ position: relative; width: 140px; height: 140px; margin: 0 auto; }}
.score-gauge svg {{ transform: rotate(-90deg); }}
.score-gauge .grade {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 2.2em; font-weight: bold; color: {color}; }}
.score-gauge .rate {{ position: absolute; top: 68%; left: 50%; transform: translateX(-50%); font-size: 0.85em; color: #94a3b8; }}
.stars {{ margin-top: 10px; font-size: 1.5em; }}
.star {{ color: #334155; }}
.star.active {{ color: #eab308; }}
.summary {{ display: flex; gap: 20px; justify-content: center; margin: 25px 0; flex-wrap: wrap; }}
.summary .stat {{ background: #1e293b; padding: 15px 25px; border-radius: 12px; text-align: center; min-width: 120px; }}
.summary .stat .value {{ font-size: 1.8em; font-weight: bold; }}
.summary .stat .label {{ color: #94a3b8; font-size: 0.85em; }}
.toolbar {{ display: flex; gap: 12px; margin: 25px 0; flex-wrap: wrap; align-items: center; }}
.search-box {{ flex: 1; min-width: 200px; padding: 10px 15px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #e2e8f0; font-size: 0.9em; outline: none; }}
.search-box:focus {{ border-color: #6366f1; }}
.filter-btn {{ padding: 8px 16px; background: #1e293b; border: 1px solid #334155; border-radius: 8px; color: #94a3b8; cursor: pointer; font-size: 0.85em; }}
.filter-btn:hover, .filter-btn.active {{ background: #334155; color: #e2e8f0; border-color: #6366f1; }}
.action-btn {{ padding: 8px 16px; background: #6366f1; border: none; border-radius: 8px; color: white; cursor: pointer; font-size: 0.85em; }}
.action-btn:hover {{ background: #5558e6; }}
.category-section {{ background: #1e293b; border-radius: 12px; margin: 10px 0; overflow: hidden; border: 1px solid #334155; }}
.category-header {{ display: flex; align-items: center; gap: 12px; padding: 15px 20px; cursor: pointer; user-select: none; }}
.category-header:hover {{ background: #253245; }}
.category-toggle {{ font-size: 1.2em; color: #6366f1; width: 20px; font-weight: bold; }}
.category-name {{ font-weight: 600; min-width: 120px; }}
.category-stats {{ display: flex; gap: 6px; }}
.category-bar {{ flex: 1; height: 8px; background: #334155; border-radius: 4px; min-width: 100px; overflow: hidden; }}
.category-bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s ease; }}
.category-rate {{ font-weight: bold; min-width: 50px; text-align: right; }}
.category-body {{ padding: 0 20px 15px; }}
.test-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 10px; border-radius: 8px; margin: 5px 0; }}
.test-row:hover {{ background: #334155; }}
.test-row.failed {{ border-left: 3px solid #ef4444; }}
.test-row.passed {{ border-left: 3px solid #22c55e; }}
.test-name {{ flex: 1; min-width: 200px; font-size: 0.9em; }}
.test-duration {{ color: #64748b; font-size: 0.85em; min-width: 60px; text-align: right; }}
.test-detail {{ width: 100%; font-size: 0.8em; color: #94a3b8; padding-left: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.how-to-fix {{ width: 100%; background: #172033; border-radius: 8px; padding: 12px 15px; margin-top: 8px; border-left: 3px solid #eab308; }}
.fix-title {{ color: #eab308; font-weight: 600; margin-bottom: 6px; font-size: 0.85em; }}
.fix-item {{ font-size: 0.8em; color: #94a3b8; margin: 3px 0; }}
.fix-quick {{ color: #22c55e; }}
.guide-box {{ width:100%; background:#0f1729; border:1px solid #334155; border-radius:10px; padding:16px; margin-top:10px; }}
.guide-title {{ font-size:1em; font-weight:700; color:#a5b4fc; margin-bottom:8px; }}
.guide-risk {{ font-size:0.85em; color:#fca5a5; margin-bottom:10px; padding:8px 12px; background:#7f1d1d30; border-radius:6px; }}
.guide-what,.guide-why {{ font-size:0.85em; color:#94a3b8; margin:4px 0; }}
.guide-steps {{ margin:10px 0; font-size:0.85em; color:#e2e8f0; }}
.guide-steps ol {{ padding-left:20px; margin:6px 0; }}
.guide-steps li {{ margin:4px 0; }}
.guide-code {{ display:flex; gap:10px; margin:10px 0; flex-wrap:wrap; }}
.guide-before,.guide-after {{ flex:1; min-width:200px; border-radius:8px; overflow:hidden; }}
.guide-before {{ background:#7f1d1d30; }}
.guide-after {{ background:#16653430; }}
.guide-label {{ font-size:0.7em; font-weight:700; padding:6px 10px; }}
.guide-before .guide-label {{ color:#fca5a5; background:#7f1d1d50; }}
.guide-after .guide-label {{ color:#86efac; background:#16653450; }}
.guide-code pre {{ padding:10px; font-size:0.8em; color:#e2e8f0; white-space:pre-wrap; word-break:break-word; margin:0; }}
.guide-warn {{ font-size:0.8em; color:#fbbf24; background:#78350f30; padding:8px 12px; border-radius:6px; margin-top:8px; border-left:3px solid #f59e0b; }}
.guide-tools {{ font-size:0.8em; color:#818cf8; margin-top:6px; }}
.badge {{ padding: 3px 10px; border-radius: 20px; font-size: 0.75em; font-weight: 600; white-space: nowrap; }}
.badge.passed {{ background: #166534; color: #86efac; }}
.badge.failed {{ background: #7f1d1d; color: #fca5a5; }}
.badge.priority-critical {{ background: #7f1d1d; color: #fca5a5; }}
.badge.priority-high {{ background: #78350f; color: #fde68a; }}
.badge.priority-medium {{ background: #1e3a5f; color: #93c5fd; }}
.badge.priority-low {{ background: #1e293b; color: #94a3b8; }}
.footer {{ text-align: center; padding: 30px; color: #475569; font-size: 0.85em; }}
@media (max-width: 768px) {{
@media (max-width: 768px) {{
    .container {{ padding: 10px; }}
    .header h1 {{ font-size: 1.8em; }}
    .summary {{ gap: 10px; }}
    .summary .stat {{ padding: 10px 15px; min-width: 80px; }}
    .summary .stat .value {{ font-size: 1.3em; }}
    .category-header {{ flex-wrap: wrap; padding: 12px 15px; }}
    .category-bar {{ min-width: 60px; }}
    .test-row {{ padding: 8px; }}
    .test-name {{ min-width: 150px; }}
    .toolbar {{ flex-direction: column; }}
    .search-box {{ width: 100%; }}
}}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>NAZAR</h1>
        <div class="subtitle">Otonom Test Raporu - {datetime.now().strftime('%d %B %Y %H:%M')}</div>
    </div>

    <div class="score-section">
        <div class="score-gauge">
            <svg width="140" height="140">
                <circle cx="70" cy="70" r="54" fill="none" stroke="#334155" stroke-width="10"/>
                <circle cx="70" cy="70" r="54" fill="none" stroke="{color}" stroke-width="10"
                    stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}"
                    stroke-linecap="round">
                    <animate attributeName="stroke-dashoffset" from="{circumference:.1f}" to="{offset:.1f}" dur="1.5s" fill="freeze" calcMode="spline" keySplines="0.4 0 0.2 1"/>
                </circle>
            </svg>
            <div class="grade">{grade}</div>
            <div class="rate">{pass_rate:.0f}%</div>
        </div>
        <div class="stars">{star_html}</div>
    </div>

    <div class="summary">
        <div class="stat">
            <div class="value">{total}</div>
            <div class="label">Toplam Test</div>
        </div>
        <div class="stat">
            <div class="value" style="color:#22c55e">{passed}</div>
            <div class="label">Passed</div>
        </div>
        <div class="stat">
            <div class="value" style="color:#ef4444">{failed}</div>
            <div class="label">Failed</div>
        </div>
        <div class="stat">
            <div class="value">{total_duration:.1f}s</div>
            <div class="label">Sure</div>
        </div>
    </div>

    <div class="toolbar">
        <input type="text" class="search-box" id="searchBox" placeholder="Test ara..." oninput="filterTests()">
        <button class="filter-btn active" onclick="setFilter('all', this)">Hepsi</button>
        <button class="filter-btn" onclick="setFilter('failed', this)">Sadece Failed</button>
        <button class="filter-btn" onclick="setFilter('passed', this)">Sadece Passed</button>
        <button class="action-btn" onclick="copyReport()">Kopyala</button>
        <button class="action-btn" onclick="window.print()">Yazdir</button>
    </div>

    {cat_cards}

    <div class="footer">
        Nazar v2.0.0 - Otonom Test Araci
    </div>
</div>

<script>
let currentFilter = 'all';

function toggleCategory(header) {{
    const body = header.nextElementSibling;
    const toggle = header.querySelector('.category-toggle');
    if (body.style.display === 'none') {{
        body.style.display = 'block';
        toggle.textContent = '-';
    }} else {{
        body.style.display = 'none';
        toggle.textContent = '+';
    }}
}}

function setFilter(filter, btn) {{
    currentFilter = filter;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    filterTests();
}}

function filterTests() {{
    const query = document.getElementById('searchBox').value.toLowerCase();
    document.querySelectorAll('.test-row').forEach(row => {{
        const name = row.dataset.name;
        const status = row.dataset.status;
        const matchQuery = !query || name.includes(query);
        const matchFilter = currentFilter === 'all' || status === currentFilter;
        row.style.display = (matchQuery && matchFilter) ? 'flex' : 'none';
    }});
}}

function copyReport() {{
    const text = `Nazar Raporu: {grade} ({pass_rate:.0f}%) - {passed}/{total} passed, {failed} failed`;
    navigator.clipboard.writeText(text);
    event.target.textContent = 'Kopyalandi!';
    setTimeout(() => event.target.textContent = 'Kopyala', 2000);
}}

// Baslangitta tum kategorileri kapat, failed olanlari ac
document.querySelectorAll('.category-section').forEach(sec => {{
    const failedCount = sec.querySelectorAll('.test-row.failed').length;
    if (failedCount > 0) {{
        const body = sec.querySelector('.category-body');
        const toggle = sec.querySelector('.category-toggle');
        body.style.display = 'block';
        toggle.textContent = '-';
    }}
}});
</script>
</body>
</html>"""

        Path(output_path).write_text(html)
