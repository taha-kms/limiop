/**
 * What a match looks like, shown rather than described.
 *
 * Four roles take turns in the same space. The skills are an illustration and
 * the card says so: showing invented numbers as though they were somebody's
 * own results would be a lie the moment the page loaded, and the mechanic is
 * the part worth explaining anyway -- skills you have are lit, the rest stay
 * dim.
 *
 * Every card is in the document and in the accessibility tree. Only which one
 * is painted changes, so a reader who never sees the animation still gets all
 * four, in order, with each skill saying which side of the line it falls on.
 */

interface Role {
  title: string;
  company: string;
  /** Named as the split rather than as a flag per skill, because the split is
      the thing the card exists to show. */
  held: string[];
  missing: string[];
}

const ROLES: Role[] = [
  {
    title: "Data Engineer",
    company: "Meridian Software",
    held: ["Python", "SQL", "Airflow"],
    missing: ["dbt", "Kubernetes"],
  },
  {
    title: "Frontend Developer",
    company: "Halcyon Analytics",
    held: ["TypeScript", "React", "CSS"],
    missing: ["Figma"],
  },
  {
    title: "Data Analyst",
    company: "Northwind Logistics",
    held: ["SQL", "Excel", "Tableau"],
    missing: ["R", "Python"],
  },
  {
    title: "Platform Engineer",
    company: "Meridian Software",
    held: ["Docker", "Linux", "Terraform"],
    missing: ["Go", "AWS"],
  },
];

function RoleCard({ role, index }: { role: Role; index: number }) {
  const skills = [
    ...role.held.map((name) => ({ name, held: true })),
    ...role.missing.map((name) => ({ name, held: false })),
  ];
  const held = role.held.length;
  const total = skills.length;

  return (
    <li
      className="fit-slide rounded-2xl border border-line bg-background p-5 shadow-sm sm:p-6"
      style={{ "--index": index, "--count": ROLES.length } as React.CSSProperties}
    >
      <p className="font-display text-xl font-semibold text-ink">{role.title}</p>
      <p className="text-sm text-ink-soft">{role.company}</p>

      <ul className="mt-5 flex flex-wrap gap-2" aria-label={`Skills ${role.title} asks for`}>
        {skills.map((skill) => (
          <li
            key={skill.name}
            className={
              skill.held
                ? "fit-held rounded-full border border-match bg-match-soft px-3 py-1 font-mono text-xs text-match"
                : "rounded-full border border-dashed border-line px-3 py-1 font-mono text-xs text-ink-soft"
            }
          >
            {skill.name}
            <span className="sr-only">{skill.held ? " — you have this" : " — not yet"}</span>
          </li>
        ))}
      </ul>

      <div className="mt-5 flex items-center gap-3">
        {/* Decorative: the sentence beside it already carries the number, and
            two readings of the same fact is one too many out loud. */}
        <span aria-hidden className="h-1.5 flex-1 overflow-hidden rounded-full bg-mist">
          <span className="block h-full rounded-full bg-mist" style={{ width: "100%" }}>
            <span
              className="fit-fill block h-full rounded-full bg-match"
              style={
                {
                  width: `${(held / total) * 100}%`,
                  "--index": index,
                  "--count": ROLES.length,
                } as React.CSSProperties
              }
            />
          </span>
        </span>
        <p className="shrink-0 text-sm font-medium text-ink">
          {held} of {total} you already have
        </p>
      </div>
    </li>
  );
}

export function FitCard() {
  return (
    <figure>
      <figcaption className="mb-3 font-mono text-[0.7rem] tracking-widest text-ink-soft uppercase">
        What a match looks like
      </figcaption>
      <ul aria-label="Example matches" className="fit-stack">
        {ROLES.map((role, index) => (
          <RoleCard key={role.title} role={role} index={index} />
        ))}
      </ul>
    </figure>
  );
}
