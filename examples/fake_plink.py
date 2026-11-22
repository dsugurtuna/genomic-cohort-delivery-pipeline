"""A tiny stand-in for PLINK 1.9, used by the demo and the tests.

Supports --bfile/--keep/--exclude/--make-bed/--out extraction, --merge-list
(writing <out>-merge.missnp and exiting non-zero when a variant's alleles
differ between inputs), and --recode vcf bgz. Not a PLINK reimplementation.
"""

import gzip
import os
import sys
from pathlib import Path

args = sys.argv[1:]


def opt(name):
    return args[args.index(name) + 1] if name in args else None


def rows(path):
    text = Path(path).read_text()
    return [line.split() for line in text.splitlines() if line.strip()]


def write(prefix, bim, fam):
    Path(prefix + ".bim").write_text("".join("\t".join(r) + "\n" for r in bim))
    Path(prefix + ".fam").write_text("".join(" ".join(r) + "\n" for r in fam))
    Path(prefix + ".bed").write_bytes(b"")
    Path(prefix + ".log").write_text("fake plink\n")


def main():
    out, bfile = opt("--out"), opt("--bfile")

    if "--recode" in args:
        iids = [r[1] for r in rows(bfile + ".fam")]
        header = [
            "#CHROM",
            "POS",
            "ID",
            "REF",
            "ALT",
            "QUAL",
            "FILTER",
            "INFO",
            "FORMAT",
        ]
        with gzip.open(out + ".vcf.gz", "wt") as fh:
            fh.write("##fileformat=VCFv4.2\n")
            fh.write("\t".join(header + iids) + "\n")
        return 0

    if "--merge-list" in args:
        if os.environ.get("FAKE_PLINK_FAIL_MERGE"):
            print("Error: Duplicate sample ID in merge.")
            return 2
        listed = [p.strip() for p in Path(opt("--merge-list")).read_text().splitlines()]
        prefixes = [bfile] + [p for p in listed if p]
        alleles, bim, fam, conflicts = {}, {}, {}, set()
        for p in prefixes:
            for r in rows(p + ".bim"):
                a = frozenset(r[4:6])
                if r[1] in alleles and alleles[r[1]] != a:
                    conflicts.add(r[1])
                alleles.setdefault(r[1], a)
                bim.setdefault(r[1], r)
            for r in rows(p + ".fam"):
                fam.setdefault((r[0], r[1]), r)
        if conflicts:
            missnp = Path(out + "-merge.missnp")
            missnp.write_text("".join(c + "\n" for c in sorted(conflicts)))
            print(f"Error: {len(conflicts)} variants with 3+ alleles present.")
            return 3
        write(out, list(bim.values()), list(fam.values()))
        return 0

    keep = {tuple(r[:2]) for r in rows(opt("--keep"))}
    exclude = set()
    if "--exclude" in args:
        exclude = set(Path(opt("--exclude")).read_text().split())
    write(
        out,
        [r for r in rows(bfile + ".bim") if r[1] not in exclude],
        [r for r in rows(bfile + ".fam") if (r[0], r[1]) in keep],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
