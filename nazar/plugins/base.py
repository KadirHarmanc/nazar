"""Base plugin class - Tum plugin'ler bunu extend eder."""
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple


class BaseTestPlugin(ABC):
    """Nazar test plugin base class.

    Kendi test kurallarinizi yazmak icin bu class'i extend edin.
    """

    name: str = "unnamed-plugin"
    version: str = "0.1.0"
    description: str = ""

    @abstractmethod
    def get_tests(self, scan_result) -> List[Dict]:
        """Plugin'in calistiracagi testlerin listesini dondur.

        Her test dict'i su alanlari icermeli:
        - name: Test adi
        - type: Test kategorisi
        - subtype: Alt kategori
        - priority: critical/high/medium/low
        """
        ...

    @abstractmethod
    def run_test(self, test: dict, project_path: str) -> Tuple[bool, str]:
        """Tek bir testi calistir.

        Returns:
            (passed, detail) tuple'i
        """
        ...

    def setup(self) -> None:
        """Plugin baslangic islemleri (opsiyonel)."""
        pass

    def teardown(self) -> None:
        """Plugin bitis islemleri (opsiyonel)."""
        pass
