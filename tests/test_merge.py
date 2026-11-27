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


def test_identical_batch_basenames_do_not_collide(fake_plink, tmp_path):
    wave1 = tmp_path / "wave1"
    wave2 = tmp_path / "wave2"
    wave1.mkdir()
    wave2.mkdir()

    (wave1 / "chr6.bim").write_text("6\trs1\t0\t100\tA\tG\n6\trs2\t0\t200\tC\tT\n")
    (wave1 / "chr6.fam").write_text("F1 S001 0 0 1 -9\n")
    (wave1 / "chr6.bed").write_bytes(b"")

    (wave2 / "chr6.bim").write_text("6\trs1\t0\t100\tT\tC\n6\trs3\t0\t300\tG\tA\n")
    (wave2 / "chr6.fam").write_text("F2 S002 0 0 2 -9\n")
    (wave2 / "chr6.bed").write_bytes(b"")

    keep = _keep(tmp_path, "F1 S001\nF2 S002\n")
    out = str(tmp_path / "final")
    report = GenotypeMerger(fake_plink).merge(
        [str(wave1 / "chr6"), str(wave2 / "chr6")],
        keep,
        out,
        work_dir=str(tmp_path / "work"),
        convert_to_vcf=False,
    )
    assert report.correction_applied
    assert report.conflict_snps == ["rs1"]
    assert report.final_sample_count == 2
    fam_text = Path(out + ".fam").read_text()
    assert "S001" in fam_text
    assert "S002" in fam_text


def test_other_merge_failure_raises_without_rerunning(
    fake_plink, batches, tmp_path, monkeypatch
):
    monkeypatch.setenv("FAKE_PLINK_FAIL_MERGE", "1")
    keep = _keep(tmp_path, "F1 S001\nF4 S004\n")

    merger = GenotypeMerger(fake_plink)
    merge_calls = 0
    orig_run_plink = merger._run_plink

    def counting_run(args, check=True):
        nonlocal merge_calls
        if "--merge-list" in args:
            merge_calls += 1
        return orig_run_plink(args, check=check)

    monkeypatch.setattr(merger, "_run_plink", counting_run)

    with pytest.raises(PlinkError, match="Duplicate sample ID"):
        merger.merge(
            batches["prefixes"],
            keep,
            str(tmp_path / "final"),
            work_dir=str(tmp_path / "w"),
        )
    assert merge_calls == 1


def test_stale_missnp_ignored_on_non_conflict_failure(
    fake_plink, batches, tmp_path, monkeypatch
):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "merge_attempt-merge.missnp").write_text("rs1\n")
    monkeypatch.setenv("FAKE_PLINK_FAIL_MERGE", "1")
    keep = _keep(tmp_path, "F1 S001\nF4 S004\n")

    with pytest.raises(PlinkError, match="Duplicate sample ID"):
        GenotypeMerger(fake_plink).merge(
            batches["prefixes"],
            keep,
            str(tmp_path / "final"),
            work_dir=str(work_dir),
        )


def test_single_batch_goes_straight_to_output(fake_plink, batches, tmp_path):
    keep = _keep(tmp_path, "F1 S001\n")
    out = str(tmp_path / "final")
    report = GenotypeMerger(fake_plink).merge(
        batches["prefixes"][:1], keep, out, work_dir=str(tmp_path / "work")
    )
    assert report.final_sample_count == 1
    assert Path(out + ".vcf.gz").exists()


def test_empty_batches_raises(tmp_path):
    keep = _keep(tmp_path, "F1 S001\n")
    with pytest.raises(ValueError, match="No batches"):
        GenotypeMerger().merge([], keep, str(tmp_path / "final"))
