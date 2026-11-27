"""Allow execution via ``python -m cohort_delivery``."""

from cohort_delivery.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
