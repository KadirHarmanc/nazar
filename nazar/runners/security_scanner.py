"""Deep Security Scanner - Kapsamli guvenlik taramasi."""
import os
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple

from nazar.runners.base import BaseRunner


# Severity helper
def _fmt(hits, msg="bulundu"):
    """Format hit results."""
    if not hits:
        return True, "Temiz"
    first = hits[0]
    return False, f"{len(hits)} {msg}: {first['file']}:{first['line']}"


class DeepSecurityScanner(BaseRunner):
    """Production-grade guvenlik tarayici. Basit gorunup buyuk sorunlara yol acan her seyi yakalar."""

    # ================================================================
    # 1. SENSITIVE DATA EXPOSURE
    # ================================================================

    def check_hardcoded_credentials(self, t: dict) -> Tuple[bool, str]:
        """Config dosyalarinda ve kaynak kodda hardcoded credential tespiti."""
        patterns = [
            # Direct assignment patterns - BREAK STRINGS to avoid self-detection
            r"""(?:passw""" + r"""ord|passwd|pwd)\s*[:=]\s*['"][^'"]{4,}['"]""",
            r"""(?:secre""" + r"""t|SECRET)\s*[:=]\s*['"][^'"]{6,}['"]""",
            r"""(?:api[_-]?key|API""" + r"""_KEY)\s*[:=]\s*['"][A-Za-z0-9_\-]{12,}['"]""",
            r"""(?:auth[_-]?token|AUTH""" + r"""_TOKEN)\s*[:=]\s*['"][^'"]{10,}['"]""",
            r"""(?:access[_-]?key|ACCESS""" + r"""_KEY)\s*[:=]\s*['"][^'"]{10,}['"]""",
        ]
        all_hits = []
        for p in patterns:
            all_hits.extend(self.scan_pattern(p, limit=150))
        return _fmt(all_hits, "hardcoded credential")

    def check_tokens_in_urls(self, t: dict) -> Tuple[bool, str]:
        """URL'lerde token/key parametresi - log'lara sizabilir."""
        hits = self.scan_pattern(
            r"""(?:https?://[^\s'"]*[?&](?:token|key|secret|api_key|access_token|auth)=[^\s&'"]+)"""
        )
        return _fmt(hits, "URL'de token")

    def check_sensitive_data_in_logs(self, t: dict) -> Tuple[bool, str]:
        """Log statement'larda hassas veri loglama tespiti."""
        patterns = [
            r"""(?:console\.log|print)\s*\([^)]*(?:passw""" + r"""ord|token|secret|key|credential)[^)]*\)""",
            r"""(?:logger?\.\w+)\s*\([^)]*(?:passw""" + r"""ord|token|secret|key)[^)]*\)""",
        ]
        all_hits = []
        for p in patterns:
            all_hits.extend(self.scan_pattern(p, limit=100))
        return _fmt(all_hits, "log'da hassas veri")

    def check_sensitive_data_in_errors(self, t: dict) -> Tuple[bool, str]:
        """Hata mesajlarinda hassas bilgi sizintisi."""
        hits = self.scan_pattern(
            r"""(?:res\.(?:status|json|send)\s*\([^)]*(?:stack|trace|internal|sql|query))|(?:throw\s+new\s+Error\s*\([^)]*(?:database|connection|credential))"""
        )
        return _fmt(hits, "hata mesajinda bilgi sizintisi")

    def check_pii_exposure(self, t: dict) -> Tuple[bool, str]:
        """Kisisel veri (PII) client-side'da acikta."""
        hits = self.scan_pattern(
            r"""(?:email|phone|ssn|social_security|birth_?date|credit_?card|card_?number)\s*[:=]"""
        )
        # Sadece client-side dosyalarda kontrol et
        client_hits = [h for h in hits if any(ext in h["file"] for ext in [".tsx", ".jsx", ".ts", ".js"]) and "server" not in h["file"].lower() and "api" not in h["file"].lower()]
        return _fmt(client_hits, "client-side PII exposure")

    def check_source_maps_in_prod(self, t: dict) -> Tuple[bool, str]:
        """Production'da source map dosyalari - kaynak kod ifsa olur."""
        source_maps = []
        for rd, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "vendor", "venv", ".venv"}]
            for f in files:
                if f.endswith(".map") and ("dist" in rd or "build" in rd or "public" in rd):
                    source_maps.append(os.path.relpath(os.path.join(rd, f), self.root))
        if source_maps:
            return False, f"{len(source_maps)} source map: {source_maps[0]}"
        return True, "Temiz"

    # ================================================================
    # 2. AUTHENTICATION & SESSION SECURITY
    # ================================================================

    def check_jwt_no_expiry(self, t: dict) -> Tuple[bool, str]:
        """JWT token olusturmada expiry kontrolu eksik."""
        # JWT sign eden ama expiresIn/exp vermeyen kodlar
        jwt_signs = self.scan_pattern(r"""(?:jwt|jsonwebtoken)\.sign\s*\(""")
        jwt_with_exp = self.scan_pattern(r"""(?:jwt|jsonwebtoken)\.sign\s*\([^)]*(?:expiresIn|exp)""")
        missing = len(jwt_signs) - len(jwt_with_exp)
        if missing > 0:
            return False, f"{missing} JWT token expiry'siz olusturuluyor"
        return True, "Temiz"

    def check_jwt_weak_secret(self, t: dict) -> Tuple[bool, str]:
        """JWT icin zayif veya hardcoded secret."""
        hits = self.scan_pattern(
            r"""(?:jwt|jsonwebtoken)\.(?:sign|verify)\s*\([^)]*['"][a-zA-Z0-9]{1,20}['"]"""
        )
        return _fmt(hits, "zayif/hardcoded JWT secret")

    def check_missing_auth_middleware(self, t: dict) -> Tuple[bool, str]:
        """API route'larinda auth middleware eksik."""
        # Express/Fastify/NestJS route'lari
        routes = self.scan_pattern(r"""(?:app|router)\.\s*(?:get|post|put|delete|patch)\s*\(\s*['"]""")
        auth_routes = self.scan_pattern(r"""(?:auth|authenticate|protect|guard|middleware|requireAuth|isAuth)""")
        if len(routes) > 5 and len(auth_routes) == 0:
            return False, f"{len(routes)} route var ama auth middleware bulunamadi"
        return True, f"{len(routes)} route, {len(auth_routes)} auth referansi"

    def check_insecure_session_storage(self, t: dict) -> Tuple[bool, str]:
        """Hassas veriyi AsyncStorage/localStorage'da saklama."""
        patterns = [
            r"""(?:localStorage|sessionStorage|AsyncStorage)\.(?:setItem|set)\s*\([^)]*(?:token|secret|passw""" + r"""ord|key|credential|session)""",
        ]
        all_hits = []
        for p in patterns:
            all_hits.extend(self.scan_pattern(p, limit=100))
        return _fmt(all_hits, "insecure storage'da hassas veri")

    def check_missing_csrf(self, t: dict) -> Tuple[bool, str]:
        """Form submit'lerde CSRF korumasi eksik."""
        forms = self.scan_pattern(r"""<form[^>]*method\s*=\s*['"]post['"]""")
        csrf = self.scan_pattern(r"""(?:csrf|_token|csrfmiddlewaretoken|__RequestVerificationToken)""")
        if len(forms) > 0 and len(csrf) == 0:
            return False, f"{len(forms)} POST form var ama CSRF token yok"
        return True, "Temiz"

    def check_weak_password_policy(self, t: dict) -> Tuple[bool, str]:
        """Zayif sifre politikasi - minimum uzunluk/karmasiklik yok."""
        # Sifre validasyonu ariyoruz
        pw_valid = self.scan_pattern(r"""(?:password|pwd).*(?:length|min|regex|pattern|validate|strong)""")
        pw_fields = self.scan_pattern(r"""(?:type\s*=\s*['"]password['"]|password.*input|input.*password)""")
        if len(pw_fields) > 0 and len(pw_valid) == 0:
            return False, f"{len(pw_fields)} sifre alani var ama validasyon bulunamadi"
        return True, "Temiz"

    # ================================================================
    # 3. INJECTION & INPUT VALIDATION
    # ================================================================

    def check_xss_vectors(self, t: dict) -> Tuple[bool, str]:
        """XSS aciklari - innerHTML, dangerouslySetInnerHTML, v-html."""
        patterns = [
            r"""dangerous""" + r"""lySetInnerHTML\s*=\s*\{""",
            r"""\.innerHTML\s*=\s*(?!['"]<)""",
            r"""v-html\s*=\s*['"]""",
            r"""document\.write\s*\(""",
            r"""\$\s*\(\s*['"].*\+.*['"]""",  # jQuery DOM injection
        ]
        all_hits = []
        for p in patterns:
            all_hits.extend(self.scan_pattern(p, limit=100))
        return _fmt(all_hits, "XSS riski")

    def check_nosql_injection(self, t: dict) -> Tuple[bool, str]:
        """NoSQL injection riski - MongoDB $where, $regex vb."""
        hits = self.scan_pattern(
            r"""(?:\$where|\$regex|\$gt|\$lt|\$ne|\$nin)\s*:\s*(?:req\.|request\.|params\.|body\.|query\.)"""
        )
        return _fmt(hits, "NoSQL injection riski")

    def check_template_injection(self, t: dict) -> Tuple[bool, str]:
        """Template injection riski - kullanici girdisi template'e direkt."""
        hits = self.scan_pattern(
            r"""(?:render_template_string|Template\(|Jinja2\(|nunjucks\.render)\s*\([^)]*(?:req\.|request\.|params\.|body\.)"""
        )
        return _fmt(hits, "template injection riski")

    def check_regex_dos(self, t: dict) -> Tuple[bool, str]:
        """ReDoS riski - nested quantifier'lar ile regex."""
        hits = self.scan_pattern(
            r"""(?:new RegExp|re\.compile)\s*\([^)]*(?:\+\+|\*\+|\?\+|\{\d+,\}\+|\(\?:.*\)\*)"""
        )
        return _fmt(hits, "ReDoS riski")

    def check_unvalidated_redirects(self, t: dict) -> Tuple[bool, str]:
        """Dogrulanmamis redirect - open redirect acigi."""
        hits = self.scan_pattern(
            r"""(?:res\.redirect|redirect|window\.location|location\.href)\s*(?:=|\()\s*(?:req\.|request\.|params\.|query\.|body\.|searchParams)"""
        )
        return _fmt(hits, "open redirect riski")

    def check_file_upload_no_validation(self, t: dict) -> Tuple[bool, str]:
        """Dosya yukleme - tip/boyut validasyonu yok."""
        upload = self.scan_pattern(r"""(?:multer|formidable|busboy|upload|file.*input|type\s*=\s*['"]file)""")
        validation = self.scan_pattern(r"""(?:mime|mimetype|content-type|file.*type|allowedTypes|accept|fileFilter|max.*size|limit.*size)""")
        if len(upload) > 2 and len(validation) == 0:
            return False, f"{len(upload)} dosya yukleme noktasi ama tip/boyut validasyonu yok"
        return True, "Temiz"

    # ================================================================
    # 4. ACCESS CONTROL & AUTHORIZATION
    # ================================================================

    def check_idor_risk(self, t: dict) -> Tuple[bool, str]:
        """IDOR riski - kullanici ID'si ile direkt erisim."""
        hits = self.scan_pattern(
            r"""(?:params\.|req\.params\.|query\.)(?:id|userId|user_id|orderId|accountId)\b"""
        )
        auth_checks = self.scan_pattern(
            r"""(?:req\.user\.id|session\.user|currentUser|auth\.uid)\s*(?:===?|!==?|==)\s*(?:params|req\.params)"""
        )
        unchecked = len(hits) - len(auth_checks)
        if unchecked > 3:
            return False, f"{unchecked} IDOR riski - parametre ID'si yetki kontrolu olmadan kullaniliyor"
        return True, "Temiz"

    def check_horizontal_privilege(self, t: dict) -> Tuple[bool, str]:
        """Yatay yetki yukseltme - baska kullanicinin verisine erisim."""
        # Supabase RLS kontrol
        rls_enabled = self.scan_pattern(r"""(?:ALTER TABLE.*ENABLE ROW LEVEL SECURITY|CREATE POLICY)""", skip_test=False, skip_env=False)
        tables = self.scan_pattern(r"""CREATE TABLE\s+(?:public\.)?(\w+)""", skip_test=False, skip_env=False)
        if len(tables) > 0 and len(rls_enabled) == 0:
            return False, f"{len(tables)} tablo var ama RLS (Row Level Security) bulunamadi"
        return True, f"{len(rls_enabled)} RLS policy aktif"

    def check_admin_routes_exposed(self, t: dict) -> Tuple[bool, str]:
        """Admin route'lari korumasiz erisime acik."""
        admin_routes = self.scan_pattern(r"""['"](?:/admin|/dashboard/admin|/api/admin|/management)['"]""")
        admin_auth = self.scan_pattern(r"""(?:isAdmin|requireAdmin|adminOnly|role.*admin|admin.*middleware|adminGuard)""")
        if len(admin_routes) > 0 and len(admin_auth) == 0:
            return False, f"{len(admin_routes)} admin route ama admin yetki kontrolu yok"
        return True, "Temiz"

    def check_mass_assignment(self, t: dict) -> Tuple[bool, str]:
        """Mass assignment - request body direkt DB'ye yaziliyor."""
        hits = self.scan_pattern(
            r"""(?:\.create|\.update|\.insert|\.upsert)\s*\(\s*(?:req\.body|body|request\.body|data)\s*\)"""
        )
        return _fmt(hits, "mass assignment riski - body direkt DB'ye")

    # ================================================================
    # 5. SECURITY MISCONFIGURATION
    # ================================================================

    def check_debug_in_production(self, t: dict) -> Tuple[bool, str]:
        """Debug modu production'da acik."""
        patterns = [
            r"""DEBUG\s*[:=]\s*(?:True|true|1|'true'|"true")""",
            r"""(?:app|server)\.debug\s*=\s*(?:True|true)""",
            r"""devtools\s*:\s*true""",
            r"""enableDevTools\s*[:=]\s*true""",
            r"""__DEV__\s*&&""",  # RN dev check (bilgi amacli)
        ]
        all_hits = []
        for p in patterns:
            all_hits.extend(self.scan_pattern(p, limit=50))
        return _fmt(all_hits, "debug modu acik")

    def check_default_credentials(self, t: dict) -> Tuple[bool, str]:
        """Default/ornek credential'lar birakilmis."""
        patterns = [
            r"""(?:admin|root|test|demo|example|default)[:@](?:admin|root|test|1234|passw""" + r"""ord|12345|qwerty)""",
            r"""(?:user(?:name)?|login)\s*[:=]\s*['"](?:admin|root|test|demo|guest)['"]""",
        ]
        all_hits = []
        for p in patterns:
            all_hits.extend(self.scan_pattern(p, limit=50))
        return _fmt(all_hits, "default credential")

    def check_missing_security_headers(self, t: dict) -> Tuple[bool, str]:
        """Eksik guvenlik header'lari (HSTS, CSP, X-Frame-Options vb.)."""
        # Framework config veya middleware'de header ayarlari ariyoruz
        headers_set = self.scan_pattern(
            r"""(?:helmet|Strict-Transport-Security|Content-Security-Policy|X-Frame-Options|X-Content-Type-Options|X-XSS-Protection|Referrer-Policy)"""
        )
        server_files = self.scan_pattern(r"""(?:app\.listen|createServer|express\(\)|fastify\(\)|new Hono)""")
        if len(server_files) > 0 and len(headers_set) == 0:
            return False, "Web server var ama guvenlik header'lari (helmet/CSP/HSTS) ayarlanmamis"
        return True, "Temiz"

    def check_cors_misconfiguration(self, t: dict) -> Tuple[bool, str]:
        """CORS yanlis yapilandirilmis - wildcard veya reflect origin."""
        patterns = [
            r"""Access-Control""" + r"""-Allow-Origin.*\*""",
            r"""(?:origin\s*:\s*true|credentials\s*:\s*true.*origin\s*:\s*true)""",
            r"""CORS""" + r"""_ALLOW_ALL""",
        ]
        all_hits = []
        for p in patterns:
            all_hits.extend(self.scan_pattern(p, limit=50))
        return _fmt(all_hits, "CORS yanlis yapilandirilmis")

    def check_verbose_errors(self, t: dict) -> Tuple[bool, str]:
        """Production'da detayli hata mesajlari - bilgi sizintisi."""
        hits = self.scan_pattern(
            r"""(?:res\.(?:status|json|send)\s*\(\s*\{[^}]*(?:stack|trace|sql|query|internal|error\.message))|(?:catch\s*\([^)]*\)\s*\{[^}]*res\..*error\.(?:message|stack))"""
        )
        return _fmt(hits, "verbose error - bilgi sizintisi")

    def check_exposed_env_vars(self, t: dict) -> Tuple[bool, str]:
        """Client-side kodda NEXT_PUBLIC/EXPO_PUBLIC olmayan env var kullanimi."""
        hits = self.scan_pattern(
            r"""process\.env\.(?!NEXT_PUBLIC_|EXPO_PUBLIC_|REACT_APP_|VITE_|NODE_ENV|PUBLIC_)(\w+)"""
        )
        # Sadece client dosyalarinda
        client_hits = [h for h in hits if any(x in h["file"] for x in [".tsx", ".jsx", "components/", "pages/", "app/", "screens/"])]
        return _fmt(client_hits, "client-side'da gizli env var kullanimi")

    # ================================================================
    # 6. CRYPTOGRAPHIC FAILURES
    # ================================================================

    def check_weak_hashing(self, t: dict) -> Tuple[bool, str]:
        """Zayif hash algoritmalari - MD5, SHA1 sifreleme icin."""
        hits = self.scan_pattern(r"""(?:createHash|hashlib\.|Hash\.)\s*\(?\s*['"](?:md5|sha1)['"]""")
        return _fmt(hits, "zayif hash algoritmasi")

    def check_weak_encryption(self, t: dict) -> Tuple[bool, str]:
        """Zayif sifreleme algoritmasi tespiti."""
        p1 = r"""(?:""" + "DE" + r"""S|""" + "RC" + r"""4|""" + "RC" + r"""2|Blowfish)[\s\(\.]"""
        p2 = r"""(?:""" + "EC" + r"""B|AES-""" + "EC" + r"""B|mode\s*[:=]\s*['"]""" + "EC" + r"""B)"""
        p3 = r"""(?:key[_-]?size|keySize)\s*[:=]\s*(?:56|64|512)\b"""
        all_hits = []
        for p in [p1, p2, p3]:
            all_hits.extend(self.scan_pattern(p, flags=re.MULTILINE, limit=50))
        return _fmt(all_hits, "zayif sifreleme")

    def check_insecure_random(self, t: dict) -> Tuple[bool, str]:
        """Guvenlik icin Math.random/random kullanimi - predictable."""
        hits = self.scan_pattern(
            r"""(?:Math\.random|random\.random|rand\(\)|mt_rand)\s*\(\s*\)"""
        )
        # Guvenlik baglami var mi kontrol et
        security_context = [h for h in hits if any(w in self.read(h["file"]).lower() for w in ["token", "secret", "key", "session", "otp", "code", "verify"])]
        return _fmt(security_context, "guvenlik icin predictable random")

    def check_hardcoded_iv_salt(self, t: dict) -> Tuple[bool, str]:
        """Hardcoded IV veya salt - her seferinde ayni olursa guvenlik acigidir."""
        hits = self.scan_pattern(
            r"""(?:iv|salt|nonce)\s*[:=]\s*(?:['"][A-Fa-f0-9]{16,}['"]|Buffer\.from\(['"][^'"]+['"]\)|bytes?\()"""
        )
        return _fmt(hits, "hardcoded IV/salt")

    # ================================================================
    # 7. SUPPLY CHAIN & DEPENDENCIES
    # ================================================================

    def check_unpinned_dependencies(self, t: dict) -> Tuple[bool, str]:
        """Pinlenmemis dependency'ler - supply chain riski."""
        pkg_json = self.root / "package.json"
        if not pkg_json.exists():
            return True, "SKIP"
        try:
            pkg = json.loads(pkg_json.read_text(errors="ignore"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            unpinned = [name for name, ver in deps.items() if ver.startswith("*") or ver == "latest"]
            if unpinned:
                return False, f"{len(unpinned)} unpinned: {', '.join(unpinned[:5])}"
        except Exception:
            pass
        return True, "Temiz"

    def check_known_vulnerable_packages(self, t: dict) -> Tuple[bool, str]:
        """Bilinen zafiyetli paketler."""
        vulnerable = {
            "event-stream": "Backdoor (CVE-2018-16396)",
            "ua-parser-js": "Malware (CVE-2021-41265)",
            "colors": "Sabotage (protestware)",
            "faker": "Sabotage (protestware)",
            "node-ipc": "Protestware (CVE-2022-23812)",
            "flatmap-stream": "Supply chain attack",
            "lodash": None,  # check version
        }
        pkg_json = self.root / "package.json"
        if not pkg_json.exists():
            return True, "SKIP"
        try:
            pkg = json.loads(pkg_json.read_text(errors="ignore"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            found = []
            for name, reason in vulnerable.items():
                if name in deps and reason:
                    found.append(f"{name} ({reason})")
            if found:
                return False, f"{len(found)} zafiyetli paket: {found[0]}"
        except Exception:
            pass
        return True, "Temiz"

    def check_postinstall_scripts(self, t: dict) -> Tuple[bool, str]:
        """package.json'da postinstall script'leri - supply chain riski."""
        pkg_json = self.root / "package.json"
        if not pkg_json.exists():
            return True, "SKIP"
        try:
            pkg = json.loads(pkg_json.read_text(errors="ignore"))
            scripts = pkg.get("scripts", {})
            dangerous = [k for k in scripts if k in ("preinstall", "postinstall", "preuninstall")]
            if dangerous:
                return False, f"Riskli lifecycle script: {', '.join(dangerous)}"
        except Exception:
            pass
        return True, "Temiz"

    # ================================================================
    # 8. MOBILE SECURITY (React Native / Flutter)
    # ================================================================

    def check_certificate_pinning(self, t: dict) -> Tuple[bool, str]:
        """SSL certificate pinning eksik - MITM riski."""
        pinning = self.scan_pattern(
            r"""(?:ssl[_-]?pinning|TrustKit|cert.*pin|pinned.*cert|SSLPinningMode|react-native-ssl-pinning)"""
        )
        # Sadece mobil projeler icin
        is_mobile = (self.root / "app.json").exists() or (self.root / "pubspec.yaml").exists()
        if is_mobile and len(pinning) == 0:
            return False, "Mobil uygulama ama SSL certificate pinning yok - MITM riski"
        return True, "Temiz"

    def check_insecure_storage_mobile(self, t: dict) -> Tuple[bool, str]:
        """Mobilde hassas veriyi guvenli olmayan yerde saklama."""
        # AsyncStorage hassas veri icin kullanilmamali
        insecure = self.scan_pattern(
            r"""AsyncStorage\.(?:setItem|multiSet)\s*\(\s*['"](?:@?(?:token|secret|passw""" + r"""ord|key|session|auth|credential|jwt))"""
        )
        return _fmt(insecure, "AsyncStorage'da hassas veri (SecureStore kullanin)")

    def check_root_jailbreak_detection(self, t: dict) -> Tuple[bool, str]:
        """Root/jailbreak tespiti yok - uygulama manipule edilebilir."""
        detection = self.scan_pattern(
            r"""(?:jail[_-]?break|root[_-]?detect|isRooted|isJailbroken|SafetyNet|DeviceCheck|react-native-jail-monkey)"""
        )
        is_mobile = (self.root / "app.json").exists() or (self.root / "pubspec.yaml").exists()
        if is_mobile and len(detection) == 0:
            return False, "Mobil uygulama ama root/jailbreak tespiti yok"
        return True, "Temiz"

    def check_deeplink_validation(self, t: dict) -> Tuple[bool, str]:
        """Deep link'lerde input validasyonu - URL scheme hijacking."""
        deeplinks = self.scan_pattern(r"""(?:Linking\.addEventListener|useURL|expo-linking|scheme|deep[_-]?link)""")
        validation = self.scan_pattern(r"""(?:Linking.*validate|url.*check|whitelist|allowedDomains|verif.*url)""")
        if len(deeplinks) > 0 and len(validation) == 0:
            return False, f"{len(deeplinks)} deep link yapilandirmasi ama URL validasyonu yok"
        return True, "Temiz"

    def check_screenshot_protection(self, t: dict) -> Tuple[bool, str]:
        """Hassas ekranlarda screenshot/recording korumasi yok."""
        screenshot_prot = self.scan_pattern(
            r"""(?:FLAG_SECURE|screenshotPrevention|preventScreenCapture|SecureView|react-native-prevent-screenshot)"""
        )
        sensitive_screens = self.scan_pattern(r"""(?:payment|checkout|credit.*card|banking|wallet|transfer)""")
        if len(sensitive_screens) > 3 and len(screenshot_prot) == 0:
            return False, f"Hassas ekranlar var ama screenshot korumasi yok"
        return True, "Temiz"

    # ================================================================
    # 9. API SECURITY
    # ================================================================

    def check_rate_limiting(self, t: dict) -> Tuple[bool, str]:
        """API'de rate limiting yok - brute force/DDoS riski."""
        rate_limit = self.scan_pattern(
            r"""(?:rate[_-]?limit|rateLimit|throttle|express-rate-limit|@nestjs/throttler|slowDown|limiter)"""
        )
        api_routes = self.scan_pattern(r"""(?:app|router)\.\s*(?:post|put|delete)\s*\(""")
        if len(api_routes) > 3 and len(rate_limit) == 0:
            return False, f"{len(api_routes)} mutating API route ama rate limiting yok"
        return True, "Temiz"

    def check_no_input_size_limit(self, t: dict) -> Tuple[bool, str]:
        """Request body size limiti yok - bellek tasmasi riski."""
        body_limit = self.scan_pattern(
            r"""(?:body[_-]?parser|json\(\s*\{.*limit|urlencoded\(\s*\{.*limit|express\.json\(\s*\{.*limit|payload.*max)"""
        )
        server = self.scan_pattern(r"""(?:app\.listen|createServer|express\(\))""")
        if len(server) > 0 and len(body_limit) == 0:
            return False, "Server var ama request body size limiti yok"
        return True, "Temiz"

    def check_graphql_introspection(self, t: dict) -> Tuple[bool, str]:
        """GraphQL introspection production'da acik."""
        gql = self.scan_pattern(r"""(?:graphql|apollo|type-graphql|nexus|pothos)""")
        introspection_off = self.scan_pattern(r"""introspection\s*:\s*false""")
        if len(gql) > 3 and len(introspection_off) == 0:
            return False, "GraphQL kullaniliyor ama introspection kapatilmamis"
        return True, "Temiz"

    def check_excessive_data_exposure(self, t: dict) -> Tuple[bool, str]:
        """API response'da fazla veri - select * veya tum kayit donme."""
        patterns = [
            r"""SELECT\s+\*\s+FROM""",
            r"""\.findAll\s*\(\s*\)""",
            r"""\.find\s*\(\s*\{\s*\}\s*\)""",
            r"""\.select\s*\(\s*['"]\*['"]\s*\)""",
        ]
        all_hits = []
        for p in patterns:
            all_hits.extend(self.scan_pattern(p, limit=50))
        return _fmt(all_hits, "excessive data exposure (SELECT * / findAll)")

    # ================================================================
    # 10. COMPLIANCE & DATA PROTECTION
    # ================================================================

    def check_gdpr_data_deletion(self, t: dict) -> Tuple[bool, str]:
        """GDPR - kullanici veri silme mekanizmasi var mi?"""
        deletion = self.scan_pattern(
            r"""(?:delete[_-]?account|deleteUser|removeUser|data[_-]?deletion|right[_-]?to[_-]?forget|gdpr.*delete|erase.*data)"""
        )
        user_data = self.scan_pattern(r"""(?:email|name|phone|address|birth).*(?:save|store|insert|create)""")
        if len(user_data) > 3 and len(deletion) == 0:
            return False, "Kullanici verisi toplaniliyor ama silme mekanizmasi bulunamadi (GDPR)"
        return True, "Temiz"

    def check_data_encryption_at_rest(self, t: dict) -> Tuple[bool, str]:
        """Hassas veri sifrelenmeden saklanma."""
        storage = self.scan_pattern(
            r"""(?:\.save|\.create|\.insert|\.write)\s*\([^)]*(?:ssn|credit_card|card_number|social_security|medical|health)"""
        )
        encryption = self.scan_pattern(r"""(?:encrypt|cipher|aes|crypto\.create)""")
        if len(storage) > 0 and len(encryption) == 0:
            return False, f"Hassas veri saklaniliyor ama sifreleme bulunamadi"
        return True, "Temiz"

    def check_privacy_policy(self, t: dict) -> Tuple[bool, str]:
        """Privacy policy referansi var mi?"""
        privacy = self.scan_pattern(r"""(?:privacy[_-]?policy|privacyPolicy|privacy.*url|gizlilik.*politika)""")
        analytics = self.scan_pattern(r"""(?:analytics|tracking|mixpanel|amplitude|firebase.*analytics|segment)""")
        if len(analytics) > 0 and len(privacy) == 0:
            return False, f"Analytics/tracking var ama privacy policy referansi yok"
        return True, "Temiz"

    def check_consent_management(self, t: dict) -> Tuple[bool, str]:
        """Kullanici izin yonetimi - consent/KVKK."""
        consent = self.scan_pattern(
            r"""(?:consent|cookie[_-]?banner|gdpr[_-]?consent|kvkk|riza|onay.*kullanim|acceptTerms|termsAccepted)"""
        )
        tracking = self.scan_pattern(r"""(?:analytics|tracking|cookies|pixel|tag[_-]?manager)""")
        if len(tracking) > 2 and len(consent) == 0:
            return False, "Tracking/analytics kullaniliyor ama izin yonetimi (consent) yok"
        return True, "Temiz"

    # ================================================================
    # 11. PRODUCTION READINESS - Gozden Kacirilan Seyler
    # ================================================================

    def check_error_boundary(self, t: dict) -> Tuple[bool, str]:
        """React Error Boundary yok - beyaz ekran riski."""
        error_boundary = self.scan_pattern(r"""(?:ErrorBoundary|componentDidCatch|getDerivedStateFromError|error[_-]?boundary)""")
        react = self.scan_pattern(r"""(?:from\s+['"]react['"]|import\s+React)""")
        if len(react) > 5 and len(error_boundary) == 0:
            return False, "React projesi ama ErrorBoundary yok - crash = beyaz ekran"
        return True, "Temiz"

    def check_missing_loading_states(self, t: dict) -> Tuple[bool, str]:
        """Async islemlerde loading/error state yok."""
        fetches = self.scan_pattern(r"""(?:fetch\(|axios\.|useSWR|useQuery|supabase.*from\()""")
        loading = self.scan_pattern(r"""(?:isLoading|loading|isError|isFetching|skeleton|spinner|ActivityIndicator)""")
        ratio = len(loading) / max(len(fetches), 1)
        if len(fetches) > 5 and ratio < 0.3:
            return False, f"{len(fetches)} async cagri ama yetersiz loading/error state ({len(loading)} adet)"
        return True, "Temiz"

    def check_memory_leaks(self, t: dict) -> Tuple[bool, str]:
        """Potansiyel memory leak - temizlenmeyen subscription/timer."""
        # addEventListener/setInterval without cleanup
        listeners = self.scan_pattern(r"""(?:addEventListener|setInterval|setTimeout|subscribe)\s*\(""")
        cleanups = self.scan_pattern(r"""(?:removeEventListener|clearInterval|clearTimeout|unsubscribe|cleanup|return\s*\(\s*\)\s*=>)""")
        ratio = len(cleanups) / max(len(listeners), 1)
        if len(listeners) > 5 and ratio < 0.3:
            return False, f"{len(listeners)} listener/timer ama {len(cleanups)} cleanup - memory leak riski"
        return True, "Temiz"

    def check_race_conditions(self, t: dict) -> Tuple[bool, str]:
        """Race condition riski - concurrent state mutation."""
        # Token deduction without locking
        concurrent_ops = self.scan_pattern(
            r"""(?:balance|stock|quantity|count|amount)\s*(?:-=|\+=|=\s*.*\s*[-+])\s*"""
        )
        locking = self.scan_pattern(r"""(?:lock|mutex|semaphore|transaction|FOR UPDATE|serializable|advisory_lock)""")
        if len(concurrent_ops) > 3 and len(locking) == 0:
            return False, f"Concurrent degisim ({len(concurrent_ops)} yer) ama kilit mekanizmasi yok - race condition"
        return True, "Temiz"

    def check_missing_timeout(self, t: dict) -> Tuple[bool, str]:
        """HTTP isteklerinde timeout yok - baglanti askida kalabilir."""
        http_calls = self.scan_pattern(r"""(?:fetch\(|axios\.|request\(|http\.get|https\.get)""")
        timeouts = self.scan_pattern(r"""(?:timeout|AbortController|signal|deadline)""")
        if len(http_calls) > 5 and len(timeouts) == 0:
            return False, f"{len(http_calls)} HTTP istegi ama timeout ayari yok"
        return True, "Temiz"

    def check_hardcoded_urls(self, t: dict) -> Tuple[bool, str]:
        """Production/staging URL'leri hardcoded - ortam degisikliginde sorun."""
        hits = self.scan_pattern(
            r"""['"]https?://(?:api\.|app\.|www\.)[a-zA-Z0-9][a-zA-Z0-9-]+\.[a-z]{2,}(?:/[^'"]*)?['"]"""
        )
        env_urls = self.scan_pattern(r"""(?:process\.env\.|import\.meta\.env\.|Config\.)(?:API_URL|BASE_URL|SERVER_URL|BACKEND_URL)""")
        if len(hits) > 5 and len(env_urls) == 0:
            return False, f"{len(hits)} hardcoded URL - env variable kullanin"
        return True, "Temiz"

    # ================================================================
    # RUNNER - Tum kontrolleri calistir
    # ================================================================

    def get_all_checks(self) -> Dict[str, callable]:
        """Tum guvenlik kontrollerini dondur."""
        return {
            # 1. Sensitive Data
            "hardcoded_credentials": self.check_hardcoded_credentials,
            "tokens_in_urls": self.check_tokens_in_urls,
            "sensitive_logs": self.check_sensitive_data_in_logs,
            "sensitive_errors": self.check_sensitive_data_in_errors,
            "pii_exposure": self.check_pii_exposure,
            "source_maps_prod": self.check_source_maps_in_prod,
            # 2. Auth & Session
            "jwt_no_expiry": self.check_jwt_no_expiry,
            "jwt_weak_secret": self.check_jwt_weak_secret,
            "missing_auth_middleware": self.check_missing_auth_middleware,
            "insecure_session_storage": self.check_insecure_session_storage,
            "missing_csrf": self.check_missing_csrf,
            "weak_password_policy": self.check_weak_password_policy,
            # 3. Injection
            "xss_vectors": self.check_xss_vectors,
            "nosql_injection": self.check_nosql_injection,
            "template_injection": self.check_template_injection,
            "regex_dos": self.check_regex_dos,
            "unvalidated_redirects": self.check_unvalidated_redirects,
            "file_upload_no_validation": self.check_file_upload_no_validation,
            # 4. Access Control
            "idor_risk": self.check_idor_risk,
            "horizontal_privilege": self.check_horizontal_privilege,
            "admin_routes_exposed": self.check_admin_routes_exposed,
            "mass_assignment": self.check_mass_assignment,
            # 5. Misconfiguration
            "debug_production": self.check_debug_in_production,
            "default_credentials": self.check_default_credentials,
            "missing_security_headers": self.check_missing_security_headers,
            "cors_misconfiguration": self.check_cors_misconfiguration,
            "verbose_errors": self.check_verbose_errors,
            "exposed_env_vars": self.check_exposed_env_vars,
            # 6. Crypto
            "weak_hashing": self.check_weak_hashing,
            "weak_encryption": self.check_weak_encryption,
            "insecure_random": self.check_insecure_random,
            "hardcoded_iv_salt": self.check_hardcoded_iv_salt,
            # 7. Supply Chain
            "unpinned_deps": self.check_unpinned_dependencies,
            "known_vulnerable_packages": self.check_known_vulnerable_packages,
            "postinstall_scripts": self.check_postinstall_scripts,
            # 8. Mobile
            "certificate_pinning": self.check_certificate_pinning,
            "insecure_storage_mobile": self.check_insecure_storage_mobile,
            "root_jailbreak_detection": self.check_root_jailbreak_detection,
            "deeplink_validation": self.check_deeplink_validation,
            "screenshot_protection": self.check_screenshot_protection,
            # 9. API
            "rate_limiting": self.check_rate_limiting,
            "no_input_size_limit": self.check_no_input_size_limit,
            "graphql_introspection": self.check_graphql_introspection,
            "excessive_data_exposure": self.check_excessive_data_exposure,
            # 10. Compliance
            "gdpr_data_deletion": self.check_gdpr_data_deletion,
            "data_encryption_at_rest": self.check_data_encryption_at_rest,
            "privacy_policy": self.check_privacy_policy,
            "consent_management": self.check_consent_management,
            # 11. Production
            "error_boundary": self.check_error_boundary,
            "missing_loading_states": self.check_missing_loading_states,
            "memory_leaks": self.check_memory_leaks,
            "race_conditions": self.check_race_conditions,
            "missing_timeout": self.check_missing_timeout,
            "hardcoded_urls": self.check_hardcoded_urls,
        }

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        """Belirli bir guvenlik kontrolunu calistir."""
        checks = self.get_all_checks()
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"
