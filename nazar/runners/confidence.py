"""Confidence Scorer - Her bulguya guven puani verir."""


# Confidence levels for each subtype
# 90-100: Kesin sorun - regex tam match, context dogrulandi
# 70-89: Buyuk ihtimalle sorun - pattern match ama context belirsiz
# 50-69: Muhtemel sorun - genel pattern, false positive olabilir
# 0-49: Bilgilendirme - pattern goruldu ama baska anlami olabilir

CONFIDENCE_SCORES = {
    # Security - High confidence (pattern-specific)
    "secrets": 85,
    "api_keys": 90,
    "private_keys": 95,
    "sensitive_files": 98,
    "secrets_comprehensive": 80,
    "cloud_keys": 95,
    "payment_keys": 95,
    "communication_keys": 90,
    "vcs_keys": 95,
    "db_connection_strings": 85,
    "crypto_keys": 95,
    "https": 90,
    "sql_injection": 75,
    "command_injection": 80,
    "path_traversal": 55,  # Often false positive in React Native imports
    "insecure_deserialization": 85,
    "weak_crypto": 70,
    "dangerous_functions": 60,  # babel.config.js often triggers
    "hardcoded_ips": 65,
    "cors_wildcard": 80,
    "cors_misconfiguration": 80,
    "debug_mode": 75,

    # Deep Security
    "hardcoded_credentials": 85,
    "tokens_in_urls": 90,
    "sensitive_logs": 80,
    "sensitive_errors": 70,
    "pii_exposure": 65,  # Context dependent
    "source_maps_prod": 90,
    "jwt_no_expiry": 85,
    "jwt_weak_secret": 90,
    "missing_auth_middleware": 60,
    "insecure_session_storage": 75,
    "missing_csrf": 65,
    "weak_password_policy": 55,
    "xss_vectors": 85,
    "nosql_injection": 80,
    "template_injection": 80,
    "regex_dos": 70,
    "unvalidated_redirects": 70,
    "file_upload_no_validation": 65,
    "idor_risk": 60,
    "horizontal_privilege": 70,
    "admin_routes_exposed": 75,
    "mass_assignment": 75,
    "debug_production": 80,
    "default_credentials": 90,
    "missing_security_headers": 65,
    "verbose_errors": 70,
    "exposed_env_vars": 75,
    "weak_hashing": 85,
    "weak_encryption": 60,  # DES/ECB in comments can be false positive
    "insecure_random": 55,  # Often used for non-security (animation)
    "hardcoded_iv_salt": 80,
    "unpinned_deps": 70,
    "known_vulnerable_packages": 95,
    "postinstall_scripts": 75,
    "rate_limiting": 60,
    "no_input_size_limit": 55,
    "graphql_introspection": 80,
    "excessive_data_exposure": 70,
    "gdpr_data_deletion": 75,
    "data_encryption_at_rest": 65,
    "privacy_policy": 80,
    "consent_management": 70,
    "error_boundary": 85,
    "missing_loading_states": 55,
    "memory_leaks": 50,
    "race_conditions": 65,
    "missing_timeout": 55,
    "hardcoded_urls": 60,

    # Mobile - context-dependent kontroller icin dusurulmus skorlar
    "certificate_pinning": 65,
    "insecure_storage_mobile": 80,
    "root_jailbreak_detection": 60,
    "deeplink_validation": 55,
    "screenshot_protection": 45,

    # Code Quality
    "long_functions": 95,
    "long_files": 95,
    "nesting_depth": 90,
    "duplication": 70,
    "todo_count": 95,
    "debug_statements": 65,  # console.print can be false positive
    "complexity": 85,
    "cyclomatic_complexity": 85,
    "maintainability_index": 80,
    "dead_code": 60,
    "mutable_default": 90,
    "star_import": 85,
    "loose_equality": 75,
    "var_usage": 50,  # Swift uses var legitimately
    "unchecked_error_go": 80,
    "unwrap_abuse": 75,

    # Type Safety
    "any_usage": 70,
    "ts_ignore": 85,
    "as_any": 80,

    # UX Text
    "spelling": 85,
    "term_consistency": 70,
    "i18n_readiness": 65,
    "button_text_quality": 60,
    "error_message_quality": 70,
    "truncation_risk": 55,
    "missing_alt_text": 90,
    "placeholder_quality": 55,

    # UI Component
    "a11y_labels": 90,
    "touch_target_size": 65,
    "hardcoded_colors": 55,
    "hardcoded_dimensions": 60,
    "dark_mode_support": 60,
    "ui_error_boundary": 90,
    "loading_states": 55,
    "empty_state": 60,
    "keyboard_handling": 75,
    "image_optimization": 50,
    "storybook_coverage": 40,

    # Other
    "test_coverage": 95,
    "empty_files": 90,
    "gitignore_quality": 85,
    "large_tracked": 90,
    "sensitive_history": 95,
    "lock_file": 80,
    "has_license": 95,
    "readme_exists": 95,
    "readme_quality": 80,
    "changelog": 70,
    "env_example": 75,
    "env_safety": 90,
    "test_ids": 85,
    "image_labels": 80,
    "source_size": 90,
    "large_files": 95,
    "large_images": 90,

    # App Store
    "privacy_manifest": 95,
    "purpose_strings": 90,
    "sign_in_with_apple": 85,
    "account_deletion_apple": 80,
    "att_compliance": 90,
    "external_payment": 80,
    "iap_restore": 85,
    "iap_verification": 80,
    "recording_consent": 75,
    "kids_tracking": 90,
    "health_data_ads": 85,
    "required_reason_api": 80,
    "app_icon_sizes": 95,
    "launch_screen": 95,
    "min_deployment_target": 90,
    "deprecated_api_apple": 85,
    "widget_no_ads": 90,
    "face_auth_method": 80,
    "data_collection_types": 70,
    "voiceover_support": 75,
    "orientation_support": 60,
    "subscription_handling": 70,
    "app_thinning": 85,
    # v2.2 Pre-Review
    "app_completeness": 85,
    "debug_urls": 90,
    "reason_code_validity": 95,
    "sdk_privacy_manifests": 80,
    "ota_compliance": 70,
    "ats_override": 95,
    "url_scheme_conflict": 95,
    "bundle_secrets": 90,
    "uiwebview_deprecated": 95,
    # Preflight - App Store Preflight Kurallari
    "siwa_standard_button": 85,
    "siwa_post_data_request": 80,
    "minimum_functionality": 70,
    "unnecessary_data": 75,
    "misleading_pricing": 80,
    "missing_tos_pp_paywall": 90,
    "subscription_metadata_info": 85,
    "china_storefront_ai": 95,
    "competitor_terms": 90,
    "apple_trademark": 90,
    "unused_entitlements": 85,
    "accurate_metadata": 70,

    # AST Analysis (Python)
    "dangerous_calls": 98,
    "bare_except": 95,
    "mutable_defaults": 95,
    "hardcoded_secrets": 92,
    "star_imports": 90,

    # Taint Tracking
    "sql_injection_taint": 90,
    "xss_taint": 88,
    "command_injection_taint": 92,
    "path_traversal_taint": 75,
    "general_taint": 80,

    # SCA (Software Composition Analysis)
    "npm_audit": 95,
    "pip_audit": 95,
    "go_vulncheck": 95,
    "outdated_packages": 70,
    "license_compatibility": 85,
    "deprecated_packages": 80,
    "typosquatting": 98,

    # YAML UI Tests
    "yaml_ui_syntax": 95,
    "yaml_ui_targets": 85,
    "yaml_ui_coverage": 70,

    # i18n Deep
    "i18n_deep": 70,
    "i18n_coverage": 75,
    "missing_translation_keys": 90,
    "unused_translation_keys": 80,
    "locale_consistency": 95,
    "rtl_support": 70,

    # Responsive
    "fixed_dimensions": 75,
    "scroll_issues": 90,
    "responsive_patterns": 65,
    "media_query_analysis": 80,
    "viewport_meta": 90,
    "responsive_touch_target": 75,
    "flexbox_grid_usage": 70,
    "responsive_images": 75,

    # Performance Static
    "large_assets": 95,
    "render_performance": 70,
    "bundle_issues": 80,

    # Spell Check
    "spell_check": 75,

    # UI Quality (Core)
    "color_consistency": 70,
    "contrast_wcag": 90,
    "font_consistency": 65,
    "form_validation_coverage": 80,
    "form_error_messages": 75,

    # UI Analysis (MVP)
    "page_discovery": 90,
    "dead_routes": 95,
    "content_quality": 92,
    "loading_state": 75,
    "error_state": 75,
    "ui_empty_state": 70,

    # Eksik confidence skorlari (checker2 tarafindan tespit edildi)
    "undefined_vars": 70,
    "gpl_check": 75,
    "deprecated": 70,
    "open_redirect": 70,

    # YAML Rules
    "yaml_security": 80,
    "yaml_code_quality": 70,
    "yaml_custom": 75,

    # Visual Regression
    "stale_snapshots": 80,
    "missing_snapshots": 75,
    "snapshot_naming": 60,
    "large_snapshots": 85,
    "uncommitted_snapshots": 90,
    "snapshot_directory_check": 70,

    # Compliance - OWASP
    "owasp_full": 80,
    "owasp_A01_broken_access_control": 70,
    "owasp_A02_cryptographic_failures": 80,
    "owasp_A03_injection": 85,
    "owasp_A04_insecure_design": 55,
    "owasp_A05_security_misconfiguration": 75,
    "owasp_A06_vulnerable_components": 70,
    "owasp_A07_auth_failures": 75,
    "owasp_A08_integrity_failures": 80,
    "owasp_A09_logging_failures": 65,
    "owasp_A10_ssrf": 70,

    # Compliance - GDPR/KVKK
    "gdpr_full": 75,
    "gdpr_consent_mechanism": 65,
    "gdpr_data_deletion": 70,
    "gdpr_privacy_policy": 80,
    "gdpr_cookie_consent": 60,
    "gdpr_data_encryption_at_rest": 65,
    "gdpr_pii_logging_prevention": 80,

    # Compliance - SOC2
    "soc2_full": 75,
    "soc2_authentication": 70,
    "soc2_access_control": 65,
    "soc2_audit_logging": 60,
    "soc2_encryption_in_transit": 85,
    "soc2_error_handling": 70,
    "soc2_dependency_updates": 75,

    # Compliance - PCI-DSS
    "pci_full": 80,
    "pci_no_credit_card_in_code": 90,
    "pci_no_pan_storage": 75,
    "pci_tls_enforcement": 85,
    "pci_input_validation_payment": 65,

    # Compliance - Ozet
    "compliance_summary": 75,

    # Play Store
    "target_sdk": 95,
    "exported_components": 90,
    "network_security": 85,
    "permissions": 75,
    "backup_rules": 70,
    "debuggable": 95,
    "metadata": 80,
    "data_safety": 75,
    "app_bundle": 70,
    "proguard": 85,
}


def get_confidence(subtype: str) -> int:
    """Get confidence score for a subtype. Default 70 if not mapped."""
    return CONFIDENCE_SCORES.get(subtype, 70)


def confidence_label(score: int) -> str:
    """Human-readable confidence label."""
    if score >= 90:
        return "Kesin"
    if score >= 70:
        return "Yuksek"
    if score >= 50:
        return "Orta"
    return "Dusuk"
