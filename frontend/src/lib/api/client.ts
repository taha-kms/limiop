/**
 * The one place the frontend talks to the job API.
 *
 * Components call these functions rather than `fetch`, so request shapes stay
 * in one place, stay tested, and cannot drift between a server component and a
 * client one.
 */

import { apiUrl } from "@/lib/config";

import {
  ApiUnreachableError,
  InvalidRequestError,
  JobNotFoundError,
  StaleCursorError,
  UnexpectedResponseError,
} from "./errors";
import {
  DEFAULT_PAGE_SIZE,
  type JobDetail,
  type JobFilters,
  type JobPage,
  type JobSource,
} from "./types";

export interface ListJobsRequest {
  filters?: JobFilters;
  cursor?: string | null;
  limit?: number;
  signal?: AbortSignal;
}

/**
 * Turn filters into query parameters.
 *
 * Absent and empty mean the same thing to a caller and must mean the same thing
 * on the wire: omitted. The listing rejects unknown parameters and rejects an
 * empty string, so serializing an unset filter as `location=` would turn "no
 * filter" into a rejected request.
 */
export function toSearchParams({ filters = {}, cursor, limit }: ListJobsRequest): URLSearchParams {
  const params = new URLSearchParams();

  if (limit !== undefined) {
    params.set("limit", String(limit));
  }
  if (cursor) {
    params.set("cursor", cursor);
  }
  if (filters.companyId) {
    params.set("company_id", filters.companyId);
  }
  if (filters.location?.trim()) {
    params.set("location", filters.location.trim());
  }
  if (filters.query?.trim()) {
    params.set("q", filters.query.trim());
  }
  if (filters.source) {
    params.set("source", filters.source);
  }
  // Repeated rather than comma-joined, because the API reads each vocabulary
  // filter as a list of separate values.
  for (const workplace of filters.workplaceTypes ?? []) {
    params.append("workplace_type", workplace);
  }
  for (const employment of filters.employmentTypes ?? []) {
    params.append("employment_type", employment);
  }

  return params;
}

async function request(path: string, signal?: AbortSignal): Promise<Response> {
  try {
    return await fetch(`${apiUrl()}${path}`, {
      signal,
      headers: { accept: "application/json" },
    });
  } catch (cause) {
    // An aborted request is the caller changing their mind, not a failure, so
    // it is rethrown untouched for them to recognise.
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw cause;
    }
    throw new ApiUnreachableError(cause);
  }
}

async function readJson<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T;
  } catch (cause) {
    throw new ApiUnreachableError(cause);
  }
}

async function rejectionDetail(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  const detail = (body as { detail?: unknown } | null)?.detail;
  return typeof detail === "string" ? detail : `status ${response.status}`;
}

/** Read one batch of jobs, newest first. */
export async function listJobs({
  filters,
  cursor,
  limit = DEFAULT_PAGE_SIZE,
  signal,
}: ListJobsRequest = {}): Promise<JobPage> {
  const params = toSearchParams({ filters, cursor, limit });
  const response = await request(`/jobs?${params.toString()}`, signal);

  if (response.ok) {
    return readJson<JobPage>(response);
  }
  if (response.status === 400) {
    throw new StaleCursorError();
  }
  if (response.status === 422) {
    throw new InvalidRequestError(await rejectionDetail(response));
  }
  throw new UnexpectedResponseError(response.status);
}

/**
 * Read the boards the catalogue ingests.
 *
 * The source filter is catalogue data rather than a fixed vocabulary, so the
 * choices are read from the API rather than held here, where a board added
 * tomorrow would go missing.
 */
export async function listSources(signal?: AbortSignal): Promise<JobSource[]> {
  const response = await request("/jobs/sources", signal);

  if (!response.ok) {
    throw new UnexpectedResponseError(response.status);
  }
  return (await readJson<{ sources: JobSource[] }>(response)).sources;
}

/** Read one job by identifier. */
export async function getJob(jobId: string, signal?: AbortSignal): Promise<JobDetail> {
  const response = await request(`/jobs/${encodeURIComponent(jobId)}`, signal);

  if (response.ok) {
    return readJson<JobDetail>(response);
  }
  if (response.status === 404) {
    throw new JobNotFoundError(jobId);
  }
  if (response.status === 422) {
    throw new InvalidRequestError(await rejectionDetail(response));
  }
  throw new UnexpectedResponseError(response.status);
}
