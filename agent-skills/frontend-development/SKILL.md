---
name: frontend-development
description: Develop and modify the SkillSync frontend using Next.js, TypeScript, Tailwind CSS, Recharts, and Playwright. Use for frontend pages, layouts, components, forms, navigation, dashboard UI, job browsing, CV-upload flows, skill-gap visualizations, API consumption, client/server rendering decisions, frontend configuration, accessibility, responsiveness, frontend tests, and any change under the SkillSync frontend directory. Apply this skill whenever a task changes frontend-owned behavior or contracts consumed by the frontend. Follow the repository task workflow and Git rules separately.
---

# SkillSync Frontend Development

Build frontend changes that fit SkillSync's existing architecture and product behavior. Keep the frontend focused on presentation, interaction, navigation, and consumption of backend APIs.

## Required Context

Before editing frontend code:

1. Read the repository root `AGENTS.md`.
2. Read `docs/PROJECT_CONTEXT.md`.
3. Inspect `frontend/package.json`, TypeScript configuration, Next.js configuration, existing routes, components, styling conventions, and tests.
4. Reuse existing dependencies and patterns before introducing new ones.
5. Follow the issue, branch, commit, pull-request, and Git identity rules from `AGENTS.md`. Do not duplicate or weaken them here.

Treat the checked-in repository as the source of truth when its concrete structure is more specific than examples in this skill.

## SkillSync Frontend Stack

Use the established stack:

- Next.js
- TypeScript
- Tailwind CSS
- Recharts for product charts where appropriate
- Playwright for end-to-end/browser testing

Do not replace the stack or add a competing framework without an explicit project decision.

Do not assume a Next.js feature exists merely from memory. Check the installed version and existing project conventions before using version-sensitive APIs.

## Ownership Boundaries

Keep these responsibilities in the frontend:

- Pages, layouts, navigation, and presentation
- User interaction and browser state
- Forms and client-side validation for usability
- Calling SkillSync backend APIs
- Rendering jobs, match scores, skills, analytics, loading states, and errors
- Accessible and responsive UI behavior

Do not place these responsibilities in the frontend:

- Direct PostgreSQL access
- SQLAlchemy models or database queries
- Airflow orchestration or scheduled ingestion
- Job-source ingestion logic
- ML training or model artifact management
- Authoritative authentication/authorization decisions
- Secrets or privileged credentials
- Business rules that belong to FastAPI services

Frontend validation improves UX; backend validation remains authoritative.

## Development Workflow

For each frontend task:

1. Identify the route, component, API contract, and user flow affected.
2. Inspect nearby code and tests before creating new abstractions.
3. Determine whether the UI can remain server-rendered or needs client-side interactivity.
4. Implement the smallest coherent change.
5. Add loading, empty, success, and error behavior where the flow can enter those states.
6. Add or update tests for meaningful behavior.
7. Run the relevant frontend checks and inspect the rendered result when practical.
8. Review for accessibility, responsiveness, type safety, and accidental exposure of secrets.

## Rendering and Component Boundaries

Prefer server-rendered components for content that does not require browser-only APIs, local interactive state, effects, or event handlers.

Use client components only when interaction requires them. Keep the client boundary as small as practical rather than marking broad page trees as client-rendered for convenience.

Prefer composition over large components. Split components when they have distinct responsibilities, not merely to satisfy an arbitrary line count.

Keep page/layout files focused on composition and route-level concerns. Move reusable product UI into feature components.

Read `references/frontend-structure.md` before creating or reorganizing frontend directories.

## TypeScript Rules

Use explicit domain types for backend payloads and meaningful component props.

Avoid `any`. If data is truly unknown at a boundary, use `unknown` and narrow it safely.

Do not duplicate the same API response shape across multiple files. Reuse the established type location or generate/reuse contracts if the repository later adopts that approach.

Model nullability honestly. Do not silence type errors with non-null assertions unless the invariant is proven by surrounding code.

Prefer readable types over elaborate generic abstractions that obscure product behavior.

## API and Data Rules

Access backend APIs through the established frontend service/client layer rather than scattering raw request logic across unrelated components.

Keep transport concerns separate from visual components when practical.

Handle expected request states explicitly:

- loading
- empty result
- success
- validation failure
- authorization/authentication failure
- backend failure
- network failure

Never expose server secrets through `NEXT_PUBLIC_*` variables. Only values intentionally safe for browsers may use public environment variables.

Treat job descriptions and other API-provided rich text as untrusted. Do not inject unsanitized HTML into the DOM.

Read `references/api-and-state-rules.md` for API consumption, state ownership, forms, and error handling.

## SkillSync Product UI Rules

Design pages around the actual SkillSync workflows defined in `PROJECT_CONTEXT.md`.

For job results, preserve the distinction between:

- job facts from the source
- SkillSync-derived match scores
- matched skills
- missing skills
- the original application link

Do not imply SkillSync is the employer or application processor. Application actions must lead to the original job destination supplied by the backend.

For CV flows, avoid unnecessarily displaying extracted personal data. Show only what the product needs for the current user task.

For analytics, label metrics and time ranges clearly. Do not imply precision or causality that the backend data does not support.

## Styling Rules

Use Tailwind CSS according to the repository's established conventions.

Prefer reusable UI primitives for repeated patterns such as buttons, cards, badges, inputs, dialogs, tables, and feedback states.

Avoid copying long identical class strings throughout the codebase when a reusable component is justified.

Do not introduce another styling system merely for convenience.

Keep responsive behavior intentional. Important workflows must remain usable on narrow viewports as well as desktop layouts.

Do not use visual styling alone to communicate state. Pair color with text, icons, labels, or other accessible cues.

Read `references/component-and-ui-rules.md` for component, styling, chart, and responsive conventions.

## Accessibility

Use semantic HTML before adding ARIA.

Ensure interactive elements are keyboard-accessible and have meaningful accessible names.

Associate form labels with controls. Surface validation errors in a way users and assistive technologies can understand.

Maintain sensible heading hierarchy and focus behavior.

Do not make clickable `div` or `span` elements when a button or link is the correct semantic element.

Charts must not be the only representation of critical information. Provide labels, summaries, or accessible supporting content for important values.

## Forms

Keep browser validation and form feedback useful but never treat them as a security boundary.

Prevent accidental double submission where the flow can create duplicate actions.

Display backend validation errors in user-understandable form without exposing implementation details.

Preserve user input after recoverable validation failures when practical.

For file uploads, validate allowed file characteristics on the client for UX while relying on backend validation for enforcement.

## Charts and Analytics

Use Recharts when a chart is the clearest presentation, not simply because the dependency exists.

Choose chart forms that match the question:

- trend over time: line/area
- category comparison: bar
- composition: use sparingly and only when categories remain readable

Always include clear labels, units, and time windows.

Handle empty datasets explicitly instead of rendering misleading axes or broken chart shells.

Keep transformation of complex analytics data outside visual rendering code when possible.

## Testing

Test user-visible behavior rather than component implementation details.

Use the repository's existing frontend test tools. Use Playwright for important browser workflows such as authentication, CV upload, job browsing, job matching, and outbound apply-link behavior where those features exist.

Do not introduce a new unit/component test framework unless the repository has a demonstrated need and the task explicitly includes that decision.

Never claim tests passed unless they were run.

Read `references/testing-and-accessibility.md` before adding substantial frontend tests or changing critical user flows.

## Security and Privacy

Never store secrets in browser code, local storage, committed frontend files, or public environment variables.

Treat URLs and rich content from external job sources as untrusted input even after they pass through the backend.

Avoid logging CV contents, tokens, or sensitive user data to the browser console.

Do not weaken backend authentication/authorization assumptions by hiding UI elements and treating that as access control.

## Dependencies

Before adding a frontend package:

1. Check whether the existing stack already solves the problem.
2. Check whether an equivalent dependency is already installed.
3. Prefer platform and framework capabilities for simple needs.
4. Keep the dependency scoped to an actual requirement.
5. Update the appropriate lockfile.
6. Verify lint, build, tests, and dependency/security automation remain healthy.

Do not add a state library, form library, component framework, chart library, or request library preemptively.

## Completion Checklist

Before finishing a frontend change, verify:

- The change respects frontend/backend/Airflow/ML boundaries.
- TypeScript passes without unsafe shortcuts introduced for convenience.
- Loading, empty, error, and success states are handled where relevant.
- The UI is usable on desktop and narrow viewports.
- Interactive behavior is keyboard accessible.
- No secrets or sensitive user data are exposed.
- External rich content is not rendered unsafely.
- Relevant tests, linting, and build/type checks were run when available.
- The diff contains only the intended task scope.
- GitHub workflow rules from `AGENTS.md` were followed.
