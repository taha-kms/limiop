import type { SourceAttribution } from "@/lib/api/types";

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
 * Per-source rendering overrides, keyed by `source.key`.
 *
 * Most sources need nothing here and fall through to `DefaultSource`. A
 * source whose terms mandate specific wording adds one entry.
 */
const SOURCE_LABELS: Record<string, (props: { source: SourceAttribution }) => React.ReactElement> =
  {};

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
