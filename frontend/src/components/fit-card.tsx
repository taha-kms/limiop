/**
 * What a match looks like, shown rather than described.
 *
 * The skills are an illustration and the card says so. Showing invented
 * numbers as though they were somebody's own results would be a lie the
 * moment the page loaded, and the mechanic is the thing worth explaining
 * anyway: skills you have are lit, the rest stay dim.
 */

const EXAMPLE = {
  title: "Remote Data Engineer",
  company: "Meridian Software",
  location: "Berlin",
  skills: [
    { name: "Python", held: true },
    { name: "SQL", held: true },
    { name: "Airflow", held: true },
    { name: "dbt", held: false },
    { name: "Kubernetes", held: false },
  ],
};

export function FitCard() {
  const held = EXAMPLE.skills.filter((skill) => skill.held).length;
  const total = EXAMPLE.skills.length;

  return (
    <figure className="rounded-2xl border border-line bg-background p-5 shadow-sm sm:p-6">
      <figcaption className="font-mono text-[0.7rem] tracking-widest text-ink-soft uppercase">
        What a match looks like
      </figcaption>

      <p className="mt-3 font-display text-xl font-semibold text-ink">{EXAMPLE.title}</p>
      <p className="text-sm text-ink-soft">
        {EXAMPLE.company} · {EXAMPLE.location}
      </p>

      <ul className="mt-5 flex flex-wrap gap-2" aria-label="Skills this job asks for">
        {EXAMPLE.skills.map((skill) => (
          <li
            key={skill.name}
            className={
              skill.held
                ? "rounded-full border border-match bg-match-soft px-3 py-1 font-mono text-xs text-match"
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
          <span
            className="block h-full rounded-full bg-match"
            style={{ width: `${(held / total) * 100}%` }}
          />
        </span>
        <p className="text-sm font-medium text-ink">
          {held} of {total} you already have
        </p>
      </div>
    </figure>
  );
}
