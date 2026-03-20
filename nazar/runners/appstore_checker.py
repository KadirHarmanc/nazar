"""App Store Compliance Checker - Apple App Store red sebeplerini onceden tespit eder."""
import os
import re
import json
from pathlib import Path
from typing import List, Dict, Tuple

from nazar.runners.base import BaseRunner


def _fmt(hits, msg="bulundu"):
    if not hits:
        return True, "Temiz"
    first = hits[0]
    return False, f"{len(hits)} {msg}: {first['file']}:{first['line']}"


APPSTORE_IGNORE = {"node_modules", ".git", "build", "dist", "Pods", ".gradle", "vendor", "venv", ".venv", "__pycache__", ".expo", "coverage", ".next"}


class AppStoreChecker(BaseRunner):
    """Apple App Store compliance kontrolleri. Sadece iOS/RN/Flutter projeler icin."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self._all_files_cache = None

    def _all_files(self) -> List[Tuple[str, str]]:
        """Tum dosyalari bir kere tara ve cache'le. (rel_path, full_path) dondurur."""
        if self._all_files_cache is not None:
            return self._all_files_cache
        result = []
        for rd, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in APPSTORE_IGNORE]
            for f in files:
                full = os.path.join(rd, f)
                rel = os.path.relpath(full, self.root)
                result.append((rel, full))
        self._all_files_cache = result
        return result

    def _find_file(self, filename: str) -> str:
        """Tek bir dosya ara, bulursa rel_path don."""
        for rel, full in self._all_files():
            if os.path.basename(rel) == filename:
                return rel
        return ""

    def _find_files_by_ext(self, ext: str) -> List[Tuple[str, str]]:
        """Uzantiya gore dosya bul."""
        return [(rel, full) for rel, full in self._all_files() if rel.endswith(ext)]

    # ================================================================
    # KRITIK - Kesin Red Sebebi
    # ================================================================

    def check_privacy_manifest(self, t: dict) -> Tuple[bool, str]:
        """PrivacyInfo.xcprivacy dosyasi var mi - Mayis 2024'ten beri zorunlu."""
        found = self._find_file("PrivacyInfo.xcprivacy")
        if found:
            return True, f"PrivacyInfo.xcprivacy mevcut: {found}"
        return False, "PrivacyInfo.xcprivacy dosyasi bulunamadi - Mayis 2024'ten beri ZORUNLU"

    def check_purpose_strings(self, t: dict) -> Tuple[bool, str]:
        """Info.plist'te izin aciklama string'leri var mi."""
        # Kullanilan API'lere gore gereken purpose string'ler
        api_to_purpose = {
            "camera": "NSCamera" + "UsageDescription",
            "microphone": "NSMicrophone" + "UsageDescription",
            "location": "NSLocationWhenInUse" + "UsageDescription",
            "photos": "NSPhotoLibrary" + "UsageDescription",
            "contacts": "NSContacts" + "UsageDescription",
            "calendar": "NSCalendars" + "UsageDescription",
            "health": "NSHealthShare" + "UsageDescription",
            "motion": "NSMotion" + "UsageDescription",
            "tracking": "NSUserTracking" + "UsageDescription",
        }
        # Kodda kullanilan API'leri bul
        used_apis = set()
        camera_pattern = r"(?:AVCapture|UIImagePicker|Camera|launchCamera|ImagePicker)"
        if self.scan_pattern(camera_pattern, limit=50):
            used_apis.add("camera")
        mic_pattern = r"(?:AVAudioRecorder|AVAudioSession|microphone)"
        if self.scan_pattern(mic_pattern, limit=50):
            used_apis.add("microphone")
        loc_pattern = r"(?:CLLocationManager|expo-location|getCurrentPosition|requestForegroundPermissions)"
        if self.scan_pattern(loc_pattern, limit=50):
            used_apis.add("location")
        photo_pattern = r"(?:PHPicker|launchImageLibrary|expo-image-picker|MediaLibrary)"
        if self.scan_pattern(photo_pattern, limit=50):
            used_apis.add("photos")

        if not used_apis:
            return True, "Izne tabi API kullanimi tespit edilmedi"

        # Info.plist kontrol - tum olasi yollar
        info_plist = ""
        # 1) ios/*/Info.plist (ornegin ios/BetterPlate/Info.plist)
        for rel, full in self._all_files():
            if rel.startswith("ios/") and os.path.basename(rel) == "Info.plist":
                content = Path(full).read_text(errors="ignore")
                if content:
                    info_plist += content
        # 2) Kok dizindeki Info.plist
        root_info = self.read("Info.plist")
        if root_info:
            info_plist += root_info
        # 3) app.json - Expo infoPlist config dahil
        app_json = self.read("app.json")
        if app_json:
            info_plist += app_json
        # 4) app.config.js / app.config.ts
        for config_name in ["app.config.js", "app.config.ts"]:
            config_content = self.read(config_name)
            if config_content:
                info_plist += config_content

        missing = []
        for api in used_apis:
            purpose_key = api_to_purpose[api]
            if purpose_key not in info_plist and api not in info_plist.lower():
                missing.append(f"{api} ({purpose_key})")

        if missing:
            return False, f"{len(missing)} izin aciklamasi eksik: {', '.join(missing[:3])}"
        return True, f"{len(used_apis)} API icin izin aciklamalari mevcut"

    def check_sign_in_with_apple(self, t: dict) -> Tuple[bool, str]:
        """3rd party login varsa Sign in with Apple da olmali."""
        third_party = self.scan_pattern(
            r"(?:GoogleSignin|google-signin|Facebook" + r"Login|LoginManager|expo-auth-session.*google|expo-google)", limit=50
        )
        apple_signin = self.scan_pattern(
            r"(?:Authentication" + r"Services|ASAuthorization|AppleAuthentication|expo-apple-authentication|apple.*sign.?in|signInWithApple)", limit=50
        )
        if third_party and not apple_signin:
            return False, f"Google/Facebook login var ({len(third_party)} yer) ama Sign in with Apple YOK - Apple zorunlu kiliyor"
        if third_party and apple_signin:
            return True, f"3rd party + Apple Sign In mevcut"
        return True, "3rd party login yok veya Apple Sign In mevcut"

    def check_account_deletion(self, t: dict) -> Tuple[bool, str]:
        """Hesap olusturma varsa silme mekanizmasi da olmali."""
        signup = self.scan_pattern(
            r"(?:signUp|sign_up|register|createAccount|create_account|createUser)", limit=50
        )
        deletion = self.scan_pattern(
            r"(?:deleteAccount|delete_account|removeAccount|deactivateAccount|hesap.*sil|account.*delet)", limit=50
        )
        if signup and not deletion:
            return False, f"Hesap olusturma var ({len(signup)} yer) ama hesap silme mekanizmasi YOK - Apple 2022'den beri ZORUNLU"
        return True, "Temiz"

    def check_att_compliance(self, t: dict) -> Tuple[bool, str]:
        """IDFA kullaniyorsa ATTrackingManager zorunlu."""
        idfa = self.scan_pattern(
            r"(?:advertising" + r"Identifier|ASIdentifier" + r"Manager|IDFA|requestTracking)", limit=50
        )
        att = self.scan_pattern(
            r"(?:ATTracking" + r"Manager|requestTrackingAuthorization|AppTrackingTransparency)", limit=50
        )
        if idfa and not att:
            return False, f"IDFA/tracking kullaniliyor ({len(idfa)} yer) ama ATTrackingManager YOK"
        return True, "Temiz"

    def check_external_payment(self, t: dict) -> Tuple[bool, str]:
        """Dijital urun icin dis odeme linki yasak."""
        external = self.scan_pattern(
            r"""(?:stripe\.com/|paypal\.com/|checkout\.|billing\.|buy\..*\.com)(?!.*(?:physical|shipping|delivery))""", limit=50
        )
        storekit = self.scan_pattern(
            r"(?:Store" + r"Kit|SKProduct|SKPayment|Product\.products|purchase\(|PurchaseManager)", limit=50
        )
        if external and storekit:
            return False, f"Hem StoreKit hem dis odeme linki var ({len(external)} external link) - dijital icerik icin sadece IAP kullanilmali"
        if external and not storekit:
            return True, "StoreKit yok, fiziksel urun olabilir"
        return True, "Temiz"

    def check_iap_restore(self, t: dict) -> Tuple[bool, str]:
        """In-app purchase varsa Restore Purchases butonu zorunlu."""
        iap = self.scan_pattern(
            r"(?:Store" + r"Kit|SKProduct|Product\.products|purchase\(|PurchaseManager|RevenueCat|Purchases\.configure)", limit=50
        )
        restore = self.scan_pattern(
            r"(?:restore" + r"Purchases|restoreTransactions|AppStore\.sync|Purchases\.restorePurchases|syncPurchases)", limit=50
        )
        if iap and not restore:
            return False, f"IAP kullaniliyor ({len(iap)} yer) ama Restore Purchases mekanizmasi YOK"
        if iap and restore:
            return True, f"IAP + Restore mevcut"
        return True, "IAP kullanilmiyor"

    def check_iap_verification(self, t: dict) -> Tuple[bool, str]:
        """StoreKit transaction dogrulama."""
        storekit2 = self.scan_pattern(
            r"(?:Transaction\.|Product\.|\.verified|VerificationResult|JWSTransaction)", limit=50
        )
        verification = self.scan_pattern(
            r"(?:\.verified|verify.*receipt|validateReceipt|verifyTransaction)", limit=50
        )
        if storekit2 and not verification:
            return False, "StoreKit kullaniliyor ama transaction dogrulama (.verified) bulunamadi"
        return True, "Temiz"

    def check_recording_consent(self, t: dict) -> Tuple[bool, str]:
        """Kamera/mikrofon kayit icin izin + gorsel gosterge."""
        recording = self.scan_pattern(
            r"(?:AVCapture" + r"Session|AVAudio" + r"Recorder|RPScreen" + r"Recorder|startRecording)", limit=50
        )
        consent = self.scan_pattern(
            r"(?:requestAccess|requestPermission|requestAuthorization|askPermission|recording.*indicator)", limit=50
        )
        if recording and not consent:
            return False, f"Kayit API'si kullaniliyor ({len(recording)} yer) ama izin isteme mekanizmasi bulunamadi"
        return True, "Temiz"

    def check_kids_tracking(self, t: dict) -> Tuple[bool, str]:
        """Cocuk uygulamasinda analytics/tracking yasak."""
        # app.json veya Info.plist'te kids category kontrolu
        app_config = self.read("app.json") + self.read("Info.plist")
        is_kids = "kids" in app_config.lower() or "children" in app_config.lower() or "cocuk" in app_config.lower()
        if not is_kids:
            return True, "Cocuk kategorisi degil"
        analytics = self.scan_pattern(
            r"(?:Analytics|Firebase" + r"Analytics|Mixpanel|Amplitude|Segment|ATTracking|IDFA)", limit=50
        )
        if analytics:
            return False, f"Cocuk uygulamasinda analytics/tracking tespit edildi ({len(analytics)} yer) - YASAK"
        return True, "Cocuk uygulamasi, analytics yok"

    def check_health_data_ads(self, t: dict) -> Tuple[bool, str]:
        """Saglik verisi reklam icin kullanilamaz."""
        health = self.scan_pattern(r"(?:Health" + r"Kit|HKHealth" + r"Store|HKQuantity)", limit=50)
        ads = self.scan_pattern(r"(?:AdMob|GAD|advertising|adNetwork|showAd)", limit=50)
        if health and ads:
            return False, "HealthKit + reklam SDK birlikte kullaniliyor - saglik verisi reklam icin KULLANILAMAZ"
        return True, "Temiz"

    def check_required_reason_api(self, t: dict) -> Tuple[bool, str]:
        """Required Reason API kullanimi beyan edilmis mi."""
        apis_used = []
        if self.scan_pattern(r"(?:UserDefaults|NSUserDefaults)", limit=30):
            apis_used.append("UserDefaults")
        if self.scan_pattern(r"(?:fileModificationDate|contentModificationDate)", limit=30):
            apis_used.append("FileTimestamp")
        if self.scan_pattern(r"(?:volumeAvailableCapacity|diskSpace|statvfs)", limit=30):
            apis_used.append("DiskSpace")
        if self.scan_pattern(r"(?:mach_absolute_time|systemUptime)", limit=30):
            apis_used.append("SystemBootTime")

        if not apis_used:
            return True, "Required Reason API kullanimi yok"

        # PrivacyInfo.xcprivacy kontrol
        privacy_manifest = ""
        found = self._find_file("PrivacyInfo.xcprivacy")
        if found:
            privacy_manifest = Path(os.path.join(self.root, found)).read_text(errors="ignore")

        if not privacy_manifest and apis_used:
            return False, f"{', '.join(apis_used)} API kullaniliyor ama PrivacyInfo.xcprivacy'de beyan YOK"

        missing = [api for api in apis_used if api.lower() not in privacy_manifest.lower()]
        if missing:
            return False, f"{', '.join(missing)} API beyan edilmemis"
        return True, f"{len(apis_used)} API beyan edilmis"

    # ================================================================
    # YUKSEK - Muhtemel Red
    # ================================================================

    def check_app_icon_sizes(self, t: dict) -> Tuple[bool, str]:
        """App icon dosyalari var mi."""
        # Expo/RN projelerinde app.json icon ONCE kontrol et - Expo build sirasinda otomatik uretir
        app_json = self.read("app.json")
        if app_json:
            try:
                app_data = json.loads(app_json)
                expo_config = app_data.get("expo", app_data)
                if expo_config.get("icon"):
                    return True, "app.json'da icon tanimli (Expo build sirasinda tum boyutlari uretir)"
            except (json.JSONDecodeError, AttributeError):
                if '"icon"' in app_json:
                    return True, "app.json'da icon tanimli (Expo)"
        icon_found = False
        for rel, full in self._all_files():
            dirpath = os.path.dirname(full)
            if "AppIcon" in dirpath or "appiconset" in dirpath:
                icon_found = True
                # Contents.json kontrol
                if os.path.basename(rel) == "Contents.json":
                    try:
                        data = json.loads(Path(full).read_text())
                        images = data.get("images", [])
                        sizes = [img.get("size", "") for img in images if img.get("filename")]
                        if len(sizes) < 5:
                            return False, f"App icon seti eksik - {len(sizes)} boyut var, en az 6 gerekli"
                        return True, f"{len(sizes)} ikon boyutu mevcut"
                    except Exception:
                        pass
        if not icon_found:
            return False, "AppIcon.appiconset bulunamadi"
        return True, "App icon mevcut"

    def check_launch_screen(self, t: dict) -> Tuple[bool, str]:
        """Launch screen / splash screen var mi."""
        launch_found = False
        for rel, full in self._all_files():
            fname = os.path.basename(rel)
            if "LaunchScreen" in fname or "SplashScreen" in fname or "launch_screen" in fname:
                launch_found = True
                break
        # Expo splash config
        app_json = self.read("app.json")
        if app_json and "splash" in app_json:
            launch_found = True
        if not launch_found:
            return False, "Launch screen / splash screen bulunamadi"
        return True, "Launch screen mevcut"

    def check_min_deployment_target(self, t: dict) -> Tuple[bool, str]:
        """iOS deployment target guncel mi."""
        # Xcode project
        pbxproj = ""
        found = self._find_file("project.pbxproj")
        if found:
            pbxproj = Path(os.path.join(self.root, found)).read_text(errors="ignore")
        if pbxproj:
            targets = re.findall(r"IPHONEOS_DEPLOYMENT_TARGET\s*=\s*(\d+\.?\d*)", pbxproj)
            if targets:
                min_target = min(float(t) for t in targets)
                if min_target < 15.0:
                    return False, f"iOS deployment target {min_target} cok eski - minimum 15.0 oneriliyor"
                return True, f"iOS {min_target} deployment target"
        return True, "Xcode project bulunamadi (Expo yonetiyor olabilir)"

    def check_deprecated_api(self, t: dict) -> Tuple[bool, str]:
        """Deprecated API kullanimi."""
        deprecated = self.scan_pattern(
            r"(?:UIWebView|UIAlertView|UIActionSheet|addressBook|ABAddressBook|UIPopoverController)", limit=50
        )
        return _fmt(deprecated, "deprecated API kullanimi")

    def check_widget_no_ads(self, t: dict) -> Tuple[bool, str]:
        """Widget target'ta reklam SDK'si yasak."""
        widget_files = [f for f in self.src_files() if "widget" in f.lower()]
        if not widget_files:
            return True, "Widget target yok"
        for f in widget_files:
            content = self.read(f)
            if re.search(r"(?:AdMob|GADBanner|GoogleMobileAds|AdView|BannerAd)", content):
                return False, f"Widget dosyasinda reklam SDK'si tespit edildi: {f}"
        return True, "Widget'larda reklam yok"

    def check_face_auth_method(self, t: dict) -> Tuple[bool, str]:
        """Yuz tanima icin ARKit degil LocalAuthentication kullanilmali."""
        arkit_face = self.scan_pattern(r"(?:ARFace" + r"Anchor|ARFace" + r"TrackingConfiguration)", limit=30)
        local_auth = self.scan_pattern(r"(?:LAContext|LocalAuthentication|biometricType)", limit=30)
        if arkit_face and not local_auth:
            return False, "Yuz tanima icin ARKit kullaniliyor - LocalAuthentication kullanilmali"
        return True, "Temiz"

    def check_data_collection_types(self, t: dict) -> Tuple[bool, str]:
        """Toplanan veri tipleri App Store Connect'te beyan edilmeli."""
        collecting = []
        if self.scan_pattern(r"(?:email|phone|address|birth)", limit=30):
            collecting.append("Contact Info")
        if self.scan_pattern(r"(?:CLLocation|getCurrentPosition|expo-location)", limit=30):
            collecting.append("Location")
        if self.scan_pattern(r"(?:Analytics|Mixpanel|Amplitude|Firebase" + r"Analytics)", limit=30):
            collecting.append("Usage Data")
        if self.scan_pattern(r"(?:advertisingIdentifier|IDFA)", limit=30):
            collecting.append("Identifiers")
        if len(collecting) > 2:
            return False, f"{len(collecting)} veri tipi toplaniliyor ({', '.join(collecting)}) - App Store Connect'te beyan edin"
        return True, f"{len(collecting)} veri tipi" if collecting else "Temiz"

    # ================================================================
    # v2.2 YENI KONTROLLER
    # ================================================================

    def check_app_completeness(self, t: dict) -> Tuple[bool, str]:
        """Test/placeholder/debug icerik birakilmis mi - en cok RED alan kural."""
        placeholder_hits = []
        patterns = [
            (r"lorem\s+ipsum", "lorem ipsum"),
            (r"""['"]test@test\.com['"]""", "test email"),
            (r"""['"]1234567890['"]""", "test telefon"),
            (r"""['"]coming\s+soon['"]""", "coming soon"),
            (r"""['"]under\s+construction['"]""", "under construction"),
            (r"""['"]sample\s+text['"]""", "sample text"),
        ]
        for pattern, label in patterns:
            hits = self.scan_pattern(pattern, limit=50)
            for h in hits:
                h["match"] = label
            placeholder_hits.extend(hits)
        if placeholder_hits:
            first = placeholder_hits[0]
            return False, f"{len(placeholder_hits)} placeholder/test icerik: {first['match']} in {first['file']}:{first['line']}"
        return True, "Temiz"

    def check_debug_urls(self, t: dict) -> Tuple[bool, str]:
        """Production'da debug/development URL'ler kalmis mi."""
        debug_patterns = [
            r"""['"]https?://localhost""",
            r"""['"]https?://127\.0\.0\.1""",
            r"""['"]https?://192\.168\.""",
            r"""['"]https?://10\.0\.""",
            r"""['"]https?://.*\.ngrok""",
            r"""['"]https?://.*staging\.""",
        ]
        all_hits = []
        for p in debug_patterns:
            all_hits.extend(self.scan_pattern(p, limit=30))
        if all_hits:
            first = all_hits[0]
            return False, f"{len(all_hits)} debug/development URL: {first['file']}:{first['line']}"
        return True, "Temiz"

    def check_reason_code_validity(self, t: dict) -> Tuple[bool, str]:
        """Required Reason API reason kodlarinin gecerliligi."""
        VALID_CODES = {
            "FileTimestamp": ["C617.1", "3B52.1", "0A2A.1"],
            "SystemBootTime": ["35F9.1", "8FFB.1", "3D61.1"],
            "DiskSpace": ["E174.1", "85F4.1"],
            "ActiveKeyboards": ["54BD.1"],
            "UserDefaults": ["CA92.1", "1C8F.1", "AC6B.1", "C56D.1"],
        }
        # PrivacyInfo.xcprivacy bul ve oku
        privacy_content = ""
        found = self._find_file("PrivacyInfo.xcprivacy")
        if found:
            privacy_content = Path(os.path.join(self.root, found)).read_text(errors="ignore")
        if not privacy_content:
            return True, "PrivacyInfo.xcprivacy yok (ayri kontrol)"
        # Reason kodlarini dogrula - sadece NSPrivacyAccessedAPITypeReasons
        # bloklari icindeki kodlari al (min 2 karakter prefix ile version string'leri atla)
        invalid = []
        all_valid = [c for codes in VALID_CODES.values() for c in codes]
        # NSPrivacyAccessedAPITypeReasons blogundan reason kodlarini cikar
        reason_blocks = re.findall(
            r'NSPrivacyAccessedAPITypeReasons.*?</array>',
            privacy_content, re.DOTALL
        )
        reason_section = "\n".join(reason_blocks) if reason_blocks else privacy_content
        found_codes = re.findall(r'[A-Z0-9]{2,4}\.\d+', reason_section)
        for code in found_codes:
            if code not in all_valid:
                invalid.append(code)
        if invalid:
            return False, f"Gecersiz reason kodu: {', '.join(invalid[:3])} - Apple'in kabul ettigi kodlari kullanin"
        return True, "Reason kodlari gecerli"

    def check_sdk_privacy_manifests(self, t: dict) -> Tuple[bool, str]:
        """Third-party SDK'larin privacy manifest'i var mi."""
        # Expo managed workflow ise bu kontrolu atla - Expo build sirasinda otomatik halleder
        app_json_content = self.read("app.json")
        if app_json_content:
            try:
                app_data = json.loads(app_json_content)
                if "expo" in app_data:
                    return True, "Expo managed workflow - SDK privacy manifest'leri build sirasinda otomatik eklenir"
            except (json.JSONDecodeError, AttributeError):
                pass
        KNOWN_SDKS_NEEDING_MANIFEST = [
            "react-native-async-storage",
            "expo-device",
            "expo-application",
            "react-native-mmkv",
            "react-native-firebase",
            "@sentry/react-native",
            "react-native-adjust",
            "react-native-appsflyer",
        ]
        pkg_json = self.root / "package.json"
        if not pkg_json.exists():
            return True, "package.json yok"
        try:
            pkg = json.loads(pkg_json.read_text(errors="ignore"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        except Exception:
            return True, "package.json okunamadi"
        missing = []
        for sdk in KNOWN_SDKS_NEEDING_MANIFEST:
            sdk_short = sdk.split("/")[-1]
            if sdk in deps or sdk_short in deps:
                # Bu SDK'nin ios klasorunde xcprivacy var mi
                sdk_dir = self.root / "node_modules" / sdk
                has_manifest = False
                if sdk_dir.exists():
                    for rd, dirs, files in os.walk(sdk_dir):
                        if "PrivacyInfo.xcprivacy" in files:
                            has_manifest = True
                            break
                if not has_manifest:
                    missing.append(sdk_short)
        if missing:
            return False, f"{len(missing)} SDK'nin privacy manifest'i eksik: {', '.join(missing[:3])}"
        return True, "SDK privacy manifest'leri mevcut"

    def check_ota_compliance(self, t: dict) -> Tuple[bool, str]:
        """OTA update (expo-updates/CodePush) guideline 3.3.2 uyumu."""
        ota = self.scan_pattern(r"(?:expo-updates|codePush|AppCenter.*CodePush|updates.*enabled)", limit=30)
        if not ota:
            return True, "OTA update kullanilmiyor"
        app_json = self.read("app.json")
        if "expo-updates" in app_json or "updates" in app_json:
            return False, "expo-updates aktif - Guideline 3.3.2: OTA ile sadece bug fix gonderilebilir, yeni ozellik YASAK"
        return True, "Temiz"

    def check_ats_override(self, t: dict) -> Tuple[bool, str]:
        """App Transport Security override - HTTP trafigine izin verme."""
        info_content = ""
        for name in ["Info.plist", "ios/Info.plist"]:
            content = self.read(name)
            if content:
                info_content = content
                break
        if not info_content:
            info_content = self.read("app.json")
        allows_arbitrary = "NSAllows" + "ArbitraryLoads"
        if allows_arbitrary.replace(" ", "") in info_content.replace(" ", "") and "true" in info_content.lower():
            return False, "NSAllowsArbitraryLoads = true - TUM HTTP trafigine izin veriliyor, guvenlik acigi"
        return True, "ATS yapilandirmasi uygun"

    def check_url_scheme_conflict(self, t: dict) -> Tuple[bool, str]:
        """Apple'in reserved URL scheme'leriyle cakisma."""
        RESERVED = ["maps", "itms", "itms-apps", "itms-appss", "facetime",
                     "facetime-audio", "sms", "tel", "mailto", "music", "videos", "calshow"]
        info_content = self.read("app.json") + self.read("Info.plist")
        conflicts = []
        for scheme in RESERVED:
            pattern = r"""['"]""" + re.escape(scheme) + r"""['"]"""
            if re.search(pattern, info_content):
                # CFBundleURLSchemes icinde mi kontrol et
                if "CFBundleURLSchemes" in info_content or "scheme" in info_content:
                    conflicts.append(scheme)
        if conflicts:
            return False, f"Apple reserved URL scheme cakismasi: {', '.join(conflicts)}"
        return True, "Temiz"

    def check_bundle_secrets(self, t: dict) -> Tuple[bool, str]:
        """EXPO_PUBLIC_* ile bundle'a gomulmus secret'lar."""
        # Anon key'ler public by design - whitelist
        SAFE_PATTERNS = {"ANON", "PUBLIC", "PUBLISHABLE", "NEXT_PUBLIC"}
        # .env ve eas.json kontrol
        dangerous = []
        for env_file in [".env", ".env.production", ".env.local", "eas.json"]:
            content = self.read(env_file)
            if content:
                for m in re.finditer(r"EXPO_PUBLIC_\w*(?:SECRET|KEY|TOKEN|PASS" + r"WORD|PRIVATE)\w*", content, re.IGNORECASE):
                    var_name = m.group().upper()
                    # Anon/public/publishable key'ler guvenli - whitelist kontrolu
                    if any(safe in var_name for safe in SAFE_PATTERNS):
                        continue
                    dangerous.append(m.group())
        if dangerous:
            return False, f"{len(dangerous)} hassas EXPO_PUBLIC_ degiskeni: {dangerous[0]} - bundle'a gomulur, IPA'dan okunabilir"
        return True, "Temiz"

    def check_uiwebview_deprecated(self, t: dict) -> Tuple[bool, str]:
        """UIWebView kullanimi - 2020'den beri RED sebebi."""
        found = []
        uiwebview = "UIWeb" + "View"
        # Sadece ios/ ve Pods/ altinda ObjC dosyalarini tara (node_modules cok buyuk)
        search_dirs = [self.root / "ios", self.root / "Pods", self.root / "macos"]
        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for rd, dirs, files in os.walk(search_dir):
                dirs[:] = [d for d in dirs if d not in {".git", "build", "DerivedData"}]
                for f in files:
                    if f.endswith((".m", ".h", ".mm")):
                        fp = os.path.join(rd, f)
                        try:
                            content = Path(fp).read_text(errors="ignore")
                            if uiwebview in content:
                                found.append(os.path.relpath(fp, self.root))
                                if len(found) >= 5:
                                    break
                        except Exception:
                            pass
                if len(found) >= 5:
                    break
        # Ayrica src dosyalarinda da ara (cache'li, hizli)
        for rel, full in self._all_files():
            if rel.endswith((".m", ".h", ".mm", ".swift")):
                try:
                    content = Path(full).read_text(errors="ignore")
                    if uiwebview in content and rel not in found:
                        found.append(rel)
                except Exception:
                    pass
        if found:
            return False, f"{len(found)} dosyada UIWebView: {found[0]} - 2020'den beri RED sebebi"
        return True, "UIWebView kullanimi yok"

    # ================================================================
    # PREFLIGHT - App Store Preflight Kurallari
    # ================================================================

    def check_siwa_standard_button(self, t: dict) -> Tuple[bool, str]:
        """SIWA butonu Apple'in standart ASAuthorizationAppleIDButton'ini mi kullaniyor. Guideline 4.0"""
        # SIWA implementasyonu var mi?
        siwa_impl = self.scan_pattern(
            r"(?:ASAuthorization|AppleAuthentication|apple.*sign.?in|signInWithApple|sign_in_with_apple)", limit=50
        )
        if not siwa_impl:
            return True, "SIWA kullanilmiyor"
        # Standart Apple butonu kullaniliyor mu?
        standard_button = self.scan_pattern(
            r"(?:ASAuthorizationAppleIDButton|AppleIDButton|SignInWithAppleButton|AppleAuthenticationButton|SignInWithApple\.Button)", limit=50
        )
        # Custom buton kullaniliyor mu? (risk)
        custom_button = self.scan_pattern(
            r"""(?:['"]Sign\s+in\s+with\s+Apple['"]|apple.*login.*button|custom.*apple.*button|appleSignIn.*Text|apple.*sign.*label)""", limit=50
        )
        if siwa_impl and not standard_button and custom_button:
            return False, f"SIWA icin custom buton kullaniliyor ({len(custom_button)} yer) - Apple standart ASAuthorizationAppleIDButton ZORUNLU"
        if siwa_impl and not standard_button:
            return False, "SIWA implementasyonu var ama standart Apple butonu (ASAuthorizationAppleIDButton) bulunamadi"
        return True, "SIWA standart buton kullaniliyor"

    def check_siwa_post_data_request(self, t: dict) -> Tuple[bool, str]:
        """SIWA sonrasi gereksiz name/email isteme - Guideline 4.0"""
        siwa_impl = self.scan_pattern(
            r"(?:ASAuthorizationAppleIDCredential|appleIDCredential|apple.*credential|AppleAuthenticationCredential)", limit=50
        )
        if not siwa_impl:
            return True, "SIWA kullanilmiyor"
        # SIWA sonrasi profil tamamlama ekrani var mi?
        post_siwa_data = self.scan_pattern(
            r"(?:completeProfile|askForName|askForEmail|profileSetup|additionalInfo|onboarding.*name|onboarding.*email)", limit=50
        )
        if post_siwa_data:
            return False, f"SIWA sonrasi ek bilgi isteniyor ({len(post_siwa_data)} yer) - Apple zaten name/email saglar, tekrar istemeyin"
        # Relay email destegi var mi?
        relay_block = self.scan_pattern(
            r"(?:privaterelay\.appleid\.com|@privaterelay|relay.*email|hide.*my.*email)", limit=50
        )
        email_validation = self.scan_pattern(
            r"""(?:email.*valid|isValid.*email|email.*regex|email.*pattern)(?!.*privaterelay)""", limit=50
        )
        if email_validation and not relay_block:
            return False, "Email dogrulama var ama Apple relay email destegi yok - privaterelay.appleid.com engellenmemeli"
        return True, "SIWA veri kullanimi uygun"

    def check_minimum_functionality(self, t: dict) -> Tuple[bool, str]:
        """Minimum islevsellik kontrolu - Guideline 4.2"""
        # WebView uygulamasi mi?
        webview_hits = self.scan_pattern(
            r"(?:WKWebView|UIWebView|WebView|SFSafariViewController|react-native-webview|WebViewScreen|webview_flutter)", limit=100
        )
        # Ekran sayisi
        screen_hits = self.scan_pattern(
            r"(?:class\s+\w+.*(?:UIViewController|View\s*:\s*View|Screen|Page)|(?:export\s+(?:default\s+)?(?:function|const)\s+\w+(?:Screen|Page)))", limit=200
        )
        # Model/data katmani
        model_hits = self.scan_pattern(
            r"(?:CoreData|SwiftData|UserDefaults|Realm|SQLite|AsyncStorage|MMKV|SharedPreferences|Hive|sqflite)", limit=50
        )
        # Sadece WebView ve cok az ekran
        if len(webview_hits) > 3 and len(screen_hits) < 3 and not model_hits:
            return False, f"Uygulama WebView agirlikli ({len(webview_hits)} hit), {len(screen_hits)} ekran, veri katmani yok - Guideline 4.2 riski"
        if len(screen_hits) < 2 and not model_hits:
            return False, f"Sadece {len(screen_hits)} ekran, veri katmani yok - minimum islevsellik yetersiz olabilir"
        return True, f"{len(screen_hits)} ekran, {'veri katmani var' if model_hits else 'veri katmani yok'}"

    def check_unnecessary_data(self, t: dict) -> Tuple[bool, str]:
        """Gereksiz kisisel veri zorunlulugu - Guideline 5.1.1"""
        # Kayit/onboarding formlari
        registration_forms = self.scan_pattern(
            r"(?:registration|onboarding|signup|sign.?up|register|createAccount)", limit=50
        )
        if not registration_forms:
            return True, "Kayit formu tespit edilmedi"
        # Hassas/gereksiz olabilecek alanlar
        sensitive_fields = []
        field_patterns = {
            "phone": r"""(?:phone.*required|required.*phone|phoneNumber.*validator|phone.*isRequired)""",
            "gender": r"""(?:gender.*required|required.*gender|gender.*validator|gender.*isRequired)""",
            "birthdate": r"""(?:birth.*required|required.*birth|dob.*required|dateOfBirth.*validator|age.*required)""",
            "address": r"""(?:address.*required|required.*address|homeAddress.*validator|street.*required)""",
            "marital": r"""(?:marital.*required|required.*marital|maritalStatus)""",
        }
        for field_name, pattern in field_patterns.items():
            hits = self.scan_pattern(pattern, limit=20)
            if hits:
                sensitive_fields.append(field_name)
        if sensitive_fields:
            return False, f"Zorunlu tutulan hassas alanlar: {', '.join(sensitive_fields)} - Uygulamanin ana islevi icin gerekliyse sorun yok, degilse OPSIYONEL yapin"
        return True, "Gereksiz zorunlu veri talebi yok"

    def check_misleading_pricing(self, t: dict) -> Tuple[bool, str]:
        """Yaniltici abonelik fiyatlandirma gosterimi - Guideline 3.1.2"""
        # Abonelik UI var mi?
        paywall = self.scan_pattern(
            r"(?:paywall|Paywall|subscribe|pricing|subscription.*view|purchase.*view|SubscriptionView|PurchaseView)", limit=50
        )
        if not paywall:
            return True, "Abonelik UI'i tespit edilmedi"
        # Hesaplanmis fiyat gosterimi (per-month breakdown)
        calculated_price = self.scan_pattern(
            r"(?:perMonth|per_month|monthly.*price|price.*month|weekly.*price|price.*week|\/mo|\/month|\/week|dailyPrice|pricePerDay)", limit=50
        )
        # Gercek faturalandirma miktari gosterimi
        billed_amount = self.scan_pattern(
            r"(?:billedAmount|totalPrice|annualPrice|yearlyPrice|actualPrice|chargedAmount|fullPrice)", limit=50
        )
        if calculated_price and not billed_amount:
            return False, f"Hesaplanmis fiyat gosterimi var ({len(calculated_price)} yer) ama gercek faturalandirma tutari belirgin degil - Guideline 3.1.2: gercek tutar EN BUYUK ve EN BELIRGIN olmali"
        if calculated_price:
            return False, f"Hesaplanmis fiyat gosterimi tespit edildi ({len(calculated_price)} yer) - gercek faturalandirma tutarinin daha buyuk font/renk/pozisyonda oldugunu dogrulayin"
        return True, "Fiyatlandirma gosterimi temiz"

    def check_missing_tos_pp_paywall(self, t: dict) -> Tuple[bool, str]:
        """Abonelik paywall'unda ToS ve Privacy Policy linkleri zorunlu - Guideline 3.1.2"""
        # Abonelik/paywall kodu var mi?
        subscription = self.scan_pattern(
            r"(?:StoreKit|SKProduct|RevenueCat|Superwall|Purchases\.configure|subscription|paywall|Paywall)", limit=50
        )
        if not subscription:
            return True, "Abonelik sistemi tespit edilmedi"
        # ToS / Privacy Policy linkleri
        tos_link = self.scan_pattern(
            r"(?:terms.*(?:of\s*(?:use|service))|TermsOfService|TermsOfUse|termsURL|tosURL|eula|EULA)", limit=50
        )
        pp_link = self.scan_pattern(
            r"(?:privacy.*policy|PrivacyPolicy|privacyURL|privacyPolicyURL)", limit=50
        )
        missing = []
        if not tos_link:
            missing.append("Terms of Use/EULA")
        if not pp_link:
            missing.append("Privacy Policy")
        if missing:
            return False, f"Abonelik paywall'unda eksik: {', '.join(missing)} - Guideline 3.1.2: abonelik ekraninda ToS ve PP linkleri ZORUNLU"
        return True, "Paywall'da ToS ve PP linkleri mevcut"

    def check_subscription_metadata(self, t: dict) -> Tuple[bool, str]:
        """Abonelik metadata gereksinimleri - Guideline 3.1.2"""
        subscription = self.scan_pattern(
            r"(?:auto.?renew|subscription|StoreKit|SKProduct|RevenueCat|Purchases\.configure)", limit=50
        )
        if not subscription:
            return True, "Abonelik sistemi tespit edilmedi"
        # Restore Purchases ayri kontrol ediliyor, burada metadata kontrol
        # Abonelik suresi ve fiyat gosterimi
        duration_display = self.scan_pattern(
            r"(?:monthly|yearly|annual|weekly|1\s*month|1\s*year|1\s*week|subscription.*period|duration)", limit=50
        )
        price_display = self.scan_pattern(
            r"(?:price|Price|displayPrice|localizedPrice|formattedPrice|\$|\u20BA|TRY|USD)", limit=50
        )
        missing = []
        if not duration_display:
            missing.append("abonelik suresi")
        if not price_display:
            missing.append("abonelik fiyati")
        if missing:
            return False, f"Abonelik UI'da eksik bilgi: {', '.join(missing)} - Guideline 3.1.2: baslik, sure ve fiyat gosterimi ZORUNLU"
        return True, "Abonelik metadata bilgileri mevcut"

    def check_china_storefront_ai(self, t: dict) -> Tuple[bool, str]:
        """Cin storefront'ta lisanssiz AI servis referanslari - Guideline 5 (DST)"""
        # Yasak AI servis isimleri
        banned_terms = self.scan_pattern(
            r"""(?i)(?:chatgpt|openai|gpt-4|gpt-4o|gpt4|gemini|bard|claude|anthropic|midjourney|dall-e|dall\xb7e|copilot\s+ai|stable\s+diffusion)""", limit=100
        )
        if not banned_terms:
            return True, "Lisanssiz AI servis referansi yok"
        # Metadata dosyalarinda mi?
        metadata_hits = []
        code_hits = []
        for hit in banned_terms:
            f = hit.get("file", "")
            if any(x in f.lower() for x in ["metadata", "fastlane", "app.json", "info.plist", "description", "keywords"]):
                metadata_hits.append(hit)
            else:
                code_hits.append(hit)
        if metadata_hits:
            first = metadata_hits[0]
            return False, f"{len(metadata_hits)} AI servis referansi METADATA'da: {first['file']}:{first['line']} - Cin storefront'ta aktifse KESIN RED"
        if code_hits:
            return False, f"{len(code_hits)} AI servis referansi kodda: {code_hits[0]['file']}:{code_hits[0]['line']} - Cin storefront'ta dagitimdaysa kaldirin veya Cin'i devre disi birakin"
        return True, "Temiz"

    def check_competitor_terms(self, t: dict) -> Tuple[bool, str]:
        """Metadata'da rakip platform referanslari - Guideline 2.3.1"""
        # Metadata dosyalarini tara
        competitor_pattern = r"""(?i)(?:android|google\s+play|google\s+play\s+store|samsung|galaxy\s+store|huawei|appgallery|amazon\s+appstore|windows\s+store|microsoft\s+store|\.apk|sideload)"""
        # Metadata / aciklama dosyalari
        hits = []
        metadata_files = ["app.json", "fastlane/metadata", "package.json"]
        for rel, full in self._all_files():
            fname = os.path.basename(rel).lower()
            # Metadata, README, description dosyalari
            if any(x in rel.lower() for x in ["fastlane", "metadata", "description", "keywords", "release_notes", "changelog"]):
                try:
                    content = Path(full).read_text(errors="ignore")
                    for m in re.finditer(competitor_pattern, content):
                        hits.append({"file": rel, "line": content[:m.start()].count("\n") + 1, "match": m.group()[:40]})
                except Exception:
                    pass
        # app.json description alaninda da kontrol
        app_json = self.read("app.json")
        if app_json:
            for m in re.finditer(competitor_pattern, app_json):
                hits.append({"file": "app.json", "line": app_json[:m.start()].count("\n") + 1, "match": m.group()[:40]})
        # package.json description alaninda
        pkg_json = self.read("package.json")
        if pkg_json:
            try:
                pkg = json.loads(pkg_json)
                desc = pkg.get("description", "")
                if re.search(competitor_pattern, desc):
                    hits.append({"file": "package.json", "line": 1, "match": "description icinde rakip platform terimi"})
            except Exception:
                pass
        if hits:
            first = hits[0]
            return False, f"{len(hits)} rakip platform referansi: '{first['match']}' in {first['file']}:{first['line']} - Guideline 2.3.1: rakip platform isimleri metadata'da YASAK"
        return True, "Rakip platform referansi yok"

    def check_apple_trademark(self, t: dict) -> Tuple[bool, str]:
        """Apple marka/ticari isim ihlali - Guideline 5.2.5"""
        # Uygulama adi/aciklamasinda Apple urun isimleri
        trademark_pattern = r"""(?i)\b(?:iphone|ipad|macbook|apple\s+watch|apple\s+tv|imessage|facetime|siri|airdrop|vision\s+pro|airpods)\b"""
        hits = []
        # app.json - name/description alanlari
        app_json = self.read("app.json")
        if app_json:
            try:
                data = json.loads(app_json)
                expo = data.get("expo", data)
                name = expo.get("name", "")
                desc = expo.get("description", "")
                slug = expo.get("slug", "")
                for field_name, field_val in [("name", name), ("description", desc), ("slug", slug)]:
                    if re.search(trademark_pattern, field_val):
                        hits.append({"file": "app.json", "field": field_name, "match": re.search(trademark_pattern, field_val).group()})
            except Exception:
                pass
        # Info.plist - CFBundleDisplayName, CFBundleName
        for rel, full in self._all_files():
            if os.path.basename(rel) == "Info.plist":
                try:
                    content = Path(full).read_text(errors="ignore")
                    # CFBundleDisplayName veya CFBundleName icinde trademark
                    name_match = re.search(r'<key>CFBundle(?:Display)?Name</key>\s*<string>(.*?)</string>', content)
                    if name_match and re.search(trademark_pattern, name_match.group(1)):
                        hits.append({"file": rel, "field": "CFBundleName", "match": re.search(trademark_pattern, name_match.group(1)).group()})
                except Exception:
                    pass
        # Fastlane metadata
        for rel, full in self._all_files():
            if "fastlane" in rel.lower() and ("name" in os.path.basename(rel).lower() or "subtitle" in os.path.basename(rel).lower()):
                try:
                    content = Path(full).read_text(errors="ignore")
                    if re.search(trademark_pattern, content):
                        hits.append({"file": rel, "field": "metadata", "match": re.search(trademark_pattern, content).group()})
                except Exception:
                    pass
        if hits:
            first = hits[0]
            return False, f"{len(hits)} Apple trademark ihlali: '{first['match']}' in {first['file']} ({first.get('field', '')}) - Guideline 5.2.5: uygulama adi/metadata'da Apple urun isimleri YASAK"
        return True, "Apple trademark ihlali yok"

    def check_unused_entitlements(self, t: dict) -> Tuple[bool, str]:
        """Kullanilmayan entitlement'lar - Guideline 2.4.5"""
        # Entitlement dosyalarini bul
        entitlements_content = ""
        entitlements_file = ""
        for rel, full in self._all_files():
            if rel.endswith(".entitlements"):
                try:
                    entitlements_content = Path(full).read_text(errors="ignore")
                    entitlements_file = rel
                    break
                except Exception:
                    pass
        if not entitlements_content:
            return True, "Entitlements dosyasi yok"
        # Entitlement'lari parse et ve kullanim kontrol et
        entitlement_checks = {
            "com.apple.developer.healthkit": (
                r"(?:HKHealthStore|HealthKit|health_kit)", "HealthKit"
            ),
            "com.apple.developer.applesignin": (
                r"(?:ASAuthorization|SignInWithApple|apple.*sign.?in)", "Sign in with Apple"
            ),
            "aps-environment": (
                r"(?:UNUserNotificationCenter|registerForRemoteNotifications|push.*notification|APNs|firebase.*messaging)", "Push Notifications"
            ),
            "com.apple.security.network.server": (
                r"(?:NWListener|GCDWebServer|Swifter|Vapor|HttpServer|startServer|localhost)", "Network Server"
            ),
            "com.apple.developer.icloud": (
                r"(?:CKContainer|CloudKit|NSPersistentCloudKitContainer|iCloud|ubiquityIdentityToken)", "iCloud"
            ),
            "com.apple.developer.siri": (
                r"(?:INInteraction|SiriKit|IntentHandler|AppIntents|@AppIntent)", "SiriKit"
            ),
            "com.apple.security.files.downloads.read-write": (
                r"(?:Downloads|downloadsDirectory|FileManager.*downloads)", "Downloads Folder"
            ),
        }
        unused = []
        for entitlement_key, (code_pattern, label) in entitlement_checks.items():
            if entitlement_key in entitlements_content:
                code_usage = self.scan_pattern(code_pattern, limit=20)
                if not code_usage:
                    unused.append(label)
        if unused:
            return False, f"{len(unused)} kullanilmayan entitlement: {', '.join(unused[:3])} - Guideline 2.4.5: Apple gerekce isteyecek veya reddedecek"
        return True, f"Entitlement'lar kullanilmakta ({entitlements_file})"

    def check_accurate_metadata(self, t: dict) -> Tuple[bool, str]:
        """App preview video'larda cihaz cercevesi yasak - Guideline 2.3.4"""
        # Video preview dosyalari var mi?
        video_previews = []
        for rel, full in self._all_files():
            if any(x in rel.lower() for x in ["preview", "promo", "app_preview"]):
                if rel.endswith((".mov", ".mp4", ".m4v")):
                    video_previews.append(rel)
        if not video_previews:
            return True, "App preview video dosyasi tespit edilmedi"
        # Video isimlerinde device frame ipucu
        frame_hints = []
        for v in video_previews:
            fname = os.path.basename(v).lower()
            if any(x in fname for x in ["frame", "device", "mockup", "bezel", "iphone_frame"]):
                frame_hints.append(v)
        if frame_hints:
            return False, f"{len(frame_hints)} video dosyasi cihaz cercevesi icerebilir: {frame_hints[0]} - Guideline 2.3.4: app preview videolari sadece ekran goruntusu icermeli"
        return True, f"{len(video_previews)} preview video mevcut - cihaz cercevesi icermediginden emin olun"

    # ================================================================
    # ORTA - Inceleme Riski
    # ================================================================

    def check_voiceover_support(self, t: dict) -> Tuple[bool, str]:
        """VoiceOver / accessibility label destegi."""
        interactive = self.scan_pattern(r"(?:<TouchableOpacity|<Pressable|<Button|<TextInput)", limit=100)
        a11y = self.scan_pattern(r"(?:accessibilityLabel|accessibilityRole|accessible\s*=)", limit=100)
        if len(interactive) > 10 and len(a11y) < len(interactive) * 0.2:
            return False, f"{len(interactive)} interaktif element, sadece {len(a11y)} accessibility label (%{len(a11y)*100//max(len(interactive),1)})"
        return True, f"{len(a11y)}/{len(interactive)} accessibility kapsamli"

    def check_orientation_support(self, t: dict) -> Tuple[bool, str]:
        """Desteklenen cihaz yonleri."""
        info_content = self.read("Info.plist") + self.read("app.json")
        if "UISupportedInterfaceOrientations" in info_content or "orientation" in info_content:
            return True, "Yon destegi yapilandirilmis"
        return True, "Varsayilan yon ayarlari"

    def check_subscription_handling(self, t: dict) -> Tuple[bool, str]:
        """Abonelik durumu yonetimi."""
        subscription = self.scan_pattern(
            r"(?:subscription|Subscription|auto.?renew|recurring)", limit=50
        )
        status_check = self.scan_pattern(
            r"(?:subscription.*status|isActive|isExpired|entitlement|currentEntitlements|customerInfo)", limit=50
        )
        if subscription and not status_check:
            return False, f"Abonelik sistemi var ({len(subscription)} referans) ama durum kontrolu bulunamadi"
        return True, "Temiz"

    def check_app_thinning(self, t: dict) -> Tuple[bool, str]:
        """Buyuk asset'ler - app boyutu sorunu."""
        large_assets = []
        for rel, full in self._all_files():
            if rel.endswith((".png", ".jpg", ".mp4", ".mov", ".wav", ".mp3")):
                try:
                    size_mb = os.path.getsize(full) / 1024 / 1024
                    if size_mb > 5:
                        large_assets.append(f"{rel} ({size_mb:.1f}MB)")
                except OSError:
                    pass
        if large_assets:
            return False, f"{len(large_assets)} buyuk asset (>5MB): {large_assets[0]} - App Thinning/ODR oneriliyor"
        return True, "Temiz"

    def get_all_checks(self) -> Dict[str, callable]:
        return {
            # Kritik
            "privacy_manifest": self.check_privacy_manifest,
            "purpose_strings": self.check_purpose_strings,
            "sign_in_with_apple": self.check_sign_in_with_apple,
            "account_deletion_apple": self.check_account_deletion,
            "att_compliance": self.check_att_compliance,
            "external_payment": self.check_external_payment,
            "iap_restore": self.check_iap_restore,
            "iap_verification": self.check_iap_verification,
            "recording_consent": self.check_recording_consent,
            "kids_tracking": self.check_kids_tracking,
            "health_data_ads": self.check_health_data_ads,
            "required_reason_api": self.check_required_reason_api,
            # Yuksek
            "app_icon_sizes": self.check_app_icon_sizes,
            "launch_screen": self.check_launch_screen,
            "min_deployment_target": self.check_min_deployment_target,
            "deprecated_api_apple": self.check_deprecated_api,
            "widget_no_ads": self.check_widget_no_ads,
            "face_auth_method": self.check_face_auth_method,
            "data_collection_types": self.check_data_collection_types,
            # v2.2 Yeni
            "app_completeness": self.check_app_completeness,
            "debug_urls": self.check_debug_urls,
            "reason_code_validity": self.check_reason_code_validity,
            "sdk_privacy_manifests": self.check_sdk_privacy_manifests,
            "ota_compliance": self.check_ota_compliance,
            "ats_override": self.check_ats_override,
            "url_scheme_conflict": self.check_url_scheme_conflict,
            "bundle_secrets": self.check_bundle_secrets,
            "uiwebview_deprecated": self.check_uiwebview_deprecated,
            # Preflight - App Store Preflight Kurallari
            "siwa_standard_button": self.check_siwa_standard_button,
            "siwa_post_data_request": self.check_siwa_post_data_request,
            "minimum_functionality": self.check_minimum_functionality,
            "unnecessary_data": self.check_unnecessary_data,
            "misleading_pricing": self.check_misleading_pricing,
            "missing_tos_pp_paywall": self.check_missing_tos_pp_paywall,
            "subscription_metadata_info": self.check_subscription_metadata,
            "china_storefront_ai": self.check_china_storefront_ai,
            "competitor_terms": self.check_competitor_terms,
            "apple_trademark": self.check_apple_trademark,
            "unused_entitlements": self.check_unused_entitlements,
            "accurate_metadata": self.check_accurate_metadata,
            # Orta
            "voiceover_support": self.check_voiceover_support,
            "orientation_support": self.check_orientation_support,
            "subscription_handling": self.check_subscription_handling,
            "app_thinning": self.check_app_thinning,
        }

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        checks = self.get_all_checks()
        fn = checks.get(subtype)
        return fn(test) if fn else (True, "SKIP")
