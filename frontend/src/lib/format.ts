/** Presentation helpers shared by the job views. */

const WORKPLACE_LABELS: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  onsite: "On site",
  // Cards drop an unstated value rather than badging it; the filter form still
  // needs a name for the option.
  unspecified: "Not stated",
};

const EMPLOYMENT_LABELS: Record<string, string> = {
  "full-time": "Full time",
  "part-time": "Part time",
  contract: "Contract",
  internship: "Internship",
  temporary: "Temporary",
  unspecified: "Not stated",
};

export function workplaceLabel(value: string): string {
  return WORKPLACE_LABELS[value] ?? value;
}

export function employmentLabel(value: string): string {
  return EMPLOYMENT_LABELS[value] ?? value;
}

/**
 * A publication date a reader can scan.
 *
 * Fixed locale and time zone on purpose. The date is rendered on the server and
 * hydrated in the browser, and letting each pick its own would produce two
 * different strings for the same job and a hydration mismatch.
 */
export function publishedLabel(value: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}
