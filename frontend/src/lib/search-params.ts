/**
 * Filters live in the URL, not in component state.
 *
 * That makes a filtered listing shareable, bookmarkable, and indexable, and it
 * survives a refresh and the back button. It also makes the cursor rule hold by
 * construction: a cursor is only meaningful inside the filter set that produced
 * it, and changing a filter produces a different URL with no cursor in it, so
 * there is nothing to remember to reset.
 */

import {
  EMPLOYMENT_TYPES,
  WORKPLACE_TYPES,
  type EmploymentType,
  type JobFilters,
  type WorkplaceType,
} from "@/lib/api/types";

export interface ParseOptions {
  /**
   * The source keys the catalogue ingests.
   *
   * Sources are rows rather than a fixed vocabulary, so the caller supplies
   * what it knows. Anything else is dropped like any other unrecognised value:
   * the listing refuses a source nothing ingests, and a hand-edited URL should
   * narrow oddly at worst rather than become a rejected request. Left out, no
   * source filter is read.
   */
  sources?: readonly string[];
}

/** What Next hands a page for `?a=1&a=2`. */
export type RawSearchParams = Record<string, string | string[] | undefined>;

function values(raw: RawSearchParams, key: string): string[] {
  const value = raw[key];
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

function single(raw: RawSearchParams, key: string): string | undefined {
  const [first] = values(raw, key);
  return first?.trim() ? first.trim() : undefined;
}

function within<T extends string>(allowed: readonly T[], candidates: string[]): T[] {
  // Unknown values are dropped rather than passed on. A hand-edited URL should
  // narrow the listing oddly at worst, never turn into a rejected request.
  const known = new Set<string>(allowed);
  return [...new Set(candidates.filter((value): value is T => known.has(value)))];
}

export function parseFilters(
  raw: RawSearchParams,
  { sources = [] }: ParseOptions = {},
): JobFilters {
  const workplaceTypes: WorkplaceType[] = within(WORKPLACE_TYPES, values(raw, "workplace_type"));
  const employmentTypes: EmploymentType[] = within(
    EMPLOYMENT_TYPES,
    values(raw, "employment_type"),
  );

  const [source] = within(sources, values(raw, "source"));

  return {
    companyId: single(raw, "company_id"),
    location: single(raw, "location"),
    query: single(raw, "q"),
    workplaceTypes,
    employmentTypes,
    source,
  };
}

/** Render filters back into a query string, so a link reproduces the view. */
export function toQueryString(filters: JobFilters): string {
  const params = new URLSearchParams();
  if (filters.query) params.set("q", filters.query);
  if (filters.location) params.set("location", filters.location);
  if (filters.companyId) params.set("company_id", filters.companyId);
  if (filters.source) params.set("source", filters.source);
  for (const value of filters.workplaceTypes ?? []) params.append("workplace_type", value);
  for (const value of filters.employmentTypes ?? []) params.append("employment_type", value);
  return params.toString();
}

export function hasAnyFilter(filters: JobFilters): boolean {
  return toQueryString(filters).length > 0;
}
