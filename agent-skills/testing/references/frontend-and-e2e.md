# Frontend and End-to-End Tests

Use accessible selectors when possible:

- role
- label
- text visible to users
- stable test IDs only when semantic selectors are unsuitable

Do not couple tests to Tailwind class names or internal component structure.

Cover critical UI states:

- loading
- empty
- error
- permission denied
- successful data

Keep browser tests independent. Avoid relying on execution order or data left behind by another test.
