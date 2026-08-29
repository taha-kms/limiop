import { serverApiUrl } from "@/lib/config";

/**
 * Job-market aggregates, read on the server.
 *
 * Public data, so no cookie is forwarded and none is needed. Read here rather
 * than in the browser so the page arrives with its numbers already in it.
 */
export interface SkillDemand {
  concept_id: string;
  preferred_label: string;
  jobs: number;
}

export interface LocationCount {
  location: string;
  jobs: number;
}

export interface WorkplaceCount {
  workplace_type: string;
  jobs: number;
}

export interface TrendPoint {
  bucket_start: string;
  jobs: number;
}

export interface MarketInsights {
  skills: SkillDemand[];
  locations: LocationCount[];
  workplaceTypes: WorkplaceCount[];
  trend: TrendPoint[];
  bucket: string;
}

/** The aggregates could not be read. The page says so rather than showing zeroes. */
export class InsightsUnavailableError extends Error {
  constructor() {
    super("The job-market figures could not be read.");
    this.name = "InsightsUnavailableError";
  }
}

async function read<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${serverApiUrl()}/api/v1/analytics${path}`, {
      cache: "no-store",
      headers: { accept: "application/json" },
    });
  } catch {
    throw new InsightsUnavailableError();
  }
  if (!response.ok) throw new InsightsUnavailableError();
  return (await response.json()) as T;
}

export async function getMarketInsights(limit = 10): Promise<MarketInsights> {
  const [skills, locations, trends] = await Promise.all([
    read<{ skills: SkillDemand[] }>(`/skills?limit=${limit}`),
    read<{ locations: LocationCount[]; workplace_types: WorkplaceCount[] }>(
      `/locations?limit=${limit}`,
    ),
    read<{ bucket: string; points: TrendPoint[] }>("/trends?bucket=month"),
  ]);

  return {
    skills: skills.skills,
    locations: locations.locations,
    workplaceTypes: locations.workplace_types,
    trend: trends.points,
    bucket: trends.bucket,
  };
}
