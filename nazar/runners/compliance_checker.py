"""Compliance Framework Checker - OWASP, GDPR/KVKK, SOC2, PCI-DSS uyumluluk kontrolu.

Statik analiz tabanli, harici API cagrisi yapmaz.
YAML-tabanli kural tanimlari ile calisir.
"""
import os
import re
from pathlib import Path
from typing import List, Dict, Tuple

from nazar.runners.base import BaseRunner


def _fmt(hits, msg="bulundu"):
    if not hits:
        return True, "Temiz"
    first = hits[0]
    return False, f"{len(hits)} {msg}: {first['file']}:{first['line']}"


def _fmt_missing(missing_items: List[str], context: str) -> Tuple[bool, str]:
    """Eksik ogeleri formatla."""
    if not missing_items:
        return True, f"{context}: Tum kontroller gecti"
    return False, f"{context}: Eksik -> {', '.join(missing_items[:5])}"


# ================================================================
# YAML-tabanli kural tanimlari (inline, dosya gerektirmez)
# ================================================================

# --- OWASP Top 10 (2021) Haritalama ---
_OWASP_A01_PATTERNS = [
    r"@app\.(?:route|get|post|put|delete)\s*\([^)]+\)\s*\ndef\s",
    r"\.findById\s*\(\s*(?:req|request)\.(?:params|query|body)",
]
# A01 ek kontrol: route decorator'dan sonra auth decorator yoksa risk var
# Bu iki adimli kontrol _check_owasp_category'de yapilir (lookahead yerine)
_OWASP_A02_PATTERNS = [
    r"(?:\bMD5\b|\bmd5\b|\bSHA1\b|\bsha1\b|\bDES\b|\bRC4\b|\bECB\b)",
    r"Math\.random\s*\(\s*\).*(?:token|key|secret|password|salt|iv|nonce)",
]
_OWASP_A03_PATTERNS = [
    r"""(?:execute|query|raw)\s*\(\s*(?:f['"]|['"].*?\+)""",
    r"""\b(?:os\.system|subprocess\.call|child_process\.exec)\s*\(""",
]
_OWASP_A04_PATTERNS = [
    r"(?:TODO|FIXME|HACK).*(?:auth|security|validation|sanitize)",
]
_OWASP_A05_PATTERNS = [
    r"(?:DEBUG\s*=\s*True|debug\s*:\s*true|app\.debug\s*=\s*True)",
    r"""(?:admin|root|test)\s*[:=]\s*['"](?:admin|root|password|123456|test)['"]""",
]
_OWASP_A07_PATTERNS = [
    r"""jwt\.sign\s*\(""",
    r"""(?:session|cookie).*(?:secure\s*:\s*false|httpOnly\s*:\s*false)""",
]
# A07 ek kontrol: jwt.sign bulundugunda expiresIn olup olmadigini iki adimda kontrol et
_OWASP_A08_PATTERNS = [
    r"""yaml\.load\s*\(""",
    r"""(?:marshal\.loads|unserialize)\s*\(""",
]
# A08 ek kontrol: yaml.load bulundugunda Loader parametresi olup olmadigini iki adimda kontrol et
_OWASP_A09_PATTERNS = [
    r"""(?:console\.log|print|logger\.\w+)\s*\(.*(?:password|token|secret|key|credential)""",
]
_OWASP_A10_PATTERNS = [
    r"""(?:fetch|axios|request|urllib|http\.get)\s*\(\s*(?:req|request)\.(?:body|query|params)""",
    r"""(?:redirect|forward)\s*\(\s*(?:req|request)\.(?:body|query|params)""",
]

OWASP_TOP10_MAP = {
    "A01_broken_access_control": {
        "id": "A01", "name": "Broken Access Control",
        "description": "Yetkilendirme ve erisim kontrolu eksiklikleri",
        "mapped_subtypes": ["missing_auth_middleware", "idor_risk", "horizontal_privilege", "mass_assignment", "cors_wildcard", "cors_misconfiguration"],
        "patterns": _OWASP_A01_PATTERNS,
    },
    "A02_cryptographic_failures": {
        "id": "A02", "name": "Cryptographic Failures",
        "description": "Kriptografi hatalari ve zayif sifreleme",
        "mapped_subtypes": ["weak_crypto", "weak_hashing", "weak_encryption", "hardcoded_iv_salt", "insecure_random"],
        "patterns": _OWASP_A02_PATTERNS,
    },
    "A03_injection": {
        "id": "A03", "name": "Injection",
        "description": "SQL, NoSQL, OS, LDAP injection riskleri",
        "mapped_subtypes": ["sql_injection", "nosql_injection", "command_injection", "xss_vectors", "path_traversal"],
        "patterns": _OWASP_A03_PATTERNS,
    },
    "A04_insecure_design": {
        "id": "A04", "name": "Insecure Design",
        "description": "Guvenli olmayan tasarim desenleri",
        "mapped_subtypes": ["rate_limiting", "no_input_size_limit"],
        "patterns": _OWASP_A04_PATTERNS,
    },
    "A05_security_misconfiguration": {
        "id": "A05", "name": "Security Misconfiguration",
        "description": "Guvenlik yapilandirma hatalari",
        "mapped_subtypes": ["debug_mode", "debug_production", "default_credentials", "missing_security_headers", "verbose_errors", "exposed_env_vars"],
        "patterns": _OWASP_A05_PATTERNS,
    },
    "A06_vulnerable_components": {
        "id": "A06", "name": "Vulnerable and Outdated Components",
        "description": "Bilinen aciklari olan veya guncel olmayan bilesenler",
        "mapped_subtypes": ["unpinned_deps", "known_vulnerable_packages", "outdated_packages", "deprecated_packages", "typosquatting"],
        "patterns": [],
    },
    "A07_auth_failures": {
        "id": "A07", "name": "Identification and Authentication Failures",
        "description": "Kimlik dogrulama ve oturum yonetim hatalari",
        "mapped_subtypes": ["jwt_no_expiry", "jwt_weak_secret", "insecure_session_storage", "missing_csrf", "default_credentials"],
        "patterns": _OWASP_A07_PATTERNS,
    },
    "A08_integrity_failures": {
        "id": "A08", "name": "Software and Data Integrity Failures",
        "description": "Yazilim ve veri butunlugu hatalari",
        "mapped_subtypes": ["insecure_deserialization", "postinstall_scripts"],
        "patterns": _OWASP_A08_PATTERNS,
    },
    "A09_logging_failures": {
        "id": "A09", "name": "Security Logging and Monitoring Failures",
        "description": "Guvenlik loglama ve izleme eksiklikleri",
        "mapped_subtypes": ["sensitive_logs", "sensitive_errors"],
        "patterns": _OWASP_A09_PATTERNS,
    },
    "A10_ssrf": {
        "id": "A10", "name": "Server-Side Request Forgery (SSRF)",
        "description": "Sunucu tarafli istek sahtecilik riskleri",
        "mapped_subtypes": ["unvalidated_redirects"],
        "patterns": _OWASP_A10_PATTERNS,
    },
}

# --- GDPR / KVKK Kurallari ---
GDPR_KVKK_RULES = {
    "consent_mechanism": {
        "name": "Riza mekanizmasi (Consent)",
        "description": "Kullanici rizasi alinma kontrolu",
        "positive_patterns": [
            r"(?:consent|riza|onay|izin)(?:Form|Modal|Dialog|Banner|Popup|Screen|Page|Component)",
            r"(?:acceptTerms|agreeTerms|consentGiven|hasConsent|isConsentGiven)",
            r"(?:cookie.*consent|consent.*cookie|gdpr.*consent|kvkk.*onay)",
        ],
        "required": True,
    },
    "data_deletion": {
        "name": "Veri silme yetenegi (Right to Erasure)",
        "description": "Kullanici verisi silme mekanizmasi",
        "positive_patterns": [
            r"(?:delete.*account|remove.*account|hesap.*sil|account.*delet)",
            r"(?:erase.*data|data.*eras|veri.*sil|delete.*user.*data)",
            r"(?:right.*forgotten|right.*erasure|silinme.*hakki)",
            r"(?:anonymize|pseudonymize|anonimles)",
        ],
        "required": True,
    },
    "privacy_policy": {
        "name": "Gizlilik politikasi baglantisi",
        "description": "Privacy policy veya KVKK aydinlatma metni referansi",
        "positive_patterns": [
            r"(?:privacy.*policy|gizlilik.*politika|kvkk|aydinlatma.*metni)",
            r"(?:privacyPolicy|privacy_policy|PrivacyPolicy)",
            r"(?:terms.*(?:service|use|conditions)|kullanim.*(?:sartlari|kosullari))",
        ],
        "required": True,
    },
    "cookie_consent": {
        "name": "Cerez onay mekanizmasi",
        "description": "Cookie consent banner veya yonetimi",
        "positive_patterns": [
            r"(?:cookie.*(?:consent|banner|policy|notice)|cerez.*(?:onay|ayar|politika))",
            r"(?:CookieConsent|CookieBanner|CookieNotice|CookiePolicy)",
            r"(?:react-cookie-consent|cookie-consent|js-cookie.*consent)",
        ],
        "required": False,
    },
    "data_encryption_at_rest": {
        "name": "Duragan veri sifreleme",
        "description": "Verilerin saklanirken sifrelenmesi",
        "positive_patterns": [
            r"(?:encrypt|sifre|cipher|crypto)(?:.*(?:store|save|persist|write|database|db))",
            r"(?:AES|aes|Aes)(?:.*(?:encrypt|Encrypt|CBC|GCM))",
            r"(?:SecureStore|Keychain|KeyStore|EncryptedSharedPreferences)",
            r"(?:pgcrypto|encryption.*at.*rest|column.*encrypt)",
        ],
        "required": True,
    },
    "pii_logging_prevention": {
        "name": "PII loglama engelleme",
        "description": "Kisisel verilerin log'lara yazilmasinin engellenmesi",
        "negative_patterns": [
            r"(?:console\.log|print|logger\.\w+|log\.(?:info|debug|warn))\s*\(.*(?:email|telefon|phone|tc_kimlik|ssn|credit.*card|kredi.*kart|address|adres)",
            r"(?:console\.log|print|logger\.\w+)\s*\(.*(?:password|sifre|parola|token|secret)",
        ],
        "required": True,
    },
}

# --- SOC2 Temel Kurallari ---
SOC2_RULES = {
    "authentication": {
        "name": "Kimlik dogrulama (Authentication)",
        "description": "Kullanici kimlik dogrulama mekanizmasi",
        "positive_patterns": [
            r"(?:passport|auth0|firebase.*auth|next-auth|clerk|supabase.*auth|cognito)",
            r"(?:login|signin|sign_in|authenticate|dogrula|giris)",
            r"(?:bcrypt|argon2|scrypt|pbkdf2)(?:.*hash|.*compare|.*verify)",
            r"(?:JWT|jwt|JsonWebToken|jsonwebtoken)",
        ],
        "required": True,
    },
    "access_control": {
        "name": "Erisim kontrolu (Access Control)",
        "description": "Rol tabanli veya izin tabanli erisim kontrolu",
        "positive_patterns": [
            r"(?:role|permission|yetki|izin|authorization)(?:.*(?:check|guard|middleware|decorator|policy))",
            r"(?:isAdmin|isAuthenticated|hasPermission|hasRole|can|authorize|checkPermission)",
            r"(?:RBAC|rbac|ACL|acl|ABAC|abac)",
            r"(?:@Roles|@Permissions|@Authorize|@RequiresAuth|@login_required)",
        ],
        "required": True,
    },
    "audit_logging": {
        "name": "Denetim loglama (Audit Logging)",
        "description": "Kullanici eylemlerinin loglanmasi",
        "positive_patterns": [
            r"(?:audit.*log|log.*audit|denetim.*log)",
            r"(?:activity.*log|log.*activity|event.*log|log.*event)",
            r"(?:winston|pino|bunyan|log4js|morgan|logging\.getLogger)",
            r"(?:createdBy|updatedBy|deletedBy|modifiedBy|changedBy)",
            r"(?:audit_trail|auditTrail|event_store|eventStore)",
        ],
        "required": True,
    },
    "encryption_in_transit": {
        "name": "Aktarim sifreleme (HTTPS)",
        "description": "TLS/HTTPS kullanimi zorunlulugu",
        "negative_patterns": [
            r"http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|10\.|192\.168\.|172\.1[6-9]\.|172\.2[0-9]\.|172\.3[0-1]\.)[a-zA-Z]",
        ],
        "positive_patterns": [
            r"(?:https://|TLS|tls|SSL|ssl|HTTPS|https)",
            r"(?:force.*https|redirect.*https|HSTS|hsts|Strict-Transport-Security)",
        ],
        "required": True,
    },
    "error_handling": {
        "name": "Hata yonetimi (Stack Trace korunmasi)",
        "description": "Uretim ortaminda stack trace gizleme",
        "negative_patterns": [
            r"(?:stack.*trace|stackTrace|\.stack).*(?:res\.send|res\.json|response\.send|return.*json)",
            r"(?:err\.message|error\.message|e\.message).*(?:res\.send|res\.json|response\.send)",
            r"(?:DEBUG\s*=\s*True|debug\s*:\s*true)(?!.*(?:test|dev|development|local))",
        ],
        "positive_patterns": [
            r"(?:ErrorBoundary|error.*boundary|errorHandler|errorMiddleware)",
        ],
        "required": True,
    },
    "dependency_updates": {
        "name": "Bagimlilk guncelleme (Dependency Management)",
        "description": "Bagimlilik versiyonlama ve guncelleme",
        "file_checks": [
            "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
            "Pipfile.lock", "poetry.lock", "go.sum", "Cargo.lock",
        ],
        "positive_patterns": [
            r"(?:renovate|dependabot|snyk|greenkeeper)",
        ],
        "required": True,
    },
}

# --- PCI-DSS Temel Kurallari ---
PCI_DSS_RULES = {
    "no_credit_card_in_code": {
        "name": "Kaynak kodda kredi karti numarasi yok",
        "description": "PAN (Primary Account Number) kaynak kodda olmamali",
        "negative_patterns": [
            r"(?<!\d)(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})(?!\d)",
        ],
        "exclude_patterns": [
            r"4242424242424242|4000056655665556|5555555555554444|378282246310005",
            r"(?://|#|/\*|\*/).*\d{13,19}",
        ],
        "required": True,
    },
    "no_pan_storage": {
        "name": "PAN saklama kontrolu",
        "description": "Kredi karti numarasi saklanmamali (sadece tokenize edilmeli)",
        "negative_patterns": [
            r"(?:card_number|cardNumber|cc_number|ccNumber|pan|creditCard|credit_card)\s*[:=]",
            r"(?:save|store|persist|write|insert).*(?:card|kart|pan|credit)",
            r"(?:card|kart|pan|credit).*(?:save|store|persist|write|insert|database|db|collection)",
        ],
        "positive_patterns": [
            r"(?:stripe|braintree|adyen|paypal|iyzico|param).*(?:token|customer|payment_method)",
            r"(?:tokenize|tokenization|tok_)",
        ],
        "required": True,
    },
    "tls_enforcement": {
        "name": "TLS zorunlulugu",
        "description": "Tum iletisim TLS uzerinden olmali",
        "negative_patterns": [
            r"http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|10\.|192\.168\.)[a-zA-Z]",
        ],
        "positive_patterns": [
            r"(?:HTTPS|https|TLS|tls|SSL|ssl|HSTS|hsts)",
            r"(?:force.*https|redirect.*https|Strict-Transport-Security)",
            r"(?:sslmode\s*=\s*require|ssl\s*:\s*true|rejectUnauthorized\s*:\s*true)",
        ],
        "required": True,
    },
    "input_validation_payment": {
        "name": "Odeme formu girdi dogrulama",
        "description": "Odeme formlari icin girdi dogrulama kontrolu",
        "positive_patterns": [
            r"(?:validate|validation|sanitize|sanitization).*(?:card|payment|amount|cvv|cvc|expir)",
            r"(?:card|payment|amount|cvv|cvc|expir).*(?:validate|validation|sanitize|sanitization)",
            r"(?:Zod|yup|joi|class-validator|express-validator).*(?:card|payment|amount)",
            r"(?:Luhn|luhn|luhn_check|isValidCard|validateCard)",
            r"(?:Stripe|stripe|braintree|adyen).*(?:Element|element|CardElement|PaymentElement)",
        ],
        "required": True,
    },
}


class ComplianceChecker(BaseRunner):
    """Compliance framework checker - OWASP, GDPR/KVKK, SOC2, PCI-DSS."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self._all_files_cache = None

    def _all_files(self) -> List[Tuple[str, str]]:
        """Tum dosyalari tara ve cache'le."""
        if self._all_files_cache is not None:
            return self._all_files_cache
        ignore = {"node_modules", ".git", "build", "dist", "Pods", ".gradle",
                  "vendor", "venv", ".venv", "__pycache__", ".expo", "coverage", ".next"}
        result = []
        for rd, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in ignore]
            for f in files:
                full = os.path.join(rd, f)
                rel = os.path.relpath(full, self.root)
                result.append((rel, full))
        self._all_files_cache = result
        return result

    def _file_exists(self, filename: str) -> bool:
        """Dosyanin projede var olup olmadigini kontrol et."""
        for rel, _ in self._all_files():
            if os.path.basename(rel) == filename or rel == filename:
                return True
        return False

    def _has_any_file(self, filenames: List[str]) -> Tuple[bool, str]:
        """Dosya listesinden herhangi biri var mi."""
        for fn in filenames:
            if self._file_exists(fn):
                return True, fn
        return False, ""

    def _search_positive(self, patterns: List[str]) -> List[Dict]:
        """Pozitif pattern'leri ara (bunlarin OLMASI gerekir)."""
        all_hits = []
        for pat in patterns:
            hits = self.scan_pattern(pat, skip_test=False, skip_env=False, limit=300)
            all_hits.extend(hits)
        return all_hits

    def _search_negative(self, patterns: List[str]) -> List[Dict]:
        """Negatif pattern'leri ara (bunlarin OLMAMASI gerekir)."""
        all_hits = []
        for pat in patterns:
            hits = self.scan_pattern(pat, skip_test=True, skip_env=True, limit=300)
            all_hits.extend(hits)
        return all_hits

    # ================================================================
    # OWASP Top 10 Mapping
    # ================================================================

    def check_owasp_mapping(self, subtype: str, t: dict) -> Tuple[bool, str]:
        """Mevcut guvenlik bulgularini OWASP kategorilerine esle."""
        if subtype == "owasp_full":
            return self._owasp_full_scan(t)

        key = subtype.replace("owasp_", "").upper()
        for rule_key, rule in OWASP_TOP10_MAP.items():
            if rule["id"] == key or rule_key == subtype.replace("owasp_", ""):
                return self._check_owasp_category(rule)
        return True, f"OWASP {subtype}: Bilinmeyen kategori, SKIP"

    def _check_owasp_category(self, rule: dict) -> Tuple[bool, str]:
        """Tek bir OWASP kategorisini kontrol et."""
        violations = []
        for pat in rule.get("patterns", []):
            hits = self.scan_pattern(pat, skip_test=True, skip_env=True, limit=200)
            if hits:
                # Iki adimli kontroller: lookahead yerine sonradan filtrele
                if pat == r"""jwt\.sign\s*\(""":
                    hits = [h for h in hits if "expiresIn" not in h.get("match", "") and "expiresIn" not in h.get("content", "")]
                elif pat == r"""yaml\.load\s*\(""":
                    hits = [h for h in hits if "Loader" not in h.get("match", "") and "Loader" not in h.get("content", "")]
                elif pat == r"@app\.(?:route|get|post|put|delete)\s*\([^)]+\)\s*\ndef\s":
                    # Route decorator sonrasi auth kontrolu: content icinde auth decorator ara
                    hits = [h for h in hits if not re.search(r"@(?:login_required|auth|requires_auth)", h.get("content", ""))]
                violations.extend(hits)
        if violations:
            first = violations[0]
            return False, f"OWASP {rule['id']} ({rule['name']}): {len(violations)} risk bulundu - {first['file']}:{first['line']}"
        return True, f"OWASP {rule['id']} ({rule['name']}): Temiz"

    def _owasp_full_scan(self, t: dict) -> Tuple[bool, str]:
        """Tum OWASP Top 10 kategorilerini tara."""
        failed_categories = []
        total_violations = 0
        for rule_key, rule in OWASP_TOP10_MAP.items():
            violations = self._count_owasp_violations(rule)
            if violations > 0:
                failed_categories.append(rule["id"])
                total_violations += violations
        if failed_categories:
            return False, f"OWASP Top 10: {len(failed_categories)}/10 kategoride {total_violations} risk - Basarisiz: {', '.join(failed_categories)}"
        return True, "OWASP Top 10: Tum kategoriler temiz"

    def _count_owasp_violations(self, rule: dict) -> int:
        """Bir OWASP kategorisindeki ihlal sayisini dogrudan say."""
        count = 0
        for pat in rule.get("patterns", []):
            hits = self.scan_pattern(pat, skip_test=True, skip_env=True, limit=200)
            if hits:
                if pat == r"""jwt\.sign\s*\(""":
                    hits = [h for h in hits if "expiresIn" not in h.get("match", "") and "expiresIn" not in h.get("content", "")]
                elif pat == r"""yaml\.load\s*\(""":
                    hits = [h for h in hits if "Loader" not in h.get("match", "") and "Loader" not in h.get("content", "")]
                elif pat == r"@app\.(?:route|get|post|put|delete)\s*\([^)]+\)\s*\ndef\s":
                    hits = [h for h in hits if not re.search(r"@(?:login_required|auth|requires_auth)", h.get("content", ""))]
                count += len(hits)
        return count

    # ================================================================
    # GDPR / KVKK
    # ================================================================

    def check_gdpr_kvkk(self, subtype: str, t: dict) -> Tuple[bool, str]:
        """GDPR/KVKK uyumluluk kontrolu."""
        rule_key = subtype.replace("gdpr_", "").replace("kvkk_", "")
        if rule_key == "full":
            return self._gdpr_full_scan(t)
        rule = GDPR_KVKK_RULES.get(rule_key)
        if not rule:
            return True, f"GDPR/KVKK {subtype}: Bilinmeyen kural, SKIP"
        return self._check_gdpr_rule(rule_key, rule)

    def _check_gdpr_rule(self, key: str, rule: dict) -> Tuple[bool, str]:
        """Tek bir GDPR/KVKK kuralini kontrol et."""
        name = rule["name"]

        # Negatif pattern kontrolu (bunlar OLMAMALI)
        neg_patterns = rule.get("negative_patterns", [])
        if neg_patterns:
            violations = self._search_negative(neg_patterns)
            if violations:
                first = violations[0]
                return False, f"GDPR/KVKK - {name}: {len(violations)} ihlal bulundu - {first['file']}:{first['line']}"

        # Pozitif pattern kontrolu (bunlar OLMALI)
        pos_patterns = rule.get("positive_patterns", [])
        if pos_patterns:
            hits = self._search_positive(pos_patterns)
            if not hits and rule.get("required", False):
                return False, f"GDPR/KVKK - {name}: Mekanizma bulunamadi"
            if hits:
                return True, f"GDPR/KVKK - {name}: Mevcut ({len(hits)} bulgu)"

        return True, f"GDPR/KVKK - {name}: Kontrol tamamlandi"

    def _gdpr_full_scan(self, t: dict) -> Tuple[bool, str]:
        """Tum GDPR/KVKK kurallarini tara."""
        failed = []
        for key, rule in GDPR_KVKK_RULES.items():
            passed, detail = self._check_gdpr_rule(key, rule)
            if not passed:
                failed.append(rule["name"])
        if failed:
            return False, f"GDPR/KVKK: {len(failed)}/{len(GDPR_KVKK_RULES)} kontrolde basarisiz - {', '.join(failed[:3])}"
        return True, f"GDPR/KVKK: Tum kontroller ({len(GDPR_KVKK_RULES)}) gecti"

    # ================================================================
    # SOC2 Basics
    # ================================================================

    def check_soc2(self, subtype: str, t: dict) -> Tuple[bool, str]:
        """SOC2 temel kontrolleri."""
        rule_key = subtype.replace("soc2_", "")
        if rule_key == "full":
            return self._soc2_full_scan(t)
        rule = SOC2_RULES.get(rule_key)
        if not rule:
            return True, f"SOC2 {subtype}: Bilinmeyen kural, SKIP"
        return self._check_soc2_rule(rule_key, rule)

    def _check_soc2_rule(self, key: str, rule: dict) -> Tuple[bool, str]:
        """Tek bir SOC2 kuralini kontrol et."""
        name = rule["name"]

        # Dosya kontrolu (lock dosyalari vb)
        file_checks = rule.get("file_checks", [])
        if file_checks:
            found, found_file = self._has_any_file(file_checks)
            if not found and rule.get("required", False) and key == "dependency_updates":
                pos_hits = self._search_positive(rule.get("positive_patterns", []))
                if not pos_hits:
                    return False, f"SOC2 - {name}: Lock dosyasi veya bagimlilk yonetim araci bulunamadi"

        # Negatif pattern kontrolu
        neg_patterns = rule.get("negative_patterns", [])
        if neg_patterns:
            violations = self._search_negative(neg_patterns)
            if violations:
                first = violations[0]
                return False, f"SOC2 - {name}: {len(violations)} ihlal bulundu - {first['file']}:{first['line']}"

        # Pozitif pattern kontrolu
        pos_patterns = rule.get("positive_patterns", [])
        if pos_patterns:
            hits = self._search_positive(pos_patterns)
            if not hits and rule.get("required", False):
                return False, f"SOC2 - {name}: Mekanizma bulunamadi"
            if hits:
                return True, f"SOC2 - {name}: Mevcut ({len(hits)} bulgu)"

        return True, f"SOC2 - {name}: Kontrol tamamlandi"

    def _soc2_full_scan(self, t: dict) -> Tuple[bool, str]:
        """Tum SOC2 temel kurallarini tara."""
        failed = []
        for key, rule in SOC2_RULES.items():
            passed, detail = self._check_soc2_rule(key, rule)
            if not passed:
                failed.append(rule["name"])
        if failed:
            return False, f"SOC2: {len(failed)}/{len(SOC2_RULES)} kontrolde basarisiz - {', '.join(failed[:3])}"
        return True, f"SOC2: Tum kontroller ({len(SOC2_RULES)}) gecti"

    # ================================================================
    # PCI-DSS Basics
    # ================================================================

    def check_pci_dss(self, subtype: str, t: dict) -> Tuple[bool, str]:
        """PCI-DSS temel kontrolleri."""
        rule_key = subtype.replace("pci_", "").replace("dss_", "")
        if rule_key == "full":
            return self._pci_full_scan(t)
        rule = PCI_DSS_RULES.get(rule_key)
        if not rule:
            return True, f"PCI-DSS {subtype}: Bilinmeyen kural, SKIP"
        return self._check_pci_rule(rule_key, rule)

    def _check_pci_rule(self, key: str, rule: dict) -> Tuple[bool, str]:
        """Tek bir PCI-DSS kuralini kontrol et."""
        name = rule["name"]

        # Negatif pattern kontrolu (bunlar OLMAMALI)
        neg_patterns = rule.get("negative_patterns", [])
        if neg_patterns:
            violations = self._search_negative(neg_patterns)

            # Exclude pattern'leri uygula (test karti numaralari vb)
            exclude_patterns = rule.get("exclude_patterns", [])
            if violations and exclude_patterns:
                filtered = []
                for v in violations:
                    line_content = v.get("match", "")
                    excluded = False
                    for exc_pat in exclude_patterns:
                        if re.search(exc_pat, line_content, re.IGNORECASE):
                            excluded = True
                            break
                    if not excluded:
                        filtered.append(v)
                violations = filtered

            if violations:
                first = violations[0]
                return False, f"PCI-DSS - {name}: {len(violations)} ihlal bulundu - {first['file']}:{first['line']}"

        # Pozitif pattern kontrolu (bunlar OLMALI)
        pos_patterns = rule.get("positive_patterns", [])
        if pos_patterns:
            hits = self._search_positive(pos_patterns)
            if not hits and rule.get("required", False):
                # Odeme ile ilgili kod yoksa bu kontrol gecersiz
                payment_indicators = self.scan_pattern(
                    r"(?:payment|odeme|checkout|kart|card|stripe|braintree|iyzico|param)",
                    skip_test=True, limit=100
                )
                if not payment_indicators:
                    return True, f"PCI-DSS - {name}: Odeme kodu bulunamadi, SKIP"
                return False, f"PCI-DSS - {name}: Odeme kodu var ama dogrulama mekanizmasi bulunamadi"
            if hits:
                return True, f"PCI-DSS - {name}: Mevcut ({len(hits)} bulgu)"

        return True, f"PCI-DSS - {name}: Kontrol tamamlandi"

    def _pci_full_scan(self, t: dict) -> Tuple[bool, str]:
        """Tum PCI-DSS temel kurallarini tara."""
        failed = []
        for key, rule in PCI_DSS_RULES.items():
            passed, detail = self._check_pci_rule(key, rule)
            if not passed:
                failed.append(rule["name"])
        if failed:
            return False, f"PCI-DSS: {len(failed)}/{len(PCI_DSS_RULES)} kontrolde basarisiz - {', '.join(failed[:3])}"
        return True, f"PCI-DSS: Tum kontroller ({len(PCI_DSS_RULES)}) gecti"

    # ================================================================
    # Ana run_check metodu - Orchestrator tarafindan cagirilir
    # ================================================================

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        """Test calistir. Orchestrator bu metodu cagirir."""
        # OWASP kontrolleri
        if subtype.startswith("owasp_"):
            return self.check_owasp_mapping(subtype, test)

        # GDPR/KVKK kontrolleri
        if subtype.startswith("gdpr_") or subtype.startswith("kvkk_"):
            return self.check_gdpr_kvkk(subtype, test)

        # SOC2 kontrolleri
        if subtype.startswith("soc2_"):
            return self.check_soc2(subtype, test)

        # PCI-DSS kontrolleri
        if subtype.startswith("pci_"):
            return self.check_pci_dss(subtype, test)

        # Toplu kontroller
        dispatch = {
            "compliance_summary": lambda: self._compliance_summary(test),
        }
        fn = dispatch.get(subtype)
        if fn:
            return fn()

        return True, f"Compliance {subtype}: Bilinmeyen kontrol, SKIP"

    def _compliance_summary(self, t: dict) -> Tuple[bool, str]:
        """Tum framework'lerin ozet durumu."""
        results = {}
        owasp_ok, _ = self._owasp_full_scan(t)
        results["OWASP"] = "PASS" if owasp_ok else "FAIL"
        gdpr_ok, _ = self._gdpr_full_scan(t)
        results["GDPR/KVKK"] = "PASS" if gdpr_ok else "FAIL"
        soc2_ok, _ = self._soc2_full_scan(t)
        results["SOC2"] = "PASS" if soc2_ok else "FAIL"
        pci_ok, _ = self._pci_full_scan(t)
        results["PCI-DSS"] = "PASS" if pci_ok else "FAIL"

        passed_count = sum(1 for v in results.values() if v == "PASS")
        all_passed = passed_count == len(results)
        summary = " | ".join(f"{k}: {v}" for k, v in results.items())
        return all_passed, f"Compliance Ozet ({passed_count}/{len(results)}): {summary}"
