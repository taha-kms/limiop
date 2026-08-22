/**
 * The shapes the job API serves.
 *
 * Written by hand rather than generated. Generating them needs either a CI job
 * that boots the backend or a committed schema snapshot whose drift check makes
 * backend tests read frontend files, and both cost more than the forty lines
 * they would replace.
 *
 * What makes that defensible is that drift fails loudly on the other side. The
 * backend asserts the exact field set, the exact nullable fields, and the exact
 * vocabulary members of every schema below, against literals rather than
 * against the enums it generates them from. Changing any of this without
 * changing these types breaks a backend test.
 */

export const WORKPLACE_TYPES = ["remote", "hybrid", "onsite", "unspecified"] as const;
export type WorkplaceType = (typeof WORKPLACE_TYPES)[number];

export const EMPLOYMENT_TYPES = [
  "full-time",
  "part-time",
  "contract",
  "internship",
  "temporary",
  "unspecified",
] as const;
export type EmploymentType = (typeof EMPLOYMENT_TYPES)[number];

export const JOB_STATUSES = ["active", "expired", "removed"] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

export interface Company {
  id: string;
  display_name: string;
  website_url: string | null;
}

export interface SourceAttribution {
  key: string;
  display_name: string;
  url: string;
}

/** A job as it appears in a listing. Carries an excerpt, never the description. */
export interface JobSummary {
  id: string;
  company: Company;
  title: string;
  excerpt: string;
  location: string | null;
  workplace_type: WorkplaceType;
  employment_type: EmploymentType;
  application_url: string;
  published_at: string | null;
}

/** One job, opened. Carries the whole description and where it was found. */
export interface JobDetail {
  id: string;
  company: Company;
  title: string;
  description: string;
  location: string | null;
  workplace_type: WorkplaceType;
  employment_type: EmploymentType;
  application_url: string;
  published_at: string | null;
  expires_at: string | null;
  status: JobStatus;
  sources: SourceAttribution[];
}

export interface JobPage {
  items: JobSummary[];
  /** Pass back as `cursor` for the next batch. Null when the listing ends. */
  next_cursor: string | null;
}

/** Everything the listing accepts. Every field optional, all combinable. */
export interface JobFilters {
  companyId?: string;
  location?: string;
  workplaceTypes?: readonly WorkplaceType[];
  employmentTypes?: readonly EmploymentType[];
  query?: string;
}

export const DEFAULT_PAGE_SIZE = 20;
export const MAX_PAGE_SIZE = 100;
