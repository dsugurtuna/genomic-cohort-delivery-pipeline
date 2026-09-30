#!/usr/bin/env python3
"""
Secure Transfer Module
=======================

Copies a delivery package into a researcher staging area on a filesystem the
pipeline can write to, with restrictive permissions and post-transfer
verification. It does not encrypt or move data between organisations; for
that, see the secure-genomic-transfer repository.

Author: Ugur Tuna
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

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

    def send(
        self,
        source_dir: str,
        dest_root: str,
        project_id: str,
        method: str = "rsync",
        chmod_dirs: str = "Du=rwx,Dg=rx,Do=",
        chmod_files: str = "Fu=rw,Fg=r,Fo=",
        manifest: DeliveryManifest | None = None,
    ) -> TransferReport:
        """
        Copy a delivery package into a new dated directory under ``dest_root``.

        Parameters
        ----------
        source_dir : str
            Source directory containing the data package.
        dest_root : str
            Root of the researcher staging area.
        project_id : str
            Project identifier (used for directory naming).
        method : str
            ``"rsync"`` or ``"copy"``. Both set owner/group permissions and
            give no access to others.
        chmod_dirs, chmod_files : str
            Permission strings for rsync ``--chmod``.
        manifest : DeliveryManifest, optional
            If given, every file at the destination is checked against its
            checksums and ``verified`` reflects that check. Without it,
            ``verified`` only means the file counts match.

        Returns
        -------
        TransferReport

        Raises
        ------
        FileExistsError
            If the dated destination already exists. Delivering into an
            existing directory could mix two runs.
        """
        if method not in self.METHODS:
            raise ValueError(f"method must be one of {self.METHODS}, got {method!r}")
        src = Path(source_dir)
        if not src.is_dir():
            raise NotADirectoryError(f"Source not found: {source_dir}")

        datestamp = datetime.now().strftime("%Y%m%d")
        dest = Path(dest_root) / f"{project_id}_Delivery_{datestamp}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.mkdir(mode=self.DIR_MODE)  # raises FileExistsError if present
        dest.chmod(self.DIR_MODE)  # mkdir mode is reduced by the umask

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

    @classmethod
    def _copy(cls, src: Path, dest: Path) -> None:
        """Copy files and set restrictive permissions."""
        for fp in src.iterdir():
            if fp.is_file():
                target = dest / fp.name
                shutil.copy2(fp, target)
                target.chmod(cls.FILE_MODE)
