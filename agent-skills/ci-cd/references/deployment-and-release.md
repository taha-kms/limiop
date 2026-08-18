# Deployment and Release

## Artifacts

Build immutable deployable artifacts/images from reviewed commits.

Tag with commit SHA or another immutable identifier.

## Environments

Keep staging and production configuration/secrets separate.

Use protected environments/approvals for sensitive production deployment where available.

## Database migrations

Run migrations as an explicit deployment step or release operation. Do not let every application replica race to perform schema migration on startup unless the architecture intentionally supports it.

Plan backward compatibility between migration and application rollout.

## Verification

After deployment, verify basic health/readiness and critical connectivity. Make rollback/redeploy procedures explicit for production changes.
