# Annotation in progress — not the gold set

These are the two annotation passes as they stand mid-run, committed only so
hours of work are not held in a temporary directory. Nothing here has been
adjudicated, and no vocabulary has been built or scored against it.

The gold set is what comes out of adjudication, and it gets committed on its
own, once. Until then, treat every file in this directory as a draft that will
be replaced rather than as evidence.

Both passes are independent: neither annotator has seen the other's labels, and
neither has seen any candidate vocabulary. That is what these files are for, and
it is why they are stored apart from the adjudicated result rather than merged
into it early.

Three files that were here are gone, and deliberately.

`arms-summary.json` carried the thousand highest-frequency n-grams of the
corpus. A fifth of them were multi-word phrases lifted verbatim out of job
descriptions, most of them fragments of equal-opportunity boilerplate. That is
exactly the provider prose the measurement design promised never to commit, so
the file was removed rather than kept for convenience. What it was for survives
in `../results.md`, which reports what those terms showed without reproducing
any of them — including here, where quoting an example to explain the problem
would have reintroduced it.

`agreement.py` and `diagnose.py` hard-coded an absolute path into a scratch
directory on one machine and read filenames that were never committed. They
could not run for anyone, here included. Their output is `agreement.txt`.
