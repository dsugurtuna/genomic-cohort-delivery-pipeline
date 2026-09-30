#!/usr/bin/env python3
"""
Genotype Merge Module
=====================

Extracts the filtered cohort from each PLINK 1.9 batch, merges the batches,
and handles the most common merge failure:

  1. Extract cohort samples from each source batch (``--keep``).
  2. Attempt a merge across all batches (``--merge-list``).
  3. If PLINK reports variants with conflicting alleles (``-merge.missnp``,
     typically strand flips or multi-allelic sites), exclude those variants
     from every batch and merge again.
  4. Convert the final result to bgzipped VCF.

Conflicting variants are excluded, not repaired by flipping strands. The
report lists them so the loss is visible. Any other PLINK failure stops the
run with the relevant log lines.

Author: Ugur Tuna
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


def _count_lines(path: Path) -> int:
    with open(path) as fh:
        return sum(1 for _ in fh)


class PlinkError(RuntimeError):
    """A PLINK command failed for a reason this module does not handle."""


@dataclass
class MergeReport:
    """Summary of a genotype merge operation."""

    batch_count: int = 0
    conflict_snp_count: int = 0
    final_sample_count: int = 0
    final_variant_count: int = 0
    correction_applied: bool = False
    output_prefix: str = ""
    conflict_snps: list[str] = field(default_factory=list)


class GenotypeMerger:
    """
    Merges multi-batch PLINK binary datasets, excluding variants whose
    alleles conflict between batches.

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

    def _run_plink(
        self, args: list[str], check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Execute a PLINK command; on failure raise PlinkError with the output."""
        cmd = [self.plink_exec, *args]
        logger.info("Running: %s", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if check and proc.returncode != 0:
            tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-10:])
            raise PlinkError(f"{' '.join(cmd)} exited {proc.returncode}:\n{tail}")
        return proc

    def extract_samples(
        self,
        bfile_prefix: str,
        keep_list: str,
        output_prefix: str,
        exclude_snps: str | None = None,
    ) -> str:
        """
        Extract samples from a PLINK binary fileset.

        Parameters
        ----------
        bfile_prefix : str
            PLINK binary file prefix (.bed/.bim/.fam).
        keep_list : str
            Path to a file of sample IDs to keep (``FID IID`` per line).
        output_prefix : str
            Output file prefix.
        exclude_snps : str, optional
            Path to a list of variant IDs to exclude.

        Returns
        -------
        str
            Output prefix of the extracted dataset.
        """
        args = [
            "--bfile",
            bfile_prefix,
            "--keep",
            keep_list,
            "--make-bed",
            "--out",
            output_prefix,
        ]
        if exclude_snps:
            args.extend(["--exclude", exclude_snps])

        self._run_plink(args)
        return output_prefix

    def _merge(
        self, prefixes: list[str], merge_list: Path, out: str, check: bool
    ) -> bool:
        merge_list.write_text("\n".join(prefixes[1:]) + "\n")
        proc = self._run_plink(
            [
                "--bfile",
                prefixes[0],
                "--merge-list",
                str(merge_list),
                "--make-bed",
                "--out",
                out,
            ],
            check=check,
        )
        return proc.returncode == 0

    def merge(
        self,
        batch_prefixes: list[str],
        keep_list: str,
        output_prefix: str,
        work_dir: str = "work",
        convert_to_vcf: bool = True,
    ) -> MergeReport:
        """
        Extract, merge and (if needed) exclude conflicting variants.

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

        Raises
        ------
        PlinkError
            If PLINK fails for any reason other than an allele conflict that
            excluding the listed variants resolves.
        """
        if not batch_prefixes:
            raise ValueError("No batches to merge")
        wd = Path(work_dir)
        wd.mkdir(parents=True, exist_ok=True)

        report = MergeReport(batch_count=len(batch_prefixes))

        if len(batch_prefixes) == 1:
            # Nothing to merge: extract straight to the final prefix.
            self.extract_samples(batch_prefixes[0], keep_list, output_prefix)
        else:
            subset_prefixes = [
                self.extract_samples(bp, keep_list, str(wd / f"{Path(bp).name}_subset"))
                for bp in batch_prefixes
            ]
            first_attempt = str(wd / "merge_attempt")
            ok = self._merge(
                subset_prefixes, wd / "merge_list.txt", first_attempt, False
            )
            missnp = Path(f"{first_attempt}-merge.missnp")

            if ok:
                for ext in (".bed", ".bim", ".fam", ".log"):
                    src = Path(f"{first_attempt}{ext}")
                    if src.exists():
                        shutil.move(str(src), f"{output_prefix}{ext}")
            elif missnp.exists() and missnp.stat().st_size > 0:
                report.conflict_snps = sorted(
                    {
                        line.strip()
                        for line in missnp.read_text().splitlines()
                        if line.strip()
                    }
                )
                report.conflict_snp_count = len(report.conflict_snps)
                report.correction_applied = True
                logger.warning(
                    "Excluding %d variants with conflicting alleles and re-merging.",
                    report.conflict_snp_count,
                )
                corrected = [
                    self.extract_samples(
                        bp,
                        keep_list,
                        str(wd / f"{Path(bp).name}_corrected"),
                        exclude_snps=str(missnp),
                    )
                    for bp in batch_prefixes
                ]
                self._merge(
                    corrected, wd / "merge_list_corrected.txt", output_prefix, True
                )
            else:
                # Re-run with check=True to raise with PLINK's own message.
                self._merge(subset_prefixes, wd / "merge_list.txt", first_attempt, True)

        report.output_prefix = output_prefix
        fam = Path(f"{output_prefix}.fam")
        bim = Path(f"{output_prefix}.bim")
        if fam.exists():
            report.final_sample_count = _count_lines(fam)
        if bim.exists():
            report.final_variant_count = _count_lines(bim)

        if convert_to_vcf:
            self._run_plink(
                [
                    "--bfile",
                    output_prefix,
                    "--recode",
                    "vcf",
                    "bgz",
                    "--out",
                    output_prefix,
                ]
            )

        return report
