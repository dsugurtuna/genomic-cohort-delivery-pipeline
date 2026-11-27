# Why it's built this way

## The problem

A research data release has to contain exactly the approved participants, drawn from genotype
batches typed at different times, with withdrawals removed. Batches often disagree on a few
variants, merges fail, and the recipient needs a way to confirm that what arrived is what was sent.

## Design choices

**Why exclude conflicting variants instead of fixing them?** Because automatic strand flipping is
only safe for SNPs whose alleles are not complementary (A/T and C/G are ambiguous), and it needs a
reference to decide which batch is wrong. Excluding loses a few variants; a wrong flip silently
corrupts genotypes. The excluded list is reported and written to `CONFLICT_VARIANTS.txt` so the
loss is visible.

**Why stop on any other PLINK error?** Because naive batch scripts often carry on after a failed
merge and report zero samples. A pipeline that halts immediately with PLINK's own message is
easier to trust and to fix.

**Why keep `FID IID` lines intact?** Because PLINK 1.9's `--keep` expects both columns. Reducing
the list to one column breaks the keep file and matches exclusions against family IDs, which could
let an excluded participant through.

**Why no unconditional "PASS" in the status file?** Because an integrity claim must come from the
code that ran the check; here that is `verify()` against `MANIFEST.tsv` (which also covers
`STATUS_SUMMARY.tsv`), either at transfer time or later via `cohort-delivery verify`.

**Why owner and group permissions only?** Because genotype data should be readable by the project
team, not every account on a shared system. Default umasks on shared systems often grant read
access to all users.

**Why refuse to write into an existing delivery directory?** Because mixing two runs is the kind of
error nobody notices until a researcher does. Callers who intentionally run multiple distinct
deliveries on one day can pass an explicit `delivery_tag` or `unique_run=True` to create a
separate directory while keeping `exist_ok=False`.

## Questions worth asking

**"How do you know withdrawn participants are really gone?"**
As far as the exclusion lists are complete and use the same IDs as the genotype files. The
pipeline removes listed IDs, counts removals by reason, asserts post-merge that the final `.fam`
is non-empty and contains zero excluded or unrequested IIDs (failing closed before manifesting or
staging), and logs a warning if the merged sample count differs from the requested count. It cannot
know about a withdrawal nobody recorded, so the list itself must come from the consent system of
record.

**"What about A/T and C/G SNPs that are flipped between batches?"**
They do not trigger a PLINK merge error, because the allele sets match. They are silently wrong
after merging. Catching them needs a strand check against a reference (or allele frequency
comparison) before the merge. That is the remaining roadmap item and a stated limitation.

**"Why MD5 and SHA-256?"**
SHA-256 is the integrity check. MD5 is there because many recipients' existing tooling still
expects it; it is not relied on for tamper detection.

## What's next

- Strand check against a reference panel before merging; flip only non-ambiguous SNPs.
