# Testing and Accessibility

## Testing Priorities

Prioritize behavior with user or product risk:

1. Authentication flows
2. CV upload and validation
3. Job search/filter/browse flows
4. Match-score and skill-gap presentation
5. Original apply-link behavior
6. Error and empty states
7. Critical navigation

Use Playwright for meaningful browser-level workflows when those features exist.

Do not test framework internals or Tailwind class strings as primary behavior.

## Stable Tests

Prefer accessible roles, labels, and user-visible text for selectors.

Use explicit test IDs only when semantic selectors cannot identify the element reliably.

Avoid arbitrary sleeps. Wait for observable UI/network state.

Keep tests deterministic and independent. Do not depend on test execution order.

Use controlled fixtures or test data rather than live third-party job APIs in frontend CI.

## Accessibility Review

For changed user flows, verify:

- logical heading order
- keyboard reachability
- visible focus
- labels for controls
- meaningful button/link names
- error association with inputs
- no color-only critical meaning
- reasonable text contrast under the established design system
- dialogs/popovers manage focus correctly when used

## File Uploads

Make the file input operable with keyboard and assistive technologies.

State accepted file types and relevant limits in visible text when the product defines them.

Show upload progress only when technically meaningful; otherwise show a clear pending state.

## Charts

Charts should have surrounding context that identifies:

- what is measured
- units
- time period
- important takeaway where appropriate

Critical values must be available outside the graphical marks alone.

## Responsive Checks

For substantial UI changes, verify at least one narrow and one desktop viewport through the project's existing browser-test or manual verification process.
