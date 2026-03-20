"""Play Store Checker - Google Play Store uyumluluk kontrolleri."""
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple
from xml.etree import ElementTree

from nazar.runners.base import BaseRunner


class PlayStoreChecker(BaseRunner):
    """Google Play Store submission oncesi kontrol araci."""

    def __init__(self, project_path: str):
        super().__init__(project_path)
        self._manifest_cache = None
        self._gradle_cache = None

    @property
    def manifest_content(self) -> str:
        if self._manifest_cache is None:
            paths = [
                "android/app/src/main/AndroidManifest.xml",
                "app/src/main/AndroidManifest.xml",
                "AndroidManifest.xml",
            ]
            for p in paths:
                full = self.root / p
                if full.exists():
                    self._manifest_cache = full.read_text(errors="ignore")
                    break
            if self._manifest_cache is None:
                self._manifest_cache = ""
        return self._manifest_cache

    @property
    def gradle_content(self) -> str:
        if self._gradle_cache is None:
            paths = [
                "android/app/build.gradle",
                "android/app/build.gradle.kts",
                "app/build.gradle",
                "app/build.gradle.kts",
            ]
            for p in paths:
                full = self.root / p
                if full.exists():
                    self._gradle_cache = full.read_text(errors="ignore")
                    break
            if self._gradle_cache is None:
                self._gradle_cache = ""
        return self._gradle_cache

    def _has_android(self) -> bool:
        return bool(self.manifest_content) or bool(self.gradle_content)

    def run_check(self, subtype: str, test: dict) -> Tuple[bool, str]:
        if not self._has_android():
            return True, "Android projesi degil, SKIP"
        checks = {
            "target_sdk": self._target_sdk,
            "exported_components": self._exported_components,
            "network_security": self._network_security,
            "permissions": self._permissions,
            "backup_rules": self._backup_rules,
            "debuggable": self._debuggable,
            "metadata": self._metadata,
            "data_safety": self._data_safety,
            "app_bundle": self._app_bundle,
            "proguard": self._proguard,
        }
        fn = checks.get(subtype)
        if fn:
            return fn(test)
        return True, "SKIP"

    def _target_sdk(self, t: dict) -> Tuple[bool, str]:
        """targetSdkVersion >= 34 (Android 14) kontrolu."""
        gradle = self.gradle_content
        if not gradle:
            return True, "build.gradle yok, SKIP"
        # targetSdkVersion veya targetSdk
        m = re.search(r"targetSdk(?:Version)?\s*(?:=\s*)?(\d+)", gradle)
        if m:
            version = int(m.group(1))
            if version >= 34:
                return True, f"targetSdk={version} (Android 14+)"
            return False, f"targetSdk={version}, >= 34 olmali (Android 14). Google Play Agustos 2024'ten beri zorunlu."
        return True, "targetSdk bulunamadi, SKIP"

    def _exported_components(self, t: dict) -> Tuple[bool, str]:
        """android:exported olmayan activity/service/receiver tespiti."""
        manifest = self.manifest_content
        if not manifest:
            return True, "AndroidManifest.xml yok, SKIP"
        # Android 12+ (API 31) exported zorunlu
        components = re.findall(
            r"<(activity|service|receiver|provider)\b([^>]*?)(?:/>|>)",
            manifest, re.DOTALL,
        )
        unsafe = []
        for comp_type, attrs in components:
            has_intent_filter = "<intent-filter" in manifest  # basitlestirmek icin
            has_exported = "android:exported" in attrs
            if not has_exported:
                name_m = re.search(r'android:name="([^"]+)"', attrs)
                name = name_m.group(1).split(".")[-1] if name_m else comp_type
                unsafe.append(f"{comp_type}:{name}")
        if unsafe:
            return False, f"{len(unsafe)} exported belirtilmemis: {unsafe[0]}. Android 12+ icin zorunlu."
        return True, "Tum component'lerde exported belirtilmis"

    def _network_security(self, t: dict) -> Tuple[bool, str]:
        """Cleartext traffic ve network security config kontrolu."""
        manifest = self.manifest_content
        issues = []
        # usesCleartextTraffic
        if "usesCleartextTraffic=\"true\"" in manifest:
            issues.append("usesCleartextTraffic=true (HTTP acik)")
        # Network security config var mi
        if "networkSecurityConfig" not in manifest:
            ns_path = self.root / "android/app/src/main/res/xml/network_security_config.xml"
            if not ns_path.exists():
                issues.append("networkSecurityConfig tanimlanmamis")
        # Certificate pinning kontrol
        ns_files = list(self.root.glob("**/network_security_config.xml"))
        has_pinning = False
        for ns_file in ns_files:
            content = ns_file.read_text(errors="ignore")
            if "pin-set" in content or "certificate" in content.lower():
                has_pinning = True
                break
        if not has_pinning and ns_files:
            issues.append("Certificate pinning yok")
        if issues:
            return False, "; ".join(issues)
        return True, "Ag guvenligi yapilandirmasi uygun"

    def _permissions(self, t: dict) -> Tuple[bool, str]:
        """Gereksiz izin tespiti."""
        manifest = self.manifest_content
        if not manifest:
            return True, "AndroidManifest.xml yok, SKIP"
        perms = re.findall(r'<uses-permission\s+android:name="android\.permission\.(\w+)"', manifest)
        risky_perms = {
            "READ_PHONE_STATE": "Telefon durumu - gercekten gerekli mi?",
            "READ_CONTACTS": "Kisiler - gercekten gerekli mi?",
            "READ_CALL_LOG": "Arama kayitlari - cok hassas",
            "READ_SMS": "SMS okuma - Google Play kisitli",
            "SEND_SMS": "SMS gonderme - Google Play kisitli",
            "CALL_PHONE": "Arama yapma - gercekten gerekli mi?",
            "CAMERA": "Kamera - gercekten gerekli mi?",
            "RECORD_AUDIO": "Mikrofon - gercekten gerekli mi?",
            "ACCESS_FINE_LOCATION": "Hassas konum - kabaca konum yeterli olabilir",
            "ACCESS_BACKGROUND_LOCATION": "Arka plan konum - Google Play ozel inceleme",
            "SYSTEM_ALERT_WINDOW": "Diger uygulamalar uzerinde gosterim",
            "WRITE_SETTINGS": "Sistem ayarlari degistirme",
            "REQUEST_INSTALL_PACKAGES": "Paket yukleme izni",
            "MANAGE_EXTERNAL_STORAGE": "Tum dosyalara erisim - Google Play ozel inceleme",
        }
        found_risky = []
        for perm in perms:
            if perm in risky_perms:
                found_risky.append(f"{perm}: {risky_perms[perm]}")
        if found_risky:
            return False, f"{len(found_risky)} riskli izin: {found_risky[0]}"
        return True, f"{len(perms)} izin, riskli yok"

    def _backup_rules(self, t: dict) -> Tuple[bool, str]:
        """allowBackup kontrolu."""
        manifest = self.manifest_content
        if not manifest:
            return True, "AndroidManifest.xml yok, SKIP"
        if 'allowBackup="true"' in manifest:
            # fullBackupRules veya dataExtractionRules var mi
            has_rules = "fullBackupRules" in manifest or "dataExtractionRules" in manifest
            if not has_rules:
                return False, "allowBackup=true ama backup rules tanimlanmamis. Hassas veri yedegenebilir."
            return True, "allowBackup=true + backup rules tanimli"
        if 'allowBackup="false"' in manifest:
            return True, "allowBackup=false, guvenli"
        return True, "allowBackup belirtilmemis (varsayilan: true, dikkat)"

    def _debuggable(self, t: dict) -> Tuple[bool, str]:
        """Release build'de debuggable=true kontrolu."""
        manifest = self.manifest_content
        gradle = self.gradle_content
        issues = []
        if 'debuggable="true"' in manifest:
            issues.append("AndroidManifest.xml: debuggable=true")
        # Gradle release config kontrol
        if gradle:
            release_block = re.search(r"release\s*\{([^}]+)\}", gradle, re.DOTALL)
            if release_block:
                block = release_block.group(1)
                if "debuggable" in block and "true" in block:
                    issues.append("build.gradle: release { debuggable=true }")
        if issues:
            return False, "; ".join(issues) + " - Play Store RED sebebi!"
        return True, "debuggable kapalı, guvenli"

    def _metadata(self, t: dict) -> Tuple[bool, str]:
        """Play Store metadata (description, vb.) kontrolu."""
        # play-store-listing klasoru var mi
        listing_dirs = [
            "fastlane/metadata/android",
            "metadata/android",
            "play-store-listing",
        ]
        found_dir = None
        for d in listing_dirs:
            if (self.root / d).is_dir():
                found_dir = d
                break
        issues = []
        if not found_dir:
            # package.json veya build.gradle'dan kontrol
            gradle = self.gradle_content
            if gradle:
                if not re.search(r'versionName\s*(?:=\s*)?["\']', gradle):
                    issues.append("versionName tanimsiz")
                if not re.search(r'versionCode\s*(?:=\s*)?\d+', gradle):
                    issues.append("versionCode tanimsiz")
        if issues:
            return False, "; ".join(issues)
        return True, "Metadata mevcut"

    def _data_safety(self, t: dict) -> Tuple[bool, str]:
        """Veri toplama beyan kontrolu (Data Safety Section)."""
        # data_safety.json veya benzer dosya var mi
        safety_files = [
            "data_safety.json",
            "data-safety-form.json",
            ".well-known/data-safety.json",
        ]
        for sf in safety_files:
            if (self.root / sf).exists():
                return True, f"{sf} mevcut"
        # Veri toplama yapiliyor mu kontrol et
        collecting = []
        for f in self.src_files()[:50]:
            content = self.read(f)
            if re.search(r"(?:analytics|firebase\.analytics|amplitude|mixpanel|segment)", content, re.IGNORECASE):
                collecting.append("Analytics kullanimi tespit edildi")
                break
            if re.search(r"(?:getLastLocation|requestLocationUpdates|FusedLocationProvider)", content):
                collecting.append("Konum verisi toplaniyor")
                break
        if collecting:
            return False, f"Veri toplaniyor ama Data Safety beyani yok: {collecting[0]}"
        return True, "Veri toplama tespit edilmedi"

    def _app_bundle(self, t: dict) -> Tuple[bool, str]:
        """AAB format zorunlulugu kontrolu."""
        gradle = self.gradle_content
        if not gradle:
            return True, "build.gradle yok, SKIP"
        # bundleRelease task var mi veya AAB ayarlari
        # React Native ve Flutter varsayilan olarak APK ve AAB uretebilir
        # Sadece bilgilendirme
        if "splits" in gradle and "abi" in gradle:
            return True, "ABI splits tanimli, AAB icin gereksiz olabilir"
        return True, "AAB format: Play Store Agustos 2021'den beri zorunlu. ./gradlew bundleRelease ile uretilir."

    def _proguard(self, t: dict) -> Tuple[bool, str]:
        """Kod obfuscation (ProGuard/R8) aktif mi kontrolu."""
        gradle = self.gradle_content
        if not gradle:
            return True, "build.gradle yok, SKIP"
        release_block = re.search(r"release\s*\{([^}]+)\}", gradle, re.DOTALL)
        if release_block:
            block = release_block.group(1)
            if "minifyEnabled" in block:
                if "true" in block.split("minifyEnabled")[1][:20]:
                    return True, "minifyEnabled=true, R8/ProGuard aktif"
                return False, "minifyEnabled=false - Release'de kod obfuscation kapalı. APK tersine muhendislige acik."
            if "isMinifyEnabled" in block:
                if "true" in block.split("isMinifyEnabled")[1][:20]:
                    return True, "isMinifyEnabled=true, R8/ProGuard aktif"
                return False, "isMinifyEnabled=false"
        return False, "Release blogu bulunamadi veya minifyEnabled tanimsiz"
