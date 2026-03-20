"""Language Rules - Dil bazinda kural filtreleme motoru."""

# Hangi kurallar hangi dosya uzantilarinda ATLANMALI (false positive onleme)
SKIP_RULES = {
    # Swift'te var gecerli keyword
    "var_usage": {".swift", ".kt"},
    # Config dosyalarinda function() normal (module.exports = function() tehlikeli degil)
    "dangerous_functions": {".config.js", ".config.ts", ".config.mjs", ".config.cjs",
                            "babel.config", "webpack.config", "vite.config", "next.config",
                            "metro.config", "jest.config", "tailwind.config", "postcss.config",
                            "eslint.config", "prettier.config", "tsconfig"},
    # Test dosyalarinda debug statement normal
    "debug_statements": {".test.", ".spec.", "__tests__"},
    # Frontend component dosyalarinda relative import (../) path traversal DEGIL
    "path_traversal": {".tsx", ".jsx", ".vue", ".svelte"},
}

# Hangi kurallar hangi dosya uzantilarinda GECERLI
APPLY_RULES = {
    "mutable_default": {".py"},
    "bare_except": {".py"},
    "global_usage": {".py"},
    "star_import": {".py"},
    "loose_equality": {".js", ".jsx", ".ts", ".tsx"},
    "unchecked_error_go": {".go"},
    "unwrap_abuse": {".rs"},
}


def should_skip_rule(subtype: str, file_path: str) -> bool:
    """Check if a rule should be skipped for a given file."""
    # Check SKIP_RULES
    if subtype in SKIP_RULES:
        skip_patterns = SKIP_RULES[subtype]
        for pattern in skip_patterns:
            if pattern in file_path.lower():
                return True

    # Check APPLY_RULES (if rule has specific extensions, skip others)
    if subtype in APPLY_RULES:
        valid_exts = APPLY_RULES[subtype]
        file_ext = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""
        if file_ext not in valid_exts:
            return True

    return False


def get_language_from_ext(file_path: str) -> str:
    """Get language name from file extension."""
    ext_map = {
        ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".py": "python",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".java": "java",
        ".kt": "kotlin",
        ".swift": "swift",
        ".dart": "dart",
        ".php": "php",
        ".cs": "csharp",
    }
    ext = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""
    return ext_map.get(ext, "unknown")
