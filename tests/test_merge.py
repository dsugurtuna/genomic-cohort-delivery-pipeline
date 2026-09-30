"""Tests for GenotypeMerger, run against a fake plink (see conftest.py)."""

from pathlib import Path

import pytest

from cohort_delivery.merge import GenotypeMerger, PlinkError


def _keep(tmp_path: Path, lines: str) -> str:
    keep = tmp_path / "keep.txt"
    keep.write_text(lines)
    return str(keep)


def test_conflicting_variant_is_excluded_and_reported(fake_plink, batches, tmp_path):
    keep = _keep(tmp_path, "F1 S001\nF3 S003\nF4 S004\nF5 S005\n")
    out = str(tmp_path / "final")
    report = GenotypeMerger(fake_plink).merge(
        batches["prefixes"], keep, out, work_dir=str(tmp_path / "work")
    )
    assert report.correction_applied
    assert report.conflict_snps == ["rs1"]
    assert report.final_sample_count == 4
    assert report.final_variant_count == 2  # rs2, rs3
    assert "rs1" not in Path(out + ".bim").read_text()
    assert Path(out + ".vcf.gz").exists()


def test_clean_merge_needs_no_correction(fake_plink, batches, tmp_path):
    # Only batch_02 conflicts with batch_01 on rs1; merging batch_02 with
    # itself under another name has no conflict.
    raw = Path(batches["prefixes"][1]).parent
    for ext in (".bim", ".fam", ".bed"):
        (raw / f"copy{ext}").write_bytes((raw / f"batch_02{ext}").read_bytes())
    keep = _keep(tmp_path, "F4 S004\n")
    report = GenotypeMerger(fake_plink).merge(
        [batches["prefixes"][1], str(raw / "copy")],
        keep,
        str(tmp_path / "final"),
        work_dir=str(tmp_path / "work"),
        convert_to_vcf=False,
    )
    assert not report.correction_applied
    assert report.final_variant_count == 3


def test_other_merge_failure_raises(fake_plink, batches, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_PLINK_FAIL_MERGE", "1")
    keep = _keep(tmp_path, "F1 S001\nF4 S004\n")
    with pytest.raises(PlinkError, match="Duplicate sample ID"):
        GenotypeMerger(fake_plink).merge(
            batches["prefixes"],
            keep,
            str(tmp_path / "final"),
            work_dir=str(tmp_path / "w"),
        )


def test_single_batch_goes_straight_to_output(fake_plink, batches, tmp_path):
    keep = _keep(tmp_path, "F1 S001\n")
    out = str(tmp_path / "final")
    report = GenotypeMerger(fake_plink).merge(
        batches["prefixes"][:1], keep, out, work_dir=str(tmp_path / "work")
    )
    assert report.final_sample_count == 1
    assert Path(out + ".vcf.gz").exists()
