"""Nazar Error Hierarchy - Tum hata tipleri."""


class NazarBaseError(Exception):
    """Tum Nazar hatalarinin atasi."""
    pass


class ProfileError(NazarBaseError):
    """Profil bulunamadi veya uyumsuz."""
    pass


class YAMLValidationError(NazarBaseError):
    """YAML syntax veya semantic hatasi."""
    pass


class RuntimeNotFoundError(NazarBaseError):
    """Maestro/Appium gibi runtime yuklu degil."""
    pass


class DeviceNotFoundError(NazarBaseError):
    """Cihaz bagli degil veya simulator kapalı."""
    pass


class AnalysisError(NazarBaseError):
    """Proje analiz edilemedi."""
    pass


class ScanTimeoutError(NazarBaseError):
    """Tarama zaman asimina ugradi."""
    pass
