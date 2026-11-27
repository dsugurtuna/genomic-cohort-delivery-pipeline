"""
Genomic Cohort Delivery Pipeline
=================================

Filter, merge and package multi-batch PLINK 1.9 genotype data for a research
delivery, with checksum manifests and verified copies to a staging area.

Author: Ugur Tuna
"""

__version__ = "0.1.0"

from cohort_delivery.filter import CohortFilter, FilterReport
from cohort_delivery.manifest import DeliveryManifest, ManifestGenerator
from cohort_delivery.merge import GenotypeMerger, MergeReport, PlinkError
from cohort_delivery.pipeline import DeliveryPipeline, PipelineConfig, PipelineResult
from cohort_delivery.transfer import SecureTransfer, TransferReport

__all__ = [
    "CohortFilter",
    "DeliveryManifest",
    "DeliveryPipeline",
    "FilterReport",
    "GenotypeMerger",
    "ManifestGenerator",
    "MergeReport",
    "PipelineConfig",
    "PipelineResult",
    "PlinkError",
    "SecureTransfer",
    "TransferReport",
]
