"""The production failure was a ``slef`` typo that ruff did not report.

Ignoring F403 makes ruff treat later undefined names as F405, and it then
suppresses F405 as well. A file that star-imports can therefore contain
``slef`` and still pass. These checks fail the build if that hole returns.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ruff(*args):
    return subprocess.run(
        ["ruff", "check", "--config", str(ROOT / "ruff.toml"), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_ruff_config_does_not_ignore_star_import_rules():
    text = (ROOT / "ruff.toml").read_text(encoding="utf-8")
    assert 'lint.ignore = ["SIM105"]' in text
    assert "F403" not in text
    assert '"F"' in text


def test_undefined_slef_is_f821(tmp_path):
    sample = tmp_path / "bare.py"
    sample.write_text("def check(self):\n    return slef.value\n", encoding="utf-8")
    result = _ruff(str(sample))
    assert result.returncode != 0
    assert "F821" in result.stdout


def test_star_import_does_not_hide_slef(tmp_path):
    sample = tmp_path / "starred.py"
    sample.write_text(
        "from os.path import *\n\n\ndef check(self):\n    return slef.value\n",
        encoding="utf-8",
    )
    result = _ruff(str(sample))
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "F403" in combined
    assert "F405" in combined


def test_application_sources_have_no_slef_typo():
    for path in (ROOT / "python").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "slef" not in text
        assert "sefl" not in text
