"""Tests for the SecureTransfer class."""

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

    def test_source_not_found_raises(self, transfer, tmp_path):
        with pytest.raises(NotADirectoryError):
            transfer.send(
                source_dir=str(tmp_path / "nonexistent"),
                dest_root=str(tmp_path),
                project_id="X",
            )

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
