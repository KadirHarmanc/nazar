"""HTML Reporter - Test sonuclarini interaktif HTML raporuna donusturur."""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


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


def _severity_order(sev: str) -> int:
    """Severity siralama icin sayi dondurur (kucuk = daha ciddi)."""
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(sev, 5)


def _esc(text) -> str:
    """HTML escape."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


class HTMLReporter:
    """Nazar HTML interaktif rapor uretici.

    Tek bir self-contained HTML dosyasi uretir. Embedded CSS ve JS icerir,
    harici bagimliligi yoktur. Dark tema varsayilan, light tema toggle ile
    degistirilebilir. Mobil responsive, print destegi vardir.
    """

    def generate(
        self,
        results: List[Dict],
        plan: dict,
        output_path: str,
        previous_scan: Optional[Dict] = None,
    ):
        """Ana rapor uretim fonksiyonu.

        Args:
            results: Test sonuclari listesi.
            plan: Tarama plan bilgisi.
            output_path: Cikti dosya yolu.
            previous_scan: Onceki tarama verisi (karsilastirma icin).
        """
        total = len(results)
        passed = sum(1 for r in results if r.get("passed"))
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0
        total_duration = sum(r.get("duration", 0) for r in results)

        grade, stars, color = _letter_grade(pass_rate)

        # Severity dagilimi
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for r in results:
            if not r.get("passed"):
                sev = r.get("priority", r.get("severity", "medium")).lower()
                if sev in severity_counts:
                    severity_counts[sev] += 1

        # Kategorilere ayir
        categories: Dict[str, Dict] = {}
        for r in results:
            cat = r.get("type", r.get("category", "other"))
            if cat not in categories:
                categories[cat] = {"passed": 0, "failed": 0, "tests": []}
            if r.get("passed"):
                categories[cat]["passed"] += 1
            else:
                categories[cat]["failed"] += 1
            categories[cat]["tests"].append(r)

        # Karsilastirma verisi
        comparison = self._build_comparison(pass_rate, grade, previous_scan, results)

        # JSON veri blob (JS tarafinda kullanilacak)
        json_blob = self._build_json_blob(
            results, plan, pass_rate, grade, total, passed, failed,
            total_duration, severity_counts, categories, comparison,
        )

        # Test satirlari verisi (JS tarafinda render edilecek)
        test_rows_data = self._build_test_rows_data(results)

        # Kategori ozet verisi
        cat_summary_data = self._build_category_summary(categories)

        # SVG gauge parametreleri
        circumference = 2 * 3.14159265 * 54

        now_str = datetime.now().strftime("%d %B %Y, %H:%M")
        project_name = plan.get("project_name", plan.get("name", "Proje"))

        html = self._render_html(
            project_name=project_name,
            grade=grade,
            grade_color=color,
            stars=stars,
            pass_rate=pass_rate,
            total=total,
            passed=passed,
            failed=failed,
            total_duration=total_duration,
            severity_counts=severity_counts,
            circumference=circumference,
            now_str=now_str,
            cat_summary_data=cat_summary_data,
            test_rows_data=test_rows_data,
            comparison=comparison,
            json_blob=json_blob,
        )

        Path(output_path).write_text(html, encoding="utf-8")

    # ------------------------------------------------------------------
    # Veri hazirlama
    # ------------------------------------------------------------------

    def _build_comparison(
        self, pass_rate, grade, previous_scan, results
    ) -> Optional[Dict]:
        """Onceki tarama ile karsilastirma verisi olusturur."""
        if not previous_scan:
            return None
        prev_grade = previous_scan.get("grade", "?")
        prev_rate = previous_scan.get("pass_rate", 0)
        delta = pass_rate - prev_rate

        prev_failed_names: set = set()
        for r in previous_scan.get("results", previous_scan.get("findings", [])):
            if not r.get("passed"):
                prev_failed_names.add(r.get("name", ""))

        cur_failed_names: set = set()
        for r in results:
            if not r.get("passed"):
                cur_failed_names.add(r.get("name", ""))

        fixed = prev_failed_names - cur_failed_names
        new_issues = cur_failed_names - prev_failed_names

        return {
            "previous_grade": prev_grade,
            "previous_rate": round(prev_rate, 1),
            "current_grade": grade,
            "current_rate": round(pass_rate, 1),
            "delta": round(delta, 1),
            "fixed": len(fixed),
            "new_issues": len(new_issues),
            "fixed_list": sorted(fixed),
            "new_list": sorted(new_issues),
        }

    def _build_json_blob(
        self, results, plan, pass_rate, grade, total, passed, failed,
        total_duration, severity_counts, categories, comparison,
    ) -> str:
        """Rapor JSON verisini string olarak uretir."""
        blob = {
            "nazar_version": "4.0.0",
            "timestamp": datetime.now().isoformat(),
            "project": {
                "name": plan.get("project_name", plan.get("name", "")),
                "tech_stack": plan.get("tech_stack", ""),
            },
            "summary": {
                "grade": grade,
                "pass_rate": round(pass_rate, 1),
                "passed": passed,
                "failed": failed,
                "total": total,
                "duration_seconds": round(total_duration, 2),
                "by_severity": severity_counts,
            },
            "categories": [
                {
                    "name": cat,
                    "passed": d["passed"],
                    "failed": d["failed"],
                    "rate": round(
                        d["passed"] / (d["passed"] + d["failed"]) * 100, 1
                    ) if (d["passed"] + d["failed"]) > 0 else 0,
                }
                for cat, d in categories.items()
            ],
            "findings": [
                {
                    "name": r.get("name", ""),
                    "passed": r.get("passed", False),
                    "category": r.get("type", r.get("category", "other")),
                    "severity": r.get("priority", r.get("severity", "medium")),
                    "detail": r.get("detail", ""),
                    "file": r.get("file", ""),
                    "duration": r.get("duration", 0),
                }
                for r in results
            ],
        }
        if comparison:
            blob["comparison"] = comparison
        return json.dumps(blob, ensure_ascii=False, indent=2)

    def _build_test_rows_data(self, results: List[Dict]) -> str:
        """Test satirlari icin JSON verisi uretir."""
        rows = []
        for i, r in enumerate(results):
            row = {
                "id": i,
                "name": r.get("name", ""),
                "passed": r.get("passed", False),
                "category": r.get("type", r.get("category", "other")),
                "severity": r.get(
                    "priority", r.get("severity", "medium")
                ).lower(),
                "detail": r.get("detail", ""),
                "file": r.get("file", ""),
                "duration": r.get("duration", 0),
                "guide": None,
                "how_to_fix": None,
            }
            if r.get("guide") and not r.get("passed"):
                g = r["guide"]
                row["guide"] = {
                    "title": g.get("title", ""),
                    "risk": g.get("risk", ""),
                    "what": g.get("what", ""),
                    "why": g.get("why", ""),
                    "steps": g.get("steps", []),
                    "before": g.get("before", ""),
                    "after": g.get("after", ""),
                    "warning": g.get("warning", ""),
                    "tools": g.get("tools", []),
                }
            elif r.get("how_to_fix") and not r.get("passed"):
                row["how_to_fix"] = r["how_to_fix"]
            rows.append(row)
        return json.dumps(rows, ensure_ascii=False)

    def _build_category_summary(self, categories: Dict) -> str:
        """Kategori ozet verisi icin JSON uretir."""
        summary = []
        for cat, d in categories.items():
            cat_total = d["passed"] + d["failed"]
            rate = (
                round(d["passed"] / cat_total * 100, 1) if cat_total > 0 else 0
            )
            summary.append({
                "name": cat,
                "passed": d["passed"],
                "failed": d["failed"],
                "total": cat_total,
                "rate": rate,
            })
        summary.sort(key=lambda x: x["rate"])
        return json.dumps(summary, ensure_ascii=False)

    # ------------------------------------------------------------------
    # HTML render
    # ------------------------------------------------------------------

    def _render_html(
        self, *, project_name, grade, grade_color, stars, pass_rate,
        total, passed, failed, total_duration, severity_counts,
        circumference, now_str, cat_summary_data, test_rows_data,
        comparison, json_blob,
    ) -> str:
        """Tam HTML ciktisini uretir."""
        offset = circumference - (pass_rate / 100) * circumference

        # Star SVG'leri
        star_parts = []
        for i in range(5):
            cls = "active" if i < stars else ""
            star_parts.append(
                '<svg class="star-icon {c}" viewBox="0 0 24 24" width="22" '
                'height="22"><polygon points="12,2 15.09,8.26 22,9.27 '
                '17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 '
                '8.91,8.26"/></svg>'.format(c=cls)
            )
        star_html = "".join(star_parts)

        # Karsilastirma bolumu
        comp_section = self._render_comparison_section(
            comparison, grade, grade_color, pass_rate
        )

        sev = severity_counts
        esc_name = _esc(project_name)

        return _HTML_TEMPLATE.format(
            esc_name=esc_name,
            now_str=now_str,
            total_duration=total_duration,
            total=total,
            grade=grade,
            grade_color=grade_color,
            passed=passed,
            failed=failed,
            pass_rate=pass_rate,
            circumference=circumference,
            offset=offset,
            star_html=star_html,
            sev_critical=sev["critical"],
            sev_high=sev["high"],
            sev_medium=sev["medium"],
            sev_low=sev["low"],
            comp_section=comp_section,
            test_rows_data=test_rows_data,
            cat_summary_data=cat_summary_data,
            json_blob=json_blob,
        )

    def _render_comparison_section(
        self, comparison, grade, grade_color, pass_rate
    ) -> str:
        """Karsilastirma bolumunun HTML'ini uretir."""
        if not comparison:
            return ""

        delta_sign = "+" if comparison["delta"] >= 0 else ""
        delta_color = "#22c55e" if comparison["delta"] >= 0 else "#ef4444"
        arrow_cls = "arrow-up" if comparison["delta"] >= 0 else "arrow-down"

        fixed_items_parts = []
        for fn in comparison.get("fixed_list", [])[:10]:
            fixed_items_parts.append(
                '<div class="comp-item comp-fixed">'
                + _esc(fn) + '</div>'
            )
        fixed_items = "".join(fixed_items_parts)

        new_items_parts = []
        for nn in comparison.get("new_list", [])[:10]:
            new_items_parts.append(
                '<div class="comp-item comp-new">'
                + _esc(nn) + '</div>'
            )
        new_items = "".join(new_items_parts)

        return (
            '<div class="comparison-section" id="comparisonSection">'
            '<div class="section-title">'
            '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" '
            'stroke="currentColor" stroke-width="2">'
            '<path d="M18 15l-6-6-6 6"/></svg>'
            'Karsilastirma (Onceki Tarama)'
            '</div>'
            '<div class="comp-grid">'
            '<div class="comp-card">'
            '<div class="comp-label">Onceki</div>'
            '<div class="comp-grade">{prev_grade}</div>'
            '<div class="comp-rate">{prev_rate}%</div>'
            '</div>'
            '<div class="comp-card comp-arrow">'
            '<div class="comp-delta" style="color:{delta_color}">'
            '<svg class="{arrow_cls}" viewBox="0 0 24 24" width="32" '
            'height="32" fill="none" stroke="{delta_color}" '
            'stroke-width="2.5">'
            '<path d="M12 19V5M5 12l7-7 7 7"/></svg>'
            '{delta_sign}{delta}%'
            '</div>'
            '</div>'
            '<div class="comp-card">'
            '<div class="comp-label">Simdi</div>'
            '<div class="comp-grade comp-current">{cur_grade}</div>'
            '<div class="comp-rate">{cur_rate:.1f}%</div>'
            '</div>'
            '</div>'
            '<div class="comp-stats">'
            '<div class="comp-stat comp-stat-fixed">'
            '<span class="comp-stat-num">{fixed_count}</span>'
            '<span class="comp-stat-label">Duzeltildi</span>'
            '</div>'
            '<div class="comp-stat comp-stat-new">'
            '<span class="comp-stat-num">{new_count}</span>'
            '<span class="comp-stat-label">Yeni Sorun</span>'
            '</div>'
            '</div>'
            '<div class="comp-details">{fixed_items}{new_items}</div>'
            '</div>'
        ).format(
            prev_grade=_esc(comparison["previous_grade"]),
            prev_rate=comparison["previous_rate"],
            delta_color=delta_color,
            arrow_cls=arrow_cls,
            delta_sign=delta_sign,
            delta=comparison["delta"],
            cur_grade=_esc(grade),
            cur_rate=pass_rate,
            fixed_count=comparison["fixed"],
            new_count=comparison["new_issues"],
            fixed_items=fixed_items,
            new_items=new_items,
        )


# ======================================================================
# HTML Template
# ======================================================================
# Python f-string icinde {{ ve }} kullanarak literal brace escape edilir.
# Placeholder'lar .format() ile doldurulur.

_HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="tr" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Nazar - {esc_name} Raporu</title>
<style>
/* ============================================================
   NAZAR HTML REPORTER v4.0 - Self-contained, dark-first
   ============================================================ */
*,*::before,*::after {{ margin:0; padding:0; box-sizing:border-box; }}

:root {{
  --bg-primary: #0b0f1a;
  --bg-secondary: #111827;
  --bg-card: #1a2234;
  --bg-card-hover: #1f2b42;
  --bg-input: #1e293b;
  --border: #1e3050;
  --border-hover: #2d4a7a;
  --text-primary: #e8edf5;
  --text-secondary: #8b97b0;
  --text-muted: #5a6580;
  --accent: #6366f1;
  --accent-hover: #818cf8;
  --accent-muted: #6366f130;
  --success: #22c55e;
  --success-bg: #16653420;
  --danger: #ef4444;
  --danger-bg: #7f1d1d20;
  --warning: #eab308;
  --warning-bg: #78350f20;
  --info: #3b82f6;
  --info-bg: #1e3a5f30;
  --shadow: 0 4px 24px rgba(0,0,0,0.3);
  --radius: 12px;
  --radius-sm: 8px;
  --radius-xs: 6px;
  --transition: 0.2s ease;
}}
[data-theme="light"] {{
  --bg-primary: #f1f5f9;
  --bg-secondary: #ffffff;
  --bg-card: #ffffff;
  --bg-card-hover: #f8fafc;
  --bg-input: #f1f5f9;
  --border: #e2e8f0;
  --border-hover: #cbd5e1;
  --text-primary: #1e293b;
  --text-secondary: #64748b;
  --text-muted: #94a3b8;
  --accent: #6366f1;
  --accent-hover: #4f46e5;
  --accent-muted: #6366f115;
  --success: #16a34a;
  --success-bg: #dcfce7;
  --danger: #dc2626;
  --danger-bg: #fee2e2;
  --warning: #ca8a04;
  --warning-bg: #fef9c3;
  --info: #2563eb;
  --info-bg: #dbeafe;
  --shadow: 0 4px 24px rgba(0,0,0,0.08);
}}
html {{ scroll-behavior:smooth; }}
body {{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
  background:var(--bg-primary); color:var(--text-primary);
  line-height:1.6; min-height:100vh;
}}
.page-wrapper {{ max-width:1440px; margin:0 auto; padding:16px; }}

/* --- Header --- */
.header {{
  display:flex; align-items:center; justify-content:space-between;
  padding:20px 24px; background:var(--bg-secondary);
  border:1px solid var(--border); border-radius:var(--radius);
  margin-bottom:16px; flex-wrap:wrap; gap:16px;
}}
.header-left {{ display:flex; align-items:center; gap:16px; }}
.header-logo {{ font-size:2.2em; line-height:1; }}
.header-info h1 {{ font-size:1.4em; font-weight:700; letter-spacing:-0.02em; }}
.header-info .header-meta {{
  font-size:0.82em; color:var(--text-secondary);
  display:flex; gap:16px; flex-wrap:wrap; margin-top:2px;
}}
.header-right {{ display:flex; align-items:center; gap:16px; }}
.grade-badge {{
  font-size:2em; font-weight:800; padding:8px 20px;
  border-radius:var(--radius); line-height:1; letter-spacing:-0.03em;
}}
.theme-toggle {{
  width:40px; height:40px; border-radius:50%;
  border:1px solid var(--border); background:var(--bg-card);
  color:var(--text-secondary); cursor:pointer;
  display:flex; align-items:center; justify-content:center;
  transition:var(--transition);
}}
.theme-toggle:hover {{ border-color:var(--accent); color:var(--accent); }}
.theme-toggle svg {{ width:20px; height:20px; }}

/* --- Filter Tabs --- */
.filter-bar {{
  display:flex; gap:8px; padding:12px 16px;
  background:var(--bg-secondary); border:1px solid var(--border);
  border-radius:var(--radius); margin-bottom:16px;
  flex-wrap:wrap; align-items:center;
}}
.filter-tab {{
  padding:7px 16px; border-radius:20px; border:1px solid var(--border);
  background:transparent; color:var(--text-secondary);
  font-size:0.82em; font-weight:500; cursor:pointer;
  transition:var(--transition); white-space:nowrap;
}}
.filter-tab:hover {{ border-color:var(--accent); color:var(--text-primary); }}
.filter-tab.active {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.filter-tab .tab-count {{
  display:inline-block; margin-left:6px; padding:1px 7px;
  border-radius:10px; font-size:0.85em; background:rgba(255,255,255,0.15);
}}
.filter-tab.active .tab-count {{ background:rgba(255,255,255,0.25); }}
.filter-sep {{ width:1px; height:24px; background:var(--border); margin:0 4px; }}

/* --- Main Grid (left + right panels) --- */
.main-grid {{
  display:grid; grid-template-columns:320px 1fr;
  gap:16px; align-items:start;
}}

/* --- Left Panel --- */
.left-panel {{
  display:flex; flex-direction:column; gap:16px;
  position:sticky; top:16px;
}}
.gauge-card {{
  background:var(--bg-secondary); border:1px solid var(--border);
  border-radius:var(--radius); padding:24px; text-align:center;
}}
.gauge-wrap {{ position:relative; width:160px; height:160px; margin:0 auto 12px; }}
.gauge-wrap svg {{ transform:rotate(-90deg); }}
.gauge-bg {{ fill:none; stroke:var(--border); stroke-width:10; }}
.gauge-fill {{
  fill:none; stroke-width:10; stroke-linecap:round;
  transition:stroke-dashoffset 1.5s cubic-bezier(0.4,0,0.2,1);
}}
.gauge-center {{
  position:absolute; top:50%; left:50%;
  transform:translate(-50%,-50%); text-align:center;
}}
.gauge-grade {{ font-size:2.4em; font-weight:800; line-height:1; letter-spacing:-0.03em; }}
.gauge-rate {{ font-size:0.9em; color:var(--text-secondary); margin-top:2px; }}
.gauge-stars {{ display:flex; justify-content:center; gap:4px; margin-top:8px; }}
.star-icon {{ fill:var(--border); stroke:none; transition:var(--transition); }}
.star-icon.active {{ fill:var(--warning); }}

.stats-row {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }}
.stat-card {{
  background:var(--bg-secondary); border:1px solid var(--border);
  border-radius:var(--radius); padding:14px 12px; text-align:center;
}}
.stat-value {{ font-size:1.5em; font-weight:700; line-height:1.2; }}
.stat-label {{ font-size:0.75em; color:var(--text-secondary); margin-top:2px; }}

.category-card {{
  background:var(--bg-secondary); border:1px solid var(--border);
  border-radius:var(--radius); padding:16px;
}}
.section-label {{
  font-size:0.72em; font-weight:600; text-transform:uppercase;
  letter-spacing:0.08em; color:var(--text-muted); margin-bottom:10px;
}}
.cat-item {{
  display:flex; align-items:center; gap:10px; padding:8px 10px;
  border-radius:var(--radius-xs); cursor:pointer;
  transition:var(--transition); margin-bottom:4px;
}}
.cat-item:hover {{ background:var(--bg-card-hover); }}
.cat-item.active {{ background:var(--accent-muted); border:1px solid var(--accent); }}
.cat-name {{ flex:1; font-size:0.85em; font-weight:500; text-transform:capitalize; }}
.cat-bar-wrap {{
  flex:1; height:6px; background:var(--border);
  border-radius:3px; overflow:hidden; min-width:50px;
}}
.cat-bar-fill {{
  height:100%; border-radius:3px;
  transition:width 0.8s cubic-bezier(0.4,0,0.2,1);
}}
.cat-rate {{ font-size:0.8em; font-weight:600; min-width:36px; text-align:right; }}

.severity-card {{
  background:var(--bg-secondary); border:1px solid var(--border);
  border-radius:var(--radius); padding:16px;
}}
.sev-item {{ display:flex; align-items:center; gap:10px; padding:6px 0; }}
.sev-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
.sev-name {{ flex:1; font-size:0.82em; text-transform:capitalize; }}
.sev-count {{
  font-size:0.85em; font-weight:700; min-width:28px; text-align:center;
  padding:2px 8px; border-radius:10px;
}}

/* --- Right Panel --- */
.right-panel {{ display:flex; flex-direction:column; gap:16px; }}
.toolbar {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }}
.search-wrap {{ position:relative; flex:1; min-width:200px; }}
.search-wrap svg {{
  position:absolute; left:12px; top:50%; transform:translateY(-50%);
  color:var(--text-muted); pointer-events:none;
}}
.search-box {{
  width:100%; padding:10px 14px 10px 38px;
  background:var(--bg-input); border:1px solid var(--border);
  border-radius:var(--radius-sm); color:var(--text-primary);
  font-size:0.88em; outline:none; transition:var(--transition);
}}
.search-box:focus {{ border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-muted); }}
.sort-select {{
  padding:10px 14px; background:var(--bg-input);
  border:1px solid var(--border); border-radius:var(--radius-sm);
  color:var(--text-primary); font-size:0.85em; cursor:pointer; outline:none;
}}
.action-btn {{
  padding:10px 16px; background:var(--bg-card);
  border:1px solid var(--border); border-radius:var(--radius-sm);
  color:var(--text-secondary); font-size:0.82em; cursor:pointer;
  transition:var(--transition); display:flex; align-items:center;
  gap:6px; white-space:nowrap;
}}
.action-btn:hover {{ border-color:var(--accent); color:var(--accent); }}

/* Results Table */
.results-container {{
  background:var(--bg-secondary); border:1px solid var(--border);
  border-radius:var(--radius); overflow:hidden;
}}
.results-header {{
  display:grid; grid-template-columns:40px 1fr 90px 80px 70px;
  gap:8px; padding:10px 16px; background:var(--bg-card);
  border-bottom:1px solid var(--border); font-size:0.72em;
  font-weight:600; text-transform:uppercase; letter-spacing:0.06em;
  color:var(--text-muted); align-items:center;
}}
.results-header span {{ cursor:pointer; user-select:none; }}
.results-header span:hover {{ color:var(--text-primary); }}
.results-body {{ max-height:70vh; overflow-y:auto; }}
.results-body::-webkit-scrollbar {{ width:6px; }}
.results-body::-webkit-scrollbar-track {{ background:transparent; }}
.results-body::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:3px; }}

.test-row {{ border-bottom:1px solid var(--border); transition:var(--transition); }}
.test-row:last-child {{ border-bottom:none; }}
.test-row-main {{
  display:grid; grid-template-columns:40px 1fr 90px 80px 70px;
  gap:8px; padding:12px 16px; align-items:center;
  cursor:pointer; transition:var(--transition);
}}
.test-row-main:hover {{ background:var(--bg-card-hover); }}
.test-row.expanded .test-row-main {{ background:var(--bg-card); }}

.test-status {{
  width:28px; height:28px; border-radius:50%;
  display:flex; align-items:center; justify-content:center; flex-shrink:0;
}}
.test-status.pass {{ background:var(--success-bg); color:var(--success); }}
.test-status.fail {{ background:var(--danger-bg); color:var(--danger); }}
.test-status svg {{ width:14px; height:14px; }}

.test-info {{ min-width:0; }}
.test-name-text {{
  font-size:0.88em; font-weight:500;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}}
.test-file {{
  font-size:0.75em; color:var(--text-muted);
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin-top:1px;
}}

.sev-badge {{
  padding:3px 10px; border-radius:12px; font-size:0.72em;
  font-weight:600; text-transform:uppercase; text-align:center; white-space:nowrap;
}}
.sev-badge.critical {{ background:#7f1d1d; color:#fca5a5; }}
.sev-badge.high {{ background:#78350f; color:#fde68a; }}
.sev-badge.medium {{ background:#1e3a5f; color:#93c5fd; }}
.sev-badge.low {{ background:#1e293b; color:#94a3b8; }}
.sev-badge.info {{ background:#1e293b; color:#94a3b8; }}
[data-theme="light"] .sev-badge.critical {{ background:#fee2e2; color:#dc2626; }}
[data-theme="light"] .sev-badge.high {{ background:#fef3c7; color:#b45309; }}
[data-theme="light"] .sev-badge.medium {{ background:#dbeafe; color:#2563eb; }}
[data-theme="light"] .sev-badge.low {{ background:#f1f5f9; color:#64748b; }}
[data-theme="light"] .sev-badge.info {{ background:#f1f5f9; color:#64748b; }}

.cat-badge {{
  font-size:0.72em; color:var(--text-secondary); text-transform:capitalize;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
}}
.test-dur {{ font-size:0.78em; color:var(--text-muted); text-align:right; }}

/* Expandable detail */
.test-detail-panel {{
  display:none; padding:0 16px 16px 56px;
  animation:slideDown 0.2s ease;
}}
.test-row.expanded .test-detail-panel {{ display:block; }}
@keyframes slideDown {{
  from {{ opacity:0; transform:translateY(-8px); }}
  to {{ opacity:1; transform:translateY(0); }}
}}
.detail-text {{
  font-size:0.82em; color:var(--text-secondary);
  margin-bottom:12px; line-height:1.5;
}}

/* Guide box */
.guide-box {{
  background:var(--bg-primary); border:1px solid var(--border);
  border-radius:var(--radius-sm); padding:16px; margin-top:8px;
}}
.guide-title {{ font-size:0.95em; font-weight:700; color:var(--accent-hover); margin-bottom:8px; }}
.guide-risk {{
  font-size:0.82em; color:#fca5a5; padding:6px 10px;
  background:var(--danger-bg); border-radius:var(--radius-xs);
  margin-bottom:10px; display:inline-block;
}}
.guide-text {{ font-size:0.82em; color:var(--text-secondary); margin:4px 0; }}
.guide-text b {{ color:var(--text-primary); }}
.guide-steps-list {{
  padding-left:20px; margin:8px 0; font-size:0.82em; color:var(--text-primary);
}}
.guide-steps-list li {{ margin:4px 0; }}
.guide-code-grid {{
  display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:10px;
}}
.guide-code-block {{ border-radius:var(--radius-xs); overflow:hidden; }}
.guide-code-block.before {{ background:var(--danger-bg); }}
.guide-code-block.after {{ background:var(--success-bg); }}
.guide-code-label {{
  font-size:0.7em; font-weight:700; padding:5px 10px;
  text-transform:uppercase; letter-spacing:0.05em;
}}
.guide-code-block.before .guide-code-label {{ color:var(--danger); background:#7f1d1d30; }}
.guide-code-block.after .guide-code-label {{ color:var(--success); background:#16653430; }}
.guide-code-block pre {{
  padding:10px; font-size:0.78em;
  font-family:'SF Mono',Menlo,Monaco,Consolas,monospace;
  color:var(--text-primary); white-space:pre-wrap;
  word-break:break-word; margin:0; line-height:1.5;
}}
.guide-warn {{
  font-size:0.78em; color:var(--warning); background:var(--warning-bg);
  padding:8px 12px; border-radius:var(--radius-xs); margin-top:8px;
  border-left:3px solid var(--warning);
}}
.guide-tools {{ font-size:0.78em; color:var(--accent-hover); margin-top:6px; }}

/* How to fix */
.fix-box {{
  background:var(--bg-primary); border:1px solid var(--border);
  border-left:3px solid var(--warning); border-radius:var(--radius-sm);
  padding:14px; margin-top:8px;
}}
.fix-title {{ color:var(--warning); font-weight:600; font-size:0.85em; margin-bottom:6px; }}
.fix-item {{ font-size:0.8em; color:var(--text-secondary); margin:3px 0; }}
.fix-item b {{ color:var(--text-primary); }}
.fix-quick {{ color:var(--success); }}

/* Empty state */
.empty-state {{ text-align:center; padding:48px 24px; color:var(--text-muted); }}
.empty-state svg {{ margin-bottom:12px; opacity:0.3; }}

/* --- Comparison Section --- */
.comparison-section {{
  background:var(--bg-secondary); border:1px solid var(--border);
  border-radius:var(--radius); padding:20px;
}}
.section-title {{
  font-size:0.95em; font-weight:600; margin-bottom:16px;
  display:flex; align-items:center; gap:8px;
}}
.comp-grid {{
  display:grid; grid-template-columns:1fr auto 1fr;
  gap:16px; align-items:center; margin-bottom:16px;
}}
.comp-card {{
  text-align:center; padding:16px;
  background:var(--bg-card); border-radius:var(--radius-sm);
}}
.comp-card.comp-arrow {{ background:transparent; padding:8px; }}
.comp-label {{
  font-size:0.72em; color:var(--text-muted);
  text-transform:uppercase; letter-spacing:0.06em; margin-bottom:4px;
}}
.comp-grade {{ font-size:2em; font-weight:800; color:var(--text-secondary); }}
.comp-grade.comp-current {{ color:var(--text-primary); }}
.comp-rate {{ font-size:0.85em; color:var(--text-secondary); }}
.comp-delta {{
  font-size:1.2em; font-weight:700;
  display:flex; flex-direction:column; align-items:center; gap:4px;
}}
.arrow-down {{ transform:rotate(180deg); }}
.comp-stats {{
  display:flex; gap:12px; justify-content:center; margin-bottom:12px;
}}
.comp-stat {{
  display:flex; align-items:center; gap:8px;
  padding:8px 16px; border-radius:var(--radius-xs);
}}
.comp-stat-fixed {{ background:var(--success-bg); }}
.comp-stat-new {{ background:var(--danger-bg); }}
.comp-stat-num {{ font-size:1.1em; font-weight:700; }}
.comp-stat-fixed .comp-stat-num {{ color:var(--success); }}
.comp-stat-new .comp-stat-num {{ color:var(--danger); }}
.comp-stat-label {{ font-size:0.8em; color:var(--text-secondary); }}
.comp-details {{ display:flex; flex-wrap:wrap; gap:6px; }}
.comp-item {{ font-size:0.75em; padding:3px 10px; border-radius:12px; }}
.comp-fixed {{ background:var(--success-bg); color:var(--success); }}
.comp-new {{ background:var(--danger-bg); color:var(--danger); }}

/* --- Footer --- */
.footer {{
  text-align:center; padding:24px; color:var(--text-muted);
  font-size:0.8em; margin-top:16px;
}}

/* --- Toast --- */
.toast {{
  position:fixed; bottom:24px; right:24px;
  padding:12px 20px; background:var(--accent); color:#fff;
  border-radius:var(--radius-sm); font-size:0.85em; z-index:1000;
  opacity:0; transform:translateY(10px);
  transition:all 0.3s ease; pointer-events:none;
}}
.toast.show {{ opacity:1; transform:translateY(0); }}

/* --- Responsive --- */
@media (max-width:900px) {{
  .main-grid {{ grid-template-columns:1fr; }}
  .left-panel {{
    position:static; display:grid;
    grid-template-columns:1fr 1fr; gap:12px;
  }}
  .gauge-card {{ grid-column:1 / -1; }}
  .header {{ flex-direction:column; text-align:center; }}
  .header-right {{ justify-content:center; }}
  .guide-code-grid {{ grid-template-columns:1fr; }}
  .comp-grid {{ grid-template-columns:1fr; gap:8px; }}
  .comp-card.comp-arrow {{ order:-1; }}
}}
@media (max-width:600px) {{
  .page-wrapper {{ padding:8px; }}
  .left-panel {{ grid-template-columns:1fr; }}
  .header {{ padding:14px; }}
  .header-info h1 {{ font-size:1.1em; }}
  .grade-badge {{ font-size:1.5em; padding:6px 14px; }}
  .filter-bar {{ gap:6px; padding:10px 12px; }}
  .filter-tab {{ padding:5px 10px; font-size:0.75em; }}
  .results-header {{ grid-template-columns:32px 1fr 70px 60px; }}
  .results-header .col-cat {{ display:none; }}
  .test-row-main {{ grid-template-columns:32px 1fr 70px 60px; }}
  .test-row-main .cat-badge {{ display:none; }}
  .toolbar {{ flex-direction:column; }}
  .search-wrap {{ min-width:100%; }}
  .stats-row {{ grid-template-columns:1fr 1fr; }}
}}
@media print {{
  body {{ background:#fff; color:#000; }}
  .theme-toggle,.action-btn,.filter-bar,.search-wrap,.sort-select {{ display:none !important; }}
  .left-panel {{ position:static; }}
  .results-body {{ max-height:none; overflow:visible; }}
  .main-grid {{ grid-template-columns:260px 1fr; }}
}}
::-webkit-scrollbar {{ width:8px; height:8px; }}
::-webkit-scrollbar-track {{ background:transparent; }}
::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:4px; }}
::-webkit-scrollbar-thumb:hover {{ background:var(--border-hover); }}
</style>
</head>
<body>

<div class="page-wrapper">

  <!-- HEADER -->
  <header class="header">
    <div class="header-left">
      <div class="header-logo">&#128065;&#65039;</div>
      <div class="header-info">
        <h1>NAZAR - {esc_name}</h1>
        <div class="header-meta">
          <span>{now_str}</span>
          <span>Tarama: {total_duration:.1f}s</span>
          <span>{total} test</span>
        </div>
      </div>
    </div>
    <div class="header-right">
      <div class="grade-badge" style="background:{grade_color}20;color:{grade_color};border:2px solid {grade_color}">{grade}</div>
      <button class="theme-toggle" onclick="toggleTheme()" title="Tema Degistir" aria-label="Tema degistir">
        <svg id="themeIcon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
      </button>
    </div>
  </header>

  <!-- FILTER TABS -->
  <div class="filter-bar">
    <button class="filter-tab active" data-filter="all" onclick="setFilterTab(this)">
      Hepsi <span class="tab-count">{total}</span>
    </button>
    <button class="filter-tab" data-filter="failed" onclick="setFilterTab(this)">
      Basarisiz <span class="tab-count">{failed}</span>
    </button>
    <button class="filter-tab" data-filter="passed" onclick="setFilterTab(this)">
      Basarili <span class="tab-count">{passed}</span>
    </button>
    <div class="filter-sep"></div>
    <span id="categoryTabs"></span>
  </div>

  <!-- MAIN GRID -->
  <div class="main-grid">

    <!-- LEFT PANEL -->
    <aside class="left-panel">
      <div class="gauge-card">
        <div class="gauge-wrap">
          <svg width="160" height="160" viewBox="0 0 160 160">
            <circle class="gauge-bg" cx="80" cy="80" r="54"/>
            <circle class="gauge-fill" cx="80" cy="80" r="54"
              stroke="{grade_color}"
              stroke-dasharray="{circumference:.2f}"
              stroke-dashoffset="{circumference:.2f}"
              id="gaugeCircle"/>
          </svg>
          <div class="gauge-center">
            <div class="gauge-grade" style="color:{grade_color}">{grade}</div>
            <div class="gauge-rate">{pass_rate:.0f}%</div>
          </div>
        </div>
        <div class="gauge-stars">{star_html}</div>
      </div>

      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-value" style="color:var(--success)">{passed}</div>
          <div class="stat-label">Basarili</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:var(--danger)">{failed}</div>
          <div class="stat-label">Basarisiz</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{total}</div>
          <div class="stat-label">Toplam</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{total_duration:.1f}s</div>
          <div class="stat-label">Sure</div>
        </div>
      </div>

      <div class="category-card">
        <div class="section-label">Kategoriler</div>
        <div id="categoryList"></div>
      </div>

      <div class="severity-card">
        <div class="section-label">Ciddiyet Dagilimi</div>
        <div class="sev-item">
          <div class="sev-dot" style="background:#ef4444"></div>
          <div class="sev-name">Critical</div>
          <div class="sev-count" style="color:#fca5a5;background:#7f1d1d30">{sev_critical}</div>
        </div>
        <div class="sev-item">
          <div class="sev-dot" style="background:#f97316"></div>
          <div class="sev-name">High</div>
          <div class="sev-count" style="color:#fdba74;background:#78350f30">{sev_high}</div>
        </div>
        <div class="sev-item">
          <div class="sev-dot" style="background:#3b82f6"></div>
          <div class="sev-name">Medium</div>
          <div class="sev-count" style="color:#93c5fd;background:#1e3a5f30">{sev_medium}</div>
        </div>
        <div class="sev-item">
          <div class="sev-dot" style="background:#64748b"></div>
          <div class="sev-name">Low</div>
          <div class="sev-count" style="color:#94a3b8;background:#334155">{sev_low}</div>
        </div>
      </div>
    </aside>

    <!-- RIGHT PANEL -->
    <main class="right-panel">
      <div class="toolbar">
        <div class="search-wrap">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
          </svg>
          <input type="text" class="search-box" id="searchBox"
            placeholder="Test adi veya dosya ara..." oninput="applyFilters()">
        </div>
        <select class="sort-select" id="sortSelect" onchange="applySort()">
          <option value="default">Siralama: Varsayilan</option>
          <option value="severity">Ciddiyet</option>
          <option value="category">Kategori</option>
          <option value="name">Isim (A-Z)</option>
          <option value="duration">Sure</option>
          <option value="status">Durum</option>
        </select>
        <button class="action-btn" onclick="copyJSON()" title="JSON kopyala">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
          JSON Kopyala
        </button>
        <button class="action-btn" onclick="window.print()" title="Yazdir">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 6 2 18 2 18 9"/>
            <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
            <rect x="6" y="14" width="12" height="8"/>
          </svg>
          Yazdir
        </button>
      </div>

      <div class="results-container">
        <div class="results-header">
          <span></span>
          <span onclick="setSortHeader('name')">Test</span>
          <span onclick="setSortHeader('severity')">Ciddiyet</span>
          <span class="col-cat" onclick="setSortHeader('category')">Kategori</span>
          <span onclick="setSortHeader('duration')">Sure</span>
        </div>
        <div class="results-body" id="resultsBody"></div>
      </div>

      {comp_section}
    </main>

  </div>

  <footer class="footer">Nazar v4.0.0 - Otonom Kod Analiz Araci</footer>
</div>

<div class="toast" id="toast"></div>

<script>
/* =================================================================
   NAZAR REPORT - Interactive Logic
   All data is embedded, no external dependencies.
   XSS protection: all user-facing text is escaped via esc() which
   uses DOM createTextNode for safe HTML entity encoding.
   ================================================================= */

var TEST_DATA = {test_rows_data};
var CAT_DATA = {cat_summary_data};
var REPORT_JSON = {json_blob};

var currentFilter = 'all';
var currentCategoryFilter = null;
var currentSort = 'default';
var expandedRows = {{}};

document.addEventListener('DOMContentLoaded', function() {{
  renderCategoryList();
  renderCategoryTabs();
  renderResults();
  animateGauge();
}});

function animateGauge() {{
  var circle = document.getElementById('gaugeCircle');
  if (!circle) return;
  var target = {offset:.2f};
  requestAnimationFrame(function() {{
    circle.style.strokeDashoffset = target;
  }});
}}

/* ---- Theme Toggle ---- */
function toggleTheme() {{
  var html = document.documentElement;
  var icon = document.getElementById('themeIcon');
  if (html.getAttribute('data-theme') === 'dark') {{
    html.setAttribute('data-theme', 'light');
    icon.textContent = '';
    var sun = '<circle cx="12" cy="12" r="5"/>'
      + '<line x1="12" y1="1" x2="12" y2="3"/>'
      + '<line x1="12" y1="21" x2="12" y2="23"/>'
      + '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>'
      + '<line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>'
      + '<line x1="1" y1="12" x2="3" y2="12"/>'
      + '<line x1="21" y1="12" x2="23" y2="12"/>'
      + '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>'
      + '<line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
    icon.insertAdjacentHTML('beforeend', sun);
  }} else {{
    html.setAttribute('data-theme', 'dark');
    icon.textContent = '';
    icon.insertAdjacentHTML('beforeend',
      '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>');
  }}
}}

/* ---- Category Rendering ---- */
function renderCategoryList() {{
  var container = document.getElementById('categoryList');
  var parts = [];
  for (var i = 0; i < CAT_DATA.length; i++) {{
    var cat = CAT_DATA[i];
    var barColor = cat.rate >= 80 ? 'var(--success)' : cat.rate >= 50 ? 'var(--warning)' : 'var(--danger)';
    parts.push(
      '<div class="cat-item" data-cat="' + esc(cat.name) + '"'
      + ' onclick="filterByCategory(this,\\'' + esc(cat.name) + '\\')">'
      + '<span class="cat-name">' + esc(cat.name) + '</span>'
      + '<div class="cat-bar-wrap"><div class="cat-bar-fill" style="width:'
      + cat.rate + '%;background:' + barColor + '"></div></div>'
      + '<span class="cat-rate" style="color:' + barColor + '">'
      + cat.rate + '%</span></div>'
    );
  }}
  container.textContent = '';
  container.insertAdjacentHTML('beforeend', parts.join(''));
}}

function renderCategoryTabs() {{
  var container = document.getElementById('categoryTabs');
  var parts = [];
  for (var i = 0; i < CAT_DATA.length; i++) {{
    var cat = CAT_DATA[i];
    parts.push(
      '<button class="filter-tab" data-filter="cat:' + esc(cat.name) + '"'
      + ' onclick="setCategoryTab(this,\\'' + esc(cat.name) + '\\')">'
      + capitalize(cat.name) + ' <span class="tab-count">' + cat.total
      + '</span></button>'
    );
  }}
  container.textContent = '';
  container.insertAdjacentHTML('beforeend', parts.join(''));
}}

/* ---- Filters ---- */
function setFilterTab(btn) {{
  var tabs = document.querySelectorAll('.filter-tab');
  for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
  btn.classList.add('active');
  currentFilter = btn.getAttribute('data-filter');
  currentCategoryFilter = null;
  var catItems = document.querySelectorAll('.cat-item');
  for (var i = 0; i < catItems.length; i++) catItems[i].classList.remove('active');
  applyFilters();
}}

function setCategoryTab(btn, catName) {{
  var tabs = document.querySelectorAll('.filter-tab');
  for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
  btn.classList.add('active');
  currentFilter = 'all';
  currentCategoryFilter = catName;
  var catItems = document.querySelectorAll('.cat-item');
  for (var i = 0; i < catItems.length; i++) {{
    catItems[i].classList.toggle('active', catItems[i].getAttribute('data-cat') === catName);
  }}
  applyFilters();
}}

function filterByCategory(el, catName) {{
  var wasActive = el.classList.contains('active');
  var catItems = document.querySelectorAll('.cat-item');
  for (var i = 0; i < catItems.length; i++) catItems[i].classList.remove('active');
  var tabs = document.querySelectorAll('.filter-tab');
  for (var i = 0; i < tabs.length; i++) tabs[i].classList.remove('active');
  if (wasActive) {{
    currentCategoryFilter = null;
    var allTab = document.querySelector('.filter-tab[data-filter="all"]');
    if (allTab) allTab.classList.add('active');
  }} else {{
    el.classList.add('active');
    currentCategoryFilter = catName;
    var matchTab = document.querySelector('.filter-tab[data-filter="cat:' + catName + '"]');
    if (matchTab) matchTab.classList.add('active');
  }}
  applyFilters();
}}

function applyFilters() {{ renderResults(); }}

function applySort() {{
  currentSort = document.getElementById('sortSelect').value;
  renderResults();
}}

function setSortHeader(field) {{
  document.getElementById('sortSelect').value = field;
  currentSort = field;
  renderResults();
}}

function getFilteredData() {{
  var query = (document.getElementById('searchBox').value || '').toLowerCase();
  var data = TEST_DATA.slice();
  if (currentFilter === 'passed') {{
    data = data.filter(function(r) {{ return r.passed; }});
  }} else if (currentFilter === 'failed') {{
    data = data.filter(function(r) {{ return !r.passed; }});
  }}
  if (currentCategoryFilter) {{
    data = data.filter(function(r) {{ return r.category === currentCategoryFilter; }});
  }}
  if (query) {{
    data = data.filter(function(r) {{
      return r.name.toLowerCase().indexOf(query) !== -1
        || (r.file && r.file.toLowerCase().indexOf(query) !== -1)
        || r.category.toLowerCase().indexOf(query) !== -1;
    }});
  }}
  var sevOrder = {{'critical':0,'high':1,'medium':2,'low':3,'info':4}};
  switch (currentSort) {{
    case 'severity':
      data.sort(function(a,b) {{ return (sevOrder[a.severity]||5) - (sevOrder[b.severity]||5); }}); break;
    case 'category':
      data.sort(function(a,b) {{ return a.category.localeCompare(b.category); }}); break;
    case 'name':
      data.sort(function(a,b) {{ return a.name.localeCompare(b.name); }}); break;
    case 'duration':
      data.sort(function(a,b) {{ return b.duration - a.duration; }}); break;
    case 'status':
      data.sort(function(a,b) {{ return (a.passed?1:0) - (b.passed?1:0); }}); break;
  }}
  return data;
}}

/* ---- Render Results ---- */
function renderResults() {{
  var data = getFilteredData();
  var body = document.getElementById('resultsBody');
  if (data.length === 0) {{
    body.textContent = '';
    body.insertAdjacentHTML('beforeend',
      '<div class="empty-state">'
      + '<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">'
      + '<circle cx="12" cy="12" r="10"/><path d="M8 15s1.5 2 4 2 4-2 4-2"/>'
      + '<line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/>'
      + '</svg><div>Sonuc bulunamadi.</div></div>');
    return;
  }}
  var parts = [];
  for (var idx = 0; idx < data.length; idx++) {{
    var r = data[idx];
    var isExpanded = expandedRows[r.id] === true;
    var expandedClass = isExpanded ? ' expanded' : '';
    var statusClass = r.passed ? 'pass' : 'fail';
    var statusIcon = r.passed
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
    var h = '<div class="test-row' + expandedClass + '" data-id="' + r.id + '">';
    h += '<div class="test-row-main" onclick="toggleRow(' + r.id + ')">';
    h += '<div class="test-status ' + statusClass + '">' + statusIcon + '</div>';
    h += '<div class="test-info"><div class="test-name-text">' + esc(r.name) + '</div>';
    if (r.file) h += '<div class="test-file">' + esc(r.file) + '</div>';
    h += '</div>';
    h += '<span class="sev-badge ' + esc(r.severity) + '">' + esc(r.severity) + '</span>';
    h += '<span class="cat-badge">' + esc(r.category) + '</span>';
    h += '<span class="test-dur">' + (r.duration || 0).toFixed(2) + 's</span>';
    h += '</div>';
    h += '<div class="test-detail-panel">';
    if (r.detail) {{
      h += '<div class="detail-text">' + esc(r.detail) + '</div>';
    }}
    if (r.guide) {{
      var g = r.guide;
      var stepsH = '';
      if (g.steps && g.steps.length) {{
        stepsH = '<ol class="guide-steps-list">';
        for (var si = 0; si < g.steps.length; si++) {{
          stepsH += '<li>' + esc(g.steps[si]) + '</li>';
        }}
        stepsH += '</ol>';
      }}
      var codeH = '';
      if (g.before || g.after) {{
        codeH = '<div class="guide-code-grid">';
        if (g.before) {{
          codeH += '<div class="guide-code-block before"><div class="guide-code-label">ONCE (yanlis)</div><pre>' + esc(g.before) + '</pre></div>';
        }}
        if (g.after) {{
          codeH += '<div class="guide-code-block after"><div class="guide-code-label">SONRA (dogru)</div><pre>' + esc(g.after) + '</pre></div>';
        }}
        codeH += '</div>';
      }}
      var warnH = g.warning ? '<div class="guide-warn">' + esc(g.warning) + '</div>' : '';
      var toolsH = (g.tools && g.tools.length) ? '<div class="guide-tools">Onerilen: ' + g.tools.map(esc).join(', ') + '</div>' : '';
      h += '<div class="guide-box">';
      h += '<div class="guide-title">' + esc(g.title) + '</div>';
      if (g.risk) h += '<div class="guide-risk">' + esc(g.risk) + '</div>';
      if (g.what) h += '<div class="guide-text"><b>Ne Oluyor:</b> ' + esc(g.what) + '</div>';
      if (g.why) h += '<div class="guide-text"><b>Neden Onemli:</b> ' + esc(g.why) + '</div>';
      if (stepsH) h += '<div class="guide-text"><b>Adim Adim:</b></div>' + stepsH;
      h += codeH + warnH + toolsH + '</div>';
    }}
    if (r.how_to_fix) {{
      var f = r.how_to_fix;
      h += '<div class="fix-box"><div class="fix-title">Nasil Duzeltilir?</div>';
      if (f.sorun) h += '<div class="fix-item"><b>SORUN:</b> ' + esc(f.sorun) + '</div>';
      if (f.cozum) h += '<div class="fix-item"><b>COZUM:</b> ' + esc(f.cozum) + '</div>';
      if (f.quick_fix) h += '<div class="fix-item fix-quick"><b>QUICK FIX:</b> ' + esc(f.quick_fix) + '</div>';
      h += '</div>';
    }}
    h += '</div></div>';
    parts.push(h);
  }}
  body.textContent = '';
  body.insertAdjacentHTML('beforeend', parts.join(''));
}}

/* ---- Row Expand/Collapse ---- */
function toggleRow(id) {{
  if (expandedRows[id]) {{
    delete expandedRows[id];
  }} else {{
    expandedRows[id] = true;
  }}
  var row = document.querySelector('.test-row[data-id="' + id + '"]');
  if (row) {{
    row.classList.toggle('expanded');
    var panel = row.querySelector('.test-detail-panel');
    if (panel) {{
      panel.style.display = row.classList.contains('expanded') ? 'block' : 'none';
    }}
  }}
}}

/* ---- Copy JSON ---- */
function copyJSON() {{
  var text = JSON.stringify(REPORT_JSON, null, 2);
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(text).then(function() {{
      showToast('JSON panoya kopyalandi!');
    }});
  }} else {{
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('JSON panoya kopyalandi!');
  }}
}}

/* ---- Toast ---- */
function showToast(msg) {{
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function() {{ t.classList.remove('show'); }}, 2500);
}}

/* ---- Utility ---- */
function esc(str) {{
  if (!str) return '';
  var d = document.createElement('div');
  d.appendChild(document.createTextNode(String(str)));
  return d.innerHTML;
}}
function capitalize(s) {{
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}}
</script>
</body>
</html>'''
