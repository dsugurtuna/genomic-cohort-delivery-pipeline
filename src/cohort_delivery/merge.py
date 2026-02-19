#!/usr/bin/env python3
"""
Genotype Merge and Correction Module
======================================

Orchestrates the extraction, merge, and automatic correction of multi-batch
PLINK datasets. Implements a self-healing workflow:

  1. Extract cohort samples from each source batch.
  2. Attempt a merge across all batches.
  3. Detect merge failures (flip/strand errors via .missnp files).
  4. Exclude conflicting variants and re-merge.
  5. Convert final result to VCF.

Author: Ugur Tuna
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MergeReport:
    """Summary of a genotype merge operation."""

    batch_count: int = 0
    conflict_snp_count: int = 0
    final_sample_count: int = 0
    final_variant_count: int = 0
    correction_applied: bool = False
    output_prefix: str = ""


class GenotypeMerger:
    """
    Merges multi-batch PLINK binary datasets with automatic conflict
    resolution.

    Example::

        merger = GenotypeMerger(plink_exec="plink")
        report = merger.merge(
            batch_prefixes=["batch_01", "batch_02", "batch_03"],
            keep_list="filtered_samples.txt",
            output_prefix="cohort_final",
            work_dir="work/",
        )
    """

    def __init__(self, plink_exec: str = "plink"):
        self.plink_exec = plink_exec

    def _run_plink(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Execute a PLINK command."""
        cmd = [self.plink_exec] + args
        logger.info("Running: %s", " ".join(cmd))
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def extract_samples(
        self,
        bfile_prefix: str,
        keep_list: str,
        output_prefix: str,
        exclude_snps: Optional[str] = None,
    ) -> str:
        """
        Extract samples from a PLINK binary fileset.

        Parameters
        ----------
        bfile_prefix : str
            PLINK binary file prefix (.bed/.bim/.fam).
        keep_list : str
            Path to a file of sample IDs to keep (FID IID format).
        output_prefix : str
            Output file prefix.
        exclude_snps : str, optional
            Path to a list of SNPs to exclude.

        Returns
        -------
        str
            Output prefix of the extracted dataset.
        """
        args = [
            "--bfile", bfile_prefix,
            "--keep", keep_list,
            "--make-bed",
            "--out", output_prefix,
        ]
        if exclude_snps:
            args.extend(["--exclude", exclude_snps])

        self._run_plink(args)
        return output_prefix

    def merge(
        self,
        batch_prefixes: List[str],
        keep_list: str,
        output_prefix: str,
        work_dir: str = "work",
        convert_to_vcf: bool = True,
    ) -> MergeReport:
        """
        Full merge pipeline with automatic conflict resolution.

        Parameters
        ----------
        batch_prefixes : list of str
            PLINK binary file prefixes for each batch.
        keep_list : str
            Path to filtered sample list.
        output_prefix : str
            Final output prefix.
        work_dir : str
            Working directory for intermediate files.
        convert_to_vcf : bool
            Whether to convert the final merge to VCF.

        Returns
        -------
        MergeReport
        """
        wd = Path(work_dir)
        wd.mkdir(parents=True, exist_ok=True)

        report = MergeReport(batch_count=len(batch_prefixes))

        # Step 1: Extract samples from each batch
        subset_prefixes: List[str] = []
        for bp in batch_prefixes:
            name = Path(bp).name
            out = str(wd / f"{name}_subset")
            self.extract_samples(bp, keep_list, out)
            subset_prefixes.append(out)

        if len(subset_prefixes) < 2:
            logger.warning("Fewer than 2 batches; skipping merge.")
            if subset_prefixes:
                report.output_prefix = subset_prefixes[0]
            return report

        # Step 2: Write merge list
        merge_list = wd / "merge_list.txt"
        merge_list.write_text("\n".join(subset_prefixes[1:]) + "\n")

        # Step 3: First merge attempt
        first_attempt = str(wd / "merge_attempt")
        self._run_plink(
            [
                "--bfile", subset_prefixes[0],
                "--merge-list", str(merge_list),
                "--make-bed",
                "--out", first_attempt,
            ],
            check=False,
        )

        # Step 4: Check for merge conflicts
        missnp = Path(f"{first_attempt}-merge.missnp")
        if missnp.exists() and missnp.stat().st_size > 0:
            conflict_count = sum(1 for _ in open(missnp))
            report.conflict_snp_count = conflict_count
            report.correction_applied = True
            logger.info(
                "Detected %d conflicting SNPs — re-extracting with exclusions.",
                conflict_count,
            )

            # Re-extract excluding problematic SNPs
            corrected_prefixes: List[str] = []
            for bp in batch_prefixes:
                name = Path(bp).name
                out = str(wd / f"{name}_corrected")
                self.extract_samples(bp, keep_list, out, exclude_snps=str(missnp))
                corrected_prefixes.append(out)

            corrected_list = wd / "merge_list_corrected.txt"
            corrected_list.write_text("\n".join(corrected_prefixes[1:]) + "\n")

            self._run_plink(
                [
                    "--bfile", corrected_prefixes[0],
                    "--merge-list", str(corrected_list),
                    "--make-bed",
                    "--out", output_prefix,
                ]
            )
        else:
            # No conflicts — rename first attempt to final
            for ext in (".bed", ".bim", ".fam", ".log"):
                src = Path(f"{first_attempt}{ext}")
                dst = Path(f"{output_prefix}{ext}")
                if src.exists():
                    shutil.move(str(src), str(dst))

        report.output_prefix = output_prefix

        # Count final samples and variants
        fam = Path(f"{output_prefix}.fam")
        bim = Path(f"{output_prefix}.bim")
        if fam.exists():
            report.final_sample_count = sum(1 for _ in open(fam))
        if bim.exists():
            report.final_variant_count = sum(1 for _ in open(bim))

        # Step 5: VCF conversion
        if convert_to_vcf:
            self._run_plink(
                [
                    "--bfile", output_prefix,
                    "--recode", "vcf", "bgz",
                    "--out", output_prefix,
                ]
            )

        return report
