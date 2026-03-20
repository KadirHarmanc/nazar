"""Responsive Analyzer - Statik layout analizi (runtime gerektirmez).

Faz 5: Media query, viewport, touch target, flexbox/grid, responsive image analizi.
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

from nazar.runners.base import BaseRunner, IGNORE_DIRS

# Web/stil dosyalari icin uzantilar
WEB_EXTS = {".css", ".scss", ".less", ".html", ".htm", ".vue", ".svelte"}
# Kaynak + web birlesik
ALL_UI_EXTS = {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".css", ".scss", ".less", ".html", ".htm"}

# Yaygin responsive breakpoint'ler (px)
COMMON_BREAKPOINTS = {320, 375, 480, 576, 640, 768, 800, 834, 900, 960, 1024, 1080, 1200, 1280, 1366, 1440, 1536, 1920}

# Minimum tap target boyutu (px) - WCAG 2.5.5 / Apple HIG / Material Design
MIN_TAP_TARGET = 44


class ResponsiveAnalyzer(BaseRunner):
    """Statik responsive ve layout analizi."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self._web_file_cache: List[str] = []

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = {
            "fixed_dimensions": self._fixed_dimensions,
            "scroll_issues": self._scroll_issues,
            "responsive_patterns": self._responsive_patterns,
            "media_query_analysis": self._media_query_analysis,
            "viewport_meta": self._viewport_meta,
            "touch_target_size": self._touch_target_size,
            "flexbox_grid_usage": self._flexbox_grid_usage,
            "responsive_images": self._responsive_images,
        }
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    # ---- Yardimci: Web/stil dosyalarini tara ----
    def _web_files(self) -> List[str]:
        """CSS, SCSS, HTML gibi web dosyalarini topla."""
        if self._web_file_cache:
            return self._web_file_cache
        result = []
        for root_dir, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for f in files:
                if Path(f).suffix.lower() in WEB_EXTS:
                    result.append(os.path.relpath(os.path.join(root_dir, f), self.root))
        self._web_file_cache = result
        return result

    def _all_ui_files(self) -> List[str]:
        """Kaynak + web dosyalarini birlesik dondur (UI analizi icin)."""
        seen = set()
        result = []
        for f in self.src_files()[:300]:
            if Path(f).suffix.lower() in ALL_UI_EXTS and f not in seen:
                seen.add(f)
                result.append(f)
        for f in self._web_files()[:200]:
            if f not in seen:
                seen.add(f)
                result.append(f)
        return result

    def _should_skip(self, f: str) -> bool:
        """Test ve nazar dosyalarini atla."""
        return "test" in f.lower() or "spec" in f.lower() or f.startswith("nazar/")

    # ---- Mevcut kontroller ----

    def _fixed_dimensions(self, t: dict) -> Tuple[bool, str]:
        """Sabit pixel boyutlari (responsive degil)."""
        findings = []
        for f in self.src_files()[:200]:
            if self._should_skip(f):
                continue
            content = self.read(f)
            if not content:
                continue
            for m in re.finditer(r'width:\s*(\d{3,})', content):
                val = int(m.group(1))
                if val >= 300 and val not in (1024, 768):  # bilinen sabitler haric
                    line = content[:m.start()].count("\n") + 1
                    findings.append({"value": val, "file": f, "line": line})

        if not findings:
            return True, "Sabit boyut sorunu yok"
        first = findings[0]
        return False, "{} sabit genislik: width:{} ({}:{})".format(
            len(findings), first["value"], first["file"], first["line"])

    def _scroll_issues(self, t: dict) -> Tuple[bool, str]:
        """ScrollView icinde FlatList gibi sorunlar."""
        findings = []
        for f in self.src_files()[:200]:
            if self._should_skip(f):
                continue
            content = self.read(f)
            if not content:
                continue
            if re.search(r'<ScrollView[^>]*>[\s\S]{0,5000}<(?:FlatList|SectionList)', content):
                line = content.find("ScrollView")
                line_num = content[:line].count("\n") + 1 if line >= 0 else 1
                findings.append({"file": f, "line": line_num, "issue": "ScrollView icinde FlatList"})

        if not findings:
            return True, "Scroll sorunu yok"
        first = findings[0]
        return False, "{} scroll sorunu: {} ({}:{})".format(
            len(findings), first["issue"], first["file"], first["line"])

    def _responsive_patterns(self, t: dict) -> Tuple[bool, str]:
        """Responsive pattern kontrolu."""
        findings = []
        for f in self.src_files()[:200]:
            if self._should_skip(f):
                continue
            content = self.read(f)
            if not content:
                continue
            # Dimensions.get yerine useWindowDimensions
            if "Dimensions.get" in content and "useWindowDimensions" not in content:
                line = content.find("Dimensions.get")
                line_num = content[:line].count("\n") + 1 if line >= 0 else 1
                findings.append({"file": f, "line": line_num,
                                "issue": "Dimensions.get yerine useWindowDimensions oneriliyor"})
            # flexDirection row + flexWrap yok
            if re.search(r'flexDirection\s*:\s*["\']row["\']', content):
                if "flexWrap" not in content:
                    findings.append({"file": f, "line": 0,
                                    "issue": "flexDirection:row ama flexWrap yok"})

        if not findings:
            return True, "Responsive pattern'ler uygun"
        first = findings[0]
        return False, "{} responsive sorunu: {} ({}:{})".format(
            len(findings), first["issue"], first["file"], first["line"])

    # ---- Faz 5: Yeni kontroller ----

    def _media_query_analysis(self, t: dict) -> Tuple[bool, str]:
        """Media query analizi - breakpoint kullanimi ve kalitesi.

        Kontrol ettikleri:
        - Projede media query var mi
        - Breakpoint degerleri standart mi
        - min-width vs max-width yaklasimlari (mobile-first kontrol)
        - Yeterli breakpoint cesitliligi (mobil, tablet, desktop)
        """
        all_breakpoints = []
        files_with_mq = 0
        max_width_count = 0
        min_width_count = 0
        mq_files = []

        for f in self._all_ui_files():
            if self._should_skip(f):
                continue
            content = self.read(f)
            if not content:
                continue

            # CSS/SCSS media query: @media (min-width: 768px)
            css_mqs = re.findall(
                r'@media\s*[^{]*\(\s*(?:min|max)-width\s*:\s*(\d+)\s*px\s*\)',
                content, re.IGNORECASE
            )
            # JS/TS media query: matchMedia, useMediaQuery
            js_mqs = re.findall(
                r'(?:matchMedia|useMediaQuery)\s*\(\s*["\'][^"\']*(?:min|max)-width\s*:\s*(\d+)\s*px',
                content, re.IGNORECASE
            )
            # Styled-components / CSS-in-JS: @media
            styled_mqs = re.findall(
                r'[`"\']@media\s*[^`"\']*\(\s*(?:min|max)-width\s*:\s*(\d+)\s*px',
                content, re.IGNORECASE
            )

            found_bps = [int(v) for v in css_mqs + js_mqs + styled_mqs]
            if found_bps:
                files_with_mq += 1
                mq_files.append(f)
                all_breakpoints.extend(found_bps)

            # min-width vs max-width sayimi
            min_width_count += len(re.findall(r'min-width\s*:', content, re.IGNORECASE))
            max_width_count += len(re.findall(r'max-width\s*:', content, re.IGNORECASE))

        # Hic UI dosyasi yoksa SKIP
        if not self._all_ui_files():
            return True, "Web/UI dosyasi bulunamadi, media query analizi atlanıyor"

        issues = []

        # Hic media query yoksa
        if files_with_mq == 0:
            return False, "Projede hic media query (responsive breakpoint) bulunamadi - farkli ekran boyutlarina uyum saglanamaz"

        # Breakpoint cesitliligi kontrolu
        unique_bps = set(all_breakpoints)
        has_mobile = any(bp <= 480 for bp in unique_bps)
        has_tablet = any(600 <= bp <= 1024 for bp in unique_bps)
        has_desktop = any(bp >= 1200 for bp in unique_bps)

        coverage = sum([has_mobile, has_tablet, has_desktop])
        if coverage < 2:
            missing = []
            if not has_mobile:
                missing.append("mobil (<=480px)")
            if not has_tablet:
                missing.append("tablet (600-1024px)")
            if not has_desktop:
                missing.append("desktop (>=1200px)")
            issues.append("Eksik breakpoint araligi: {}".format(", ".join(missing)))

        # Standart olmayan breakpoint'ler
        non_standard = [bp for bp in unique_bps if bp not in COMMON_BREAKPOINTS]
        if non_standard and len(non_standard) > len(unique_bps) * 0.5:
            issues.append("{} standart disi breakpoint degeri".format(len(non_standard)))

        # Mobile-first kontrol (min-width tercih edilmeli)
        total_mq = min_width_count + max_width_count
        if total_mq > 3 and max_width_count > min_width_count * 2:
            issues.append("max-width agirlikli ({} max vs {} min) - mobile-first yaklasim (min-width) onerilir".format(
                max_width_count, min_width_count))

        if not issues:
            return True, "{} dosyada {} benzersiz breakpoint ile responsive yapilandirma uygun".format(
                files_with_mq, len(unique_bps))

        return False, "Media query sorunlari: {}".format("; ".join(issues))

    def _viewport_meta(self, t: dict) -> Tuple[bool, str]:
        """Viewport meta tag kontrolu.

        Kontrol ettikleri:
        - HTML dosyalarinda viewport meta tag var mi
        - width=device-width ayarli mi
        - initial-scale=1.0 ayarli mi
        - maximum-scale=1 veya user-scalable=no (erisilebilirlik sorunu)
        """
        html_files = []
        for f in self._web_files():
            if self._should_skip(f):
                continue
            if f.lower().endswith((".html", ".htm")):
                html_files.append(f)

        # Ayrica src_files'tan JSX/TSX'te Head/Helmet icinde viewport arayalim
        jsx_viewport_found = False
        for f in self.src_files()[:200]:
            if self._should_skip(f):
                continue
            content = self.read(f)
            if not content:
                continue
            # React Helmet veya Next.js Head'de viewport
            if re.search(r'<(?:Helmet|Head)[^>]*>[\s\S]{0,5000}viewport', content, re.IGNORECASE):
                jsx_viewport_found = True
                break
            # next.js metadata export
            if re.search(r'viewport\s*[:=]\s*["\']width=device-width', content, re.IGNORECASE):
                jsx_viewport_found = True
                break

        if not html_files and not jsx_viewport_found:
            # Framework tabanli proje olabilir (React Native, Flutter vs)
            # HTML olmayan projelerde bu kontrol uygulanmaz
            has_web_framework = False
            for f in self.src_files()[:50]:
                content = self.read(f)
                if content and re.search(r'import.*(?:react-dom|next|nuxt|angular|svelte|vue)', content, re.IGNORECASE):
                    has_web_framework = True
                    break

            if not has_web_framework:
                return True, "Web projesi degil, viewport kontrolu atlanıyor"

            if jsx_viewport_found:
                return True, "Viewport ayari framework uzerinden yapilmis"
            return False, "Web framework tespit edildi ama viewport meta tag bulunamadi"

        if jsx_viewport_found and not html_files:
            return True, "Viewport ayari framework (Helmet/Head) uzerinden tanimli"

        issues = []
        files_ok = 0
        files_missing = []
        a11y_issues = []

        for f in html_files:
            content = self.read(f)
            if not content:
                continue

            viewport_match = re.search(
                r'<meta\s+[^>]*name\s*=\s*["\']viewport["\'][^>]*content\s*=\s*["\']([^"\']+)["\']',
                content, re.IGNORECASE
            )
            if not viewport_match:
                # Farkli siralama: content once olabilir
                viewport_match = re.search(
                    r'<meta\s+[^>]*content\s*=\s*["\']([^"\']*device-width[^"\']*)["\'][^>]*name\s*=\s*["\']viewport["\']',
                    content, re.IGNORECASE
                )

            if not viewport_match:
                files_missing.append(f)
                continue

            vp_content = viewport_match.group(1)

            # width=device-width kontrolu
            if "width=device-width" not in vp_content:
                issues.append("{}: viewport'ta width=device-width eksik".format(f))

            # initial-scale kontrolu
            if "initial-scale" not in vp_content:
                issues.append("{}: initial-scale tanimli degil".format(f))

            # Erisilebilirlik: user-scalable=no veya maximum-scale=1
            if re.search(r'user-scalable\s*=\s*no', vp_content, re.IGNORECASE):
                a11y_issues.append("{}: user-scalable=no - kullanicilar yakinlastirma yapamaz (WCAG 1.4.4)".format(f))
            if re.search(r'maximum-scale\s*=\s*1(?:\.0)?(?:\s|,|$)', vp_content):
                a11y_issues.append("{}: maximum-scale=1 - zoom kisitli (WCAG 1.4.4)".format(f))

            if not issues and not a11y_issues:
                files_ok += 1

        all_issues = []
        if files_missing:
            all_issues.append("{} HTML dosyasinda viewport meta tag eksik: {}".format(
                len(files_missing), ", ".join(files_missing[:3])))
        all_issues.extend(issues[:3])
        all_issues.extend(a11y_issues[:2])

        if not all_issues:
            return True, "{} HTML dosyasinda viewport dogru yapilandirilmis".format(files_ok)

        return False, "Viewport sorunlari: {}".format("; ".join(all_issues))

    def _touch_target_size(self, t: dict) -> Tuple[bool, str]:
        """Dokunma hedefi boyut kontrolu (min 44x44px).

        WCAG 2.5.5 / Apple HIG / Material Design onerisine gore
        interaktif elementler en az 44x44 piksel olmali.
        """
        findings = []

        for f in self._all_ui_files():
            if self._should_skip(f):
                continue
            content = self.read(f)
            if not content:
                continue

            # CSS'te kucuk buton/link boyutlari
            # Pattern: width/height/min-width/min-height deger < 44px (interaktif elementlerde)
            small_targets = re.finditer(
                r'(?:(?:button|a|input|\.btn|\.tab|\.icon-btn|\.nav-link|\.clickable|\.touchable)[^{]*\{[^}]{0,2000}'
                r'(?:width|height|min-width|min-height)\s*:\s*(\d{1,2})px)',
                content, re.IGNORECASE
            )
            for m in small_targets:
                val = int(m.group(1))
                if val < MIN_TAP_TARGET and val > 0:
                    line = content[:m.start()].count("\n") + 1
                    findings.append({"file": f, "line": line, "size": val})

            # React Native: style icinde kucuk width/height (Touchable, Pressable, Button)
            rn_patterns = re.finditer(
                r'<(?:TouchableOpacity|TouchableHighlight|Pressable|Button)[^>]*'
                r'style\s*=\s*\{[^}]{0,2000}(?:width|height)\s*:\s*(\d{1,2})',
                content
            )
            for m in rn_patterns:
                val = int(m.group(1))
                if val < MIN_TAP_TARGET and val > 0:
                    line = content[:m.start()].count("\n") + 1
                    findings.append({"file": f, "line": line, "size": val})

            # Inline style: style="width:30px;height:30px" on interactive elements
            inline_patterns = re.finditer(
                r'<(?:button|a|input)\s[^>]*style\s*=\s*["\'][^"\']*'
                r'(?:width|height)\s*:\s*(\d{1,2})px',
                content, re.IGNORECASE
            )
            for m in inline_patterns:
                val = int(m.group(1))
                if val < MIN_TAP_TARGET and val > 0:
                    line = content[:m.start()].count("\n") + 1
                    findings.append({"file": f, "line": line, "size": val})

            # Tailwind CSS: w-6, h-8 gibi kucuk boyutlar (interaktif elementlerde)
            # w-10 = 40px, w-11 = 44px, yani w-10 ve alti sorunlu
            tw_patterns = re.finditer(
                r'<(?:button|a|Link)\s[^>]*class(?:Name)?\s*=\s*["\'][^"\']*'
                r'(?:^|\s)(?:w|h)-(\d{1,2})(?:\s|["\'])',
                content, re.IGNORECASE
            )
            for m in tw_patterns:
                tw_val = int(m.group(1))
                px_val = tw_val * 4  # Tailwind: w-N = N*4px
                if px_val < MIN_TAP_TARGET and px_val > 0:
                    line = content[:m.start()].count("\n") + 1
                    findings.append({"file": f, "line": line, "size": px_val})

        if not findings:
            return True, "Dokunma hedefi boyutlari uygun (min {}px)".format(MIN_TAP_TARGET)

        first = findings[0]
        return False, "{} kucuk dokunma hedefi: {}px < {}px min ({}:{})".format(
            len(findings), first["size"], MIN_TAP_TARGET, first["file"], first["line"])

    def _flexbox_grid_usage(self, t: dict) -> Tuple[bool, str]:
        """Flexbox/Grid kullanim analizi.

        Kontrol ettikleri:
        - Projede flexbox veya CSS Grid kullaniliyor mu
        - Float-tabanli layout (eski yaklasim) var mi
        - Sabit pozisyonlama (absolute px) yerine esnek layout tercih edilmis mi
        """
        flex_count = 0
        grid_count = 0
        float_count = 0
        absolute_layout_count = 0
        files_analyzed = 0

        for f in self._all_ui_files():
            if self._should_skip(f):
                continue
            content = self.read(f)
            if not content:
                continue
            files_analyzed += 1

            # Flexbox kullanimi
            flex_count += len(re.findall(r'display\s*:\s*flex', content, re.IGNORECASE))
            flex_count += len(re.findall(r'flexDirection\s*:', content))  # React Native
            flex_count += len(re.findall(r'(?:^|\s)(?:flex|inline-flex|items-center|justify-center|flex-row|flex-col)(?:\s|["\'])', content))  # Tailwind

            # CSS Grid kullanimi
            grid_count += len(re.findall(r'display\s*:\s*grid', content, re.IGNORECASE))
            grid_count += len(re.findall(r'grid-template-(?:columns|rows)\s*:', content, re.IGNORECASE))
            grid_count += len(re.findall(r'(?:^|\s)(?:grid-cols-|grid-rows-)', content))  # Tailwind

            # Float tabanli layout (eski yaklasim)
            float_count += len(re.findall(r'float\s*:\s*(?:left|right)', content, re.IGNORECASE))

            # Sabit absolute pozisyonlama (px ile)
            abs_matches = re.findall(
                r'position\s*:\s*absolute[^;]*;[^}]{0,2000}(?:left|top|right|bottom)\s*:\s*\d+px',
                content, re.IGNORECASE
            )
            absolute_layout_count += len(abs_matches)

        if files_analyzed == 0:
            return True, "UI dosyasi bulunamadi, layout analizi atlanıyor"

        issues = []
        responsive_score = flex_count + grid_count

        # Hic esnek layout yoksa
        if responsive_score == 0:
            issues.append("Projede flexbox veya CSS Grid kullanimi bulunamadi - responsive layout icin modern CSS oneriliyor")

        # Float agirlikli layout
        if float_count > 0 and float_count > responsive_score * 0.3:
            issues.append("{} float kullanimi tespit edildi - flexbox/grid'e gecis onerilir".format(float_count))

        # Cok fazla absolute pozisyonlama
        if absolute_layout_count > 5:
            issues.append("{} absolute pozisyonlama (px) - farkli ekran boyutlarinda bozulabilir".format(absolute_layout_count))

        if not issues:
            layout_info = []
            if flex_count:
                layout_info.append("flex:{}".format(flex_count))
            if grid_count:
                layout_info.append("grid:{}".format(grid_count))
            return True, "Esnek layout kullanimi uygun ({})".format(", ".join(layout_info) if layout_info else "tanimsiz")

        return False, "Layout sorunlari: {}".format("; ".join(issues))

    def _responsive_images(self, t: dict) -> Tuple[bool, str]:
        """Responsive gorsel (srcset, picture, responsive image) analizi.

        Kontrol ettikleri:
        - <img> etiketlerinde srcset kullaniliyor mu
        - <picture> elementi kullaniliyor mu
        - Sabit boyutlu gorseller var mi
        - Lazy loading kullaniliyor mu
        - next/image, gatsby-image gibi framework optimizasyonlari
        """
        img_total = 0
        img_with_srcset = 0
        picture_elements = 0
        framework_optimized = 0
        fixed_size_images = 0
        lazy_loading = 0
        files_with_images = []

        for f in self._all_ui_files():
            if self._should_skip(f):
                continue
            content = self.read(f)
            if not content:
                continue

            # <img> tag sayisi
            img_tags = re.findall(r'<img\s[^>]{0,2000}>', content, re.IGNORECASE)
            if not img_tags:
                # React: Image component (React Native)
                rn_images = re.findall(r'<Image\s[^>]*source\s*=', content)
                img_total += len(rn_images)
                if rn_images:
                    files_with_images.append(f)
                continue

            img_total += len(img_tags)
            files_with_images.append(f)

            for img in img_tags:
                # srcset kontrolu
                if re.search(r'srcset\s*=', img, re.IGNORECASE):
                    img_with_srcset += 1
                # sizes attribute
                # lazy loading
                if re.search(r'loading\s*=\s*["\']lazy["\']', img, re.IGNORECASE):
                    lazy_loading += 1
                # Sabit boyut (width="500" height="300" gibi buyuk px degerler)
                w_match = re.search(r'width\s*=\s*["\']?(\d+)', img, re.IGNORECASE)
                h_match = re.search(r'height\s*=\s*["\']?(\d+)', img, re.IGNORECASE)
                if w_match and int(w_match.group(1)) > 100:
                    if not re.search(r'srcset|sizes', img, re.IGNORECASE):
                        fixed_size_images += 1

            # <picture> elementi
            picture_elements += len(re.findall(r'<picture[\s>]', content, re.IGNORECASE))

            # Framework optimizasyonlari
            # next/image
            if re.search(r'import.*Image.*from\s+["\']next/image["\']', content):
                framework_optimized += 1
            # gatsby-image
            if re.search(r'import.*(?:GatsbyImage|StaticImage).*gatsby', content, re.IGNORECASE):
                framework_optimized += 1
            # nuxt-img
            if re.search(r'<(?:nuxt-img|NuxtImg)', content):
                framework_optimized += 1

        if img_total == 0:
            return True, "Gorsel elementi bulunamadi, responsive image kontrolu atlanıyor"

        issues = []

        # srcset kullanim orani
        non_optimized = img_total - img_with_srcset - framework_optimized - picture_elements
        if non_optimized > 0 and non_optimized > img_total * 0.5:
            issues.append("{}/{} gorsel srcset/picture olmadan kullaniliyor - farkli ekran yoğunluklari icin optimize degil".format(
                non_optimized, img_total))

        # Sabit boyutlu gorseller
        if fixed_size_images > 0:
            issues.append("{} gorsel sabit pixel boyutunda (srcset/sizes olmadan)".format(fixed_size_images))

        # Lazy loading eksikligi
        non_lazy = img_total - lazy_loading
        if non_lazy > 3 and lazy_loading == 0:
            issues.append("{} gorsel lazy loading kullanmiyor - sayfa yukleme performansini etkiler".format(non_lazy))

        if not issues:
            info = []
            if img_with_srcset:
                info.append("srcset:{}".format(img_with_srcset))
            if picture_elements:
                info.append("picture:{}".format(picture_elements))
            if framework_optimized:
                info.append("framework-optimized:{}".format(framework_optimized))
            if lazy_loading:
                info.append("lazy:{}".format(lazy_loading))
            return True, "{} gorsel responsive uyumlu ({})".format(
                img_total, ", ".join(info) if info else "uygun")

        return False, "Responsive gorsel sorunlari: {}".format("; ".join(issues))
