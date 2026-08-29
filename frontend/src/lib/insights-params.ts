/**
 * The job-market page's filters, in the URL.
 *
 * Same rule as the listing's: a filtered view is a link. Unknown values are
 * dropped rather than passed on, so a hand-edited URL narrows oddly at worst
 * instead of turning into a rejected request.
 */

import type { RawSearchParams } from "@/lib/search-params";

export const WINDOWS = ["30d", "90d", "12m", "all"] as const;
export type MarketWindow = (typeof WINDOWS)[number];

export const DEFAULT_WINDOW: MarketWindow = "all";

export const WINDOW_LABELS: Record<MarketWindow, string> = {
  "30d": "Last 30 days",
  "90d": "Last 90 days",
  "12m": "Last 12 months",
  all: "All time",
};

/** How far back each window reaches. `all` reaches back to the first posting. */
const WINDOW_DAYS: Record<MarketWindow, number | null> = {
  "30d": 30,
  "90d": 90,
  "12m": 365,
  all: null,
};

const DAY_MS = 24 * 60 * 60 * 1000;

export interface InsightsFilters {
  window: MarketWindow;
  /** A source key the catalogue ingests, or undefined for every source. */
  source?: string;
}

export function parseInsightsFilters(
  raw: RawSearchParams,
  { sources = [] }: { sources?: readonly string[] } = {},
): InsightsFilters {
  const window = first(raw, "window");
  const source = first(raw, "source");
  return {
    window: isWindow(window) ? window : DEFAULT_WINDOW,
    source: source && sources.includes(source) ? source : undefined,
  };
}

/**
 * The start of the window as the API wants it, or undefined for all time.
 *
 * Computed from the request's own clock rather than stored, so "last 30 days"
 * means the same thing on a page rendered now as on one rendered tomorrow.
 */
export function windowStart(window: MarketWindow, now: Date): string | undefined {
  const days = WINDOW_DAYS[window];
  return days === null ? undefined : new Date(now.getTime() - days * DAY_MS).toISOString();
}

/** Render the filters back into a query string, so a link reproduces the view. */
export function toQueryString(filters: InsightsFilters): string {
  const params = new URLSearchParams();
  if (filters.window !== DEFAULT_WINDOW) params.set("window", filters.window);
  if (filters.source) params.set("source", filters.source);
  return params.toString();
}

function first(raw: RawSearchParams, key: string): string | undefined {
  const value = raw[key];
  const found = Array.isArray(value) ? value[0] : value;
  return found?.trim() ? found.trim() : undefined;
}

function isWindow(value: string | undefined): value is MarketWindow {
  return value !== undefined && (WINDOWS as readonly string[]).includes(value);
}
