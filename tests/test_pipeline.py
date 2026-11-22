"""End-to-end pipeline test with a fake plink and copy transfer."""

from pathlib import Path

import pytest

from cohort_delivery.pipeline import DeliveryPipeline, PipelineConfig


def test_pipeline_end_to_end(fake_plink, batches, tmp_path):
    config = PipelineConfig(
        project_id="DEMO01",
        cohort_file=batches["cohort"],
        exclusion_files=[batches["exclusions"]],
        batch_prefixes=batches["prefixes"],
        work_dir=str(tmp_path / "work"),
        delivery_dir=str(tmp_path / "delivery"),
        staging_root=str(tmp_path / "staging"),
        plink_exec=fake_plink,
        transfer_method="copy",
    )
    result = DeliveryPipeline().run(config)

    assert result.filter_report.removed_count == 1
    assert result.filter_report.exclusion_reasons == {"Withdrawal": 1}
    assert result.merge_report.conflict_snps == ["rs1"]
    assert result.merge_report.final_sample_count == 4
    assert result.transfer_report.verified
    assert result.transfer_report.problems == []

    status = (tmp_path / "delivery" / "STATUS_SUMMARY.tsv").read_text()
    assert "Samples_Requested\t4" in status
    assert "Variants_Excluded_Conflicts\t1" in status
    assert "PASS" not in status

    dest = Path(result.transfer_report.destination_dir)
    fam = (dest / "DEMO01_final_genotypes.fam").read_text()
    assert "S002" not in fam


def test_pipeline_stops_when_everyone_is_excluded(batches, tmp_path):
    excl = tmp_path / "all.csv"
    excl.write_text("SampleID\nS001\nS002\nS003\nS004\nS005\n")
    config = PipelineConfig(
        cohort_file=batches["cohort"],
        exclusion_files=[str(excl)],
        work_dir=str(tmp_path / "work"),
        delivery_dir=str(tmp_path / "delivery"),
        staging_root=str(tmp_path / "staging"),
    )
    with pytest.raises(ValueError, match="No samples left"):
        DeliveryPipeline().run(config)
