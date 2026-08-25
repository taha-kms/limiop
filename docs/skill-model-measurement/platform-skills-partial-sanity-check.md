# Platform skills extractor — partial sanity check

This is a **partial sanity check**, not a reproduction of the full skill-model
measurement. Only 14 of the 78 gold-set postings were still present in the
live catalog with descriptions matching the committed SHA-256 hashes. Those
14 postings contain 414 of the 2,059 adjudicated gold mentions.

Provider text is not committed under the repository's data policy. The
recovery command joins the committed posting keys and SHA-256 hashes to the
live catalog, writes the matching text under ignored `.research/`, and reports
the number actually recovered. It returned:

```console
$ python platform/skills/scripts/recover_partial_gold.py
{
  "measurement": "partial sanity check",
  "recovered_postings": 14,
  "destination": "/work/.research/platform-skills-recovered-postings.json"
}
```

The extractor was then scored with the shipped `2026.08.25.1` alias-table
artifact:

```console
$ python platform/skills/scripts/evaluate_partial_gold.py
{
  "measurement": "partial sanity check",
  "recovered_postings": 14,
  "gold_mentions": 414,
  "extracted_mentions": 1341,
  "precision": 0.1417,
  "recall": 0.4106
}
```

Precision is the share of extracted spans that overlap at least one gold span.
Recall is the share of gold spans overlapped by at least one extracted span.
The check can catch broken tokenization or an extractor that misses obvious
vocabulary matches. It cannot establish whether this extractor is better or
worse than the hand-written surface forms: the available postings and
denominators are different from the full measurement, so those scores are not
compared here.
