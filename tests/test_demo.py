"""Smoke test: the README quickstart demo runs and prints what the README shows."""

import runpy
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo.py"


def test_demo_output(capsys):
    runpy.run_path(str(DEMO), run_name="__main__")
    out = capsys.readouterr().out
    assert "Cohort: 10 samples; removed 2 {'Withdrawal': 1, 'SexMismatch': 1}" in out
    assert "Merged: 8 samples, 3 variants" in out
    assert "Excluded for allele conflicts: ['rs9300001']" in out
    assert "Delivered 7 files; checksums verified: True" in out
