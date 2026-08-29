/**
 * A ranked list of counts, drawn as bars.
 *
 * Bars rather than a chart library: the shape is one number per row, every row
 * is labelled and readable as text, and a screen reader gets the figure rather
 * than an SVG. The widths are relative to the largest row, so a bar says how
 * this row compares to the top of its own list and nothing more.
 */
export interface Counted {
  readonly key: string;
  readonly label: string;
  readonly jobs: number;
}

export function CountBars({ rows, unit }: { rows: Counted[]; unit: string }) {
  if (rows.length === 0) {
    return <p className="text-sm text-slate-600 dark:text-slate-400">Nothing to show yet.</p>;
  }
  const largest = Math.max(...rows.map((row) => row.jobs));

  return (
    <ul className="flex flex-col gap-2">
      {rows.map((row) => (
        <li key={row.key} className="flex items-center gap-3">
          <span className="w-40 shrink-0 truncate text-sm" title={row.label}>
            {row.label}
          </span>
          <span
            aria-hidden
            className="h-2 rounded-full bg-slate-900 dark:bg-slate-100"
            style={{ width: `${Math.max(2, (row.jobs / largest) * 100)}%` }}
          />
          <span className="shrink-0 text-sm tabular-nums text-slate-600 dark:text-slate-400">
            {row.jobs} {unit}
          </span>
        </li>
      ))}
    </ul>
  );
}
