"""The engine answers replayed by the interface tests (app/e2e/fixtures/) are those of the current engine."""

import subprocess
import sys
from pathlib import Path

APP_E2E = Path(__file__).resolve().parents[2] / "app" / "e2e"


def test_the_interface_tests_replay_the_current_engine_answers(tmp_path):
    # A separate process: the generator sets the engine's folders before importing it.
    subprocess.run([sys.executable, str(APP_E2E / "make_fixtures.py"), str(tmp_path)], check=True,
                   capture_output=True, timeout=120)
    committed = APP_E2E / "fixtures"
    stale = [f.name for f in sorted(tmp_path.iterdir())
             if not (committed / f.name).is_file() or (committed / f.name).read_text() != f.read_text()]
    assert not stale, f"out of date, run app/e2e/make_fixtures.py again: {stale}"
