"""Shared fixtures: a fake `plink` executable and small synthetic batches.

The fake (tests/fake_plink.py) implements just enough of PLINK 1.9's
behaviour for these tests. Set FAKE_PLINK_FAIL_MERGE=1 to make merges fail
for a reason other than an allele conflict.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

FAKE_PLINK = Path(__file__).with_name("fake_plink.py")


@pytest.fixture()
def fake_plink(tmp_path: Path) -> str:
    path = tmp_path / "bin" / "plink"
    path.parent.mkdir()
    path.write_text(f"#!{sys.executable}\n" + FAKE_PLINK.read_text())
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


@pytest.fixture()
def batches(tmp_path: Path) -> dict[str, object]:
    """Two synthetic batches. rs1 is A/G in batch_01 but A/C in batch_02."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "batch_01.bim").write_text("1\trs1\t0\t100\tA\tG\n1\trs2\t0\t200\tC\tT\n")
    (raw / "batch_01.fam").write_text(
        "F1 S001 0 0 1 -9\nF2 S002 0 0 2 -9\nF3 S003 0 0 1 -9\n"
    )
    (raw / "batch_01.bed").write_bytes(b"")
    (raw / "batch_02.bim").write_text(
        "1\trs1\t0\t100\tA\tC\n1\trs2\t0\t200\tC\tT\n2\trs3\t0\t300\tG\tA\n"
    )
    (raw / "batch_02.fam").write_text("F4 S004 0 0 2 -9\nF5 S005 0 0 1 -9\n")
    (raw / "batch_02.bed").write_bytes(b"")
    cohort = tmp_path / "cohort.txt"
    cohort.write_text("F1 S001\nF2 S002\nF3 S003\nF4 S004\nF5 S005\n")
    exclusions = tmp_path / "exclusions.csv"
    exclusions.write_text("SampleID,Reason\nS002,Withdrawal\n")
    return {
        "prefixes": [str(raw / "batch_01"), str(raw / "batch_02")],
        "cohort": str(cohort),
        "exclusions": str(exclusions),
    }


@pytest.fixture(autouse=True)
def _no_fail_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAKE_PLINK_FAIL_MERGE", raising=False)
