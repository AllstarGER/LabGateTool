"""Sichert ab, dass die LabGate-Aktion nicht mehr direkt auf die Portal-Datenbank zugreift."""

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATTERNS = (
    r"\bmysql\.connector\b",
    r"\bMySQLConnectionPool\b",
    r"\bimport\s+labgate_db\b",
    r"\blabgate_db\.",
    r"\[Database\]",
)
SOURCE_SUFFIXES = (".py", ".spec", ".txt", ".ini", ".md")


def source_files():
    for path in sorted(PROJECT_ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if relative.startswith(".git/") or relative.startswith("tests/") or "__pycache__" in relative:
            continue
        yield path, relative


class NoDirectDatabaseAccessTests(unittest.TestCase):
    def test_no_direct_database_artefacts_in_sources(self):
        findings = []
        for path, relative in source_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in FORBIDDEN_PATTERNS:
                if re.search(pattern, text):
                    findings.append(f"{relative}: {pattern}")
        self.assertEqual(findings, [], f"Direkter Datenbankzugriff gefunden: {findings}")

    def test_former_database_module_is_gone(self):
        self.assertFalse((PROJECT_ROOT / "labgate_db.py").exists())

    def test_api_client_is_the_only_data_source(self):
        service = (PROJECT_ROOT / "labgate_action_service.py").read_text(encoding="utf-8")
        ui = (PROJECT_ROOT / "ui" / "labgateaction.py").read_text(encoding="utf-8")
        for source in (service, ui):
            self.assertIn("import labgate_api", source)
            self.assertNotIn("get_connection(", source)

    def test_requirements_do_not_pull_a_database_driver(self):
        requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertNotIn("mysql", requirements)
        self.assertNotIn("cryptography", requirements)


if __name__ == "__main__":
    unittest.main()
