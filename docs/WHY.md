# Why it's built this way

## The problem

A research data release has to contain exactly the approved participants, drawn from genotype
batches typed at different times, with withdrawals removed. Batches often disagree on a few
variants, merges fail, and the recipient needs a way to confirm that what arrived is what was sent.

## Design choices

**Why exclude conflicting variants instead of fixing them?** Because automatic strand flipping is
only safe for SNPs whose alleles are not complementary (A/T and C/G are ambiguous), and it needs a
reference to decide which batch is wrong. Excluding loses a few variants; a wrong flip silently
corrupts genotypes. The excluded list is reported so the loss is visible.

**Why stop on any other PLINK error?** Because the first version carried on after a failed merge
and reported zero samples. A pipeline that halts with PLINK's own message is easier to trust and to
fix.

**Why keep `FID IID` lines intact?** Because PLINK 1.9's `--keep` expects both columns. Reducing
the list to one column broke the keep file and matched exclusions against family IDs, which could
let an excluded participant through.

**Why no "PASS" in the status file by default?** Because it was written unconditionally. An
integrity claim must come from the code that ran the check; here that is `verify()` at the
destination, against the manifest.

**Why owner and group permissions only?** Because genotype data should be readable by the project
team, not every account on a shared system. The old defaults granted read access to all users.

**Why refuse to write into an existing delivery directory?** Because mixing two runs is the kind of
error nobody notices until a researcher does.

## Questions worth asking

**"How do you know withdrawn participants are really gone?"**
Only as far as the exclusion lists are complete and use the same IDs as the genotype files. The
pipeline removes listed IDs, counts removals by reason, and compares the number of samples
requested with the number in the merged files, warning on a mismatch. It cannot know about a
withdrawal nobody recorded, so the list itself must come from the consent system of record.

**"What about A/T and C/G SNPs that are flipped between batches?"**
They do not trigger a PLINK merge error, because the allele sets match. They are silently wrong
after merging. Catching them needs a strand check against a reference (or allele frequency
comparison) before the merge. That is the first roadmap item and a stated limitation.

**"Why MD5 and SHA-256?"**
SHA-256 is the integrity check. MD5 is there because many recipients' existing tooling still
expects it; it is not relied on for tamper detection.

## What's next

- Strand check against a reference before merging; flip only non-ambiguous SNPs.
- A config-file CLI so a delivery is reproducible from one file.
- Include the excluded-variant list in the delivery package.
