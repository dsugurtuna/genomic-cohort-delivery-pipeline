"""Tests for the CohortFilter class."""

import pytest

from cohort_delivery.filter import CohortFilter


@pytest.fixture
def filter_instance():
    return CohortFilter()


class TestCohortFilter:
    def test_load_exclusion_set(self, filter_instance, tmp_path):
        excl = tmp_path / "exclusions.csv"
        excl.write_text("SampleID,Reason\nS001,GenderMismatch\nS002,Withdrawal\n")
        ids = filter_instance.load_exclusion_set(str(excl))
        assert ids == {"S001", "S002"}

    def test_load_exclusion_set_with_reasons(self, filter_instance, tmp_path):
        excl = tmp_path / "exclusions.csv"
        excl.write_text("SampleID,Reason\nS001,GenderMismatch\nS002,Withdrawal\n")
        mapping = filter_instance.load_exclusion_set_with_reasons(str(excl))
        assert mapping == {"S001": "GenderMismatch", "S002": "Withdrawal"}

    def test_apply_basic(self, filter_instance, tmp_path):
        cohort = tmp_path / "cohort.txt"
        cohort.write_text("S001\nS002\nS003\nS004\n")

        excl = tmp_path / "excl.csv"
        excl.write_text("SampleID,Reason\nS001,Mismatch\nS002,Withdrawn\n")

        output = tmp_path / "filtered.txt"
        report = filter_instance.apply(
            cohort_path=str(cohort),
            exclusion_paths=[str(excl)],
            output_path=str(output),
        )
        assert report.original_count == 4
        assert report.final_count == 2
        assert output.read_text().strip().split("\n") == ["S003", "S004"]

    def test_apply_with_set(self, filter_instance, tmp_path):
        cohort = tmp_path / "cohort.txt"
        cohort.write_text("S001\nS002\nS003\n")

        report = filter_instance.apply(
            cohort_path=str(cohort),
            exclusion_set={"S002"},
        )
        assert report.final_count == 2

    def test_missing_cohort_raises(self, filter_instance):
        with pytest.raises(FileNotFoundError):
            filter_instance.apply(cohort_path="/nonexistent/file.txt")

    def test_missing_exclusion_raises(self, filter_instance):
        with pytest.raises(FileNotFoundError):
            filter_instance.load_exclusion_set("/nonexistent/file.csv")
