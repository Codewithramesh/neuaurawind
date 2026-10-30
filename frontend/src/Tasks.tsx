import { useEffect, useState } from "react";
import { ListTodo, Check, ArrowRight } from "lucide-react";
import { useResource } from "./useResource";
import { SectionTitle, ErrorNotice, Empty, Badge } from "./ui";
import { api, json, human } from "./api";
import type { Member, Task } from "./types";

export function TasksPage({ onOpen }: { onOpen: (id: string) => void }) {
  const { data, error, refresh } = useResource<Task[]>("/tasks");
  const [filter, setFilter] = useState("open");
  const filtered = data?.filter(
    (t) =>
      filter === "all" ||
      (filter === "open"
        ? ["suggested", "approved"].includes(t.status)
        : t.status === filter),
  );
  return (
    <>
      <SectionTitle
        eyebrow="MAKE EVERY INSIGHT COUNT"
        title="Action center"
        description="Review the suggestions. Decide what happens next."
      />
      <div className="tabs">
        {["open", "suggested", "approved", "completed", "dismissed", "all"].map(
          (s) => (
            <button
              className={s === filter ? "selected" : ""}
              key={s}
              onClick={() => setFilter(s)}
            >
              {human(s)}
            </button>
          ),
        )}
      </div>
      <ErrorNotice message={error} />
      <section className="panel">
        {filtered?.length ? (
          filtered.map((t) => (
            <TaskRow key={t.id} task={t} onRefresh={refresh} onOpen={onOpen} />
          ))
        ) : (
          <Empty
            icon={ListTodo}
            title="Room for your next best action"
            description="Evidence-linked follow-up suggestions appear here after conversations are analyzed. You decide which ones to approve."
          />
        )}
      </section>
    </>
  );
}

export function TaskRow({
  task,
  onRefresh,
  onOpen,
}: {
  task: Task;
  onRefresh: () => Promise<void>;
  onOpen: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [members, setMembers] = useState<Member[]>([]);
  useEffect(() => {
    if (editing)
      void api<Member[]>("/members")
        .then(setMembers)
        .catch(() => {});
  }, [editing]);
  async function update(values: unknown) {
    setBusy(true);
    setError("");
    try {
      await api("/tasks/" + task.id, { method: "PATCH", ...json(values) });
      setEditing(false);
      await onRefresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="task-row">
      <span
        className={`task-check ${task.status === "completed" ? "done" : ""}`}
      >
        <Check size={17} />
      </span>
      <div className="task-body">
        <div className="inline-tags">
          <Badge status={task.status} />
          <span className={`priority ${task.priority}`}>
            {human(task.priority)} priority
          </span>
        </div>
        {editing ? (
          <form
            className="task-form"
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void update({
                description: f.get("description"),
                title: f.get("title"),
                owner_id: f.get("owner_id") || null,
                due_date: f.get("due_date") || null,
                deadline_basis: f.get("deadline_basis"),
                deadline_quote: f.get("deadline_quote") || null,
                priority: f.get("priority"),
              });
            }}
          >
            <label>
              Task title
              <input
                name="title"
                defaultValue={task.title}
                required
                maxLength={180}
              />
            </label>
            <label>
              Description
              <textarea
                name="description"
                required
                maxLength={2000}
                defaultValue={task.description}
              />
            </label>
            <div className="form-row">
              <label>
                Owner
                <select name="owner_id" defaultValue={task.owner_id || ""}>
                  <option value="">Unassigned</option>
                  {members
                    .filter((m) => m.active)
                    .map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.email}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Due date
                <input
                  name="due_date"
                  type="date"
                  defaultValue={task.due_date || ""}
                />
              </label>
              <label>
                Priority
                <select name="priority" defaultValue={task.priority}>
                  {["low", "medium", "high"].map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              Deadline basis
              <select
                name="deadline_basis"
                defaultValue={
                  task.deadline_basis === "reviewer_confirmed_commitment"
                    ? task.deadline_basis
                    : "operator_set"
                }
              >
                <option value="operator_set">Date set by operator</option>
                <option value="reviewer_confirmed_commitment">
                  Reviewer-confirmed spoken commitment
                </option>
              </select>
            </label>
            <label>
              Exact supporting commitment quote (when applicable)
              <textarea
                name="deadline_quote"
                maxLength={3000}
                defaultValue={task.deadline_quote || ""}
              />
            </label>
            <div className="button-row">
              <button className="button primary small" disabled={busy}>
                Save changes
              </button>
              <button
                type="button"
                className="button secondary small"
                onClick={() => setEditing(false)}
              >
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <>
            <h3>{task.description}</h3>
            <p className="muted">
              {task.owner ? `Assigned to ${task.owner}` : "Unassigned"}
              {task.due_date
                ? ` · Due ${task.due_date} (${human(task.deadline_basis)})`
                : " · No deadline established"}
            </p>
            <div className="task-actions">
              <button
                className="text-button"
                onClick={() => onOpen(task.conversation_id)}
              >
                View evidence <ArrowRight size={13} />
              </button>
              <button className="text-button" onClick={() => setEditing(true)}>
                Edit
              </button>
              {task.status === "suggested" && (
                <button
                  className="button small secondary"
                  disabled={busy}
                  onClick={() => void update({ status: "approved" })}
                >
                  <Check size={13} /> Approve
                </button>
              )}
              {task.status === "approved" && (
                <button
                  className="button small secondary"
                  disabled={busy}
                  onClick={() => void update({ status: "completed" })}
                >
                  Complete
                </button>
              )}
              {["completed", "dismissed"].includes(task.status) && (
                <button
                  className="button small secondary"
                  disabled={busy}
                  onClick={() => void update({ status: "approved" })}
                >
                  Reopen
                </button>
              )}
              {["suggested", "approved"].includes(task.status) && (
                <button
                  className="text-button muted"
                  disabled={busy}
                  onClick={() => void update({ status: "dismissed" })}
                >
                  Dismiss
                </button>
              )}
            </div>
          </>
        )}
        <ErrorNotice message={error} />
      </div>
    </article>
  );
}
