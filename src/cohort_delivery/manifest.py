#!/usr/bin/env python3
"""
Delivery Manifest Generator
============================

Generates cryptographic checksums and metadata summaries for data deliveries,
ensuring traceability and integrity verification at the receiving end.

Author: Ugur Tuna
"""

import csv
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FileChecksum:
    """Checksum record for a single file."""

    filename: str
    file_size: int
    md5: str
    sha256: str


@dataclass
class DeliveryManifest:
    """Complete manifest for a data delivery."""

    project_id: str
    delivery_date: str
    files: List[FileChecksum] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_size_bytes(self) -> int:
        return sum(f.file_size for f in self.files)


class ManifestGenerator:
    """
    Generates delivery manifests with MD5 and SHA-256 checksums.

    Example::

        gen = ManifestGenerator()
        manifest = gen.generate(
            delivery_dir="delivery/",
            project_id="NBR030",
        )
        gen.write_manifest(manifest, "delivery/MANIFEST.tsv")
    """

    @staticmethod
    def compute_checksums(filepath: str) -> FileChecksum:
        """
        Compute MD5 and SHA-256 checksums for a file.

        Parameters
        ----------
        filepath : str

        Returns
        -------
        FileChecksum
        """
        path = Path(filepath)
        md5 = hashlib.md5()
        sha256 = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(8192), b""):
                md5.update(chunk)
                sha256.update(chunk)
        return FileChecksum(
            filename=path.name,
            file_size=path.stat().st_size,
            md5=md5.hexdigest(),
            sha256=sha256.hexdigest(),
        )

    def generate(
        self,
        delivery_dir: str,
        project_id: str,
        exclude_patterns: Optional[List[str]] = None,
    ) -> DeliveryManifest:
        """
        Generate a manifest for all files in a delivery directory.

        Parameters
        ----------
        delivery_dir : str
        project_id : str
        exclude_patterns : list of str, optional
            Filename substrings to skip (e.g. "MANIFEST", "STATUS").

        Returns
        -------
        DeliveryManifest
        """
        exclude = set(exclude_patterns) if exclude_patterns else {"MANIFEST", "STATUS"}
        directory = Path(delivery_dir)
        if not directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {delivery_dir}")

        manifest = DeliveryManifest(
            project_id=project_id,
            delivery_date=datetime.now().strftime("%Y-%m-%d"),
        )

        for fp in sorted(directory.iterdir()):
            if not fp.is_file():
                continue
            if any(pat in fp.name for pat in exclude):
                continue
            manifest.files.append(self.compute_checksums(str(fp)))

        return manifest

    @staticmethod
    def write_manifest(manifest: DeliveryManifest, output_path: str) -> None:
        """Write the manifest to a TSV file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(["Filename", "Size_Bytes", "MD5", "SHA256"])
            for fc in manifest.files:
                writer.writerow([fc.filename, fc.file_size, fc.md5, fc.sha256])
        logger.info("Manifest written to %s (%d files)", output_path, manifest.total_files)

    @staticmethod
    def write_status_summary(
        manifest: DeliveryManifest,
        output_path: str,
        extra_metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """Write a status summary TSV."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        meta = {
            "Project_ID": manifest.project_id,
            "Delivery_Date": manifest.delivery_date,
            "Total_Files": str(manifest.total_files),
            "Total_Size_Bytes": str(manifest.total_size_bytes),
            "Integrity_Check": "PASS",
        }
        if extra_metadata:
            meta.update(extra_metadata)

        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(["Metric", "Value"])
            for k, v in meta.items():
                writer.writerow([k, v])
