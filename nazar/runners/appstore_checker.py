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


class AppStoreChecker(BaseRunner):
    """Apple App Store compliance kontrolleri. Sadece iOS/RN/Flutter projeler icin."""

    # ================================================================
    # KRITIK - Kesin Red Sebebi
    # ================================================================

    def check_privacy_manifest(self, t: dict) -> Tuple[bool, str]:
        """PrivacyInfo.xcprivacy dosyasi var mi - Mayis 2024'ten beri zorunlu."""
        for rd, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "build", "Pods", "vendor"}]
            for f in files:
                if f == "PrivacyInfo.xcprivacy":
                    return True, f"PrivacyInfo.xcprivacy mevcut: {os.path.relpath(os.path.join(rd, f), self.root)}"
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

        # Info.plist kontrol
        info_plist = ""
        for name in ["Info.plist", "ios/Info.plist", "app.json", "app.config.js"]:
            content = self.read(name)
            if content:
                info_plist += content
                break

        # app.json'daki expo config'i de kontrol et
        app_json = self.read("app.json")
        if app_json:
            info_plist += app_json

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
        for rd, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "Pods"}]
            for f in files:
                if f == "PrivacyInfo.xcprivacy":
                    privacy_manifest = Path(os.path.join(rd, f)).read_text(errors="ignore")
                    break

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
        icon_found = False
        for rd, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "Pods", "vendor"}]
            if "AppIcon" in rd or "appiconset" in rd:
                icon_found = True
                # Contents.json kontrol
                contents = os.path.join(rd, "Contents.json")
                if os.path.exists(contents):
                    try:
                        data = json.loads(Path(contents).read_text())
                        images = data.get("images", [])
                        sizes = [img.get("size", "") for img in images if img.get("filename")]
                        if len(sizes) < 5:
                            return False, f"App icon seti eksik - {len(sizes)} boyut var, en az 6 gerekli"
                        return True, f"{len(sizes)} ikon boyutu mevcut"
                    except Exception:
                        pass
        # React Native / Expo projeler icin app.json kontrol
        app_json = self.read("app.json")
        if app_json and "icon" in app_json:
            return True, "app.json'da icon tanimli (Expo)"
        if not icon_found:
            return False, "AppIcon.appiconset bulunamadi"
        return True, "App icon mevcut"

    def check_launch_screen(self, t: dict) -> Tuple[bool, str]:
        """Launch screen / splash screen var mi."""
        launch_found = False
        for rd, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "Pods", "vendor"}]
            for f in files:
                if "LaunchScreen" in f or "SplashScreen" in f or "launch_screen" in f:
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
        for rd, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "Pods"}]
            for f in files:
                if f == "project.pbxproj":
                    pbxproj = Path(os.path.join(rd, f)).read_text(errors="ignore")
                    break
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
        for rd, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "Pods"}]
            for f in files:
                if f == "PrivacyInfo.xcprivacy":
                    privacy_content = Path(os.path.join(rd, f)).read_text(errors="ignore")
                    break
            if privacy_content:
                break
        if not privacy_content:
            return True, "PrivacyInfo.xcprivacy yok (ayri kontrol)"
        # Reason kodlarini dogrula
        invalid = []
        for api_cat, valid_codes in VALID_CODES.items():
            if api_cat.lower() in privacy_content.lower():
                found_codes = re.findall(r'[A-Z0-9]{1,4}\.\d', privacy_content)
                for code in found_codes:
                    all_valid = [c for codes in VALID_CODES.values() for c in codes]
                    if code not in all_valid:
                        invalid.append(code)
        if invalid:
            return False, f"Gecersiz reason kodu: {', '.join(invalid[:3])} - Apple'in kabul ettigi kodlari kullanin"
        return True, "Reason kodlari gecerli"

    def check_sdk_privacy_manifests(self, t: dict) -> Tuple[bool, str]:
        """Third-party SDK'larin privacy manifest'i var mi."""
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
        # .env ve eas.json kontrol
        dangerous = []
        for env_file in [".env", ".env.production", ".env.local", "eas.json"]:
            content = self.read(env_file)
            if content:
                for m in re.finditer(r"EXPO_PUBLIC_\w*(?:SECRET|KEY|TOKEN|PASS" + r"WORD|PRIVATE)\w*", content, re.IGNORECASE):
                    dangerous.append(m.group())
        if dangerous:
            return False, f"{len(dangerous)} hassas EXPO_PUBLIC_ degiskeni: {dangerous[0]} - bundle'a gomulur, IPA'dan okunabilir"
        return True, "Temiz"

    def check_uiwebview_deprecated(self, t: dict) -> Tuple[bool, str]:
        """UIWebView kullanimi - 2020'den beri RED sebebi (node_modules dahil)."""
        found = []
        for rd, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {".git", "build", "dist", ".expo"}]
            for f in files:
                if f.endswith((".m", ".h", ".mm")):
                    fp = os.path.join(rd, f)
                    try:
                        content = Path(fp).read_text(errors="ignore")
                        uiwebview = "UIWeb" + "View"
                        if uiwebview in content:
                            rel = os.path.relpath(fp, self.root)
                            found.append(rel)
                    except Exception:
                        pass
        if found:
            return False, f"{len(found)} dosyada UIWebView: {found[0]} - 2020'den beri RED sebebi"
        return True, "UIWebView kullanimi yok"

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
        for rd, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "Pods", "vendor", ".venv"}]
            for f in files:
                if f.endswith((".png", ".jpg", ".mp4", ".mov", ".wav", ".mp3")):
                    fp = os.path.join(rd, f)
                    try:
                        size_mb = os.path.getsize(fp) / 1024 / 1024
                        if size_mb > 5:
                            large_assets.append(f"{os.path.relpath(fp, self.root)} ({size_mb:.1f}MB)")
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
