#!/usr/bin/env python3
"""
Cohort Filtering Module
========================

Filters participant lists based on exclusion criteria (gender mismatches,
consent withdrawals, failed QC samples) using efficient set-based lookups.

Addresses data governance requirements: withdrawn participants must never
appear in a delivery.

Author: Ugur Tuna
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_HEADER_ID_TOKENS = frozenset(
    {
        "sampleid",
        "sample_id",
        "sample",
        "iid",
        "fid",
        "familyid",
        "family_id",
        "individualid",
        "individual_id",
        "id",
        "participantid",
        "participant_id",
        "participant",
        "subjectid",
        "subject_id",
        "subject",
        "memberid",
        "member_id",
    }
)
_SELF_ID_HEADER_TOKENS = _HEADER_ID_TOKENS - frozenset({"fid", "familyid", "family_id"})


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", value.strip().lower())


@dataclass
class FilterReport:
    """Summary of a cohort filtering run."""

    original_count: int = 0
    exclusion_count: int = 0
    final_count: int = 0
    exclusion_reasons: dict[str, int] = field(default_factory=dict)
    excluded_iids: set[str] = field(default_factory=set)

    @property
    def removed_count(self) -> int:
        return self.original_count - self.final_count


class CohortFilter:
    """
    Filters a participant list by removing samples that appear in one or
    more exclusion lists.

    Example::

        flt = CohortFilter()
        report = flt.apply(
            cohort_path="cohort_all_samples.txt",
            exclusion_paths=["exclusion_list.csv"],
            output_path="cohort_filtered.txt",
        )
        print(report.final_count)
    """

    @staticmethod
    def _parse_rows(path: Path, delimiter: str | None) -> tuple[str, list[list[str]]]:
        """Read non-empty exclusion rows, auto-detecting CSV/TSV vs whitespace."""
        raw_lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if delimiter is None:
            if any("," in line for line in raw_lines):
                fmt = ","
            elif any("\t" in line for line in raw_lines):
                fmt = "\t"
            else:
                fmt = "whitespace"
        elif delimiter.isspace() and delimiter != "\t":
            fmt = "whitespace"
        else:
            fmt = delimiter

        if fmt == "whitespace":
            rows = [line.split() for line in raw_lines]
        else:
            rows = [
                row
                for row in csv.reader(raw_lines, delimiter=fmt)
                if any(cell.strip() for cell in row)
            ]
        return fmt, rows

    @classmethod
    def _load_exclusion_data(
        cls,
        filepath: str,
        id_column: int | None = None,
        reason_column: int | None = None,
        has_header: bool | None = None,
        delimiter: str | None = None,
    ) -> tuple[set[str], dict[str, str]]:
        """Read an exclusion file once and return (excluded_ids, id_to_reason)."""
        if not filepath:
            raise FileNotFoundError("Exclusion file path cannot be empty.")
        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"Exclusion file not found: {filepath}")

        fmt, rows = cls._parse_rows(path, delimiter)
        if not rows:
            return set(), {}

        if fmt in (",", "\t") or delimiter is not None:
            effective_has_header = True if has_header is None else has_header
            effective_id_col = 0 if id_column is None else id_column
            effective_reason_col: int | None = (
                1 if reason_column is None else reason_column
            )
        else:
            first0 = _normalize_token(rows[0][0])
            effective_has_header = (
                first0 in _HEADER_ID_TOKENS if has_header is None else has_header
            )
            if id_column is not None:
                effective_id_col = id_column
            elif effective_has_header and first0 in _SELF_ID_HEADER_TOKENS:
                effective_id_col = 0
            elif len(rows[0]) >= 2:
                # PLINK FID IID (or .fam) exclusion lists match on IID (column 1).
                effective_id_col = 1
            else:
                effective_id_col = 0

            if reason_column is not None:
                effective_reason_col = reason_column
            elif effective_has_header and first0 in _SELF_ID_HEADER_TOKENS:
                effective_reason_col = 1
            else:
                effective_reason_col = None

        data_rows = rows[1:] if effective_has_header else rows
        ids: set[str] = set()
        mapping: dict[str, str] = {}
        for row in data_rows:
            if len(row) <= effective_id_col:
                continue
            sample_id = row[effective_id_col].strip()
            if not sample_id:
                continue
            ids.add(sample_id)
            if effective_reason_col is not None and len(row) > effective_reason_col:
                reason = row[effective_reason_col].strip()
                if reason:
                    mapping[sample_id] = reason
        return ids, mapping

    def load_exclusion_set(
        self,
        filepath: str,
        id_column: int | None = None,
        has_header: bool | None = None,
        delimiter: str | None = None,
    ) -> set[str]:
        """
        Read an exclusion file and return a set of non-empty sample identifiers.

        Supports comma/tab-delimited files as well as whitespace-delimited
        PLINK ``FID IID`` exclusion lists when ``delimiter`` is omitted.
        """
        ids, _ = self._load_exclusion_data(
            filepath=filepath,
            id_column=id_column,
            has_header=has_header,
            delimiter=delimiter,
        )
        return ids

    def load_exclusion_set_with_reasons(
        self,
        filepath: str,
        id_column: int | None = None,
        reason_column: int | None = None,
        has_header: bool | None = None,
        delimiter: str | None = None,
    ) -> dict[str, str]:
        """
        Read an exclusion file and return a mapping of sample ID to reason.
        """
        _, mapping = self._load_exclusion_data(
            filepath=filepath,
            id_column=id_column,
            reason_column=reason_column,
            has_header=has_header,
            delimiter=delimiter,
        )
        return mapping

    def apply(
        self,
        cohort_path: str,
        exclusion_paths: list[str] | None = None,
        exclusion_set: set[str] | None = None,
        output_path: str | None = None,
    ) -> FilterReport:
        """
        Apply exclusion filtering to a cohort sample list.

        The cohort file is either one sample ID per line, or PLINK-style
        whitespace-delimited ``FID IID`` lines. Matching uses the sample ID
        (the IID when there are two or more columns), and the output keeps
        each line exactly as it was, so it stays valid for ``plink --keep``.

        Parameters
        ----------
        cohort_path : str
            Path to the original sample list.
        exclusion_paths : list of str, optional
            Paths to exclusion CSV/TSV or whitespace ``FID IID`` files.
        exclusion_set : set of str, optional
            Pre-loaded set of IDs to exclude.
        output_path : str, optional
            Where to write the filtered list. If None, no file is written.

        Returns
        -------
        FilterReport
            ``exclusion_count`` is the number of distinct non-empty IDs on the
            exclusion lists; ``removed_count`` is how many cohort lines were
            actually removed; ``exclusion_reasons`` counts removed samples by
            reason where a reason was given; ``excluded_iids`` holds the full
            exclusion set for downstream verification.
        """
        if not cohort_path:
            raise FileNotFoundError("Cohort file path cannot be empty.")
        cohort = Path(cohort_path)
        if not cohort.is_file():
            raise FileNotFoundError(f"Cohort file not found: {cohort_path}")

        to_exclude: set[str] = {
            sid.strip() for sid in (exclusion_set or set()) if sid.strip()
        }
        reasons: dict[str, str] = {}
        if exclusion_paths:
            for ep in exclusion_paths:
                ids, file_reasons = self._load_exclusion_data(ep)
                to_exclude |= ids
                reasons.update(file_reasons)

        original: list[tuple[str, str]] = []
        with open(cohort, encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if parts:
                    sample_id = parts[1] if len(parts) >= 2 else parts[0]
                    original.append((sample_id, line.rstrip("\r\n")))

        kept = [line for sid, line in original if sid not in to_exclude]
        removed = [sid for sid, _ in original if sid in to_exclude]

        report = FilterReport(
            original_count=len(original),
            exclusion_count=len(to_exclude),
            final_count=len(kept),
            excluded_iids=set(to_exclude),
        )
        for sid in removed:
            reason = reasons.get(sid, "unspecified")
            report.exclusion_reasons[reason] = (
                report.exclusion_reasons.get(reason, 0) + 1
            )

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")
            logger.info("Wrote %d samples to %s", len(kept), output_path)

        return report
