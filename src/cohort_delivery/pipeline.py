#!/usr/bin/env python3
"""
Delivery Pipeline Orchestrator
===============================

Coordinates the complete end-to-end workflow:

  1. Filter the cohort (remove exclusions)
  2. Extract and merge genotypes across batches
  3. Generate a delivery manifest with checksums
  4. Transfer the package to the researcher staging area

Author: Ugur Tuna
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from cohort_delivery.filter import CohortFilter, FilterReport
from cohort_delivery.manifest import DeliveryManifest, ManifestGenerator
from cohort_delivery.merge import GenotypeMerger, MergeReport
from cohort_delivery.transfer import SecureTransfer, TransferReport

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for an end-to-end delivery run."""

    project_id: str = "PROJ001"
    cohort_file: str = ""
    exclusion_files: Optional[List[str]] = None
    batch_prefixes: Optional[List[str]] = None
    work_dir: str = "work"
    delivery_dir: str = "delivery"
    staging_root: str = "staging"
    plink_exec: str = "plink"
    convert_to_vcf: bool = True
    transfer_method: str = "rsync"


@dataclass
class PipelineResult:
    """Aggregated output of the full pipeline."""

    filter_report: Optional[FilterReport] = None
    merge_report: Optional[MergeReport] = None
    manifest: Optional[DeliveryManifest] = None
    transfer_report: Optional[TransferReport] = None


class DeliveryPipeline:
    """
    Orchestrates the complete cohort delivery workflow.

    Example::

        config = PipelineConfig(
            project_id="NBR030",
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

        # Step 2: Merge
        if config.batch_prefixes:
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
                "Merge complete: %d samples, %d variants, %d conflicts resolved",
                result.merge_report.final_sample_count,
                result.merge_report.final_variant_count,
                result.merge_report.conflict_snp_count,
            )

        # Step 3: Manifest
        logger.info("Step 3: Generating delivery manifest")
        gen = ManifestGenerator()
        result.manifest = gen.generate(
            delivery_dir=config.delivery_dir,
            project_id=config.project_id,
        )
        gen.write_manifest(result.manifest, str(dd / "MANIFEST.tsv"))
        gen.write_status_summary(result.manifest, str(dd / "STATUS_SUMMARY.tsv"))

        # Step 4: Transfer
        logger.info("Step 4: Secure transfer")
        xfer = SecureTransfer()
        result.transfer_report = xfer.send(
            source_dir=config.delivery_dir,
            dest_root=config.staging_root,
            project_id=config.project_id,
            method=config.transfer_method,
        )
        logger.info(
            "Transfer complete: %d files, verified=%s",
            result.transfer_report.file_count,
            result.transfer_report.verified,
        )

        return result
