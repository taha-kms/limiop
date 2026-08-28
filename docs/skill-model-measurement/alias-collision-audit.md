# Alias-table collision audit — 2026-08-28

Issue #193. The first run of the shared extractor over real postings scored
0.1417 precision, and `own → Ownership` was the named suspect. This audit read
the whole `2026.08.25.1` alias table against live postings and published
`2026.08.28.1`, which removes 50 surface forms and adds none.

The result, in one line: **the removals delete 41% of the extractor's output
and cost none of the gold labels it could resolve.**

| | `2026.08.25.1` | `2026.08.28.1` |
| --- | --- | --- |
| Surface forms | 182 | 132 |
| Spans extracted from the 14 recoverable gold postings | 1341 | 789 |
| Gold labels resolved, of 2,059 | **455** | **455** |

Two findings matter as much as the removals:

- The span-overlap check **cannot score a vocabulary change**. Its 14
  recoverable postings all come from one employer, it annotates each term at
  most once per posting, and 97% of the matches it credits are the extractor
  hitting a fragment of a longer annotated phrase. Its precision figure did not
  improve here, and that is reported rather than chased.
- The vocabulary's real defect is not `own`. A third of the removed forms are
  **compound heads** — `management`, `operations`, `systems`, `design` — which
  only ever appear inside longer phrases the vocabulary does not contain.

## How the removals were chosen

`platform/skills/scripts/audit_alias_forms.py` matched every surface form
against every posting in the live catalog: 985 postings from 295 employers,
65,749 mentions, 67 mentions per posting.

One employer, Anthropic, accounts for 500 of the 985 postings and repeats a
long boilerplate blurb in all of them. Counting per posting therefore measures
who is hiring rather than how a form behaves: `interpretability` appears in 500
postings and **one** employer, `biology` in 501 and two, `physics` in 506 and
five. Every count below is per employer, and the script samples each form's
contexts at most once per employer for the same reason.

Sampling that way changed three verdicts. `collaborate` looked like pure noise
because every naive sample was the same boilerplate line; per employer it reads
"Collaborate with peers", "collaborate closely with product, design, customer
success". `adoption` and `recruiting` were rescued the same way.

## The check that can judge this change

`backend/scripts/measure_gold_label_resolution.py` asks whether at least one of
a gold mention's recorded annotator labels resolves **exactly** through the
alias table. It runs over all 2,059 mentions from all 78 gold postings, not the
14 that are still fetchable, and it credits nothing for partial overlap.

| Alias version | Resolved gold labels | Rate |
| --- | ---: | ---: |
| `2026.08.25.1` | 455 / 2,059 | 0.220981 |
| `2026.08.28.1` | 455 / 2,059 | 0.220981 |

Removing 50 of 182 surface forms changed this by zero. The audit's first cut
removed 51 and cost exactly seven mentions, all of them the single label
`hiring`; `hiring` was restored on that evidence and nothing else was.

That is the argument for the change. Forty-one percent less output, and not one
annotator label that used to resolve stopped resolving.

## Span-overlap scores before and after

The measurement the issue asked for, on the same 14 postings.

| Alias version | Extracted spans | Precision | Recall |
| --- | --- | --- | --- |
| `2026.08.25.1` | 1341 | 0.1417 | 0.4106 |
| `2026.08.28.1` | 789 | 0.1343 | 0.2488 |

**Precision did not improve.** Per the issue, that is a finding rather than a
reason to keep removing entries until it moved. The next section is why this
particular number could not have moved.

## Why the span-overlap scores cannot judge this change

Four facts, each checkable from committed data.

**All 14 recoverable postings are from one employer.** The other 64 expired
from their boards. There is no cross-employer signal in this corpus, and it is
the same employer whose boilerplate dominates the live catalog.

**Gold annotates a term at most once per posting; the extractor fires on every
occurrence.** No gold span text repeats within a posting — 0 of 414. A term
appearing ten times where annotators marked it once is capped at 0.1 precision
on that term whatever the vocabulary says. Re-scoring `2026.08.25.1` at one
mention per term per posting lifts precision from 0.1417 to 0.1686 with no
vocabulary change at all.

**Of the 190 matches the gold set credits, 6 are exact.** The other 184 are the
extractor matching a fragment of a longer annotated phrase, credited because
the score counts any span overlap. All 6 exact matches survive into
`2026.08.28.1`.

**Every additional restoration improves both numbers.** Variants removing 51,
49, 45, and 40 forms scored precision 0.1350, 0.1488, 0.1594, 0.1621 and recall
0.2488, 0.2826, 0.3309, 0.3551. A measure whose optimum is "change nothing" is
measuring overlap with one employer's prose, not correctness, and cannot be
used to choose how much to remove.

## The span-overlap scores argued for six forms, and then argued against themselves

Six removals — `management`, `operations`, `systems`, `design`, `platform`,
`training` — have the highest on-gold rates among the forms this audit selected
for removal: 0.50, 0.41, 0.26, 0.36, 0.33, 0.19, against 0.02–0.05 for the
high-volume forms that were kept. Two annotators plus adjudication marked those
spans. That is a specific, well-provenanced contradiction of the contextual
reading, so the spans themselves were read.

Not one of them is the bare word:

| Form | What the annotators actually marked |
| --- | --- |
| `management` | "contract management", "people management experience", "pipeline management skills", "change management strategies", "incident management", "order management" |
| `operations` | "legal operations", "procurement operations", "people operations", "revenue operations function", "security operations" |
| `systems` | "backend systems", "subscription, or fintech systems", "datacenter, hardware, and network systems", "automated enforcement systems" |
| `design` | "design RL environments", "shaping experimental design", "process design", "design evaluation approaches" |
| `platform` | "building backend or platform systems in production", "CLM platform (Ironclad)", "policy enforcement at platform scale" |
| `training` | "large-scale distributed training", "post-training", "generating and curating training data", "training materials" |

The apparent agreement was overlap credit, not an annotator judgment that the
bare word is a skill. All six stay removed, and the gold-label resolution rate
confirms it: none of these forms is an exact annotator label anywhere in the
corpus.

## Two concepts are now unreachable

`Management` and `Operations` had no surface forms other than the ones removed
— `management`, `manage`, `managing`, `managers`, and `operations`,
`operational`, `operating` — and every one reads as ordinary English. Both
concepts remain published in `2026.08.28.1`, and nothing resolves to them.

That is the correct outcome for this change and the wrong end state. Restoring
them needs the compound forms the gold spans name — "people management",
"incident management", "security operations", "revenue operations" — and adding
surface forms is out of scope here. Filed as a follow-up, with the gold spans
above as its evidence.

## Removed in `2026.08.28.1`

Counts are over the 985-posting live catalog; contexts were sampled at most
once per employer.

| Removed | Mentions | Employers | Why |
| --- | --- | --- | --- |
| `accelerators` | 64 | 5 | collides with sales compensation ("commission plan with accelerators") and consulting assets. `compute` and `gpu` remain. |
| `activation` | 53 | 12 | marketing jargon for a campaign launch: "Brand Activation", "GTM activation". Not adoption. |
| `budget` | 188 | 70 | predominantly a benefit: "Monatliches Budget für Benefits", "£1,000 annual education budget", "Training budget". |
| `collaborative` | 650 | 56 | describes the employer's culture, not the candidate: "a collaborative and supportive environment". `collaborate` and `collaboration` remain. |
| `contract` | 187 | 27 | predominantly the employment arrangement ("fixed-term contract", "six-month employment contract") and collides with "Contract-Testing". `contracts` remains. |
| `customers` | 710 | 83 | names the clients, not the service skill. `customer service`, `customer support`, `customer success` remain. |
| `delivery` | 390 | 68 | overloaded: project delivery, delivery framework, and physical delivery in a catalog that carries logistics employers. |
| `design` | 1221 | 117 | too broad for Product design, and every gold span containing it is longer: "design RL environments", "shaping experimental design", "process design". |
| `education` | 1097 | 23 | a benefit or a requirement line: "Minimum education: Bachelor's degree", "Education Reimbursement", "annual education budget". `teaching` and `curriculum` remain. |
| `engineering` | 1273 | 111 | names a department or an unrelated discipline: "partnering with engineering", "Electrical Engineering", "prompt engineering". `software engineering` remains. |
| `enterprise` | 785 | 49 | a market-segment adjective, and collides with "Red Hat Enterprise Linux". `saas` and `b2b` remain. |
| `execute` | 209 | 36 | ordinary verb, and collides with agent descriptions: "agents that plan and execute multi-step tasks". `execution` remains. |
| `flexibility` | 118 | 43 | same: "flexibility days policy", "remote flexibility". `adaptability` and `adaptable` remain. |
| `flexible` | 783 | 132 | a benefit, not a trait: "flexible working hours", "Flexible Arbeitszeiten", "hybrid or remote". |
| `influence` | 165 | 45 | ordinary verb, and appears in EEO boilerplate: "will not influence the outcome of your application". `influencing` and `persuasion` remain. |
| `lead` | 758 | 103 | collides with "lead generation" and with job titles ("Senior Cyber Policy Lead"). `leadership` remains. |
| `leaders` | 662 | 36 | names other people ("business leaders", "leaders in the functions you serve"), never the candidate. |
| `legal` | 442 | 29 | names a department: "alongside Legal, Strategy, and FP&A", "Finance, Legal, Security, and IT". `contracts` remains. |
| `manage` | 342 | 78 | ordinary verb: "Manage prospects", "manage multiple projects", "manage and optimize their capital". |
| `management` | 917 | 149 | always a compound head. The gold set marks "contract management", "people management experience", "pipeline management skills", "incident management", "order management" — never the bare word. |
| `managers` | 131 | 38 | names other people: "product managers", "hiring managers", "partner managers". |
| `managing` | 309 | 61 | ordinary verb: "managing conditions", "configuring, managing, and querying headless CMS". |
| `market` | 626 | 75 | always a compound: "go-to-market", "product-market fit", "Standard market". `market analysis` remains. |
| `medical` | 98 | 28 | a benefit: "Private Medical Insurance", "private medical cover", and EEO boilerplate. `healthcare` and `clinical` remain. |
| `mindset` | 169 | 78 | never stands alone: "proactive mindset", "AI-first mindset", "Technisches Mindset". `growth mindset` remains. |
| `monitoring` | 140 | 42 | collides with finance and credit: "Performance Monitoring", "Credit Monitoring Team". `observability` and `telemetry` remain. |
| `operating` | 347 | 49 | ordinary verb: "comfortable operating with CRO-level leadership", "the pharmacy is operating safely". |
| `operational` | 425 | 61 | ordinary adjective: "operational rhythm", "operational processes". |
| `operations` | 615 | 93 | always a compound head. The gold set marks "legal operations", "procurement operations", "people operations", "revenue operations", "security operations" — never the bare word. |
| `own` | 989 | 108 | verb and possessive. "you will own the annual IT budget", "our own products". States a duty, not the competency; `ownership` and `accountability` carry it. |
| `plans` | 184 | 32 | collides with benefits: "pension plans", "medical, dental and vision plans". `planning` and `roadmap` remain. |
| `platform` | 720 | 103 | a product noun, and every gold span containing it is longer: "building backend or platform systems in production", "CLM platform (Ironclad)". |
| `platforms` | 381 | 64 | same, plural. |
| `problems` | 774 | 66 | ordinary noun, and matches the paper title "Concrete Problems in AI Safety". `problem solving` and `troubleshooting` remain. |
| `process` | 1007 | 104 | collides with the hiring process it appears inside: "application process", "Interview Process", "recruitment journey". `process improvement` remains. |
| `processes` | 588 | 81 | same, plural. |
| `projects` | 401 | 74 | ordinary noun: "challenging projects", "internships, projects". `project management` remains. |
| `quality` | 510 | 101 | ordinary modifier: "high-quality communication", "code quality", "speed and quality". `quality assurance`, `qa`, `testing` remain. |
| `reports` | 90 | 36 | collides with org structure: "your direct reports". `reporting` and `dashboards` remain. |
| `safety` | 1468 | 13 | never occupational safety here: "AI Safety", "psychological safety", "Your safety matters to us" (anti-scam boilerplate). `health and safety` and `food safety` remain. |
| `science` | 1204 | 33 | fires as a fragment of a longer term the vocabulary lacks: "Data Science", "the data science field". `computer science` and `scientific` remain. |
| `software` | 441 | 112 | the product-category noun, not the engineering skill: "a software environment", "software and SaaS agreements", "AI-powered MRO software". |
| `stakeholders` | 535 | 82 | names people. `stakeholder management` and `stakeholder engagement` remain and are precise. |
| `standards` | 349 | 79 | ordinary noun: "building codes and standards", "Real Chemistry standards", "klare Standards". `best practices` remains. |
| `strategic` | 610 | 67 | an adjective on another noun: "strategic partner", "strategic developer communities", "strategic account plans". `strategy` remains. |
| `system` | 416 | 86 | same, singular. |
| `systems` | 1769 | 106 | ordinary noun, and every gold span containing it is longer: "backend systems", "fintech systems", "datacenter, hardware, and network systems". |
| `training` | 1451 | 62 | predominantly what the candidate receives, and every gold span containing it is longer: "large-scale distributed training", "post-training", "training materials". |
| `usage` | 661 | 16 | ordinary noun: "data usage", "product usage", "Candidates' AI Usage". |
| `warehouse` | 24 | 8 | in this catalog it is always a data warehouse, never a building. |

## Kept, having been suspected

The issue named `ai`, `ml`, `qa`, `gpu`, and `b2b` as milder cases of the same
shape as `own`. Read against real postings, four of the five show no collision
at all, and `own` behaves differently from `ownership`.

| Kept | Mentions | Employers | Evidence |
| --- | --- | --- | --- |
| `adoption` | 326 | 36 | per-employer sampling shows "responsible adoption of generative AI", "driving adoption of the platform". The "maternity or adoption" collision is a minority. |
| `ai` | 6413 | 136 | sampled per employer, every context is a real mention. Its 6,413 hits are boilerplate repetition, not a bad alias. |
| `b2b` | 120 | 38 | "B2B sales", "B2B-Vertrieb". One minority misfire: "Contract Type: We prefer B2B". |
| `collaborate` | 777 | 60 | per-employer sampling shows "Collaborate with peers", "collaborate closely with product, design". The dominant employer's boilerplate had masked this. |
| `english` | 382 | 195 | "Full professional proficiency in English". Its inflated count comes from Arbeitnow's own footer, which is a normalization defect, not a vocabulary one. |
| `execution` | 298 | 50 | "planning through to execution", "hands-on execution", "rapid execution". |
| `financial` | 432 | 53 | "owning our financial steering", "financial outcomes". |
| `gpu` | 29 | 5 | "multi-GPU training", "GPU clusters", "GPU node orchestration". No collision found. |
| `hiring` | 242 | 61 | selected for removal on its contexts ("hiring managers", "hiring process", "hiring panel"), then restored: it is the only removed form that any annotator used as an exact gold label, 7 times across the full 78-posting gold set. |
| `logistics` | 558 | 16 | "autonomous logistics", "logistics, manufacturing". Real, despite one employer using it as a section heading. |
| `ml` | 195 | 13 | "complex ML systems", "ML models", "ML frameworks". No collision found. |
| `ownership` | 371 | 115 | "High level of ownership", "You'll have real ownership". The competency, unlike `own`. |
| `qa` | 39 | 12 | "QA engineers", "QA Engineering", "QA tools". No collision found. |
| `recruiting` | 601 | 28 | "Recruiting-Strategie", "von Recruiting über Onboarding". Real, despite the anti-scam boilerplate. |
| `sourcing` | 60 | 12 | 2 of 3 sampled are recruiting; the procurement sense is a minority. |

`own` was also dropped from `TEXT_MATCHING_HAZARD_FORMS` in
`backend/app/modules/skills/resolution.py`: that constant lists short forms that
are published and hazardous, and it is no longer published.

## What this leaves open

**Repetition, not vocabulary, is most of the precision problem.** 67 mentions
per posting is mostly the same terms recurring. `job_skill_mentions.occurrences`
counts per-posting occurrences and the evaluation script counts spans; they
should agree before either number is trusted.

**Two provider footers are being extracted as posting text.** Arbeitnow appends
`Find more English Speaking Jobs in … on Arbeitnow` to every posting, which is
why `english` fires on nearly every Arbeitnow row; Anthropic appends an
anti-scam notice and a `Logistics / Minimum education:` block. These are
normalization defects in the ingestion path, not vocabulary defects, and they
will pollute `job_skill_mentions` as soon as #189 runs.

**The span-overlap corpus needs replacing, not re-scoring.** One employer,
annotated once per term, scored by overlap. The observations
`job_skill_mentions` accumulates under #189 are the intended replacement and
carry the employer and posting this corpus lacks.

## Reproducing

```bash
python platform/skills/scripts/audit_alias_forms.py \
  --database-url "$SKILLSYNC_DATABASE_URL" \
  --counts counts.json --contexts contexts.json

python -m scripts.measure_gold_label_resolution --vocabulary-version 2026.08.25.1
python -m scripts.measure_gold_label_resolution --vocabulary-version 2026.08.28.1

python platform/skills/scripts/recover_partial_gold.py
python platform/skills/scripts/evaluate_partial_gold.py \
  --vocabulary backend/app/modules/skills/data/aliases.v2.json
python platform/skills/scripts/evaluate_partial_gold.py \
  --vocabulary backend/app/modules/skills/data/aliases.v3.json
```

The catalog text is not committed under the repository's data policy, so the
audit and recovery scripts read it from a database holding the catalog.
