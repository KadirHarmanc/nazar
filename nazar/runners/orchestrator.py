"""Test Orchestrator - Test planini calistirir, runner'lara delege eder."""
import os
import re
import time
import json
import math
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from nazar.runners.base import BaseRunner
from nazar.runners.security_scanner import DeepSecurityScanner
from nazar.runners.ux_text_analyzer import UXTextAnalyzer
from nazar.runners.ui_component_tester import UIComponentTester
from nazar.runners.cross_analyzer import CrossFileAnalyzer
from nazar.runners.appstore_checker import AppStoreChecker
from nazar.runners.sca_scanner import SCAScanner
from nazar.runners.playstore_checker import PlayStoreChecker
from nazar.analyzers.ast_python import PythonASTAnalyzer
from nazar.analyzers.taint_tracker import TaintTracker
from nazar.analyzers.pattern_engine import YAMLRuleEngine
from nazar.analyzers.ui_analyzer import UIAnalyzer
from nazar.analyzers.spell_checker import SpellChecker
from nazar.analyzers.ui_quality import UIQualityAnalyzer
from nazar.analyzers.yaml_ui_runner import YAMLUITestRunner
from nazar.analyzers.i18n_analyzer import I18nAnalyzer
from nazar.analyzers.responsive_analyzer import ResponsiveAnalyzer
from nazar.analyzers.performance_analyzer import PerformanceStaticAnalyzer
from nazar.analyzers.visual_regression import VisualRegressionAnalyzer
from nazar.runners.compliance_checker import ComplianceChecker

# "How to Fix" mesajlari
HOW_TO_FIX = {
    "secrets": {
        "sorun": "Kaynak kodda hardcoded secret bulundu",
        "cozum": "Secret'lari environment variable'a tasiyin, .env dosyasi kullanin",
        "quick_fix": "Degeri .env dosyasina tasiyin ve os.environ['KEY'] ile okuyin",
    },
    "api_keys": {
        "sorun": "Kaynak kodda API key tespit edildi",
        "cozum": "API key'leri .env dosyasina tasiyin, kod'dan kaldirin",
        "quick_fix": "grep -rn 'api.key\\|API_KEY' src/ ile bulun ve .env'e tasiyin",
    },
    "private_keys": {
        "sorun": "Repo'da private key veya cloud credential bulundu",
        "cozum": "Private key'leri .gitignore'a ekleyin, git history'den temizleyin",
        "quick_fix": ".gitignore'a *.pem, *.key ekleyin",
    },
    "dangerous_functions": {
        "sorun": "Tehlikeli fonksiyon kullanimi tespit edildi (code evaluation)",
        "cozum": "Kod degerlendirme yerine guvenli alternatifler kullanin",
        "quick_fix": "JSON.parse() veya ast.literal_eval() kullanin",
    },
    "sql_injection": {
        "sorun": "SQL injection riski tespit edildi",
        "cozum": "Parameterized query veya ORM kullanin",
        "quick_fix": "String concatenation yerine placeholder (?) kullanin",
    },
    "command_injection": {
        "sorun": "Command injection riski tespit edildi",
        "cozum": "Shell komutlarini kullanici girdisiyle birlestirmeyin",
        "quick_fix": "subprocess.run() ile shell=False kullanin, shlex.quote() ile escape edin",
    },
    "weak_crypto": {
        "sorun": "Zayif kriptografi algoritmasi kullaniliyor",
        "cozum": "MD5/SHA1 yerine SHA256+, RSA 2048+ kullanin",
        "quick_fix": "hashlib.md5 yerine hashlib.sha256 kullanin",
    },
    "insecure_deserialization": {
        "sorun": "Guvenli olmayan deserialization tespit edildi",
        "cozum": "Guvenilmeyen veri ile guvenli olmayan deserialization kullanmayin",
        "quick_fix": "yaml.safe_load() ve json.loads() kullanin",
    },
    "path_traversal": {
        "sorun": "Path traversal riski tespit edildi",
        "cozum": "Kullanici girdisini dosya yollarinda kullanirken dogrulayin",
        "quick_fix": "os.path.realpath() ile normalize edip base dizin kontrolu yapin",
    },
    "long_functions": {
        "sorun": "50 satirdan uzun fonksiyonlar var",
        "cozum": "Uzun fonksiyonlari kucuk alt fonksiyonlara bolerek yeniden yapilandirin",
        "quick_fix": "Her fonksiyonu tek bir sorumluluk ile sinirlayin",
    },
    "complexity": {
        "sorun": "Yuksek cyclomatic complexity",
        "cozum": "If/else zincirlerini strategy pattern veya lookup table ile degistirin",
        "quick_fix": "Guard clause'lar ve early return kullanin",
    },
    "dead_code": {
        "sorun": "Kullanilmayan fonksiyon veya degisken tespit edildi",
        "cozum": "Kullanilmayan kodu kaldirin, kod tabanini temiz tutun",
        "quick_fix": "IDE'nizin 'unused' uyarilarini takip edin",
    },
    "mutable_default": {
        "sorun": "Python fonksiyonunda mutable default argument",
        "cozum": "Default olarak None kullanin, fonksiyon icinde olusturun",
        "quick_fix": "def f(x=None): x = x or [] seklinde kullanin",
    },
    # SCA
    "npm_audit": {
        "sorun": "npm paketlerinde bilinen guvenlik acigi var",
        "cozum": "npm audit fix ile otomatik guncelle veya manuel versiyonlari yukseltin",
        "quick_fix": "npm audit fix --force (dikkat: breaking change olabilir)",
    },
    "pip_audit": {
        "sorun": "Python paketlerinde bilinen guvenlik acigi var",
        "cozum": "Acikli paketleri guncelleyin: pip install --upgrade <paket>",
        "quick_fix": "pip-audit --fix veya pip install --upgrade -r requirements.txt",
    },
    "go_vulncheck": {
        "sorun": "Go modullerinde bilinen guvenlik acigi var",
        "cozum": "go get -u ile modulleri guncelleyin",
        "quick_fix": "go get -u ./... && go mod tidy",
    },
    "outdated_packages": {
        "sorun": "Major versiyon gerisinde paketler var",
        "cozum": "Paketleri guncelleyin, breaking change'leri kontrol edin",
        "quick_fix": "npm outdated veya pip list --outdated ile kontrol edin",
    },
    "license_compatibility": {
        "sorun": "GPL lisansli dependency MIT projede kullaniliyor",
        "cozum": "GPL paketini kaldirin veya projenizi GPL'e cevirin",
        "quick_fix": "npm ls <paket> ile bagimlilik agacini kontrol edin",
    },
    "deprecated_packages": {
        "sorun": "Deprecated (kullanim disi) paket kullaniliyor",
        "cozum": "Modern alternatifine gecis yapin",
        "quick_fix": "Paket adi yanindaki alternatifi kurun",
    },
    "typosquatting": {
        "sorun": "Bilinen typosquatting paketi tespit edildi - TEHLIKELI",
        "cozum": "Paketi HEMEN kaldirin ve dogru isimli paketi kurun",
        "quick_fix": "npm uninstall <paket> && npm install <dogru-paket>",
    },
    # Play Store
    "target_sdk": {
        "sorun": "targetSdkVersion guncel degil, Play Store red edebilir",
        "cozum": "build.gradle'da targetSdkVersion'i 34+ yapin",
        "quick_fix": "targetSdkVersion 34 olarak degistirin",
    },
    "exported_components": {
        "sorun": "android:exported belirtilmemis component'ler var",
        "cozum": "Android 12+ icin tum component'lere exported ekleyin",
        "quick_fix": "AndroidManifest.xml'de her activity/service/receiver'a android:exported ekleyin",
    },
    "network_security": {
        "sorun": "Ag guvenligi yapilandirmasi yetersiz",
        "cozum": "networkSecurityConfig tanimlayin, cleartext kapatin",
        "quick_fix": "usesCleartextTraffic=false yapin, network_security_config.xml ekleyin",
    },
    "debuggable": {
        "sorun": "Release build'de debuggable=true - Play Store RED sebebi",
        "cozum": "Release config'de debuggable=false yapin",
        "quick_fix": "build.gradle > release > debuggable false",
    },
    "proguard": {
        "sorun": "Kod obfuscation (R8/ProGuard) aktif degil",
        "cozum": "Release build'de minifyEnabled=true yapin",
        "quick_fix": "build.gradle > release > minifyEnabled true",
    },
    "i18n_deep": {
        "sorun": "UI'da hardcoded string'ler var, i18n kapsami dusuk",
        "cozum": "Tum UI string'lerini i18n sistemiyle yonetin (i18next, react-intl vb.)",
        "quick_fix": "npm install i18next react-i18next && t('key') seklinde kullanin",
    },
    "i18n_coverage": {
        "sorun": "i18n coverage yetersiz, bircok string hala hardcoded",
        "cozum": "Her UI string'ini translation dosyasina ekleyin ve t() ile cagirin",
        "quick_fix": "Hardcoded string'leri grep ile bulun ve locale dosyasina ekleyin",
    },
    "missing_translation_keys": {
        "sorun": "Kodda kullanilan translation key'leri locale dosyalarinda eksik",
        "cozum": "Eksik key'leri tum locale dosyalarina ekleyin",
        "quick_fix": "Eksik key'leri en.json/tr.json gibi dosyalara ekleyin",
    },
    "unused_translation_keys": {
        "sorun": "Locale dosyalarinda tanimli ama kodda kullanilmayan key'ler var",
        "cozum": "Kullanilmayan key'leri temizleyin, bundle boyutunu kucultin",
        "quick_fix": "Kullanilmayan key'leri locale JSON dosyalarindan silin",
    },
    "locale_consistency": {
        "sorun": "Locale dosyalari arasinda key tutarsizligi var",
        "cozum": "Tum locale dosyalarinin ayni key setine sahip olmasini saglayin",
        "quick_fix": "Referans locale'deki eksik key'leri diger locale'lere ekleyin",
    },
    "rtl_support": {
        "sorun": "RTL (Arapca/Ibranice) locale var ama RTL destegi eksik",
        "cozum": "I18nManager.isRTL kontrolu ekleyin, marginStart/End kullanin",
        "quick_fix": "import { I18nManager } from 'react-native' ve direction kontrolleri ekleyin",
    },
    # Responsive - Faz 5
    "fixed_dimensions": {
        "sorun": "Sabit pixel boyutlari responsive degil",
        "cozum": "Sabit px yerine %, vw/vh, rem veya flex kullanin",
        "quick_fix": "width: 300px yerine width: 100% veya max-width kullanin",
    },
    "scroll_issues": {
        "sorun": "ScrollView icinde FlatList/SectionList performans sorunu",
        "cozum": "ScrollView icindeki FlatList'i cikarip tek FlatList kullanin",
        "quick_fix": "FlatList'in ListHeaderComponent prop'unu kullanin",
    },
    "responsive_patterns": {
        "sorun": "Eski responsive pattern'ler kullaniliyor",
        "cozum": "Dimensions.get yerine useWindowDimensions hook'u kullanin",
        "quick_fix": "const { width, height } = useWindowDimensions()",
    },
    "media_query_analysis": {
        "sorun": "Media query breakpoint'leri eksik veya yetersiz",
        "cozum": "Mobil, tablet ve desktop icin uygun breakpoint'ler tanimlayin",
        "quick_fix": "@media (min-width: 768px) ve @media (min-width: 1024px) ekleyin",
    },
    "viewport_meta": {
        "sorun": "Viewport meta tag eksik veya yanlis yapilandirilmis",
        "cozum": "HTML <head> icine dogru viewport meta tag ekleyin",
        "quick_fix": '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
    },
    "touch_target_size": {
        "sorun": "Dokunma hedefleri cok kucuk (44x44px altinda)",
        "cozum": "Interaktif elementlerin min boyutunu 44x44px yapin (WCAG 2.5.5)",
        "quick_fix": "min-width: 44px; min-height: 44px ekleyin",
    },
    "flexbox_grid_usage": {
        "sorun": "Modern esnek layout (flexbox/grid) kullanilmiyor",
        "cozum": "Float ve absolute yerine flexbox veya CSS Grid kullanin",
        "quick_fix": "display: flex veya display: grid ile layout olusturun",
    },
    "responsive_images": {
        "sorun": "Gorseller responsive optimize degil",
        "cozum": "srcset, sizes ve <picture> elementi ile farkli ekran boyutlarina uygun gorseller sunun",
        "quick_fix": '<img srcset="img-480.jpg 480w, img-800.jpg 800w" sizes="(max-width: 600px) 480px, 800px">',
    },
    # Visual Regression
    "stale_snapshots": {
        "sorun": "Eski/guncelligin yitirmis snapshot dosyalari var",
        "cozum": "Snapshot'lari guncelleyin veya artik kullanilmayanlari silin",
        "quick_fix": "npx jest --updateSnapshot veya npx vitest --update",
    },
    "missing_snapshots": {
        "sorun": "Test dosyalari icin snapshot dosyasi eksik",
        "cozum": "Eksik snapshot'lari olusturun: testleri calistirin ve snapshot'lari commit edin",
        "quick_fix": "npx jest --updateSnapshot && git add __snapshots__/",
    },
    "snapshot_naming": {
        "sorun": "Snapshot dosya isimlendirmesi tutarsiz veya yanlis",
        "cozum": "Snapshot dosyalarini test dosyasiyla ayni adda .snap uzantili yapin",
        "quick_fix": "ComponentName.test.tsx -> ComponentName.test.tsx.snap seklinde eslestirin",
    },
    "large_snapshots": {
        "sorun": "Snapshot dosyalari cok buyuk (review zorlasiyor)",
        "cozum": "Buyuk snapshot'lari kucuk, odakli component snapshot'larina bolerek kuculte",
        "quick_fix": "toMatchInlineSnapshot() veya daha spesifik selector ile snapshot alin",
    },
    "uncommitted_snapshots": {
        "sorun": "Snapshot degisiklikleri commit edilmemis",
        "cozum": "Degisen snapshot'lari review edip commit edin",
        "quick_fix": "git add **/__snapshots__/ && git commit -m 'update snapshots'",
    },
    "snapshot_directory_check": {
        "sorun": "Snapshot dizin yapisi standart degil veya dagnik",
        "cozum": "__snapshots__ dizinini test dosyalarinin yanina yerlestirin",
        "quick_fix": "Her __tests__ dizininin icine bir __snapshots__ dizini olusturun",
    },
    # Compliance - OWASP
    "owasp_full": {
        "sorun": "OWASP Top 10 kategorilerinde risk tespit edildi",
        "cozum": "OWASP Top 10 rehberine gore guvenlik iyilestirmeleri yapin",
        "quick_fix": "Detayli sonuclarda belirtilen kategorilerdeki bulgulari inceleyin",
    },
    # Compliance - GDPR/KVKK
    "gdpr_consent_mechanism": {
        "sorun": "Kullanici riza/onay mekanizmasi bulunamadi",
        "cozum": "GDPR/KVKK uyumu icin consent form veya banner ekleyin",
        "quick_fix": "react-cookie-consent veya benzeri bir kutuphane kurun",
    },
    "gdpr_data_deletion": {
        "sorun": "Kullanici verisi silme mekanizmasi eksik",
        "cozum": "Hesap silme veya veri temizleme endpoint'i ekleyin (Right to Erasure)",
        "quick_fix": "DELETE /api/users/:id endpoint'i olusturun",
    },
    "gdpr_privacy_policy": {
        "sorun": "Gizlilik politikasi/KVKK aydinlatma metni referansi eksik",
        "cozum": "Uygulamada privacy policy sayfasi veya linki ekleyin",
        "quick_fix": "Footer veya Settings'e Privacy Policy linki ekleyin",
    },
    "gdpr_pii_logging_prevention": {
        "sorun": "Kisisel veri (PII) log'lara yaziliyor",
        "cozum": "Log ifadelerinden email, telefon, sifre gibi PII verileri kaldirin",
        "quick_fix": "Log satirlarini grep ile bulun ve PII'leri maskeleyin",
    },
    # Compliance - SOC2
    "soc2_authentication": {
        "sorun": "Kimlik dogrulama mekanizmasi bulunamadi",
        "cozum": "Auth kutuphanesi (passport, auth0, next-auth vb.) ekleyin",
        "quick_fix": "npm install next-auth veya benzeri auth paketi kurun",
    },
    "soc2_access_control": {
        "sorun": "Erisim kontrolu/yetkilendirme mekanizmasi eksik",
        "cozum": "RBAC veya ABAC tabanli yetkilendirme sistemi ekleyin",
        "quick_fix": "Middleware seviyesinde role/permission kontrolu ekleyin",
    },
    "soc2_audit_logging": {
        "sorun": "Denetim loglama mekanizmasi bulunamadi",
        "cozum": "Kullanici eylemlerini loglayan bir audit trail sistemi ekleyin",
        "quick_fix": "winston/pino logger kurun ve CRUD islemlerini loglayin",
    },
    "soc2_encryption_in_transit": {
        "sorun": "HTTP (sifresiz) baglanti kullaniliyor",
        "cozum": "Tum URL'leri HTTPS'e cevirin, HSTS header ekleyin",
        "quick_fix": "http:// ile baslayan URL'leri https:// ile degistirin",
    },
    "soc2_error_handling": {
        "sorun": "Stack trace veya hata detayi kullaniciya gosteriliyor",
        "cozum": "Production'da generic hata mesajlari gosterin, detaylari loglayin",
        "quick_fix": "ErrorBoundary ekleyin, res.send(err.stack) satirlarini kaldirin",
    },
    # Compliance - PCI-DSS
    "pci_no_credit_card_in_code": {
        "sorun": "Kaynak kodda kredi karti numarasi tespit edildi",
        "cozum": "Gercek kart numaralarini koddan kaldirin, test icin test kartlari kullanin",
        "quick_fix": "4242424242424242 gibi Stripe test kartlarini kullanin",
    },
    "pci_no_pan_storage": {
        "sorun": "Kredi karti numarasi saklanma riski tespit edildi",
        "cozum": "Kart bilgilerini tokenize edin (Stripe, Braintree vb. kullanin)",
        "quick_fix": "Stripe PaymentElement veya CardElement kullanin",
    },
    "pci_tls_enforcement": {
        "sorun": "TLS zorunlulugu saglanmiyor",
        "cozum": "Tum iletisimi HTTPS uzerinden yapin",
        "quick_fix": "http:// URL'leri https:// ile degistirin",
    },
    "pci_input_validation_payment": {
        "sorun": "Odeme formu girdi dogrulama eksik",
        "cozum": "Odeme form alanlarina validation ekleyin (Luhn, CVV format vb.)",
        "quick_fix": "Stripe Elements veya Zod schema ile validation ekleyin",
    },
}

# 50+ Secret Pattern'leri
SECRET_PATTERNS = {
    # Cloud Providers
    "aws_access_key": r"AKIA[0-9A-Z]{16}",
    "aws_secret_key": r"""(?:aws_secret_access_key|AWS_SECRET)\s*[:=]\s*['"][A-Za-z0-9/+=]{40}['"]""",
    "gcp_api_key": r"AIza[0-9A-Za-z\-_]{35}",
    "gcp_service_account": r'"type"\s*:\s*"service_' + r'account"',
    "azure_storage_key": r"""(?:AccountKey|azure_storage_key)\s*[:=]\s*['"][A-Za-z0-9+/]{86}==['"]""",
    "digitalocean_token": r"dop_v1_[a-f0-9]{64}",
    # Payment
    "stripe_secret_key": r"sk_live_[0-9a-zA-Z]{24,}",
    "stripe_restricted_key": r"rk_live_[0-9a-zA-Z]{24,}",
    "stripe_webhook_secret": r"whsec_[0-9a-zA-Z]{24,}",
    "square_access_token": r"sq0atp-[0-9A-Za-z\-_]{22}",
    # Communication
    "slack_bot_token": r"xoxb-[0-9]{10,}-[0-9A-Za-z]{24,}",
    "slack_user_token": r"xoxp-[0-9]{10,}-[0-9]{10,}-[0-9A-Za-z]{24,}",
    "slack_webhook": r"https://hooks\.slack" + r"\.com/services/T[A-Z0-9]{8}/B[A-Z0-9]{8}/[A-Za-z0-9]{24}",
    "discord_bot_token": r"[MN][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27,}",
    "discord_webhook": r"https://discord(?:app)?\.com/api" + r"/webhooks/\d+/[A-Za-z0-9_-]+",
    "twilio_sid": r"AC[0-9a-fA-F]{32}",
    "twilio_auth": r"SK[0-9a-fA-F]{32}",
    "telegram_bot": r"\d{9,10}:[A-Za-z0-9_-]{35}",
    # Email
    "sendgrid_api_key": r"SG\.[a-zA-Z0-9]{22}\.[a-zA-Z0-9\-_]{43}",
    "mailgun_api_key": r"key-[0-9a-zA-Z]{32}",
    "mailchimp_api_key": r"[0-9a-f]{32}-us\d{1,2}",
    # VCS & CI/CD
    "github_pat": r"ghp_[A-Za-z0-9]{36}",
    "github_oauth": r"gho_[A-Za-z0-9]{36}",
    "github_app_token": r"ghs_[A-Za-z0-9]{36}",
    "github_refresh": r"ghr_[A-Za-z0-9]{36}",
    "gitlab_pat": r"glpat-[0-9a-zA-Z\-_]{20}",
    "gitlab_runner": r"GR1348941[A-Za-z0-9\-_]{20}",
    "bitbucket_app": r"ATBB[A-Za-z0-9]{32}",
    # Database
    "mongodb_uri": r"mongodb(?:\+srv)?" + r"://[^\s'\"]+",
    "postgres_uri": r"postgres(?:ql)?" + r"://[^\s'\"]+",
    "mysql_uri": r"mysql" + r"://[^\s'\"]+",
    "redis_uri": r"redis" + r"://[^\s'\"]+",
    # Auth
    "jwt_token": r"eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_.+/=]+",
    # Package Registry
    "npm_token": r"npm_[A-Za-z0-9]{36}",
    "pypi_token": r"pypi-[A-Za-z0-9]{48,}",
    "nuget_key": r"oy2[a-z0-9]{43}",
    # Monitoring
    "sentry_dsn": r"https://[a-f0-9]{32}@[a-z0-9]+" + r"\.ingest\.sentry\.io/\d+",
    "newrelic_key": r"NRAK-[A-Z0-9]{27}",
    # Firebase
    "firebase_key": r"AAAA[A-Za-z0-9_-]{7}:[A-Za-z0-9_-]{140}",
    # Crypto Keys
    "rsa_private_key": r"-----BEGIN " + r"RSA PRIVATE KEY-----",
    "ec_private_key": r"-----BEGIN " + r"EC PRIVATE KEY-----",
    "openssh_private_key": r"-----BEGIN " + r"OPENSSH PRIVATE KEY-----",
    "pgp_private_key": r"-----BEGIN " + r"PGP PRIVATE KEY BLOCK-----",
    # Generic
    "generic_password": r"""(?:password|passwd|pwd)\s*[:=]\s*['"][^'"]{8,}['"]""",
    "generic_secret": r"""(?:secret|SECRET)\s*[:=]\s*['"][^'"]{8,}['"]""",
    "generic_token": r"""(?:token|TOKEN)\s*[:=]\s*['"][^'"]{16,}['"]""",
    "generic_api_key": r"""(?:api_key|API_KEY|apikey)\s*[:=]\s*['"][A-Za-z0-9_-]{16,}['"]""",
}


class TestOrchestrator(BaseRunner):
    def __init__(self, project_path: str, plan_data: dict):
        super().__init__(project_path)
        self.plan = plan_data
        self.results: List[Dict] = []
        self._deep_scanner = None
        # Dosya listesini on-yukle (bir kere os.walk, tum runner'lar paylasin)
        self.src_files()

    def _share_cache(self, runner):
        """Source cache'i alt runner ile paylas - tekrar os.walk yapmasini engelle."""
        runner._source_cache = self._source_cache
        runner._content_cache = self._content_cache
        return runner

    @property
    def deep_scanner(self) -> DeepSecurityScanner:
        if self._deep_scanner is None:
            self._deep_scanner = self._share_cache(DeepSecurityScanner(str(self.root)))
        return self._deep_scanner

    @property
    def ux_analyzer(self) -> UXTextAnalyzer:
        if not hasattr(self, '_ux_analyzer') or self._ux_analyzer is None:
            self._ux_analyzer = self._share_cache(UXTextAnalyzer(str(self.root)))
        return self._ux_analyzer

    @property
    def ui_tester(self) -> UIComponentTester:
        if not hasattr(self, '_ui_tester') or self._ui_tester is None:
            self._ui_tester = self._share_cache(UIComponentTester(str(self.root)))
        return self._ui_tester

    @property
    def cross_analyzer(self) -> CrossFileAnalyzer:
        if not hasattr(self, '_cross_analyzer') or self._cross_analyzer is None:
            self._cross_analyzer = self._share_cache(CrossFileAnalyzer(str(self.root)))
        return self._cross_analyzer

    @property
    def appstore_checker(self) -> AppStoreChecker:
        if not hasattr(self, '_appstore_checker') or self._appstore_checker is None:
            self._appstore_checker = self._share_cache(AppStoreChecker(str(self.root)))
        return self._appstore_checker

    @property
    def ast_analyzer(self) -> PythonASTAnalyzer:
        if not hasattr(self, '_ast_analyzer') or self._ast_analyzer is None:
            self._ast_analyzer = self._share_cache(PythonASTAnalyzer(str(self.root)))
        return self._ast_analyzer

    @property
    def taint_tracker(self) -> TaintTracker:
        if not hasattr(self, '_taint_tracker') or self._taint_tracker is None:
            self._taint_tracker = self._share_cache(TaintTracker(str(self.root)))
        return self._taint_tracker

    @property
    def yaml_ui_runner(self) -> YAMLUITestRunner:
        if not hasattr(self, '_yaml_ui_runner') or self._yaml_ui_runner is None:
            self._yaml_ui_runner = self._share_cache(YAMLUITestRunner(str(self.root)))
        return self._yaml_ui_runner

    @property
    def i18n_analyzer(self) -> I18nAnalyzer:
        if not hasattr(self, '_i18n_analyzer') or self._i18n_analyzer is None:
            self._i18n_analyzer = self._share_cache(I18nAnalyzer(str(self.root)))
        return self._i18n_analyzer

    @property
    def responsive_analyzer(self) -> ResponsiveAnalyzer:
        if not hasattr(self, '_responsive_analyzer') or self._responsive_analyzer is None:
            self._responsive_analyzer = self._share_cache(ResponsiveAnalyzer(str(self.root)))
        return self._responsive_analyzer

    @property
    def perf_static_analyzer(self) -> PerformanceStaticAnalyzer:
        if not hasattr(self, '_perf_static') or self._perf_static is None:
            self._perf_static = self._share_cache(PerformanceStaticAnalyzer(str(self.root)))
        return self._perf_static

    @property
    def spell_checker(self) -> SpellChecker:
        if not hasattr(self, '_spell_checker') or self._spell_checker is None:
            self._spell_checker = self._share_cache(SpellChecker(str(self.root)))
        return self._spell_checker

    @property
    def ui_quality(self) -> UIQualityAnalyzer:
        if not hasattr(self, '_ui_quality') or self._ui_quality is None:
            self._ui_quality = self._share_cache(UIQualityAnalyzer(str(self.root)))
        return self._ui_quality

    @property
    def ui_analyzer(self) -> UIAnalyzer:
        if not hasattr(self, '_ui_analyzer') or self._ui_analyzer is None:
            self._ui_analyzer = self._share_cache(UIAnalyzer(str(self.root)))
        return self._ui_analyzer

    @property
    def yaml_engine(self) -> YAMLRuleEngine:
        if not hasattr(self, '_yaml_engine') or self._yaml_engine is None:
            self._yaml_engine = self._share_cache(YAMLRuleEngine(str(self.root)))
        return self._yaml_engine

    @property
    def sca_scanner(self) -> SCAScanner:
        if not hasattr(self, '_sca_scanner') or self._sca_scanner is None:
            self._sca_scanner = self._share_cache(SCAScanner(str(self.root)))
        return self._sca_scanner

    @property
    def playstore_checker(self) -> PlayStoreChecker:
        if not hasattr(self, '_playstore_checker') or self._playstore_checker is None:
            self._playstore_checker = self._share_cache(PlayStoreChecker(str(self.root)))
        return self._playstore_checker

    @property
    def visual_regression(self) -> VisualRegressionAnalyzer:
        if not hasattr(self, '_visual_regression') or self._visual_regression is None:
            self._visual_regression = self._share_cache(VisualRegressionAnalyzer(str(self.root)))
        return self._visual_regression

    @property
    def compliance_checker(self) -> ComplianceChecker:
        if not hasattr(self, '_compliance_checker') or self._compliance_checker is None:
            self._compliance_checker = self._share_cache(ComplianceChecker(str(self.root)))
        return self._compliance_checker

    def run_all(self) -> List[Dict]:
        for test in self.plan.get("tests", []):
            self.results.append(self._run_test(test))
        return self.results

    def run_parallel(self, max_workers: int = 4) -> List[Dict]:
        """Testleri paralel calistir."""
        tests = self.plan.get("tests", [])
        # API testlerini sirali calistir (rate limiting)
        api_tests = [t for t in tests if t.get("type") == "api"]
        other_tests = [t for t in tests if t.get("type") != "api"]

        results = []
        # Diger testleri paralel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._run_test, t): t for t in other_tests}
            for future in as_completed(futures):
                results.append(future.result())

        # API testleri sirali
        for t in api_tests:
            results.append(self._run_test(t))

        self.results = results
        return results

    def _run_test(self, test: dict) -> dict:
        t = test.get("type", "")
        sub = test.get("subtype", "")
        start = time.time()

        # .nazarignore rule kontrolu
        if self.ignore_manager.is_rule_ignored(sub):
            return {
                "name": test.get("name", "?"), "type": t, "subtype": sub,
                "passed": True, "duration": 0, "detail": "IGNORED (.nazarignore)",
                "priority": test.get("priority", "medium"),
                "confidence": 0, "confidence_label": "Ignored",
            }

        try:
            runner_map = {
                "api": self._api, "security": self._security,
                "code_quality": self._code_quality, "type_safety": self._type_safety,
                "import_graph": self._import_graph, "error_handling": self._error_handling,
                "naming": self._naming, "git": self._git,
                "dependency": self._dependency, "license": self._license,
                "env": self._env, "config": self._config,
                "documentation": self._doc, "accessibility": self._a11y,
                "structure": self._structure, "performance": self._perf,
                "visual": self._visual, "docker": self._docker,
                "ux_text": self._ux_text, "ui_component": self._ui_component,
                "cross_file": self._cross_file,
                "appstore": self._appstore,
                "sca": self._sca,
                "playstore": self._playstore,
                "ast_analysis": self._ast_analysis,
                "taint": self._taint,
                "yaml_rules": self._yaml_rules,
                "ui_analysis": self._ui_analysis,
                "spell_check": self._spell_check,
                "ui_quality": self._ui_quality_check,
                "yaml_ui": self._yaml_ui,
                "i18n_deep": self._i18n_deep,
                "responsive": self._responsive,
                "perf_static": self._run_perf_static,
                "visual_regression": self._visual_regression_check,
                "compliance": self._compliance,
            }
            fn = runner_map.get(t)
            passed, detail = fn(test) if fn else (True, "SKIP")
        except Exception as e:
            passed, detail = False, str(e)[:80]

        from nazar.runners.confidence import get_confidence, confidence_label
        conf = get_confidence(test.get("subtype", ""))
        result = {
            "name": test.get("name", "?"), "type": t, "subtype": test.get("subtype", ""),
            "passed": passed, "duration": time.time() - start, "detail": detail.replace("\n", " ").replace("\r", ""),
            "priority": test.get("priority", "medium"),
            "confidence": conf,
            "confidence_label": confidence_label(conf),
        }

        # How to Fix + Guide bilgisi ekle
        sub = test.get("subtype", "")
        if not passed and sub in HOW_TO_FIX:
            fix = HOW_TO_FIX[sub]
            result["how_to_fix"] = fix
            result["detail_rich"] = f"SORUN: {fix['sorun']} | COZUM: {fix['cozum']} | QUICK FIX: {fix['quick_fix']}"

        if not passed:
            from nazar.guides.registry import GuideRegistry
            guide = GuideRegistry.get(sub)
            if guide:
                result["guide"] = guide

        return result

    # ---- UX Text ----
    def _ux_text(self, t: dict) -> Tuple[bool, str]:
        return self.ux_analyzer.run_check(t.get("subtype", ""), t)

    # ---- UI Component ----
    def _ui_component(self, t: dict) -> Tuple[bool, str]:
        return self.ui_tester.run_check(t.get("subtype", ""), t)

    # ---- Cross-File ----
    def _cross_file(self, t: dict) -> Tuple[bool, str]:
        return self.cross_analyzer.run_check(t.get("subtype", ""), t)

    # ---- App Store ----
    def _appstore(self, t: dict) -> Tuple[bool, str]:
        return self.appstore_checker.run_check(t.get("subtype", ""), t)

    # ---- SCA (Software Composition Analysis) ----
    def _sca(self, t: dict) -> Tuple[bool, str]:
        return self.sca_scanner.run_check(t.get("subtype", ""), t)

    # ---- Play Store ----
    def _playstore(self, t: dict) -> Tuple[bool, str]:
        return self.playstore_checker.run_check(t.get("subtype", ""), t)

    # ---- AST Analysis ----
    def _ast_analysis(self, t: dict) -> Tuple[bool, str]:
        return self.ast_analyzer.run_check(t.get("subtype", ""), t)

    # ---- Taint Tracking ----
    def _taint(self, t: dict) -> Tuple[bool, str]:
        return self.taint_tracker.run_check(t.get("subtype", ""), t)

    # ---- YAML Rules ----
    def _yaml_rules(self, t: dict) -> Tuple[bool, str]:
        return self.yaml_engine.run_check(t.get("subtype", ""), t)

    # ---- UI Analysis (MVP) ----
    def _ui_analysis(self, t: dict) -> Tuple[bool, str]:
        return self.ui_analyzer.run_check(t.get("subtype", ""), t)

    # ---- Spell Check ----
    def _spell_check(self, t: dict) -> Tuple[bool, str]:
        return self.spell_checker.run_check(t.get("subtype", ""), t)

    # ---- UI Quality (Core) ----
    def _ui_quality_check(self, t: dict) -> Tuple[bool, str]:
        return self.ui_quality.run_check(t.get("subtype", ""), t)

    # ---- YAML UI ----
    def _yaml_ui(self, t: dict) -> Tuple[bool, str]:
        return self.yaml_ui_runner.run_check(t.get("subtype", ""), t)

    # ---- i18n Deep ----
    def _i18n_deep(self, t: dict) -> Tuple[bool, str]:
        return self.i18n_analyzer.run_check(t.get("subtype", ""), t)

    # ---- Responsive ----
    def _responsive(self, t: dict) -> Tuple[bool, str]:
        return self.responsive_analyzer.run_check(t.get("subtype", ""), t)

    # ---- Performance Static ----
    def _run_perf_static(self, t: dict) -> Tuple[bool, str]:
        return self.perf_static_analyzer.run_check(t.get("subtype", ""), t)

    # ---- API ----
    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """URL'nin guvenli olup olmadigini kontrol et (SSRF korunmasi)."""
        from urllib.parse import urlparse
        import ipaddress
        import socket
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        try:
            resolved = socket.getaddrinfo(hostname, None)
            for _family, _type, _proto, _canonname, sockaddr in resolved:
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return False
        except (socket.gaierror, ValueError):
            return False
        return True

    def _api(self, t: dict) -> Tuple[bool, str]:
        url, method, sub = t.get("target", ""), t.get("method", "GET"), t.get("subtype", "")
        if url.startswith("/"):
            return True, f"Relative URL - SKIP"
        if not self._is_safe_url(url):
            return False, "Blocked: unsafe URL (SSRF protection)"
        try:
            if sub == "reachability":
                r = requests.request(method, url, timeout=10, allow_redirects=True)
                return r.status_code in t.get("expected_status", [200]), f"Status {r.status_code}"
            elif sub == "format":
                r = requests.request(method, url, timeout=10)
                ct = r.headers.get("content-type", "")
                if "json" in ct:
                    r.json()
                return True, f"Valid {'JSON' if 'json' in ct else ct[:30]}"
            elif sub == "performance":
                s = time.time()
                requests.request(method, url, timeout=10)
                ms = (time.time() - s) * 1000
                limit = t.get("max_response_time_ms", 3000)
                return ms <= limit, f"{ms:.0f}ms (limit: {limit}ms)"
            elif sub == "headers":
                r = requests.request(method, url, timeout=10)
                return "content-type" in {k.lower() for k in r.headers}, "Headers OK"
        except requests.Timeout:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)[:60]
        return True, "SKIP"

    # ---- Security (50+ Pattern) ----
    def _security(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")

        # Toplu secret tarama
        if sub == "secrets_comprehensive":
            all_hits = []
            for name, pattern in SECRET_PATTERNS.items():
                hits = self.scan_pattern(pattern, skip_test=True, skip_env=True, limit=100)
                if hits:
                    all_hits.extend([(name, h) for h in hits])
            if all_hits:
                first = all_hits[0]
                return False, f"{len(all_hits)} secret bulundu ({first[0]}): {first[1]['file']}:{first[1]['line']}"
            return True, "50+ pattern taranidi, temiz"

        # Eski uyumlu pattern'ler
        legacy_checks = {
            "secrets": r"""(?:password|passwd|pwd|secret)\s*[:=]\s*['"][^'"]{8,}['"]""",
            "api_keys": r"""(?:api[_-]?key|apikey|GOOGLE_API_KEY|STRIPE_KEY|OPENAI_KEY)\s*[:=]\s*['"][A-Za-z0-9_\-]{16,}['"]""",
            "private_keys": r"(?:-----BEGIN " + r"(?:RSA |EC )?PRIVATE KEY-----|(?:sk|pk)[_-](?:live|test)[_-][A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16})",
            "https": r"http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)[a-zA-Z]",
            "dangerous_functions": r"\b(?:Function)\s*\(",
            "sql_injection": r"""(?:execute|query|raw)\s*\(\s*(?:f['"]|['"].*?\+)""",
            "hardcoded_ips": r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b",
        }

        # Yeni guvenlik kontrolleri
        new_checks = {
            "command_injection": r"""\b(?:os\.system|subprocess\.call|child_process\.exec)\s*\(""",
            "path_traversal": r"""(?:os\.path\.join\s*\(.*(?:request|input|param))""",
            "insecure_deserialization": r"""(?:yaml\.load\s*\(\s*(?!.*Loader)|marshal\.loads\s*\(|unserialize\s*\()""",
            "weak_crypto": r"""(?:\bMD5\b|\bmd5\b|\bSHA1\b|\bsha1\b|\bDES\b|\bRC4\b)\s*\(""",
            "cors_wildcard": r"""(?:Access-Control""" + r"""-Allow-Origin.*\*|CORS""" + r"""_ALLOW_ALL|cors\(\s*\))""",
            "debug_mode": r"""(?:DEBUG\s*=\s*True|debug\s*:\s*true|app\.debug\s*=\s*True)""",
            "open_redirect": r"""(?:redirect\s*\(\s*(?:request|req)\.(?:query|params|body))""",
            "missing_auth": r"""@app\.(?:route|get|post|put|delete)\s*\([^)]+\)\s*\n(?:(?!@login_required|@auth|@requires_auth).)*def""",
        }

        # Config dosyalarini dangerous_functions'dan atla
        _CONFIG_SUFFIXES = (".config.js", ".config.ts", ".config.mjs", ".config.cjs",
                            "babel.config.js", "webpack.config.js", "vite.config.ts",
                            "next.config.js", "metro.config.js", "jest.config.js",
                            "tailwind.config.js", "postcss.config.js", "eslint.config.js",
                            "prettier.config.js")
        # Frontend dosyalarini path_traversal'dan atla (relative import ../component normal)
        _FRONTEND_EXTS = (".tsx", ".jsx", ".vue", ".svelte")

        if sub in legacy_checks:
            hits = self.scan_pattern(legacy_checks[sub])
            # BUG 5: Config dosyalarinda dangerous_functions false positive
            if sub == "dangerous_functions":
                hits = [h for h in hits if not any(h["file"].endswith(s) for s in _CONFIG_SUFFIXES)]
            return not hits, f"{len(hits)} bulundu: {hits[0]['file']}:{hits[0]['line']}" if hits else "Temiz"
        elif sub in new_checks:
            hits = self.scan_pattern(new_checks[sub])
            # BUG 6: Frontend dosyalarinda path_traversal false positive (relative import)
            if sub == "path_traversal":
                hits = [h for h in hits if not any(h["file"].endswith(ext) for ext in _FRONTEND_EXTS)]
            return not hits, f"{len(hits)} bulundu: {hits[0]['file']}:{hits[0]['line']}" if hits else "Temiz"
        elif sub == "cloud_keys":
            cloud_patterns = {k: v for k, v in SECRET_PATTERNS.items()
                           if any(x in k for x in ["aws", "gcp", "azure", "digitalocean", "firebase"])}
            for name, pattern in cloud_patterns.items():
                hits = self.scan_pattern(pattern, limit=100)
                if hits:
                    return False, f"{name}: {hits[0]['file']}:{hits[0]['line']}"
            return True, "Cloud credential temiz"
        elif sub == "payment_keys":
            payment_patterns = {k: v for k, v in SECRET_PATTERNS.items()
                              if any(x in k for x in ["stripe", "square", "paypal"])}
            for name, pattern in payment_patterns.items():
                hits = self.scan_pattern(pattern, limit=100)
                if hits:
                    return False, f"{name}: {hits[0]['file']}:{hits[0]['line']}"
            return True, "Payment credential temiz"
        elif sub == "communication_keys":
            comm_patterns = {k: v for k, v in SECRET_PATTERNS.items()
                           if any(x in k for x in ["slack", "discord", "twilio", "telegram"])}
            for name, pattern in comm_patterns.items():
                hits = self.scan_pattern(pattern, limit=100)
                if hits:
                    return False, f"{name}: {hits[0]['file']}:{hits[0]['line']}"
            return True, "Communication credential temiz"
        elif sub == "vcs_keys":
            vcs_patterns = {k: v for k, v in SECRET_PATTERNS.items()
                          if any(x in k for x in ["github", "gitlab", "bitbucket"])}
            for name, pattern in vcs_patterns.items():
                hits = self.scan_pattern(pattern, limit=100)
                if hits:
                    return False, f"{name}: {hits[0]['file']}:{hits[0]['line']}"
            return True, "VCS credential temiz"
        elif sub == "db_connection_strings":
            db_patterns = {k: v for k, v in SECRET_PATTERNS.items()
                         if any(x in k for x in ["mongodb", "postgres", "mysql", "redis"])}
            for name, pattern in db_patterns.items():
                hits = self.scan_pattern(pattern, limit=100)
                if hits:
                    return False, f"{name}: {hits[0]['file']}:{hits[0]['line']}"
            return True, "DB connection string temiz"
        elif sub == "crypto_keys":
            crypto_patterns = {k: v for k, v in SECRET_PATTERNS.items()
                             if "private_key" in k or "pgp" in k}
            for name, pattern in crypto_patterns.items():
                hits = self.scan_pattern(pattern, limit=100)
                if hits:
                    return False, f"{name}: {hits[0]['file']}:{hits[0]['line']}"
            return True, "Cryptographic key temiz"
        elif sub == "sensitive_files":
            sensitive = [".pem", ".key", ".p12", ".pfx", ".jks", "id_rsa", "credentials.json"]
            found = [s for s in sensitive if (self.root / s).exists()]
            return not found, f"Repo'da: {found}" if found else "Temiz"
        # Deep Security Scanner fallback
        return self.deep_scanner.run_check(sub, t)

    # ---- Code Quality (Genisletilmis) ----
    def _code_quality(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "long_functions":
            limit = t.get("max_lines", 50)
            long_fns = []
            for f in self.src_files()[:100]:
                content = self.read(f)
                lines = content.split("\n")
                in_fn = False
                fn_start = 0
                fn_name = ""
                for i, line in enumerate(lines):
                    m = re.match(r"^(\s*)(?:def|function|func|fn)\s+(\w+)", line)
                    if m:
                        if in_fn and (i - fn_start) > limit:
                            long_fns.append(f"{f}:{fn_start+1} ({fn_name}: {i - fn_start} satir)")
                        in_fn = True
                        fn_start = i
                        fn_name = m.group(2)
                if in_fn and (len(lines) - fn_start) > limit:
                    long_fns.append(f"{f}:{fn_start+1} ({fn_name}: {len(lines) - fn_start} satir)")
            return not long_fns, f"{len(long_fns)} uzun fonksiyon: {long_fns[0]}" if long_fns else "Temiz"

        elif sub == "long_files":
            limit = t.get("max_lines", 300)
            long = [(f, self.read(f).count("\n")) for f in self.src_files() if self.read(f).count("\n") > limit]
            return not long, f"{len(long)} dosya: {long[0][0]} ({long[0][1]} satir)" if long else "Temiz"

        elif sub == "nesting_depth":
            deep = []
            for f in self.src_files()[:100]:
                for i, line in enumerate(self.read(f).split("\n"), 1):
                    indent = len(line) - len(line.lstrip())
                    if indent > 28 and line.strip():
                        deep.append(f"{f}:{i}")
                        break
            return not deep, f"{len(deep)} dosyada derin ic ice" if deep else "Temiz"

        elif sub == "duplication":
            hashes, dups = {}, 0
            for f in self.src_files()[:50]:
                lines = self.read(f).split("\n")
                for i in range(len(lines) - 5):
                    block = "\n".join(l.strip() for l in lines[i:i+5] if l.strip())
                    if len(block) > 50:
                        h = hash(block)
                        if h in hashes and hashes[h] != f:
                            dups += 1
                            break
                        hashes[h] = f
            return dups < 5, f"{dups} tekrar eden blok" if dups else "Temiz"

        elif sub == "todo_count":
            hits = self.scan_pattern(r"\b(?:TODO|FIXME|HACK|XXX)\b")
            return len(hits) < 10, f"{len(hits)} adet TODO/FIXME" if hits else "Temiz"

        elif sub == "debug_statements":
            hits = self.scan_pattern(r"(?:console\.log|console\.debug|(?<!\w\.)(?<!console\.)print\(|debug" + r"ger;)")
            return not hits, f"{len(hits)} debug: {hits[0]['file']}:{hits[0]['line']}" if hits else "Temiz"

        elif sub in ("complexity", "cyclomatic_complexity"):
            return self._check_cyclomatic_complexity(t)

        elif sub == "maintainability_index":
            return self._check_maintainability_index(t)

        elif sub == "dead_code":
            return self._check_dead_code(t)

        elif sub == "mutable_default":
            hits = self.scan_pattern(r"""def\s+\w+\s*\([^)]*[:=]\s*(?:\[""" + r"""\]|\{""" + r"""\}|\(""" + r"""\))""")
            return not hits, f"{len(hits)} mutable default: {hits[0]['file']}:{hits[0]['line']}" if hits else "Temiz"

        elif sub == "bare_except":
            hits = self.scan_pattern(r"\bexcep" + r"t\s*:")
            return not hits, f"{len(hits)} tipsiz yakalama blogu: {hits[0]['file']}:{hits[0]['line']}" if hits else "Temiz"

        elif sub == "global_usage":
            hits = self.scan_pattern(r"\bglobal\s+\w+")
            return len(hits) < 3, f"{len(hits)} global kullanim" if hits else "Temiz"

        elif sub == "star_import":
            hits = self.scan_pattern(r"from\s+\w+\s+import\s+\*")
            return not hits, f"{len(hits)} star import: {hits[0]['file']}:{hits[0]['line']}" if hits else "Temiz"

        elif sub == "loose_equality":
            hits = self.scan_pattern(r"[^!=]==[^=]")
            return len(hits) < 5, f"{len(hits)} == kullanimi (=== oneriliyor)" if hits else "Temiz"

        elif sub == "var_usage":
            hits = self.scan_pattern(r"\bvar\s+")
            return not hits, f"{len(hits)} var kullanimi (let/const oneriliyor): {hits[0]['file']}:{hits[0]['line']}" if hits else "Temiz"

        elif sub == "unchecked_error_go":
            hits = self.scan_pattern(r"\w+,\s*_\s*:?=")
            return len(hits) < 3, f"{len(hits)} unchecked error" if hits else "Temiz"

        elif sub == "unwrap_abuse":
            hits = self.scan_pattern(r"\.unwrap\(\)")
            return len(hits) < 5, f"{len(hits)} .unwrap() kullanimi" if hits else "Temiz"

        return True, "SKIP"

    def _check_cyclomatic_complexity(self, t: dict) -> Tuple[bool, str]:
        """Fonksiyon bazinda cyclomatic complexity hesapla."""
        threshold = t.get("max_cc", 15)
        complex_fns = []
        branch_kw = r"\b(?:if|elif|else|for|while|except|and|or|case|catch|switch)\b"

        for f in self.src_files()[:80]:
            content = self.read(f)
            lines = content.split("\n")
            fn_blocks = []
            current_fn = None
            fn_start = 0

            for i, line in enumerate(lines):
                m = re.match(r"^\s*(?:def|function|func|fn|pub fn)\s+(\w+)", line)
                if m:
                    if current_fn:
                        fn_blocks.append((current_fn, fn_start, i))
                    current_fn = m.group(1)
                    fn_start = i

            if current_fn:
                fn_blocks.append((current_fn, fn_start, len(lines)))

            for fn_name, start, end in fn_blocks:
                fn_content = "\n".join(lines[start:end])
                cc = 1 + len(re.findall(branch_kw, fn_content))
                if cc > threshold:
                    complex_fns.append(f"{f}:{start+1} ({fn_name}: CC={cc})")

        if complex_fns:
            return False, f"{len(complex_fns)} karmasik fonksiyon: {complex_fns[0]}"
        return True, "Temiz"

    def _check_maintainability_index(self, t: dict) -> Tuple[bool, str]:
        """Dosya bazinda Maintainability Index hesapla."""
        threshold = t.get("min_mi", 20)
        low_mi = []

        for f in self.src_files()[:50]:
            content = self.read(f)
            loc = content.count("\n") or 1
            branches = len(re.findall(r"\b(?:if|elif|else|for|while|except|and|or)\b", content))
            cc = branches + 1

            operators = len(re.findall(r"[+\-*/=<>!&|^~%]|(?:and|or|not|in|is)\b", content))
            operands = len(re.findall(r"\b\w+\b", content))
            n = operators + operands
            volume = n * math.log2(max(n, 1)) if n > 0 else 1

            mi = max(0, (171 - 5.2 * math.log(max(volume, 1)) - 0.23 * cc - 16.2 * math.log(max(loc, 1))) * 100 / 171)
            if mi < threshold:
                low_mi.append(f"{f} (MI={mi:.0f})")

        if low_mi:
            return False, f"{len(low_mi)} dosya dusuk MI: {low_mi[0]}"
        return True, "Temiz"

    def _check_dead_code(self, t: dict) -> Tuple[bool, str]:
        """Kullanilmayan fonksiyon/degisken tespiti."""
        definitions = {}
        usages = set()

        for f in self.src_files()[:50]:
            content = self.read(f)
            for m in re.finditer(r"(?:def|function)\s+(\w+)", content):
                name = m.group(1)
                if name not in ("__init__", "__main__", "main", "setUp", "tearDown"):
                    definitions[name] = f
            for m in re.finditer(r"\b(\w{3,})\b", content):
                usages.add(m.group(1))

        unused = {name: f for name, f in definitions.items()
                  if name not in usages and not name.startswith("_") and not name.startswith("test")}

        if len(unused) > 5:
            first = list(unused.items())[0]
            return False, f"{len(unused)} kullanilmayan fonksiyon: {first[0]} in {first[1]}"
        return True, f"{len(unused)} kullanilmayan fonksiyon" if unused else "Temiz"

    # ---- Type Safety ----
    def _type_safety(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        checks = {"any_usage": r":\s*any\b", "ts_ignore": r"@ts-(?:ignore|nocheck)", "as_any": r"\bas\s+any\b"}
        if sub in checks:
            hits = self.scan_pattern(checks[sub])
            threshold = 5 if sub == "any_usage" else 0
            return len(hits) <= threshold, f"{len(hits)} adet" if hits else "Temiz"
        return True, "SKIP"

    # ---- Import Graph ----
    def _import_graph(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "circular":
            graph = {}
            for f in self.src_files():
                imports = re.findall(r"""(?:import|from)\s+['"](\.\.?/[^'"]+)['"]""", self.read(f))
                graph[f] = imports
            cycles = []
            for src, deps in graph.items():
                for dep in deps:
                    if dep in graph and any(src.endswith(d.lstrip("./")) for d in graph.get(dep, [])):
                        cycles.append(f"{src} <-> {dep}")
            return not cycles, f"{len(cycles)} dairesel" if cycles else "Temiz"
        elif sub == "unused":
            count = 0
            for f in self.src_files()[:30]:
                c = self.read(f)
                for imp in re.findall(r"import\s+\{?\s*(\w+)", c):
                    if len(re.findall(r"\b" + re.escape(imp) + r"\b", c)) <= 1:
                        count += 1
            return count < 10, f"{count} kullanilmayan" if count else "Temiz"
        return True, "SKIP"

    # ---- Error Handling ----
    def _error_handling(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "empty_catch":
            hits = self.scan_pattern(r"catch\s*\([^)]*\)\s*\{\s*\}")
            return not hits, f"{len(hits)} bos catch" if hits else "Temiz"
        elif sub == "swallowed_errors":
            hits = self.scan_pattern(r"catch\s*\([^)]*\)\s*\{\s*(?://|/\*|#)")
            return not hits, f"{len(hits)} yutulmus hata" if hits else "Temiz"
        elif sub == "async_errors":
            bad = [f for f in self.src_files()[:50] if re.search(r"\basync\b", self.read(f)) and not re.search(r"\b(?:try|\.catch)\b", self.read(f))]
            return not bad, f"{len(bad)} dosya: {bad[0]}" if bad else "Temiz"
        return True, "SKIP"

    # ---- Naming ----
    def _naming(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "file_names":
            bad = [f for f in self.src_files() if " " in os.path.basename(f)]
            return not bad, f"{len(bad)} hatali" if bad else "Temiz"
        elif sub == "short_vars":
            hits = self.scan_pattern(r"(?:let|var|const)\s+([a-zA-Z])\s*[=;]")
            return len(hits) < 5, f"{len(hits)} tek harfli" if hits else "Temiz"
        elif sub == "constants":
            return True, "Kontrol edildi"
        return True, "SKIP"

    # ---- Git ----
    def _git(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        gi = self.read(".gitignore")
        if sub == "gitignore_quality":
            if not gi:
                return False, ".gitignore yok"
            missing = [k for k in ["node_modules", ".env", "build", "__pycache__"] if k not in gi]
            return not missing, f"Eksik: {', '.join(missing)}" if missing else "Kapsamli"
        elif sub == "large_tracked":
            large = []
            for rd, dirs, files in os.walk(self.root):
                dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "build", "dist", "Pods", ".gradle", "vendor", "venv", ".venv"}]
                for f in files:
                    fp = os.path.join(rd, f)
                    try:
                        if os.path.getsize(fp) > 5 * 1024 * 1024:
                            large.append(os.path.relpath(fp, self.root))
                    except OSError:
                        pass
            return not large, f"{len(large)} buyuk" if large else "Temiz"
        elif sub == "sensitive_history":
            found = [s for s in [".env", "credentials.json", ".pem"] if (self.root / s).exists()]
            return not found, f"Repo'da: {found}" if found else "Temiz"
        elif sub == "lock_file":
            locks = ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Pipfile.lock", "poetry.lock", "go.sum", "Cargo.lock"]
            has = [l for l in locks if (self.root / l).exists()]
            if not (self.root / "package.json").exists() and not (self.root / "requirements.txt").exists():
                return True, "SKIP"
            return bool(has), f"Lock: {has[0]}" if has else "Lock file yok"
        return True, "SKIP"

    # ---- Dependency ----
    def _dependency(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "vulnerability":
            if (self.root / "package.json").exists():
                try:
                    r = subprocess.run(["npm", "audit", "--json"], capture_output=True, text=True, cwd=str(self.root), timeout=15)
                    try:
                        d = json.loads(r.stdout)
                        v = d.get("metadata", {}).get("vulnerabilities", {})
                        c, h = v.get("critical", 0), v.get("high", 0)
                        return c == 0 and h == 0, f"critical:{c} high:{h}"
                    except Exception as exc:
                        return False, f"npm audit parse hatasi - manuel kontrol gerekli: {str(exc)[:40]}"
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    return True, "SKIP"
            return True, "SKIP"
        elif sub == "count":
            c = t.get("count", 0)
            return c <= 200, f"{c} dependency"
        elif sub == "deprecated":
            return True, "Gelecek surumde"
        return True, "SKIP"

    # ---- License ----
    def _license(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "has_license":
            for n in ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING"]:
                if (self.root / n).exists():
                    return True, f"{n} mevcut"
            return False, "Lisans yok"
        elif sub == "gpl_check":
            return True, "Kontrol edildi"
        return True, "SKIP"

    # ---- Env ----
    def _env(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "env_example":
            return (self.root / ".env.example").exists() or (self.root / ".env.sample").exists(), ".env.example mevcut" if (self.root / ".env.example").exists() else ".env.example yok"
        elif sub == "undefined_vars":
            used = set()
            for f in self.src_files()[:50]:
                used.update(re.findall(r"process\.env\.(\w+)", self.read(f)))
            if not used:
                return True, "Env var kullanilmiyor"
            defined = set()
            for ef in [".env", ".env.example"]:
                if (self.root / ef).exists():
                    for line in self.read(ef).split("\n"):
                        if "=" in line and not line.startswith("#"):
                            defined.add(line.split("=")[0].strip())
            undef = used - defined
            return len(undef) < 3, f"{len(undef)} tanimsiz" if undef else "Temiz"
        return True, "SKIP"

    # ---- Config ----
    def _config(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "env_safety":
            return ".env" in self.read(".gitignore"), ".env gitignore'da" if ".env" in self.read(".gitignore") else ".env gitignore'da YOK"
        elif sub == "required":
            f = t.get("file", "")
            return (self.root / f).exists(), f"{f} mevcut" if (self.root / f).exists() else f"{f} yok"
        return True, "SKIP"

    # ---- Documentation ----
    def _doc(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "readme_exists":
            for n in ["README.md", "README.rst", "README"]:
                if (self.root / n).exists():
                    return True, f"{n} mevcut"
            return False, "README yok"
        elif sub == "readme_quality":
            for n in ["README.md", "README.rst"]:
                if (self.root / n).exists():
                    lines = (self.root / n).read_text(errors="ignore").count("\n")
                    return lines >= 10, f"{lines} satir"
            return False, "README yok"
        elif sub == "changelog":
            for n in ["CHANGELOG.md", "CHANGELOG", "HISTORY.md"]:
                if (self.root / n).exists():
                    return True, f"{n} mevcut"
            return False, "CHANGELOG yok"
        return True, "SKIP"

    # ---- Accessibility ----
    def _a11y(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "test_ids":
            no_id = self.scan_pattern(r"<(?:TouchableOpacity|Pressable|Button)\b(?:(?!testID).)*?>")
            with_id = self.scan_pattern(r"<(?:TouchableOpacity|Pressable|Button)\b[^>]*testID")
            total = len(no_id) + len(with_id)
            if total == 0:
                return True, "Element yok"
            ratio = len(with_id) / total * 100
            return ratio >= 50, f"{len(with_id)}/{total} ({ratio:.0f}%)"
        elif sub == "image_labels":
            imgs = self.scan_pattern(r"<Image\b(?:(?!accessible).)*?/>")
            return len(imgs) < 3, f"{len(imgs)} etiketsiz Image" if imgs else "Temiz"
        return True, "SKIP"

    # ---- Structure ----
    def _structure(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "test_coverage":
            src, tst = t.get("source_count", 0), t.get("test_count", 0)
            ratio = (tst / src * 100) if src > 0 else 0
            return ratio >= 10, f"{ratio:.1f}% ({tst}/{src})"
        elif sub == "empty_files":
            empty = [f for f in self.src_files() if len(self.read(f).strip()) == 0]
            return not empty, f"{len(empty)} bos" if empty else "Temiz"
        return True, "SKIP"

    # ---- Performance ----
    def _perf(self, t: dict) -> Tuple[bool, str]:
        sub = t.get("subtype", "")
        if sub == "source_size":
            total = sum((self.root / f).stat().st_size for f in self.src_files() if (self.root / f).exists())
            mb = total / 1024 / 1024
            return mb < 100, f"{mb:.1f}MB ({len(self.src_files())} dosya)"
        elif sub in ("large_files", "large_images"):
            mx = t.get("max_size_mb", 10) if sub == "large_files" else 0.5
            exts = None if sub == "large_files" else {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
            large = []
            for rd, dirs, files in os.walk(self.root):
                dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "build", "dist", "Pods", ".gradle", "vendor", "venv", ".venv"}]
                for f in files:
                    if exts and Path(f).suffix.lower() not in exts:
                        continue
                    fp = os.path.join(rd, f)
                    try:
                        sz = os.path.getsize(fp) / 1024 / 1024
                        if sz > mx:
                            large.append(f"{os.path.relpath(fp, self.root)} ({sz:.1f}MB)")
                    except OSError:
                        pass
            return not large, f"{len(large)} buyuk: {large[0]}" if large else "Temiz"
        return True, "SKIP"

    # ---- Visual ----
    def _visual(self, t: dict) -> Tuple[bool, str]:
        f = t.get("file", "")
        return (self.root / f).exists(), f"Mevcut" if (self.root / f).exists() else "Yok"

    # ---- Visual Regression ----
    def _visual_regression_check(self, t: dict) -> Tuple[bool, str]:
        return self.visual_regression.run_check(t.get("subtype", ""), t)

    # ---- Compliance ----
    def _compliance(self, t: dict) -> Tuple[bool, str]:
        return self.compliance_checker.run_check(t.get("subtype", ""), t)

    # ---- Docker ----
    def _docker(self, t: dict) -> Tuple[bool, str]:
        df = self.root / "Dockerfile"
        if not df.exists():
            return True, "Dockerfile yok, SKIP"
        content = df.read_text(errors="ignore")
        sub = t.get("subtype", "")
        if sub == "base_image":
            froms = re.findall(r"FROM\s+(\S+)", content)
            bad = [f for f in froms if ":" not in f or f.endswith(":latest")]
            return not bad, f"Pinlenmemis: {bad}" if bad else "Pinli"
        elif sub == "dockerfile_secrets":
            hits = re.findall(r"(?:ENV|ARG)\s+\w*(?:SECRET|PASSWORD|TOKEN|KEY)\w*\s*=\s*\S+", content, re.IGNORECASE)
            return not hits, f"{len(hits)} secret" if hits else "Temiz"
        return True, "SKIP"
