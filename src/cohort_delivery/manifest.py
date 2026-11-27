#!/usr/bin/env python3
"""
Delivery Manifest Generator
============================

Generates cryptographic checksums and metadata summaries for data deliveries,
ensuring traceability and integrity verification at the receiving end.

Author: Ugur Tuna
"""

from __future__ import annotations

import csv
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_EXPECTED_HEADER = ["Filename", "Size_Bytes", "MD5", "SHA256"]
_MD5_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _is_safe_filename(name: str) -> bool:
    return (
        bool(name)
        and "/" not in name
        and "\\" not in name
        and name not in {".", ".."}
        and Path(name).name == name
    )


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
    files: list[FileChecksum] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_size_bytes(self) -> int:
        return sum(f.file_size for f in self.files)


class ManifestGenerator:
    """
    Generates, parses, and verifies delivery manifests with MD5 and SHA-256 checksums.

    Example::

        gen = ManifestGenerator()
        manifest = gen.generate(
            delivery_dir="delivery/",
            project_id="STUDY-A",
        )
        gen.write_manifest(manifest, "delivery/MANIFEST.tsv")
    """

    OWN_FILES = frozenset({"MANIFEST.tsv"})

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
        exclude_patterns: list[str] | None = None,
    ) -> DeliveryManifest:
        """
        Generate a manifest for all files in a delivery directory.

        Parameters
        ----------
        delivery_dir : str
        project_id : str
        exclude_patterns : list of str, optional
            Filename substrings to skip. By default only ``MANIFEST.tsv`` is
            skipped, by exact name, so data files and ``STATUS_SUMMARY.tsv``
            (if already present) are included and checksummed.

        Returns
        -------
        DeliveryManifest
        """
        directory = Path(delivery_dir)
        if not directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {delivery_dir}")

        manifest = DeliveryManifest(
            project_id=project_id,
            delivery_date=datetime.now().strftime("%Y-%m-%d"),
        )

        for fp in sorted(directory.iterdir()):
            if not fp.is_file() or fp.is_symlink():
                continue
            if exclude_patterns is None:
                if fp.name in self.OWN_FILES:
                    continue
            elif any(pat in fp.name for pat in exclude_patterns):
                continue
            manifest.files.append(self.compute_checksums(str(fp)))

        return manifest

    @staticmethod
    def write_manifest(manifest: DeliveryManifest, output_path: str) -> None:
        """Write the manifest to a TSV file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(_EXPECTED_HEADER)
            for fc in manifest.files:
                writer.writerow([fc.filename, fc.file_size, fc.md5, fc.sha256])
        logger.info(
            "Manifest written to %s (%d files)", output_path, manifest.total_files
        )

    @staticmethod
    def read_manifest(
        manifest_path: str,
        project_id: str = "",
        delivery_date: str = "",
    ) -> DeliveryManifest:
        """
        Parse a ``MANIFEST.tsv`` file on disk back into a :class:`DeliveryManifest`.

        Validates the header schema, filename safety, duplicate entries,
        non-negative byte counts, and MD5/SHA-256 digest formats.
        """
        if not manifest_path:
            raise FileNotFoundError("Manifest path cannot be empty.")
        path = Path(manifest_path)
        if not path.is_file():
            raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh, delimiter="\t")
            header = next(reader, None)
            if header != _EXPECTED_HEADER:
                raise ValueError(
                    f"Invalid manifest header in {manifest_path}: {header!r}"
                )

            files: list[FileChecksum] = []
            seen: set[str] = set()
            for line_num, row in enumerate(reader, start=2):
                if not row:
                    continue
                if len(row) != 4:
                    raise ValueError(
                        f"Malformed manifest row {line_num} in {manifest_path}: {row!r}"
                    )
                filename, size_raw, md5_hex, sha256_hex = row
                if not _is_safe_filename(filename):
                    raise ValueError(
                        f"Unsafe manifest filename at row {line_num}: {filename!r}"
                    )
                if filename in seen:
                    raise ValueError(
                        f"Duplicate manifest entry at row {line_num}: {filename!r}"
                    )
                seen.add(filename)

                try:
                    file_size = int(size_raw)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid file size at row {line_num}: {size_raw!r}"
                    ) from exc
                if file_size < 0:
                    raise ValueError(
                        f"Negative file size at row {line_num}: {file_size}"
                    )
                if not _MD5_RE.fullmatch(md5_hex):
                    raise ValueError(
                        f"Invalid MD5 digest at row {line_num}: {md5_hex!r}"
                    )
                if not _SHA256_RE.fullmatch(sha256_hex):
                    raise ValueError(
                        f"Invalid SHA-256 digest at row {line_num}: {sha256_hex!r}"
                    )

                files.append(
                    FileChecksum(
                        filename=filename,
                        file_size=file_size,
                        md5=md5_hex.lower(),
                        sha256=sha256_hex.lower(),
                    )
                )

        return DeliveryManifest(
            project_id=project_id,
            delivery_date=delivery_date,
            files=files,
        )

    @staticmethod
    def write_status_summary(
        manifest: DeliveryManifest,
        output_path: str,
        extra_metadata: dict[str, str] | None = None,
    ) -> None:
        """Write a status summary TSV.

        No integrity verdict is written unless the caller supplies one in
        ``extra_metadata`` (for example after ``verify``). A summary must not
        claim a check that was never run.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        meta = {
            "Project_ID": manifest.project_id,
            "Delivery_Date": manifest.delivery_date,
            "Total_Files": str(manifest.total_files),
            "Total_Size_Bytes": str(manifest.total_size_bytes),
        }
        if extra_metadata:
            meta.update(extra_metadata)

        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, delimiter="\t")
            writer.writerow(["Metric", "Value"])
            for k, v in meta.items():
                writer.writerow([k, v])

    def verify(self, manifest: DeliveryManifest, directory: str) -> list[str]:
        """Check files in ``directory`` against a manifest.

        Returns a list of problems (empty manifest, missing files, size or
        checksum mismatches, unexpected extra files); an empty list means
        every file matches.
        """
        root = Path(directory)
        if not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")

        if not manifest.files:
            return ["manifest contains no files"]

        problems: list[str] = []
        expected: dict[str, FileChecksum] = {}
        for fc in manifest.files:
            if not _is_safe_filename(fc.filename):
                problems.append(f"invalid filename: {fc.filename}")
                continue
            expected[fc.filename] = fc

        for name, fc in expected.items():
            fp = root / name
            if not fp.is_file() or fp.is_symlink():
                problems.append(f"missing: {name}")
                continue
            actual = self.compute_checksums(str(fp))
            if actual.file_size != fc.file_size:
                problems.append(f"size mismatch: {name}")
            elif actual.sha256 != fc.sha256.lower() or actual.md5 != fc.md5.lower():
                problems.append(f"checksum mismatch: {name}")

        for fp in sorted(root.iterdir()):
            if (
                fp.is_file()
                and not fp.is_symlink()
                and fp.name not in expected
                and fp.name not in self.OWN_FILES
            ):
                problems.append(f"unexpected: {fp.name}")
        return problems
