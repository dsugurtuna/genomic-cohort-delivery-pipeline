#!/usr/bin/env python3
"""
Command-line interface for genomic-cohort-delivery-pipeline.

Subcommands:
    run     Execute a delivery pipeline from a JSON config file and/or flags.
    verify  Verify a delivery directory on disk against a MANIFEST.tsv file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from cohort_delivery import __version__
from cohort_delivery.manifest import ManifestGenerator
from cohort_delivery.merge import PlinkError
from cohort_delivery.pipeline import DeliveryPipeline, PipelineConfig

_CONFIG_KEYS = frozenset(
    {
        "project_id",
        "cohort_file",
        "exclusion_files",
        "batch_prefixes",
        "work_dir",
        "delivery_dir",
        "staging_root",
        "plink_exec",
        "convert_to_vcf",
        "transfer_method",
        "delivery_tag",
        "unique_run",
    }
)


def _load_config_from_args(args: argparse.Namespace) -> PipelineConfig:
    data: dict[str, object] = {}
    if args.config:
        raw = json.loads(Path(args.config).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Config file must contain a JSON object.")
        unknown = sorted(set(raw) - _CONFIG_KEYS)
        if unknown:
            raise ValueError(f"Unknown config keys: {unknown}")
        data.update(raw)

    if args.project_id is not None:
        data["project_id"] = args.project_id
    if args.cohort is not None:
        data["cohort_file"] = args.cohort
    if args.exclusion is not None:
        data["exclusion_files"] = args.exclusion
    if args.batch is not None:
        data["batch_prefixes"] = args.batch
    if args.work_dir is not None:
        data["work_dir"] = args.work_dir
    if args.delivery_dir is not None:
        data["delivery_dir"] = args.delivery_dir
    if args.staging_root is not None:
        data["staging_root"] = args.staging_root
    if args.plink_exec is not None:
        data["plink_exec"] = args.plink_exec
    if args.no_vcf:
        data["convert_to_vcf"] = False
    if args.transfer_method is not None:
        data["transfer_method"] = args.transfer_method
    if args.delivery_tag is not None:
        data["delivery_tag"] = args.delivery_tag
    if args.unique_run:
        data["unique_run"] = True

    if not data.get("cohort_file"):
        raise ValueError("cohort_file must be provided via --config or --cohort.")

    return PipelineConfig(**data)  # type: ignore[arg-type]


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="cohort-delivery",
        description="Filter, merge, manifest, and stage multi-batch PLINK cohorts.",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser(
        "run",
        help="Run the cohort delivery pipeline from a JSON config and/or flags.",
    )
    run_p.add_argument("--config", help="Path to a JSON PipelineConfig file.")
    run_p.add_argument("--project-id", help="Project identifier for output names.")
    run_p.add_argument("--cohort", help="Path to cohort sample list (FID IID or IID).")
    run_p.add_argument(
        "--exclusion",
        action="append",
        help="Exclusion file path (repeatable).",
    )
    run_p.add_argument(
        "--batch",
        action="append",
        help="PLINK batch prefix (repeatable).",
    )
    run_p.add_argument("--work-dir", help="Working directory for intermediate files.")
    run_p.add_argument("--delivery-dir", help="Output directory for delivery package.")
    run_p.add_argument("--staging-root", help="Staging root directory.")
    run_p.add_argument("--plink-exec", help="Path to PLINK 1.9 executable.")
    run_p.add_argument(
        "--transfer-method",
        choices=("rsync", "copy"),
        help="Transfer method into staging.",
    )
    run_p.add_argument(
        "--no-vcf",
        action="store_true",
        help="Skip VCF conversion after merging.",
    )
    run_p.add_argument(
        "--delivery-tag",
        help="Optional suffix for distinct deliveries on the same calendar day.",
    )
    run_p.add_argument(
        "--unique-run",
        action="store_true",
        help="Include timestamp precision in the staging directory name.",
    )

    ver_p = sub.add_parser(
        "verify",
        help="Verify a delivery directory on disk against a MANIFEST.tsv file.",
    )
    ver_p.add_argument("directory", help="Path to the delivery directory.")
    ver_p.add_argument(
        "--manifest",
        help="Path to MANIFEST.tsv (defaults to <directory>/MANIFEST.tsv).",
    )

    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    config = _load_config_from_args(args)
    result = DeliveryPipeline().run(config)
    f = result.filter_report
    m = result.merge_report
    t = result.transfer_report
    if f is None or m is None or t is None:
        print("Error: pipeline returned incomplete reports.", file=sys.stderr)
        return 1

    print(
        f"Filtered: {f.original_count} -> {f.final_count} samples "
        f"(removed {f.removed_count})"
    )
    print(
        f"Merged: {m.final_sample_count} samples, {m.final_variant_count} variants "
        f"(excluded conflicts: {m.conflict_snp_count})"
    )
    print(
        f"Delivered {t.file_count} files to {t.destination_dir}; verified={t.verified}"
    )
    if not t.verified:
        for problem in t.problems:
            print(f"Verification problem: {problem}", file=sys.stderr)
        return 1
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    manifest_path = Path(args.manifest) if args.manifest else directory / "MANIFEST.tsv"
    gen = ManifestGenerator()
    manifest = gen.read_manifest(str(manifest_path))
    problems = gen.verify(manifest, str(directory))
    if problems:
        for problem in problems:
            print(f"Verification problem: {problem}", file=sys.stderr)
        return 1
    print(f"OK: verified {manifest.total_files} files in {directory}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "verify":
            return _cmd_verify(args)
    except (
        ValueError,
        TypeError,
        FileNotFoundError,
        NotADirectoryError,
        FileExistsError,
        PlinkError,
        RuntimeError,
        OSError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
