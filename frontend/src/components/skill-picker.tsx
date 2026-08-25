"use client";

import { type FormEvent, useEffect, useState } from "react";

import {
  addCandidateProfileSkill,
  type CandidateProfileSkill,
  listCandidateProfileSkills,
  NotSignedInError,
  ProfileUnavailableError,
  removeCandidateProfileSkill,
  searchSkillConcepts,
  SkillSelectionRejectedError,
  type SkillConceptSearchResult,
} from "@/lib/api/profile";

function skillProblem(cause: unknown, fallback: string): string {
  if (
    cause instanceof NotSignedInError ||
    cause instanceof SkillSelectionRejectedError ||
    cause instanceof ProfileUnavailableError
  ) {
    return cause.message;
  }
  return fallback;
}

function byLabel(left: SkillConceptSearchResult, right: SkillConceptSearchResult): number {
  return left.preferred_label.localeCompare(right.preferred_label);
}

export function SkillPicker() {
  const [skills, setSkills] = useState<CandidateProfileSkill[]>([]);
  const [results, setResults] = useState<SkillConceptSearchResult[] | null>(null);
  const [searchedFor, setSearchedFor] = useState("");
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [changing, setChanging] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    listCandidateProfileSkills(controller.signal)
      .then((saved) => {
        if (active) setSkills(saved);
      })
      .catch((cause: unknown) => {
        if (active && !(cause instanceof DOMException && cause.name === "AbortError")) {
          setProblem(skillProblem(cause, "Your saved skills could not be loaded."));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const query = String(form.get("skill_query") ?? "").trim();
    if (!query) return;

    setProblem(null);
    setSearching(true);
    setSearchedFor(query);
    try {
      setResults(await searchSkillConcepts(query));
    } catch (cause) {
      setResults(null);
      setProblem(skillProblem(cause, "Canonical skills could not be searched."));
    } finally {
      setSearching(false);
    }
  }

  async function add(concept: SkillConceptSearchResult) {
    setProblem(null);
    setChanging(concept.concept_id);
    try {
      const stored = await addCandidateProfileSkill(concept.concept_id);
      setSkills((current) =>
        [...current.filter((skill) => skill.concept_id !== stored.concept_id), stored].sort(
          byLabel,
        ),
      );
    } catch (cause) {
      setProblem(skillProblem(cause, "That skill could not be added."));
    } finally {
      setChanging(null);
    }
  }

  async function remove(skill: CandidateProfileSkill) {
    setProblem(null);
    setChanging(skill.concept_id);
    try {
      await removeCandidateProfileSkill(skill.concept_id);
      setSkills((current) => current.filter((item) => item.concept_id !== skill.concept_id));
    } catch (cause) {
      setProblem(skillProblem(cause, "That skill could not be removed."));
    } finally {
      setChanging(null);
    }
  }

  const selectedIds = new Set(skills.map((skill) => skill.concept_id));

  return (
    <section className="flex flex-col gap-4" aria-labelledby="skills-heading">
      <div className="flex flex-col gap-1">
        <h3 id="skills-heading" className="text-lg font-semibold">
          Your skills
        </h3>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Search the canonical vocabulary and choose the concepts that describe you. Skills improve
          matching readiness but do not change profile completeness.
        </p>
      </div>

      {problem ? (
        <p
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
        >
          {problem}
        </p>
      ) : null}

      {loading ? <p role="status">Loading your saved skills…</p> : null}

      {!loading && skills.length > 0 ? (
        <ul className="flex flex-wrap gap-2" aria-label="Selected skills">
          {skills.map((skill) => (
            <li
              key={skill.concept_id}
              className="flex items-center gap-2 rounded-full border border-slate-300 px-3 py-1 text-sm dark:border-slate-700"
            >
              <span>{skill.preferred_label}</span>
              <button
                type="button"
                className="text-red-700 underline dark:text-red-400"
                disabled={changing !== null}
                onClick={() => void remove(skill)}
                aria-label={`Remove ${skill.preferred_label}`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {!loading && skills.length === 0 ? (
        <p className="text-sm text-slate-600 dark:text-slate-400">No skills selected yet.</p>
      ) : null}

      <form className="flex flex-col gap-2 sm:flex-row" onSubmit={search}>
        <label htmlFor="skill-query" className="sr-only">
          Search canonical skills
        </label>
        <input
          id="skill-query"
          name="skill_query"
          required
          maxLength={255}
          placeholder="Search canonical skills"
          className="min-w-0 flex-1 rounded-md border border-slate-300 bg-transparent px-3 py-2 dark:border-slate-700"
        />
        <button className="primary-button" disabled={searching}>
          {searching ? "Searching…" : "Search"}
        </button>
      </form>

      {results?.length === 0 ? (
        <p role="status" className="text-sm text-slate-700 dark:text-slate-300">
          No canonical skills match “{searchedFor}”. The typed text cannot be saved.
        </p>
      ) : null}

      {results && results.length > 0 ? (
        <ul className="flex flex-col gap-2" aria-label="Skill search results">
          {results.map((concept) => {
            const selected = selectedIds.has(concept.concept_id);
            return (
              <li
                key={concept.concept_id}
                className="flex items-center justify-between gap-3 rounded-md border border-slate-200 p-3 dark:border-slate-800"
              >
                <span>{concept.preferred_label}</span>
                <button
                  type="button"
                  className="text-blue-700 underline disabled:text-slate-500 dark:text-blue-400"
                  disabled={selected || changing !== null}
                  onClick={() => void add(concept)}
                  aria-label={
                    selected
                      ? `${concept.preferred_label} already added`
                      : `Add ${concept.preferred_label}`
                  }
                >
                  {selected ? "Added" : "Add"}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
