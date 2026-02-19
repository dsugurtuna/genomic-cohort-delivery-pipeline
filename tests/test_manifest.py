"""Tests for the ManifestGenerator class."""

import pytest

from cohort_delivery.manifest import ManifestGenerator


@pytest.fixture
def generator():
    return ManifestGenerator()


class TestManifestGenerator:
    def test_compute_checksums(self, generator, tmp_path):
        fp = tmp_path / "data.txt"
        fp.write_text("hello world\n")
        result = generator.compute_checksums(str(fp))
        assert result.filename == "data.txt"
        assert result.file_size > 0
        assert len(result.md5) == 32
        assert len(result.sha256) == 64

    def test_generate(self, generator, tmp_path):
        (tmp_path / "file_a.vcf.gz").write_bytes(b"fake vcf")
        (tmp_path / "file_b.txt").write_text("metadata")
        manifest = generator.generate(
            delivery_dir=str(tmp_path),
            project_id="TEST001",
        )
        assert manifest.project_id == "TEST001"
        assert manifest.total_files == 2
        assert manifest.total_size_bytes > 0

    def test_generate_excludes_manifest(self, generator, tmp_path):
        (tmp_path / "data.vcf.gz").write_bytes(b"data")
        (tmp_path / "MANIFEST.tsv").write_text("skip me")
        manifest = generator.generate(str(tmp_path), "TEST002")
        assert manifest.total_files == 1

    def test_write_manifest(self, generator, tmp_path):
        (tmp_path / "data.txt").write_text("content")
        manifest = generator.generate(str(tmp_path), "TEST003")
        out = tmp_path / "MANIFEST.tsv"
        generator.write_manifest(manifest, str(out))
        assert out.exists()
        lines = out.read_text().strip().split("\n")
        assert lines[0].startswith("Filename")
        assert len(lines) == 2  # header + 1 file

    def test_write_status_summary(self, generator, tmp_path):
        (tmp_path / "data.txt").write_text("content")
        manifest = generator.generate(str(tmp_path), "TEST004")
        out = tmp_path / "STATUS.tsv"
        generator.write_status_summary(manifest, str(out))
        assert out.exists()
        text = out.read_text()
        assert "TEST004" in text
