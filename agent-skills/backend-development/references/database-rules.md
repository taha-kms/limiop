# Database Rules

## Models

Keep SQLAlchemy models focused on persistence mapping and database-level invariants. Avoid burying request-specific behavior inside ORM models.

Use clear table, column, relationship, foreign-key, and constraint names that match repository conventions.

Represent timestamps consistently and prefer timezone-aware application behavior.

Use database-generated or application-generated identifiers consistently with the codebase. Do not introduce a second ID strategy casually.

## Constraints

Use constraints when they express durable data invariants, including:

- foreign keys
- uniqueness
- non-null requirements
- valid relationship rules

Application validation complements database constraints; it does not replace them.

## Migrations

Use Alembic for schema evolution.

For every migration:

1. Inspect the generated operations rather than trusting autogeneration blindly.
2. Confirm upgrade behavior.
3. Provide a sensible downgrade when safely possible.
4. Consider existing rows when adding non-null columns.
5. Consider table size before expensive rewrites or index creation.
6. Separate destructive data removal from ordinary feature migrations when possible.

Never edit an already-applied shared migration to make history look cleaner. Create a new migration unless the repository is still explicitly in disposable pre-history.

## Queries

Avoid loading full ORM graphs accidentally. Select what the operation needs and use eager loading deliberately when relationships would otherwise cause N+1 queries.

Paginate collections that can grow significantly.

Use database transactions for multi-step state changes that must succeed or fail together.

Avoid helper functions that silently commit. Let the caller own transaction boundaries unless the codebase has an explicit unit-of-work convention.

## Testing PostgreSQL Behavior

When a test depends on PostgreSQL-specific behavior such as constraints, JSON operators, indexes, transaction semantics, or SQL syntax, run it against PostgreSQL through the project's test database setup. Do not assume SQLite proves PostgreSQL behavior.
