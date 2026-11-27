"""Tests for the SecureTransfer class."""

import shutil
import subprocess
from pathlib import Path

import pytest

from cohort_delivery.transfer import SecureTransfer


@pytest.fixture
def transfer():
    return SecureTransfer()


class TestSecureTransfer:
    def test_copy_method(self, transfer, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "file_a.txt").write_text("data a")
        (src / "file_b.txt").write_text("data b")

        dest_root = tmp_path / "staging"
        dest_root.mkdir()

        report = transfer.send(
            source_dir=str(src),
            dest_root=str(dest_root),
            project_id="TEST001",
            method="copy",
        )
        assert report.file_count == 2
        assert report.verified is True
        assert report.total_bytes > 0

    def test_rsync_mocked_flat_files_and_chmod(self, transfer, tmp_path, monkeypatch):
        src = tmp_path / "source"
        src.mkdir()
        (src / "a.txt").write_text("data a")
        (src / "b.txt").write_text("data b")
        (src / "nested").mkdir()
        (src / "nested" / "ignored.txt").write_text("nested")
        (src / "link.txt").symlink_to(src / "a.txt")

        seen_cmds: list[list[str]] = []

        def fake_run(cmd, check=False, capture_output=False, text=False):
            seen_cmds.append(list(cmd))
            dest = Path(cmd[-1].rstrip("/"))
            for arg in cmd[3:-1]:
                shutil.copy2(arg, dest / Path(arg).name)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        report = transfer.send(
            source_dir=str(src),
            dest_root=str(tmp_path / "staging"),
            project_id="RSYNC01",
        )
        assert len(seen_cmds) == 1
        cmd = seen_cmds[0]
        assert cmd[0] == "rsync"
        assert "-a" not in cmd
        assert "--chmod=Du=rwx,Dg=rx,Do=,Fu=rw,Fg=r,Fo=" in cmd
        transferred_names = [Path(arg).name for arg in cmd[3:-1]]
        assert transferred_names == ["a.txt", "b.txt"]
        assert report.method == "rsync"
        assert report.file_count == 2
        assert report.verified is True

        dest = Path(report.destination_dir)
        assert not (dest / "nested").exists()
        assert not (dest / "link.txt").exists()
        assert (dest / "a.txt").stat().st_mode & 0o777 == 0o640

    def test_failed_transfer_cleans_up_partial_staging_dir(
        self, transfer, tmp_path, monkeypatch
    ):
        src = tmp_path / "source"
        src.mkdir()
        (src / "a.txt").write_text("data a")
        staging = tmp_path / "staging"

        def failing_run(cmd, check=False, capture_output=False, text=False):
            dest = Path(cmd[-1].rstrip("/"))
            (dest / "partial.tmp").write_text("half")
            raise subprocess.CalledProcessError(23, cmd, stderr="rsync failed")

        monkeypatch.setattr(subprocess, "run", failing_run)

        with pytest.raises(subprocess.CalledProcessError):
            transfer.send(str(src), str(staging), "FAIL01", method="rsync")

        assert list(staging.iterdir()) == []

    def test_copy_skips_subdirectories_and_symlinks(self, transfer, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "a.txt").write_text("data a")
        (src / "subdir").mkdir()
        (src / "subdir" / "x.txt").write_text("skip")
        (src / "sym.txt").symlink_to(src / "a.txt")

        report = transfer.send(str(src), str(tmp_path / "staging"), "FLAT", "copy")
        dest = Path(report.destination_dir)
        assert report.file_count == 1
        assert report.verified is True
        assert [p.name for p in dest.iterdir()] == ["a.txt"]

    def test_source_not_found_raises(self, transfer, tmp_path):
        with pytest.raises(NotADirectoryError):
            transfer.send(
                source_dir=str(tmp_path / "nonexistent"),
                dest_root=str(tmp_path),
                project_id="X",
            )

    def test_empty_source_dir_rejected(self, transfer, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ValueError, match="contains no files"):
            transfer.send(str(empty), str(tmp_path / "staging"), "EMPTY", method="copy")

    @pytest.mark.parametrize("bad_id", ["", "../escape", "a/b", "..", ".hidden"])
    def test_invalid_project_id_rejected(self, transfer, tmp_path, bad_id):
        src = tmp_path / "source"
        src.mkdir()
        (src / "a.txt").write_text("a")
        with pytest.raises(ValueError, match="Invalid project_id"):
            transfer.send(str(src), str(tmp_path / "staging"), bad_id, method="copy")

    def test_copy_sets_no_access_for_others(self, transfer, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "data.vcf.gz").write_bytes(b"x")
        report = transfer.send(str(src), str(tmp_path / "staging"), "T2", method="copy")
        dest = Path(report.destination_dir)
        assert (dest / "data.vcf.gz").stat().st_mode & 0o777 == 0o640
        assert dest.stat().st_mode & 0o777 == 0o750

    def test_refuses_existing_destination(self, transfer, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "a.txt").write_text("a")
        transfer.send(str(src), str(tmp_path / "staging"), "T3", method="copy")
        with pytest.raises(FileExistsError):
            transfer.send(str(src), str(tmp_path / "staging"), "T3", method="copy")

    def test_same_day_distinct_delivery_tag_and_unique_run(self, transfer, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "a.txt").write_text("a")
        staging = tmp_path / "staging"

        r1 = transfer.send(
            str(src), str(staging), "T3", method="copy", delivery_tag="r1"
        )
        r2 = transfer.send(
            str(src), str(staging), "T3", method="copy", delivery_tag="r2"
        )
        r3 = transfer.send(str(src), str(staging), "T3", method="copy", unique_run=True)
        assert len({r1.destination_dir, r2.destination_dir, r3.destination_dir}) == 3
        assert r1.verified and r2.verified and r3.verified

    def test_unknown_method_rejected(self, transfer, tmp_path):
        with pytest.raises(ValueError):
            transfer.send(str(tmp_path), str(tmp_path / "s"), "T4", method="scp")

    def test_manifest_verification(self, transfer, tmp_path):
        from cohort_delivery.manifest import ManifestGenerator

        src = tmp_path / "source"
        src.mkdir()
        (src / "a.txt").write_text("a")
        manifest = ManifestGenerator().generate(str(src), "T5")
        report = transfer.send(
            str(src), str(tmp_path / "staging"), "T5", method="copy", manifest=manifest
        )
        assert report.verified
        assert report.problems == []
