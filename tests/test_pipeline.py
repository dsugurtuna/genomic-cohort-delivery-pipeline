"""End-to-end pipeline tests with a fake plink and copy transfer."""

from pathlib import Path

import pytest

from cohort_delivery.manifest import ManifestGenerator
from cohort_delivery.merge import GenotypeMerger, MergeReport
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
    assert (dest / "CONFLICT_VARIANTS.txt").read_text() == "rs1\n"

    # Tampering with STATUS_SUMMARY.tsv at destination is caught on disk.
    loaded = ManifestGenerator.read_manifest(str(dest / "MANIFEST.tsv"))
    assert ManifestGenerator().verify(loaded, str(dest)) == []
    (dest / "STATUS_SUMMARY.tsv").write_text("Metric\tValue\nTampered\t1\n")
    problems = ManifestGenerator().verify(loaded, str(dest))
    assert any("STATUS_SUMMARY.tsv" in p for p in problems)


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


@pytest.mark.parametrize("empty_batches", [None, []])
def test_pipeline_rejects_empty_batch_prefixes(batches, tmp_path, empty_batches):
    config = PipelineConfig(
        project_id="EMPTYBATCH",
        cohort_file=batches["cohort"],
        exclusion_files=[batches["exclusions"]],
        batch_prefixes=empty_batches,
        work_dir=str(tmp_path / "work"),
        delivery_dir=str(tmp_path / "delivery"),
        staging_root=str(tmp_path / "staging"),
        transfer_method="copy",
    )
    with pytest.raises(ValueError, match="batch_prefixes"):
        DeliveryPipeline().run(config)


def test_pipeline_governance_gate_catches_leaked_excluded_iid(
    batches, tmp_path, monkeypatch
):
    def leaky_merge(
        self,
        batch_prefixes,
        keep_list,
        output_prefix,
        work_dir="work",
        convert_to_vcf=True,
    ):
        Path(f"{output_prefix}.fam").write_text("F1 S001 0 0 1 -9\nF2 S002 0 0 2 -9\n")
        Path(f"{output_prefix}.bim").write_text("1\trs2\t0\t200\tC\tT\n")
        return MergeReport(
            batch_count=len(batch_prefixes),
            final_sample_count=2,
            final_variant_count=1,
            output_prefix=output_prefix,
        )

    monkeypatch.setattr(GenotypeMerger, "merge", leaky_merge)

    delivery_dir = tmp_path / "delivery"
    staging_root = tmp_path / "staging"
    config = PipelineConfig(
        project_id="LEAKTEST",
        cohort_file=batches["cohort"],
        exclusion_files=[batches["exclusions"]],
        batch_prefixes=batches["prefixes"],
        work_dir=str(tmp_path / "work"),
        delivery_dir=str(delivery_dir),
        staging_root=str(staging_root),
        transfer_method="copy",
    )
    with pytest.raises(RuntimeError, match=r"excluded participant IDs.*S002"):
        DeliveryPipeline().run(config)

    assert not (delivery_dir / "MANIFEST.tsv").exists()
    assert not staging_root.exists()


def test_pipeline_governance_gate_catches_unexpected_iid(
    batches, tmp_path, monkeypatch
):
    def extra_sample_merge(
        self,
        batch_prefixes,
        keep_list,
        output_prefix,
        work_dir="work",
        convert_to_vcf=True,
    ):
        Path(f"{output_prefix}.fam").write_text("F1 S001 0 0 1 -9\nF9 S999 0 0 1 -9\n")
        Path(f"{output_prefix}.bim").write_text("1\trs2\t0\t200\tC\tT\n")
        return MergeReport(
            batch_count=len(batch_prefixes),
            final_sample_count=2,
            final_variant_count=1,
            output_prefix=output_prefix,
        )

    monkeypatch.setattr(GenotypeMerger, "merge", extra_sample_merge)

    config = PipelineConfig(
        project_id="UNREQ",
        cohort_file=batches["cohort"],
        exclusion_files=[batches["exclusions"]],
        batch_prefixes=batches["prefixes"],
        work_dir=str(tmp_path / "work"),
        delivery_dir=str(tmp_path / "delivery"),
        staging_root=str(tmp_path / "staging"),
        transfer_method="copy",
    )
    with pytest.raises(RuntimeError, match=r"unrequested participant IDs.*S999"):
        DeliveryPipeline().run(config)
