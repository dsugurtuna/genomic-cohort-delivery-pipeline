#!/usr/bin/env python3
"""
Secure Transfer Module
=======================

Copies a delivery package into a researcher staging area on a filesystem the
pipeline can write to, with restrictive permissions and post-transfer
verification. External cross-organisation encryption (such as GPG or envelope
encryption) is outside the scope of this package.

Author: Ugur Tuna
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cohort_delivery._validation import validate_identifier
from cohort_delivery.manifest import DeliveryManifest, ManifestGenerator

logger = logging.getLogger(__name__)


@dataclass
class TransferReport:
    """Summary of a secure transfer operation."""

    source_dir: str
    destination_dir: str
    file_count: int = 0
    total_bytes: int = 0
    verified: bool = False
    method: str = "rsync"
    problems: list[str] = field(default_factory=list)


class SecureTransfer:
    """
    Transfers data packages with verification and permission control.

    Example::

        transfer = SecureTransfer()
        report = transfer.send(
            source_dir="delivery/",
            dest_root="researcher_staging/",
            project_id="STUDY-A",
        )
    """

    METHODS = ("rsync", "copy")
    FILE_MODE = 0o640  # owner read/write, group read, no access for others
    DIR_MODE = 0o750

    @staticmethod
    def _top_level_files(directory: Path) -> list[Path]:
        return sorted(
            fp for fp in directory.iterdir() if fp.is_file() and not fp.is_symlink()
        )

    def send(
        self,
        source_dir: str,
        dest_root: str,
        project_id: str,
        method: str = "rsync",
        chmod_dirs: str = "Du=rwx,Dg=rx,Do=",
        chmod_files: str = "Fu=rw,Fg=r,Fo=",
        manifest: DeliveryManifest | None = None,
        delivery_tag: str | None = None,
        unique_run: bool = False,
        cleanup_on_verify_failure: bool = False,
    ) -> TransferReport:
        """
        Copy a delivery package into a new dated directory under ``dest_root``.

        Only top-level regular non-symlink files in ``source_dir`` are copied,
        giving identical behaviour across ``"rsync"`` and ``"copy"``. Partial
        staging directories created before a transfer error are removed.

        Parameters
        ----------
        source_dir : str
            Source directory containing the data package.
        dest_root : str
            Root of the researcher staging area.
        project_id : str
            Validated project identifier (used for directory naming).
        method : str
            ``"rsync"`` or ``"copy"``. Both set owner/group permissions and
            give no access to others.
        chmod_dirs, chmod_files : str
            Permission strings for rsync ``--chmod``.
        manifest : DeliveryManifest, optional
            If given, every file at the destination is checked against its
            checksums and ``verified`` reflects that check. Without it,
            ``verified`` only means the file counts match.
        delivery_tag : str, optional
            Optional validated suffix appended to allow distinct named
            deliveries on the same calendar day.
        unique_run : bool
            When True (and ``delivery_tag`` is not set), includes
            ``HHMMSS_ffffff`` precision so multiple deliveries on the same
            calendar day do not collide.
        cleanup_on_verify_failure : bool
            When True, removes the staging directory if post-transfer
            verification fails.

        Returns
        -------
        TransferReport

        Raises
        ------
        FileExistsError
            If the target destination already exists. Delivering into an
            existing directory could mix two runs.
        ValueError
            If ``method``, ``project_id``, ``delivery_tag``, or an empty
            ``source_dir`` is invalid.
        """
        if method not in self.METHODS:
            raise ValueError(f"method must be one of {self.METHODS}, got {method!r}")
        validate_identifier(project_id, "project_id")
        if delivery_tag is not None:
            validate_identifier(delivery_tag, "delivery_tag")

        src = Path(source_dir)
        if not src.is_dir():
            raise NotADirectoryError(f"Source not found: {source_dir}")

        src_files = self._top_level_files(src)
        if not src_files:
            raise ValueError(f"Source directory contains no files: {source_dir}")

        now = datetime.now()
        if delivery_tag is not None:
            folder = f"{project_id}_Delivery_{now.strftime('%Y%m%d')}_{delivery_tag}"
        elif unique_run:
            folder = f"{project_id}_Delivery_{now.strftime('%Y%m%d_%H%M%S_%f')}"
        else:
            folder = f"{project_id}_Delivery_{now.strftime('%Y%m%d')}"

        dest = Path(dest_root) / folder
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.mkdir(mode=self.DIR_MODE)  # raises FileExistsError if present
        dest.chmod(self.DIR_MODE)  # mkdir mode is reduced by the umask

        report = TransferReport(
            source_dir=str(src),
            destination_dir=str(dest),
            method=method,
        )

        try:
            if method == "rsync":
                self._rsync(src, dest, chmod_dirs, chmod_files, files=src_files)
                for fp in self._top_level_files(dest):
                    fp.chmod(self.FILE_MODE)
            else:
                self._copy(src, dest, files=src_files)
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)
            raise

        # Verify
        dst_files = self._top_level_files(dest)
        report.file_count = len(dst_files)
        report.total_bytes = sum(f.stat().st_size for f in dst_files)
        report.verified = len(src_files) == len(dst_files)
        if manifest is not None:
            report.problems = ManifestGenerator().verify(manifest, str(dest))
            report.verified = report.verified and not report.problems

        if not report.verified:
            logger.warning(
                "Verification failed: source=%d files, dest=%d files, problems=%s",
                len(src_files),
                len(dst_files),
                report.problems,
            )
            if cleanup_on_verify_failure:
                shutil.rmtree(dest, ignore_errors=True)

        return report

    @classmethod
    def _rsync(
        cls,
        src: Path,
        dest: Path,
        chmod_dirs: str,
        chmod_files: str,
        files: list[Path] | None = None,
    ) -> None:
        """Execute flat-file rsync transfer without recursing subdirectories."""
        transfer_files = files if files is not None else cls._top_level_files(src)
        cmd = [
            "rsync",
            "-pt",
            f"--chmod={chmod_dirs},{chmod_files}",
            *[str(fp) for fp in transfer_files],
            f"{dest}/",
        ]
        logger.info("Running: %s", " ".join(cmd))
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    @classmethod
    def _copy(
        cls,
        src: Path,
        dest: Path,
        files: list[Path] | None = None,
    ) -> None:
        """Copy top-level regular files and set restrictive permissions."""
        transfer_files = files if files is not None else cls._top_level_files(src)
        for fp in transfer_files:
            target = dest / fp.name
            shutil.copy2(fp, target)
            target.chmod(cls.FILE_MODE)
