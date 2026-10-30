import { useState } from "react";
import { Mic, Plus, Search, AudioLines, Cpu, ChevronRight } from "lucide-react";
import { useResource } from "./useResource";
import { SectionTitle, ErrorNotice, Empty, Badge } from "./ui";
import { human, dateLabel, durationLabel } from "./api";
import type { Conversation } from "./types";

export function ConversationsPage({
  onRecord,
  onOpen,
}: {
  onRecord: () => void;
  onOpen: (id: string) => void;
}) {
  const [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [offset, setOffset] = useState(0);
  const params = new URLSearchParams({
    q,
    status,
    date_from: from,
    date_to: to,
    limit: "50",
    offset: String(offset),
  });
  for (const key of ["status", "date_from", "date_to"])
    if (!params.get(key)) params.delete(key);
  const { data, error } = useResource<Conversation[]>(
    "/conversations?" + params,
  );
  return (
    <>
      <SectionTitle
        eyebrow="THE WHOLE STORY"
        title="Conversations"
        description="Every voice. Every detail. All in one place."
        action={
          <button className="button primary" onClick={onRecord}>
            <Plus size={17} /> New conversation
          </button>
        }
      />
      <div className="filters">
        <div className="search-field">
          <Search size={17} />
          <input
            aria-label="Search conversations"
            placeholder="Search titles and transcripts…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
        </div>
        <select
          aria-label="Processing status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All statuses</option>
          {[
            "needs_review",
            "approved",
            "awaiting_consent",
            "ready",
            "recording",
            "paused",
            "interrupted",
            "finalizing",
            "complete",
            "processing",
            "queued",
            "failed",
            "awaiting_audio",
            "restricted",
            "cancelled",
          ].map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <label className="date-filter">
          From
          <input
            type="date"
            value={from}
            onChange={(e) => {
              setFrom(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label className="date-filter">
          To
          <input
            type="date"
            value={to}
            onChange={(e) => {
              setTo(e.target.value);
              setOffset(0);
            }}
          />
        </label>
      </div>
      <ErrorNotice message={error} />
      <section className="panel">
        {data?.length ? (
          <div className="table-wrap">
            <table className="conversation-table">
              <thead>
                <tr>
                  <th>Conversation</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Duration</th>
                  <th>Date</th>
                  <th>
                    <span className="sr-only">Open</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((c) => (
                  <tr key={c.id} onClick={() => onOpen(c.id)}>
                    <td>
                      <button
                        className="table-title"
                        onClick={(e) => {
                          e.stopPropagation();
                          onOpen(c.id);
                        }}
                      >
                        <span className="table-icon">
                          <AudioLines size={18} />
                        </span>
                        <span>
                          <strong>{c.title}</strong>
                          <small>
                            {c.summary ||
                              c.job?.error_message ||
                              "Waiting for processing"}
                          </small>
                        </span>
                      </button>
                    </td>
                    <td>
                      <span className="source-tag">
                        {c.source_type === "device" ? (
                          <Cpu size={14} />
                        ) : (
                          <Mic size={14} />
                        )}{" "}
                        {human(c.source_type)}
                      </span>
                    </td>
                    <td>
                      <Badge status={c.session_state} />
                    </td>
                    <td>{c.duration ? durationLabel(c.duration) : "—"}</td>
                    <td className="nowrap">{dateLabel(c.created_at)}</td>
                    <td>
                      <ChevronRight size={16} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={
              q || status || from || to
                ? "No matching conversations"
                : "Your story starts with a conversation"
            }
            description={
              q || status || from || to
                ? "Try adjusting the search or filters."
                : "Record or upload an authorized conversation to build your business knowledge."
            }
            action={
              <button className="button secondary" onClick={onRecord}>
                <Mic size={16} /> Add a conversation
              </button>
            }
          />
        )}
        <div className="pagination">
          <button
            className="button small secondary"
            disabled={!offset}
            onClick={() => setOffset((x) => Math.max(0, x - 50))}
          >
            Previous
          </button>
          <span className="muted">Page {offset / 50 + 1}</span>
          <button
            className="button small secondary"
            disabled={!data || data.length < 50}
            onClick={() => setOffset((x) => x + 50)}
          >
            Next
          </button>
        </div>
      </section>
    </>
  );
}
