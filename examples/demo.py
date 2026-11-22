"""Run the whole delivery pipeline on synthetic data, offline.

PLINK is replaced by examples/fake_plink.py, a small stand-in that mimics
the behaviour this pipeline depends on (extraction, merge conflicts via
-merge.missnp, VCF conversion). For real use, install PLINK 1.9 and pass its
path as plink_exec. All samples and variants here are made up.

Run from the repository root:  python examples/demo.py
"""

from __future__ import annotations

import stat
import sys
import tempfile
from pathlib import Path

from cohort_delivery import DeliveryPipeline
from cohort_delivery.pipeline import PipelineConfig

HERE = Path(__file__).resolve().parent


def build_inputs(root: Path) -> PipelineConfig:
    raw = root / "raw"
    raw.mkdir()
    # Batch 1: SYN01-SYN06. Batch 2: SYN07-SYN10. rs9300001 has different
    # alleles in the two batches (a strand problem), so the merge conflicts.
    (raw / "batch_01.bim").write_text(
        "1\trs9300001\t0\t1000\tA\tG\n"
        "1\trs9300002\t0\t2000\tC\tT\n"
        "2\trs9300003\t0\t3000\tG\tA\n"
    )
    (raw / "batch_02.bim").write_text(
        "1\trs9300001\t0\t1000\tT\tC\n"
        "1\trs9300002\t0\t2000\tC\tT\n"
        "2\trs9300003\t0\t3000\tG\tA\n"
        "3\trs9300004\t0\t4000\tA\tC\n"
    )
    for name, ids in (("batch_01", range(1, 7)), ("batch_02", range(7, 11))):
        (raw / f"{name}.fam").write_text(
            "".join(f"F{i:02d} SYN{i:02d} 0 0 1 -9\n" for i in ids)
        )
        (raw / f"{name}.bed").write_bytes(b"")

    cohort = root / "cohort_all_samples.txt"
    cohort.write_text("".join(f"F{i:02d} SYN{i:02d}\n" for i in range(1, 11)))
    exclusions = root / "exclusions.csv"
    exclusions.write_text("SampleID,Reason\nSYN03,Withdrawal\nSYN08,SexMismatch\n")

    plink = root / "bin" / "plink"
    plink.parent.mkdir()
    plink.write_text(f"#!{sys.executable}\n" + (HERE / "fake_plink.py").read_text())
    plink.chmod(plink.stat().st_mode | stat.S_IXUSR)

    return PipelineConfig(
        project_id="DEMO01",
        cohort_file=str(cohort),
        exclusion_files=[str(exclusions)],
        batch_prefixes=[str(raw / "batch_01"), str(raw / "batch_02")],
        work_dir=str(root / "work"),
        delivery_dir=str(root / "delivery"),
        staging_root=str(root / "staging"),
        plink_exec=str(plink),
        transfer_method="copy",
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config = build_inputs(Path(tmp))
        result = DeliveryPipeline().run(config)

        f, m, t = result.filter_report, result.merge_report, result.transfer_report
        assert f is not None and m is not None and t is not None
        print(f"Cohort: {f.original_count} samples; ", end="")
        print(f"removed {f.removed_count} {f.exclusion_reasons}")
        print(f"Merged: {m.final_sample_count} samples, ", end="")
        print(f"{m.final_variant_count} variants")
        print(f"Excluded for allele conflicts: {m.conflict_snps}")
        print(f"Delivered {t.file_count} files; checksums verified: {t.verified}")
        for name in sorted(p.name for p in Path(t.destination_dir).iterdir()):
            print(f"  {name}")


if __name__ == "__main__":
    main()
