"""Validate shipped HA locales without importing Home Assistant.

Locale filenames follow HA's BCP47 convention, including case-sensitive pt-BR:
https://developers.home-assistant.io/docs/internationalization/custom_integration/
https://github.com/home-assistant/frontend/blob/dev/src/translations/translationMetadata.json
English is the semantic source; Italian is retained as an existing cross-check.
"""

from collections import Counter
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "custom_components/backup_manager_actions/translations"
LOCALES = {"en", "it", "de", "fr", "es", "nl", "pt-BR"}
NEW_LOCALES = LOCALES - {"en", "it"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate translation key: {key}")
        result[key] = value
    return result


def flatten(value, path=()):
    """Keep container nodes too, so extra empty objects cannot escape checks."""
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from flatten(child, (*path, key))


class TranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {
            path.stem: json.loads(path.read_text(encoding="utf-8"),
                                  object_pairs_hook=unique_object)
            for path in TRANSLATIONS.glob("*.json")
        }
        cls.flat = {locale: dict(flatten(data)) for locale, data in cls.data.items()}

    def test_exact_locale_files_and_unique_json_keys(self):
        self.assertEqual(set(self.data), LOCALES)

    def test_same_keys_and_value_types_as_english(self):
        english = self.flat["en"]
        for locale, translated in self.flat.items():
            with self.subTest(locale=locale):
                self.assertEqual(set(translated), set(english))
                for path, value in english.items():
                    self.assertIs(type(translated[path]), type(value), path)

    def test_nonempty_strings_and_no_build_time_references(self):
        for locale, translated in self.flat.items():
            for path, value in translated.items():
                if isinstance(value, dict):
                    continue
                with self.subTest(locale=locale, path=path):
                    self.assertIsInstance(value, str)
                    self.assertTrue(value.strip())
                    self.assertEqual(value, value.strip())
                    self.assertNotIn("[%key:", value)

    def test_placeholder_names_and_counts_match_english(self):
        for locale, translated in self.flat.items():
            for path, value in self.flat["en"].items():
                if isinstance(value, str):
                    with self.subTest(locale=locale, path=path):
                        self.assertEqual(
                            Counter(re.findall(r"\{[^{}]+\}", value)),
                            Counter(re.findall(r"\{[^{}]+\}", translated[path])),
                        )

    def test_new_locales_preserve_technical_terms(self):
        terms = ("Home Assistant", "Backup Agent", "SSL", "BMA", "HA Native",
                 "App Update", "full", "partial", "ISO", "N-1")
        for locale in NEW_LOCALES:
            for path, value in self.flat["en"].items():
                if not isinstance(value, str):
                    continue
                for term in terms:
                    if term in value:
                        with self.subTest(locale=locale, path=path, term=term):
                            self.assertIn(term, self.flat[locale][path])
            self.assertEqual(self.data[locale]["title"], "Backup Manager Actions")

    def test_plan_and_apply_share_retention_field_wording(self):
        for locale, data in self.data.items():
            with self.subTest(locale=locale):
                services = data["services"]
                self.assertEqual(services["plan_retention"]["fields"],
                                 services["apply_retention"]["fields"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
