"""Scanner icin sabit pattern ve tanimlamalar."""

IGNORE_DIRS = {
    "node_modules", ".git", "build", "dist", ".next", ".nuxt",
    "__pycache__", ".pytest_cache", "venv", ".venv", "env",
    "Pods", ".gradle", "android/build", "ios/build", ".expo",
    "coverage", ".nyc_output", "vendor",
}

TECH_MARKERS = {
    "react-native": [("react-native", "package.json"), ("expo", "app.json")],
    "flutter": [("flutter", "pubspec.yaml")],
    "ios-native": [(None, "*.xcodeproj"), (None, "*.xcworkspace")],
    "android-native": [(None, "build.gradle"), (None, "build.gradle.kts")],
    "nextjs": [("next", "package.json"), (None, "next.config.js"), (None, "next.config.mjs")],
    "vue": [("vue", "package.json"), (None, "vue.config.js")],
    "django": [(None, "manage.py"), ("django", "requirements.txt")],
    "fastapi": [("fastapi", "requirements.txt"), ("fastapi", "pyproject.toml")],
    "flask": [("flask", "requirements.txt")],
    "express": [("express", "package.json")],
    "nestjs": [("@nestjs/core", "package.json")],
    "spring": [(None, "pom.xml")],
    "dotnet": [(None, "*.csproj"), (None, "*.sln")],
    "go": [(None, "go.mod")],
    "rust": [(None, "Cargo.toml")],
    "ruby-rails": [("rails", "Gemfile"), (None, "config/routes.rb")],
    "php-laravel": [("laravel/framework", "composer.json"), (None, "artisan")],
}

API_PATTERNS = {
    "js": [
        (r"""fetch\s*\(\s*[`'"](https?://[^`'"]+|/[^`'"]+)[`'"]""", "GET"),
        (r"""axios\.(get|post|put|delete|patch)\s*\(\s*[`'"](https?://[^`'"]+|/[^`'"]+)[`'"]""", None),
        (r"""\.(get|post|put|delete|patch)\s*\(\s*[`'"](/api/[^`'"]+)[`'"]""", None),
    ],
    "py": [
        (r"""requests\.(get|post|put|delete|patch)\s*\(\s*[f]?['"](https?://[^'"]+|/[^'"]+)['"]""", None),
        (r"""@app\.(get|post|put|delete|patch)\s*\(\s*['"](/[^'"]+)['"]""", None),
        (r"""@router\.(get|post|put|delete|patch)\s*\(\s*['"](/[^'"]+)['"]""", None),
    ],
    "go": [
        (r"""HandleFunc\s*\(\s*['"](/[^'"]+)['"]""", "GET"),
        (r"""\.(GET|POST|PUT|DELETE)\s*\(\s*['"](/[^'"]+)['"]""", None),
    ],
    "rb": [(r"""(get|post|put|delete|patch)\s+['"](/[^'"]+)['"]""", None)],
    "java": [
        (r"""@(GetMapping|PostMapping|PutMapping|DeleteMapping)\s*\(\s*['"](/[^'"]+)['"]""", None),
    ],
    "php": [(r"""Route::(get|post|put|delete|patch)\s*\(\s*['"](/[^'"]+)['"]""", None)],
    "rs": [(r"""#\[(get|post|put|delete)\s*\(\s*['"](/[^'"]+)['"]\s*\)\]""", None)],
}

TEST_PATTERNS = [
    r".*test.*\.(js|ts|tsx|jsx|py|go|rs|rb|java|php|cs)$",
    r".*spec.*\.(js|ts|tsx|jsx|rb)$",
    r".*_test\.(go|py|rb)$",
    r".*Test\.(java|cs|php)$",
]

SCREEN_PATTERNS = {
    "react-native": [
        (r"export\s+(?:default\s+)?(?:function|class|const)\s+(\w*Screen\w*)", "screen"),
        (r"export\s+(?:default\s+)?(?:function|class|const)\s+(\w*Page\w*)", "screen"),
        (r"export\s+(?:default\s+)?(?:function|class|const)\s+(\w*View\w*)", "view"),
        (r"export\s+(?:default\s+)?(?:function|class|const)\s+(\w*Modal\w*)", "modal"),
    ],
    "flutter": [
        (r"class\s+(\w*Screen\w*)\s+extends\s+(?:Stateful|Stateless)Widget", "screen"),
        (r"class\s+(\w*Page\w*)\s+extends\s+(?:Stateful|Stateless)Widget", "screen"),
    ],
    "ios-native": [
        (r"class\s+(\w*ViewController\w*)\s*:", "screen"),
        (r"struct\s+(\w*View\w*)\s*:\s*View", "view"),
    ],
    "generic": [
        (r"export\s+(?:default\s+)?(?:function|class|const)\s+(\w+)", "component"),
        (r"class\s+(\w+)", "component"),
    ],
}

STATE_LIBS = {
    "redux": ["redux", "@reduxjs/toolkit", "react-redux"],
    "mobx": ["mobx", "mobx-react"],
    "zustand": ["zustand"],
    "recoil": ["recoil"],
    "jotai": ["jotai"],
    "provider": ["provider"],
    "riverpod": ["riverpod", "flutter_riverpod"],
    "bloc": ["bloc", "flutter_bloc"],
    "vuex": ["vuex"],
    "pinia": ["pinia"],
}

NAVIGATION_LIBS = {
    "react-navigation": ["@react-navigation/native"],
    "expo-router": ["expo-router"],
    "react-router": ["react-router", "react-router-dom"],
    "vue-router": ["vue-router"],
    "go-router": ["go_router"],
}

SOURCE_EXTS = {
    ".js", ".jsx", ".ts", ".tsx", ".py", ".dart",
    ".swift", ".kt", ".java", ".go", ".rs", ".rb", ".php", ".cs",
}

EXT_TO_LANG = {
    ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".py": "Python", ".dart": "Dart", ".swift": "Swift",
    ".kt": "Kotlin", ".java": "Java", ".go": "Go",
    ".rs": "Rust", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
}

EXT_TO_API_LANG = {
    ".js": "js", ".jsx": "js", ".ts": "js", ".tsx": "js",
    ".py": "py", ".go": "go", ".rb": "rb",
    ".java": "java", ".php": "php", ".rs": "rs",
}
