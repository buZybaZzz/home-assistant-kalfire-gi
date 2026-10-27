"""Test automatic titles without contacting GitHub."""

import custom_components.kalfire_gi.discovery  # noqa: F401
from scripts.name_test_report import DEFAULT_TITLE, make_title


def report(model="Gi85/55S", version="v0.1.4", other="_No response_"):
    return (
        f"### Exact Gi model\n\n{model}\n\n"
        f"### Kalfire Gi Local version tested\n\n{version}\n\n"
        f"### Other integration version or build\n\n{other}\n\n"
        "### Home Assistant and HACS versions\n\n2026.10.2\n"
    )


def test_release_version():
    assert make_title(DEFAULT_TITLE, report()) == "[Test report] Gi85/55S — v0.1.4"


def test_custom_and_unknown_version():
    option = "Other / unknown (specify below)"
    assert make_title(DEFAULT_TITLE, report(version=option, other="main abc123")) == (
        "[Test report] Gi85/55S — main abc123"
    )
    assert make_title(DEFAULT_TITLE, report(version=option)).endswith(" — unknown version")


def test_skip_custom_title_and_missing_fields():
    assert make_title("User's chosen title", report()) is None
    assert make_title(DEFAULT_TITLE, report(model="_No response_")) is None
    assert make_title(DEFAULT_TITLE, "### Different form\n\ntext") is None


def test_long_values_and_control_characters():
    title = make_title(DEFAULT_TITLE, report(model="X" * 400, version="v0.1.4\x00"))
    assert len(title) <= 256
    assert "\x00" not in title
