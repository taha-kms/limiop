# Authentication and Web Security

## Authorization

- Enforce on the server.
- Check resource ownership, not only authentication.
- Deny by default.
- Avoid mass-assignment of privileged fields.

## Sessions/tokens

- Keep signing/encryption secrets out of code.
- Validate expiry and intended claims according to the chosen auth design.
- Use secure cookie attributes if cookies carry authentication state.

## CORS/CSRF

Keep CORS origins narrow. Do not use permissive credentials + wildcard-style configurations.

If browser authentication relies on ambient cookies for state-changing requests, review CSRF protections appropriate to the framework/design.

## XSS

Treat external job descriptions and user-derived text as untrusted. Avoid unsafe HTML injection APIs; sanitize HTML only when rich HTML is truly required.

## Injection

Use ORM/parameterized SQL, structured APIs, and context-appropriate output encoding. Never concatenate untrusted values into SQL or shell commands.
