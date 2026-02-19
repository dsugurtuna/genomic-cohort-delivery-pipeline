#!/usr/bin/env python3
"""
Secure Transfer Module
=======================

Orchestrates the permission-controlled transfer of sensitive genomic data
to researcher staging areas. Supports rsync and local copy modes with
post-transfer verification.

Author: Ugur Tuna
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

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


class SecureTransfer:
    """
    Transfers data packages with verification and permission control.

    Example::

        transfer = SecureTransfer()
        report = transfer.send(
            source_dir="delivery/",
            dest_root="researcher_staging/",
            project_id="NBR030",
        )
    """

    def send(
        self,
        source_dir: str,
        dest_root: str,
        project_id: str,
        method: str = "rsync",
        chmod_dirs: str = "Du=rwx,Dgo=rx",
        chmod_files: str = "Fu=rw,Fgo=r",
    ) -> TransferReport:
        """
        Execute a secure transfer from source to destination.

        Parameters
        ----------
        source_dir : str
            Source directory containing the data package.
        dest_root : str
            Root of the researcher staging area.
        project_id : str
            Project identifier (used for directory naming).
        method : str
            Transfer method: "rsync" or "copy".
        chmod_dirs, chmod_files : str
            Permission strings for rsync --chmod.

        Returns
        -------
        TransferReport
        """
        src = Path(source_dir)
        if not src.is_dir():
            raise NotADirectoryError(f"Source not found: {source_dir}")

        datestamp = datetime.now().strftime("%Y%m%d")
        dest = Path(dest_root) / f"{project_id}_Delivery_{datestamp}"
        dest.mkdir(parents=True, exist_ok=True)

        report = TransferReport(
            source_dir=str(src),
            destination_dir=str(dest),
            method=method,
        )

        if method == "rsync":
            self._rsync(src, dest, chmod_dirs, chmod_files)
        else:
            self._copy(src, dest)

        # Verify
        src_files = [f for f in src.iterdir() if f.is_file()]
        dst_files = [f for f in dest.iterdir() if f.is_file()]
        report.file_count = len(dst_files)
        report.total_bytes = sum(f.stat().st_size for f in dst_files)
        report.verified = len(src_files) == len(dst_files)

        if not report.verified:
            logger.warning(
                "File count mismatch: source=%d, dest=%d",
                len(src_files),
                len(dst_files),
            )

        return report

    @staticmethod
    def _rsync(src: Path, dest: Path, chmod_dirs: str, chmod_files: str) -> None:
        """Execute rsync transfer."""
        cmd = [
            "rsync",
            "-a",
            f"--chmod={chmod_dirs},{chmod_files}",
            f"{src}/",
            f"{dest}/",
        ]
        logger.info("Running: %s", " ".join(cmd))
        subprocess.run(cmd, check=True)

    @staticmethod
    def _copy(src: Path, dest: Path) -> None:
        """Execute simple copy-based transfer."""
        for fp in src.iterdir():
            if fp.is_file():
                shutil.copy2(fp, dest / fp.name)
