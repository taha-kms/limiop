# Candidate profile and authentication — design

Approved 2026-08-24. Phase C's foundation: the profile both onboarding routes
write, and the session that gates it.

## What a profile is

One row per account. Both routes — CV extraction and manual onboarding — write
the same table, and nothing records which one did. #100 requires a manually
built profile to be indistinguishable from a CV-derived one, so a `source`
column would be a way to violate that by accident.

| field | required | notes |
| --- | --- | --- |
| `display_name` | yes | |
| `location` | yes | Free text, the same shape jobs use |
| `workplace_types` | yes | At least one member of the existing vocabulary |
| `employment_types` | yes | At least one member of the existing vocabulary |
| `headline` | no | One line |
| `summary` | no | Prose. CV extraction fills it; manual onboarding may skip it |
| `years_experience` | no | |

Skills live in their own table, owned by the profile.

The three vocabulary fields reuse `WorkplaceType` and `EmploymentType`
unchanged. A candidate's preferences and a job's attributes are then already
expressed in one vocabulary, and matching needs no translation layer between
them.

## Two states, not one

A profile has two independent readiness properties, and conflating them was the
mistake this section exists to avoid.

**`profile_complete`** — the canonical onboarding fields are present. This is
what onboarding drives toward and what applying is gated on.

**`matching_ready`** — complete, *and* carrying enough usable skill data to be
matched. This is what the personalized features are gated on.

Both are derived from stored data rather than written by application code.
`profile_complete` is a generated column, computed by PostgreSQL from the row
itself, because #99 asks for completeness derived from the row and a generated
column is the only version of that a buggy writer cannot lie about.
`matching_ready` depends on a count in another table, so it is a query rather
than a column, expressed once and reused rather than reimplemented per caller.

Splitting them is what lets the profile ship before the skill model does. A
candidate reaches `profile_complete` and can apply while #46 and #130 are still
being built; they become `matching_ready` later, without redoing onboarding.

### "Sufficient usable skill data" is load-bearing and not yet defined

This is the same shape of gap as "legitimate unknown skill" in #130, and it
deserves the same suspicion. A threshold of "at least one skill" is not a
threshold, it is a formality: the measurement showed unrestricted extraction
runs at 0.151 precision, so a profile holding one junk term would be
`matching_ready` and match nothing usefully.

The rule must be stated, versioned, and measured rather than assumed, and it
depends on #130 having decided what counts as a usable skill at all. Until then
`matching_ready` is defined structurally — complete, plus a skill count above a
named constant — with the constant recorded as provisional and the real rule
tracked as its own decision.

## Authentication

Registration hashes with argon2id. Login sets a JWT in a cookie:

```
Set-Cookie: session=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/
```

HttpOnly means JavaScript cannot read it, so an XSS bug cannot exfiltrate the
session. The cookie is readable by Next.js server components, which is the
property that matters beyond security: Phase A settled that pages render
complete on first byte, and a token held in JavaScript would turn every
personalized page into a client-side fetch after hydration.

### Revocation

The user row carries `token_version`. Every issued token carries the same value
as a claim, and a token whose claim does not match the row is rejected.

Incrementing it invalidates every token issued before that moment, across every
device. That is a strong action, so it is reserved for the cases that want it:

| event | effect |
| --- | --- |
| Normal logout | Clears the cookie on this device only |
| Password change | Increments `token_version` — every session ends |
| Account disabled | Increments `token_version` — every session ends |
| Explicit "log out everywhere" | Increments `token_version` |

Normal logout clearing only the cookie is the conventional behaviour and the
right default: logging out of a work laptop should not sign you out of your
phone. The honest cost is that a token already stolen before logout stays valid
until it expires, because clearing a cookie only affects the browser holding
it. **Token lifetime is therefore a security parameter rather than a
convenience one, and is set short — one hour — with re-login rather than
refresh tokens in the first version.** Refresh tokens need their own storage and
their own revocation story, which is the complexity this design was avoiding.

This makes the token only partly stateless, since checking the version needs
the user row. That is not an added cost: #40 requires a typed current user,
which needs that row regardless.

`SameSite=Lax` covers CSRF for same-site form posts and top-level navigation.
If a cross-site POST is ever added, that assumption breaks and needs an
explicit token. Recorded here so it is a decision rather than an oversight.

## Implementation order

**Track 1 — identity.** Nothing blocks it.

`#38` user model → `#39` registration and hashing → `#40` login, cookie
issuance, current-user dependency.

`#38` gains `token_version`; `#40` gains the version check.

**Track 2 — profile.** Starts once `#38` lands, and runs beside track 3.

`#99` profile model, `profile_complete` as a generated column, `matching_ready`
as a query → `#100` manual onboarding.

Independent of `#46` and `#130` because skills do not gate completeness. The
onboarding skills step is added later to a form that already works, rather than
holding the form hostage to a vocabulary.

**Track 3 — CV.** Serial, gated on `#40`.

`#41` upload policy → `#42` metadata and `#43` storage → `#44` upload endpoint
→ `#45` PDF text extraction.

`#43` needs rewriting before pickup. Whether an abstraction beats one concrete
backend is a decision rather than a given; the case for the interface here is
that `#44` must be testable without touching a real filesystem.

**Last — `#98`, what applying does.** It gates on `profile_complete`, so it
cannot be decided usefully until `#99` exists.

The recommendation when it comes up is the gated redirect. Every job already
carries `application_url`, SkillSync never receives the application, and the
outcome happens on somebody else's site and is never reported back — so a
tracked application's status vocabulary would be mostly states nobody can
observe. Ship the redirect and add tracking when a product reason exists.

## What this leaves open

- **What makes skill data sufficient** for `matching_ready`. Depends on `#130`.
- **Whether v1 serves German.** The encoder is multilingual, so the exclusion
  the skill measurement made is no longer forced. A profile has no language
  field in this design; adding one later is cheap, adding it wrongly now is not.
- **Refresh tokens.** Out of the first version deliberately. Revisit if a
  one-hour lifetime proves hostile in practice.
