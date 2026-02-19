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
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class FilterReport:
    """Summary of a cohort filtering run."""

    original_count: int = 0
    exclusion_count: int = 0
    final_count: int = 0
    exclusion_reasons: Dict[str, int] = field(default_factory=dict)

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
    ) -> Set[str]:
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

        ids: Set[str] = set()
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
    ) -> Dict[str, str]:
        """
        Read an exclusion file and return a mapping of sample ID to reason.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Exclusion file not found: {filepath}")

        mapping: Dict[str, str] = {}
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
        exclusion_paths: Optional[List[str]] = None,
        exclusion_set: Optional[Set[str]] = None,
        output_path: Optional[str] = None,
    ) -> FilterReport:
        """
        Apply exclusion filtering to a cohort sample list.

        Parameters
        ----------
        cohort_path : str
            Path to the original sample list (one ID per line or whitespace-
            delimited FID/IID).
        exclusion_paths : list of str, optional
            Paths to exclusion CSV files.
        exclusion_set : set of str, optional
            Pre-loaded set of IDs to exclude.
        output_path : str, optional
            Where to write the filtered list. If None, no file is written.

        Returns
        -------
        FilterReport
        """
        cohort = Path(cohort_path)
        if not cohort.exists():
            raise FileNotFoundError(f"Cohort file not found: {cohort_path}")

        # Build combined exclusion set
        to_exclude: Set[str] = set(exclusion_set) if exclusion_set else set()
        if exclusion_paths:
            for ep in exclusion_paths:
                to_exclude |= self.load_exclusion_set(ep)

        # Read original cohort
        original_ids: List[str] = []
        with open(cohort) as fh:
            for line in fh:
                parts = line.strip().split()
                if parts:
                    original_ids.append(parts[0])

        # Filter
        filtered = [sid for sid in original_ids if sid not in to_exclude]

        report = FilterReport(
            original_count=len(original_ids),
            exclusion_count=len(to_exclude),
            final_count=len(filtered),
        )

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("\n".join(filtered) + "\n")
            logger.info("Wrote %d samples to %s", len(filtered), output_path)

        return report
