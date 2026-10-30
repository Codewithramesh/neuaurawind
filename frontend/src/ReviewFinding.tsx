import { useState } from "react";
import { api, human, json } from "./api";
import { Badge, ErrorNotice, InsightCard } from "./ui";
import type { Insight } from "./types";
export function ReviewFinding({
  finding,
  onRefresh,
  canReview,
}: {
  finding: Insight;
  onRefresh: () => Promise<void>;
  canReview: boolean;
}) {
  const [editing, setEditing] = useState(false),
    [checked, setChecked] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function save(values: unknown) {
    setBusy(true);
    setError("");
    try {
      await api(`/insights/${finding.id}/review`, {
        method: "PATCH",
        ...json(values),
      });
      setEditing(false);
      setChecked(false);
      await onRefresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="finding-review">
      <Badge status={finding.review_status} />
      <InsightCard insight={finding} onOpen={() => {}} />
      <p className="field-help">
        Evidence: {human(finding.evidence_status)}. Model confidence is an
        uncalibrated estimate, not a measured probability of correctness.
      </p>
      {canReview && (
        <>
          {editing ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                void save({
                  ...Object.fromEntries(f),
                  review_status: "corrected",
                });
              }}
            >
              {[
                ["title", "Title"],
                ["description", "Description"],
                ["category", "Category"],
                ["topic", "Topic"],
                ["uncertainty", "Uncertainty and sample limits"],
                ["impact", "Potential business impact"],
                ["recommendation", "Recommended investigation or action"],
                ["success_metric", "Success metric"],
                ["priority_rationale", "Priority rationale"],
              ].map(([key, label]) => (
                <label key={key}>
                  {label}
                  <textarea
                    name={key}
                    maxLength={
                      key === "title"
                        ? 180
                        : key === "category"
                          ? 80
                          : key === "topic"
                            ? 120
                            : key === "uncertainty" ||
                                key === "success_metric" ||
                                key === "priority_rationale"
                              ? 1000
                              : 2000
                    }
                    defaultValue={String(finding[key as keyof Insight] || "")}
                  />
                </label>
              ))}
              <label>
                Fact or inference
                <select name="basis" defaultValue={finding.basis}>
                  <option value="stated">Explicitly stated</option>
                  <option value="inferred">Inference</option>
                </select>
              </label>
              <label>
                Sentiment
                <select name="sentiment" defaultValue={finding.sentiment}>
                  {["positive", "negative", "neutral"].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <div className="button-row">
                <button className="button primary small" disabled={busy}>
                  Save correction
                </button>
                <button
                  type="button"
                  className="button secondary small"
                  onClick={() => setEditing(false)}
                >
                  Cancel edit
                </button>
              </div>
            </form>
          ) : (
            <button className="text-button" onClick={() => setEditing(true)}>
              Correct finding and recommendation
            </button>
          )}
          <label className="consent-box">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
            />
            <span>
              I checked the finding against its evidence, uncertainty and
              identifying information, and approve it for this store’s shared
              intelligence.
            </span>
          </label>
          <div className="button-row">
            <button
              className="button primary small"
              disabled={busy || !checked}
              onClick={() =>
                void save({ review_status: "approved", sharing_checked: true })
              }
            >
              Approve finding
            </button>
            <button
              className="button secondary small"
              disabled={busy}
              onClick={() => void save({ review_status: "rejected" })}
            >
              Reject finding
            </button>
            <button
              className="text-button"
              disabled={busy}
              onClick={() => void save({ review_status: "restricted" })}
            >
              Restrict finding
            </button>
          </div>
        </>
      )}
      <ErrorNotice message={error} />
    </section>
  );
}
