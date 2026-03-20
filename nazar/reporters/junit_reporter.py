"""JUnit XML Reporter - CI/CD entegrasyonu icin JUnit XML formati."""
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import List, Dict


class JUnitReporter:
    """JUnit XML cikti reporter'i."""

    def generate(self, results: List[Dict], plan: dict, output_path: str = None) -> str:
        """JUnit XML rapor olustur."""
        total = len(results)
        passed = sum(1 for r in results if r["passed"])
        failed = total - passed
        total_time = sum(r.get("duration", 0) for r in results)

        testsuites = ET.Element("testsuites")
        testsuites.set("tests", str(total))
        testsuites.set("failures", str(failed))
        testsuites.set("time", f"{total_time:.3f}")
        testsuites.set("timestamp", datetime.now().isoformat())
        testsuites.set("name", "Nazar")

        # Kategorilere ayir
        categories: Dict[str, List[Dict]] = {}
        for r in results:
            cat = r.get("type", "other")
            categories.setdefault(cat, []).append(r)

        for cat_name, cat_tests in categories.items():
            cat_passed = sum(1 for t in cat_tests if t["passed"])
            cat_failed = len(cat_tests) - cat_passed
            cat_time = sum(t.get("duration", 0) for t in cat_tests)

            testsuite = ET.SubElement(testsuites, "testsuite")
            testsuite.set("name", cat_name)
            testsuite.set("tests", str(len(cat_tests)))
            testsuite.set("failures", str(cat_failed))
            testsuite.set("time", f"{cat_time:.3f}")

            for test in cat_tests:
                testcase = ET.SubElement(testsuite, "testcase")
                testcase.set("name", test["name"])
                testcase.set("classname", f"nazar.{cat_name}")
                testcase.set("time", f"{test.get('duration', 0):.3f}")

                if not test["passed"]:
                    failure = ET.SubElement(testcase, "failure")
                    failure.set("message", test.get("detail", "Test failed"))
                    failure.set("type", test.get("priority", "medium"))
                    failure.text = test.get("detail", "")

        tree = ET.ElementTree(testsuites)
        ET.indent(tree, space="  ")
        xml_str = ET.tostring(testsuites, encoding="unicode", xml_declaration=True)

        if output_path:
            Path(output_path).write_text(xml_str)
        return xml_str
