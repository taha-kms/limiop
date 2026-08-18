# Schema Design

## Domain modeling

- Model stable SkillSync concepts relationally.
- Keep many-to-many relationships explicit with association tables when relationship metadata may matter.
- Avoid duplicating canonical values across tables without a reason.
- Keep source-provider identifiers separate from SkillSync internal identifiers.
- Preserve source provenance for externally ingested data.

## Constraints

Use database constraints for invariants that must survive every code path.

Examples include:

- required foreign-key ownership
- unique provider/source job identifiers where guaranteed by the source contract
- valid bounded values when a stable domain constraint exists
- uniqueness of association rows such as `(job_id, skill_id)` when duplicates are invalid

Do not encode uncertain product assumptions as irreversible constraints.

## JSON/JSONB

Use JSONB for source payloads, flexible metadata, or structures that are genuinely not stable relational entities.

Do not place frequently joined/filterable core fields only inside JSONB.

## Indexes

Create indexes from real access patterns. Review composite index column order against the actual predicate/sort pattern.

Do not duplicate indexes already provided by primary-key or unique constraints unless PostgreSQL behavior justifies it.
