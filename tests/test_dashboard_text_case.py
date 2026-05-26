from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_shell_does_not_force_uppercase_text():
    app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "bg-black uppercase text-midground" not in app


def test_dashboard_uppercase_utility_is_neutralized_for_localized_fork():
    css = (ROOT / "web" / "src" / "index.css").read_text(encoding="utf-8")

    assert "#root .uppercase" in css
    assert "text-transform: none" in css
