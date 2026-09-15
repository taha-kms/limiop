import type { SourceAttribution } from "@/lib/api/types";

const ADZUNA_HOME = "https://www.adzuna.co.uk";

/**
 * A generic source: "via" plus a link to the original posting.
 *
 * `rel` carries only `noopener`, deliberately without `nofollow`: unlike the
 * employer application link, several sources (RemoteOK, Adzuna) require this
 * link to be followed as a condition of use.
 */
function DefaultSource({ source }: { source: SourceAttribution }) {
  return (
    <>
      via{" "}
      <a href={source.url} rel="noopener" target="_blank">
        {source.display_name}
      </a>
    </>
  );
}

/**
 * Adzuna's terms (checked 2026-09-15) require: "every displayed advert must
 * carry 'Jobs by Adzuna' with the word linked and the logo shown."
 *
 * The official wordmark asset is not yet in the repo. `/sources/adzuna.svg`
 * is a placeholder rendering "Adzuna" as plain text in the brand colour
 * (#24a0ed); it must be replaced with Adzuna's official logo file before the
 * Adzuna source is enabled in production, per the terms' trademark clause.
 */
function AdzunaSource({ source }: { source: SourceAttribution }) {
  return (
    <>
      <a href={ADZUNA_HOME} rel="noopener" target="_blank">
        Jobs
      </a>{" "}
      by{" "}
      <a href={source.url} rel="noopener" target="_blank">
        <img src="/sources/adzuna.svg" alt="Adzuna" height={16} />
      </a>
    </>
  );
}

/**
 * Per-source rendering overrides, keyed by `source.key`.
 *
 * Most sources need nothing here and fall through to `DefaultSource`. A
 * source whose terms mandate specific wording, like Adzuna, adds one entry.
 */
const SOURCE_LABELS: Record<string, (props: { source: SourceAttribution }) => React.ReactElement> =
  {
    adzuna: AdzunaSource,
  };

/** Where a job was found. Renders nothing when no source is recorded. */
export function SourceLine({ sources }: { sources: SourceAttribution[] }) {
  if (sources.length === 0) return null;

  return (
    <p className="text-xs text-slate-500 dark:text-slate-500">
      {sources.map((source, index) => {
        const Source = SOURCE_LABELS[source.key] ?? DefaultSource;
        return (
          <span key={source.key}>
            {index > 0 ? " · " : ""}
            <Source source={source} />
          </span>
        );
      })}
    </p>
  );
}
