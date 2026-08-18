# Component and UI Rules

## Components

Keep components focused on one recognizable UI responsibility.

Prefer explicit props over passing large loosely typed objects when a component needs only a few fields.

Avoid mirroring every backend entity as one giant UI component. Shape presentation around the user's task.

Do not extract a component merely because markup appears once and is short. Extract when it improves reuse, readability, testing, or ownership.

## Server and Client Boundaries

Use server rendering by default where the installed Next.js version and project architecture support it.

Add a client boundary only for browser APIs, local interactive state, effects, event handlers, or client-only libraries.

Keep interactive islands small. Do not add client directives to an entire page tree to solve one button click.

## Tailwind

Follow existing token/theme conventions.

Prefer consistent spacing, typography, radius, and responsive patterns over one-off arbitrary values.

Use reusable variants/components when the same semantic control appears repeatedly.

Do not combine Tailwind with a second styling framework unless explicitly approved.

## Responsive UI

Start from the narrow layout and ensure content remains understandable as width increases.

For tables on small screens, choose a deliberate pattern such as horizontal scrolling, prioritized columns, or cards. Do not simply let layouts overflow invisibly.

Keep primary actions reachable and understandable on mobile.

## Feedback States

For asynchronous content, design explicit states:

- loading
- no results
- partial/filtered no results where relevant
- recoverable error
- successful data display

Use skeletons only when they preserve layout meaningfully. A simple loading indicator is better than decorative complexity when the wait is brief.

## Job UI

A job card/detail view should distinguish source data from SkillSync-derived data.

Common information may include:

- title
- company
- location/remote status
- employment type when available
- publication date when available
- match score
- matched skills
- missing skills
- original apply action

Do not fabricate unavailable salary, location, company, or skill information.

## Match Scores

Present scores with enough explanation that users do not mistake them for hiring probability.

Do not label a match score as "chance of getting hired" unless a future validated model explicitly supports that interpretation.

## Charts

Keep legends and axes readable.

Provide units and time ranges.

Avoid excessive categories that make a chart illegible.

Provide a textual summary or accessible supporting representation for important insights.
