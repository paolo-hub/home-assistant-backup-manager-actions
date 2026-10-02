"""Check the static action UI contract and its English/Italian explanations."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1] / "custom_components" / "backup_manager_actions"


def test_folder_selector_preserves_ssl_and_native_defaults():
    fields = yaml.safe_load((ROOT / "services.yaml").read_text())["create"]["fields"]
    folders = fields["include_folders"]
    assert set(folders) == {"selector"}
    assert folders["selector"]["select"]["multiple"] is True
    assert [option["value"] for option in folders["selector"]["select"]["options"]] == [
        "share", "addons/local", "ssl", "media"
    ]
    assert fields["include_homeassistant"]["default"] is True


def test_ssl_explanation_in_both_translations():
    for language, label, automatic in (
        ("en", "Additional folders", "automatically included"),
        ("it", "Cartelle aggiuntive", "inclusa automaticamente"),
    ):
        data = json.loads((ROOT / "translations" / f"{language}.json").read_text())
        fields = data["services"]["create"]["fields"]
        assert fields["include_folders"]["name"] == label
        for field in ("include_folders", "include_homeassistant"):
            assert "SSL" in fields[field]["description"]
            assert automatic in fields[field]["description"]
        assert ("not included" if language == "en" else "non è incluso") in fields["include_folders"]["description"]


if __name__ == "__main__":
    test_folder_selector_preserves_ssl_and_native_defaults()
    test_ssl_explanation_in_both_translations()
    print("action UI schema: OK (2 tests)")
