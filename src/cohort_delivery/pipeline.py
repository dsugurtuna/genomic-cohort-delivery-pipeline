#!/usr/bin/env python3
"""
Delivery Pipeline Orchestrator
===============================

Coordinates the complete end-to-end workflow:

  1. Filter the cohort (remove exclusions)
  2. Extract and merge genotypes across batches
  3. Enforce fail-closed post-merge withdrawal verification
  4. Generate a delivery manifest with checksums (conflict list + status summary)
  5. Transfer the package to the researcher staging area

Author: Ugur Tuna
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from cohort_delivery._validation import validate_identifier
from cohort_delivery.filter import CohortFilter, FilterReport
from cohort_delivery.manifest import DeliveryManifest, ManifestGenerator
from cohort_delivery.merge import GenotypeMerger, MergeReport
from cohort_delivery.transfer import SecureTransfer, TransferReport

logger = logging.getLogger(__name__)


def _read_sample_iids(path: Path) -> set[str]:
    """Read individual IDs (IIDs) from a cohort keep list or PLINK .fam file."""
    iids: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if parts:
                iids.add(parts[1] if len(parts) >= 2 else parts[0])
    return iids


@dataclass
class PipelineConfig:
    """Configuration for an end-to-end delivery run."""

    project_id: str = "PROJ001"
    cohort_file: str = ""
    exclusion_files: list[str] | None = None
    batch_prefixes: list[str] | None = None
    work_dir: str = "work"
    delivery_dir: str = "delivery"
    staging_root: str = "staging"
    plink_exec: str = "plink"
    convert_to_vcf: bool = True
    transfer_method: str = "rsync"
    delivery_tag: str | None = None
    unique_run: bool = False


@dataclass
class PipelineResult:
    """Aggregated output of the full pipeline."""

    filter_report: FilterReport | None = None
    merge_report: MergeReport | None = None
    manifest: DeliveryManifest | None = None
    transfer_report: TransferReport | None = None


class DeliveryPipeline:
    """
    Orchestrates the complete cohort delivery workflow.

    Example::

        config = PipelineConfig(
            project_id="STUDY-A",
            cohort_file="cohort_all.txt",
            exclusion_files=["exclusions.csv"],
            batch_prefixes=["batch_01", "batch_02"],
        )
        pipeline = DeliveryPipeline()
        result = pipeline.run(config)
    """

    def run(self, config: PipelineConfig) -> PipelineResult:
        """
        Execute the full delivery pipeline.

        Parameters
        ----------
        config : PipelineConfig

        Returns
        -------
        PipelineResult
        """
        validate_identifier(config.project_id, "project_id")
        if config.delivery_tag is not None:
            validate_identifier(config.delivery_tag, "delivery_tag")

        result = PipelineResult()
        wd = Path(config.work_dir)
        wd.mkdir(parents=True, exist_ok=True)
        dd = Path(config.delivery_dir)
        dd.mkdir(parents=True, exist_ok=True)

        # Step 1: Filter
        logger.info("Step 1: Filtering cohort for project %s", config.project_id)
        flt = CohortFilter()
        filtered_path = str(wd / "cohort_filtered.txt")
        result.filter_report = flt.apply(
            cohort_path=config.cohort_file,
            exclusion_paths=config.exclusion_files,
            output_path=filtered_path,
        )
        logger.info(
            "Filtered: %d -> %d samples",
            result.filter_report.original_count,
            result.filter_report.final_count,
        )
        if result.filter_report.final_count == 0:
            raise ValueError("No samples left after exclusions; nothing to deliver.")

        # Step 2: Merge (fail closed if no genotype batches are supplied)
        if not config.batch_prefixes:
            raise ValueError(
                "batch_prefixes must contain at least one genotype batch prefix."
            )

        logger.info("Step 2: Merging %d batches", len(config.batch_prefixes))
        merger = GenotypeMerger(plink_exec=config.plink_exec)
        output_prefix = str(dd / f"{config.project_id}_final_genotypes")
        result.merge_report = merger.merge(
            batch_prefixes=config.batch_prefixes,
            keep_list=filtered_path,
            output_prefix=output_prefix,
            work_dir=config.work_dir,
            convert_to_vcf=config.convert_to_vcf,
        )
        logger.info(
            "Merge complete: %d samples, %d variants, %d excluded for conflicts",
            result.merge_report.final_sample_count,
            result.merge_report.final_variant_count,
            result.merge_report.conflict_snp_count,
        )

        # Governance gate: verify no excluded or unrequested IIDs appear in output .fam.
        fam_path = Path(f"{output_prefix}.fam")
        if not fam_path.is_file():
            raise FileNotFoundError(f"Merged .fam file missing: {fam_path}")
        delivered_iids = _read_sample_iids(fam_path)
        if not delivered_iids:
            raise ValueError(
                "Merged output contains 0 samples; refusing empty delivery."
            )

        leaked_excluded = sorted(result.filter_report.excluded_iids & delivered_iids)
        if leaked_excluded:
            raise RuntimeError(
                "Governance gate failed: excluded participant IDs present in merged "
                f"output: {leaked_excluded}"
            )

        requested_iids = _read_sample_iids(Path(filtered_path))
        unexpected_iids = sorted(delivered_iids - requested_iids)
        if unexpected_iids:
            raise RuntimeError(
                "Governance gate failed: unrequested participant IDs present in "
                f"merged output: {unexpected_iids}"
            )

        if result.merge_report.final_sample_count != result.filter_report.final_count:
            logger.warning(
                "Requested %d samples but genotypes have %d; check IDs, batches.",
                result.filter_report.final_count,
                result.merge_report.final_sample_count,
            )

        # Persist excluded variants in delivery package before manifesting.
        conflict_file = dd / "CONFLICT_VARIANTS.txt"
        if result.merge_report.conflict_snps:
            conflict_file.write_text(
                "\n".join(result.merge_report.conflict_snps) + "\n",
                encoding="utf-8",
            )
        else:
            conflict_file.unlink(missing_ok=True)

        # Step 3: Manifest (checksum payload, write status, include status)
        logger.info("Step 3: Generating delivery manifest")
        manifest_path = dd / "MANIFEST.tsv"
        status_path = dd / "STATUS_SUMMARY.tsv"
        manifest_path.unlink(missing_ok=True)
        status_path.unlink(missing_ok=True)

        gen = ManifestGenerator()
        manifest = gen.generate(
            delivery_dir=config.delivery_dir,
            project_id=config.project_id,
        )
        counts = {
            "Samples_Requested": str(result.filter_report.final_count),
            "Samples_In_Genotypes": str(result.merge_report.final_sample_count),
            "Variants": str(result.merge_report.final_variant_count),
            "Variants_Excluded_Conflicts": str(result.merge_report.conflict_snp_count),
        }
        gen.write_status_summary(manifest, str(status_path), counts)
        manifest.files.append(gen.compute_checksums(str(status_path)))
        manifest.files.sort(key=lambda fc: fc.filename)
        result.manifest = manifest
        gen.write_manifest(result.manifest, str(manifest_path))

        # Step 4: Transfer
        logger.info("Step 4: Transfer to staging and verify checksums")
        xfer = SecureTransfer()
        result.transfer_report = xfer.send(
            source_dir=config.delivery_dir,
            dest_root=config.staging_root,
            project_id=config.project_id,
            method=config.transfer_method,
            manifest=result.manifest,
            delivery_tag=config.delivery_tag,
            unique_run=config.unique_run,
        )
        logger.info(
            "Transfer complete: %d files, checksums verified=%s",
            result.transfer_report.file_count,
            result.transfer_report.verified,
        )

        return result
