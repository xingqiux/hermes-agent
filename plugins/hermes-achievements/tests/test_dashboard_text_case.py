from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "dashboard" / "dist"


def test_dashboard_bundle_overrides_app_shell_uppercase():
    css = (DASHBOARD_DIR / "style.css").read_text(encoding="utf-8")

    assert ".ha-page" in css
    assert ".ha-page, .ha-page *" in css
    assert "text-transform: none" in css


def test_share_card_keeps_human_readable_case():
    js = (DASHBOARD_DIR / "index.js").read_text(encoding="utf-8")

    assert ".toUpperCase()" not in js
    assert '" TIER"' not in js
    assert '"Hermes Agent"' in js
