# Frontend Structure

Use the repository's actual structure first. When creating a new area and no stronger convention exists, prefer this shape:

```text
frontend/
├── app/
│   ├── auth/
│   ├── dashboard/
│   ├── jobs/
│   ├── profile/
│   └── upload-cv/
├── components/
│   ├── ui/
│   ├── jobs/
│   ├── skills/
│   └── charts/
├── services/
├── lib/
├── types/
├── tests/
├── public/
├── package.json
└── tsconfig.json
```

## Placement Rules

### `app/`

Keep route segments, pages, layouts, route-level loading/error UI, and route-specific composition here.

Do not turn route files into general-purpose component libraries.

### `components/ui/`

Place low-level reusable presentation primitives here when the repository uses this convention. Examples include buttons, inputs, badges, cards, dialogs, and empty-state shells.

Do not place SkillSync business rules in UI primitives.

### Feature component folders

Use `components/jobs/`, `components/skills/`, `components/charts/`, or an equivalent established feature organization for reusable product UI.

Prefer feature-local components when reuse is limited to one product area. Promote components to more general locations only after real reuse appears.

### `services/`

Place typed backend API access and transport adapters here when the repository follows this pattern.

Keep HTTP details out of unrelated presentation components.

### `types/`

Place shared frontend domain/API types here when they are used across features. Keep highly local component prop types beside their components.

### `lib/`

Use for small framework/application utilities that do not belong to a feature or transport service. Do not turn `lib/` into an unowned dumping ground.

### `tests/`

Follow the repository's chosen Playwright/test layout. Keep browser workflows understandable by product scenario.

## Dependency Direction

Prefer:

```text
Page/Layout
    ↓
Feature component
    ↓
UI primitive

Page/Feature
    ↓
Frontend service
    ↓
FastAPI
```

Avoid:

```text
UI primitive → feature business rules
component → PostgreSQL
component → Airflow
component → ML training
```

## Imports

Use the repository's configured path aliases when they improve clarity. Do not introduce a second alias scheme.

Avoid circular dependencies between features and shared UI.
