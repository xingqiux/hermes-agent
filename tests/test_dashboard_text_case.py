from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_shell_does_not_force_uppercase_text():
    app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "bg-black uppercase text-midground" not in app


def test_dashboard_shell_does_not_inherit_display_font():
    app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert 'className="font-mondwest flex h-dvh' not in app


def test_dashboard_uppercase_utility_is_neutralized_for_localized_fork():
    css = (ROOT / "web" / "src" / "index.css").read_text(encoding="utf-8")

    assert "#root .uppercase" in css
    assert "#root .text-display" in css
    assert '[class*="tracking-"]' in css
    assert "text-transform: none" in css
    assert "letter-spacing: 0" in css


def test_models_page_new_settings_copy_uses_i18n():
    page = (ROOT / "web" / "src" / "pages" / "ModelsPage.tsx").read_text(
        encoding="utf-8"
    )
    zh = (ROOT / "web" / "src" / "i18n" / "zh.ts").read_text(encoding="utf-8")

    assert 'mt("modelSettings", "Model Settings")' in page
    assert 'modelSettings: "模型设置"' in zh
