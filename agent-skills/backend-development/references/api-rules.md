# API Rules

## Endpoint Design

Match existing API versioning and naming first. If none exists, keep URLs resource-oriented and predictable.

Prefer:

```text
GET    /jobs
GET    /jobs/{job_id}
POST   /cvs
GET    /cvs/{cv_id}
GET    /recommendations
POST   /saved-jobs
DELETE /saved-jobs/{job_id}
```

Avoid action-heavy RPC-style paths unless the operation is genuinely not a resource operation.

## Contracts

Define explicit Pydantic request and response models. Separate creation/update/input models from output models when fields differ.

Do not expose by accident:

- password hashes
- internal tokens
- storage credentials
- private object-storage paths when a safer public/signed abstraction is intended
- internal-only model metadata

## Pagination

Any endpoint that can grow without a practical fixed bound should paginate. Follow the repository's established pagination style. Do not return an unbounded jobs table because the development database currently contains twelve rows.

## Filtering

Validate filters and keep semantics stable. Prefer explicit typed fields over accepting arbitrary query expressions.

## Errors

Use stable client-safe error responses. Distinguish common cases such as:

- invalid request -> 400/422 as appropriate to existing conventions
- unauthenticated -> 401
- authenticated but forbidden -> 403
- missing resource -> 404
- conflict/duplicate state -> 409 where appropriate

Do not expose raw database or Python exception strings as the public error contract.

## Idempotency

Make naturally idempotent operations behave that way. For create operations vulnerable to duplicate requests, use database uniqueness/transaction strategies appropriate to the resource rather than relying only on frontend behavior.
