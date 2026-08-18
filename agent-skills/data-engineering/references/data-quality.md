# Data Quality Rules

## Contents

1. Quality philosophy
2. Field classification
3. Record outcomes
4. Run metrics
5. Thresholds
6. Quarantine
7. Schema drift

## 1. Quality Philosophy

Quality checks protect product behavior and analytical truth. They should distinguish imperfect but usable records from dangerous/systemic corruption.

Do not make every optional null fatal. Do not make every error a warning either.

## 2. Field Classification

Classify important fields as one of:

- required for identity
- required for user-facing usefulness
- optional but valuable
- derived
- audit/provenance

A typical job requires enough information to identify it, present a meaningful vacancy, and send the user to a legitimate original destination.

## 3. Record Outcomes

Use explicit outcomes:

### Accept

Record meets required contract.

### Accept with warning/null

Optional information is absent or unusable but the job remains valid.

### Repair

Apply only deterministic, documented repairs. Preserve the fact that repair occurred if operationally useful.

### Quarantine

Keep the record available for investigation/reprocessing without promoting it to serving data.

### Reject

Record cannot safely/meaningfully be used.

### Fail run/source

Use when failure indicates systemic corruption, such as a provider schema changing and making most records invalid.

## 4. Run Metrics

Capture useful counts per source/run:

- fetched
- parsed
- accepted
- repaired
- warned
- quarantined
- rejected
- duplicate source records
- duplicate canonical records
- inserted
- updated
- unchanged
- marked inactive
- enrichment successes/failures

Metrics should reconcile where practical. A run reporting 10,000 fetched and 9 inserted with no explanation is not observability; it is a puzzle.

## 5. Thresholds

Use thresholds for systemic anomalies when justified, such as:

- rejection ratio suddenly above a known-safe limit
- required field null rate spike
- zero records from a normally active source
- unexpectedly large source volume jump/drop

Do not invent arbitrary thresholds. Base them on provider behavior or explicitly configured expectations.

## 6. Quarantine

Quarantined data should include enough metadata to diagnose the reason without exposing unnecessary sensitive/raw content.

Useful fields:

- source
- source record ID
- run ID
- error/reason code
- timestamp
- safe excerpt or payload reference if required

Avoid logging/storing complete sensitive documents just to preserve an error trace.

## 7. Schema Drift

A provider contract change should produce a detectable failure or quality signal before corrupt data reaches serving tables.

Add a regression fixture for every discovered drift case.
