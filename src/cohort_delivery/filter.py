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

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FilterReport:
    """Summary of a cohort filtering run."""

    original_count: int = 0
    exclusion_count: int = 0
    final_count: int = 0
    exclusion_reasons: dict[str, int] = field(default_factory=dict)

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
            exclusion_path="exclusion_list.csv",
            output_path="cohort_filtered.txt",
        )
        print(report.final_count)
    """

    def load_exclusion_set(
        self,
        filepath: str,
        id_column: int = 0,
        has_header: bool = True,
        delimiter: str = ",",
    ) -> set[str]:
        """
        Read an exclusion file and return a set of sample identifiers.

        Parameters
        ----------
        filepath : str
            Path to exclusion CSV/TSV.
        id_column : int
            Zero-indexed column containing the sample identifier.
        has_header : bool
            Whether the file has a header row.
        delimiter : str
            Column delimiter.

        Returns
        -------
        set of str
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Exclusion file not found: {filepath}")

        ids: set[str] = set()
        with open(path) as fh:
            reader = csv.reader(fh, delimiter=delimiter)
            if has_header:
                next(reader, None)
            for row in reader:
                if row and len(row) > id_column:
                    ids.add(row[id_column].strip())
        return ids

    def load_exclusion_set_with_reasons(
        self,
        filepath: str,
        id_column: int = 0,
        reason_column: int = 1,
        has_header: bool = True,
        delimiter: str = ",",
    ) -> dict[str, str]:
        """
        Read an exclusion file and return a mapping of sample ID to reason.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Exclusion file not found: {filepath}")

        mapping: dict[str, str] = {}
        with open(path) as fh:
            reader = csv.reader(fh, delimiter=delimiter)
            if has_header:
                next(reader, None)
            for row in reader:
                if row and len(row) > max(id_column, reason_column):
                    mapping[row[id_column].strip()] = row[reason_column].strip()
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
            Paths to exclusion CSV files (ID in the first column; a second
            column, if present, is read as the reason).
        exclusion_set : set of str, optional
            Pre-loaded set of IDs to exclude.
        output_path : str, optional
            Where to write the filtered list. If None, no file is written.

        Returns
        -------
        FilterReport
            ``exclusion_count`` is the number of distinct IDs on the
            exclusion lists; ``removed_count`` is how many cohort lines were
            actually removed; ``exclusion_reasons`` counts removed samples by
            reason where a reason was given.
        """
        cohort = Path(cohort_path)
        if not cohort.exists():
            raise FileNotFoundError(f"Cohort file not found: {cohort_path}")

        # Build combined exclusion set, remembering reasons where given.
        to_exclude: set[str] = set(exclusion_set) if exclusion_set else set()
        reasons: dict[str, str] = {}
        if exclusion_paths:
            for ep in exclusion_paths:
                to_exclude |= self.load_exclusion_set(ep)
                reasons.update(self.load_exclusion_set_with_reasons(ep))

        # Read original cohort, keeping each line intact.
        original: list[tuple[str, str]] = []
        with open(cohort) as fh:
            for line in fh:
                parts = line.split()
                if parts:
                    sample_id = parts[1] if len(parts) >= 2 else parts[0]
                    original.append((sample_id, line.rstrip("\n")))

        kept = [line for sid, line in original if sid not in to_exclude]
        removed = [sid for sid, _ in original if sid in to_exclude]

        report = FilterReport(
            original_count=len(original),
            exclusion_count=len(to_exclude),
            final_count=len(kept),
        )
        for sid in removed:
            reason = reasons.get(sid, "unspecified")
            report.exclusion_reasons[reason] = (
                report.exclusion_reasons.get(reason, 0) + 1
            )

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("".join(f"{line}\n" for line in kept))
            logger.info("Wrote %d samples to %s", len(kept), output_path)

        return report
