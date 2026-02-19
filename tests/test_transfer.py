"""Tests for the SecureTransfer class."""

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
