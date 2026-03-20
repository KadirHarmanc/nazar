"""Test Profilleri - Kullanici secimina gore test kategorileri."""
from typing import Dict, List, Optional


TEST_PROFILES = {
    "full": {
        "name": "Tam Tarama",
        "description": "Tum kategoriler, projenin tech_stack'ine gore otomatik filtreleme",
        "categories": "__all__",
        "estimated_minutes": 8,
    },
    "frontend": {
        "name": "Frontend / UI",
        "description": "UI component, UX text, accessibility, visual, type safety, UI analysis",
        "categories": [
            "ux_text", "ui_component", "accessibility", "visual",
            "cross_file", "performance", "type_safety", "yaml_rules",
            "ui_analysis", "spell_check", "ui_quality",
            "yaml_ui", "i18n_deep", "responsive",
        ],
        "estimated_minutes": 3,
    },
    "backend": {
        "name": "Backend / API",
        "description": "Security, API, taint tracking, code quality, error handling",
        "categories": [
            "security", "api", "taint", "code_quality", "error_handling",
            "dependency", "docker", "env", "config", "ast_analysis",
            "sca", "import_graph",
        ],
        "estimated_minutes": 4,
    },
    "security": {
        "name": "Guvenlik",
        "description": "63 guvenlik + SCA + taint tracking + AST",
        "categories": [
            "security", "sca", "taint", "ast_analysis",
            "cross_file", "git",
        ],
        "estimated_minutes": 5,
    },
    "mobile": {
        "name": "Mobil Uyumluluk",
        "description": "App Store + Play Store + accessibility + performance",
        "categories": [
            "appstore", "playstore", "accessibility",
            "performance", "security",
        ],
        "estimated_minutes": 4,
    },
    "ci": {
        "name": "CI/CD (hizli)",
        "description": "Sadece critical/high oncelikli testler, fail-fast, hizli sonuc",
        "categories": [
            "security", "sca", "git", "taint", "ast_analysis",
        ],
        "priority_filter": ["critical", "high"],
        "fail_fast": True,
        "timeout": 300,
        "estimated_minutes": 1,
        "json_output": True,
        "quiet": True,
    },
    "dependency": {
        "name": "Bagimlilik Analizi",
        "description": "npm/pip/go audit, lisans, typosquatting",
        "categories": [
            "sca", "dependency", "license",
        ],
        "estimated_minutes": 2,
    },
    "performance": {
        "name": "Performans",
        "description": "Bundle boyutu, buyuk asset, kaynak analizi",
        "categories": [
            "performance",
        ],
        "estimated_minutes": 1,
    },
}


def get_profile(name: str) -> Optional[dict]:
    """Profil bilgisini getir."""
    return TEST_PROFILES.get(name)


def get_profile_categories(name: str) -> List[str]:
    """Profilin kategori listesini getir."""
    profile = TEST_PROFILES.get(name)
    if not profile:
        return []
    cats = profile.get("categories", "__all__")
    if cats == "__all__":
        return []  # bos liste = tum kategoriler
    return cats


def get_profile_priority_filter(name: str) -> List[str]:
    """Profilin priority filtresini getir. Bos liste = filtre yok."""
    profile = TEST_PROFILES.get(name)
    if not profile:
        return []
    return profile.get("priority_filter", [])


def get_profile_fail_fast(name: str) -> bool:
    """Profilin fail_fast ayarini getir."""
    profile = TEST_PROFILES.get(name)
    if not profile:
        return False
    return profile.get("fail_fast", False)


def get_profile_defaults(name: str) -> dict:
    """Profilin varsayilan cikti ayarlarini getir (json_output, quiet vb.)."""
    profile = TEST_PROFILES.get(name)
    if not profile:
        return {}
    defaults = {}
    if profile.get("json_output"):
        defaults["json_output"] = True
    if profile.get("quiet"):
        defaults["quiet"] = True
    return defaults


def list_profiles() -> List[dict]:
    """Tum profilleri listele."""
    return [
        {"key": k, "name": v["name"], "description": v["description"],
         "estimated_minutes": v.get("estimated_minutes", 0)}
        for k, v in TEST_PROFILES.items()
    ]


def resolve_categories(profile_names: List[str]) -> List[str]:
    """Birden fazla profil secildiginde kategorileri birlestirir, duplicate atar."""
    seen = set()
    result = []
    for name in profile_names:
        cats = get_profile_categories(name)
        if not cats:  # __all__
            return []  # full secilmisse hepsini calistir
        for cat in cats:
            if cat not in seen:
                seen.add(cat)
                result.append(cat)
    return result
