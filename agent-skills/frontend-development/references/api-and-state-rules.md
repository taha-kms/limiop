# API and State Rules

## API Access

Use the existing frontend API client/service convention.

Centralize repeated concerns such as:

- API base URL
- shared headers
- serialization/deserialization
- standard error translation
- authentication transport, according to the established auth design

Do not build a giant client abstraction before repeated needs exist.

## Contracts

Treat FastAPI response schemas as the authoritative network contract.

Keep frontend types synchronized with that contract. When the repository later adopts schema/code generation, use that system instead of maintaining competing handwritten contracts.

Do not silently reinterpret backend fields in multiple components. Normalize once when a presentation-specific shape is genuinely useful.

## State Ownership

Keep state as close as practical to the component or route that owns it.

Do not add global state for values that are naturally local or URL-derived.

Use URL/query parameters for shareable/search/filter state when appropriate.

Prefer server-fetched data or framework-supported fetching where it fits the installed Next.js version and current architecture.

Add client caching/state libraries only when actual product requirements justify them.

## Forms

Keep form state local unless multiple distant views genuinely share an in-progress workflow.

Validate basic format/client constraints for immediate feedback, but preserve backend validation as authoritative.

Map backend field errors to the relevant controls when possible.

Disable or guard repeat submissions when duplicate operations would be harmful.

## Authentication

Follow the repository's chosen authentication design. Do not invent a second auth mechanism.

Never treat frontend route hiding as authorization.

Avoid exposing tokens to browser storage unless the established architecture explicitly requires it and security implications have been accepted.

## Errors

Convert technical failures into useful user-facing messages without exposing stack traces, raw internal errors, database information, or secrets.

Keep diagnostic detail in appropriate backend/observability channels, not the UI.

Preserve retry paths for transient failures when retry is safe.

## Untrusted Content

Do not render raw job-description HTML with unsafe DOM injection.

If the product requires rich HTML, use the repository's approved sanitization/rendering path and keep the sanitization boundary explicit.

Validate outbound job URLs before using them in application links. Prefer normalized URLs supplied by the backend.
