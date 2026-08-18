# Dependencies and Maintenance

Configure Dependabot for dependency ecosystems actually present in SkillSync.

Keep PR volume manageable through sensible schedules/grouping, but do not group unrelated high-risk upgrades so broadly that failures become impossible to diagnose.

Require dependency PRs to pass normal relevant checks.

Review major-version upgrades manually for migration notes and compatibility.

Keep lockfiles committed where the package manager expects them.

Do not disable vulnerable-dependency alerts merely to reduce noise; triage and document exceptions.
