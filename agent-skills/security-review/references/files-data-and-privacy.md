# Files, Data, and Privacy

## CV uploads

Validate size and content type; do not trust extension alone.

Generate storage object names/paths server-side. Keep original filenames as metadata only when needed and sanitize before display.

Store uploaded files outside publicly executable application paths.

Apply access control to download/read URLs and object storage.

## Parsing

Treat parsers as attack surface. Limit CPU/memory/time where feasible and keep libraries patched.

Never invoke a shell with a user-controlled filename or document text.

## Personal data

Collect and retain only what SkillSync needs.

Do not log full CV text or expose it in analytics/training artifacts by default.

Do not use user CVs for model training without an explicit approved consent/governance path.
