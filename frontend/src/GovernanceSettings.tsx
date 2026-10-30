import { useState } from "react";
import { api, human, json } from "./api";
import { useResource } from "./useResource";
import { Badge, ErrorNotice } from "./ui";
import type { Member, Settings } from "./types";
export function GovernanceSettings({
  settings,
  onChange,
}: {
  settings: Settings | null;
  onChange: () => Promise<void>;
}) {
  const { data: members, refresh } = useResource<Member[]>("/members", 15000);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [editing, setEditing] = useState<Member | null>(null);
  if (!settings) return null;
  const admin = ["owner", "admin"].includes(settings.role);
  async function work(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh();
      await onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel settings-panel governance-settings">
      <h2>Organization, stores and access</h2>
      <p>
        {settings.organization.name} · {human(settings.role)}. Each account
        belongs to one organization; store selection scopes its authorized data.
      </p>
      <ErrorNotice message={error} />
      {admin && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget;
            const f = new FormData(form);
            void work(async () => {
              await api("/stores", {
                method: "POST",
                ...json({ name: f.get("name") }),
              });
              form.reset();
            });
          }}
        >
          <label>
            New store name
            <input name="name" required maxLength={120} />
          </label>
          <button className="button secondary small" disabled={busy}>
            Add store
          </button>
        </form>
      )}
      <h3>Authorized team</h3>
      {members?.map((m) => (
        <div className="setting-row" key={m.id}>
          <span>
            {m.email} · {human(m.role)} · {m.active ? "Active" : "Disabled"}
          </span>
          {admin && (
            <button className="text-button" onClick={() => setEditing(m)}>
              Edit access
            </button>
          )}
        </div>
      ))}
      {admin && (
        <form
          key={editing?.id || "new"}
          onSubmit={(e) => {
            e.preventDefault();
            const form = e.currentTarget,
              f = new FormData(form);
            const values = {
              role: f.get("role"),
              store_ids: f.getAll("stores"),
              ...(editing
                ? { active: f.get("active") === "on" }
                : { email: f.get("email"), password: f.get("password") }),
            };
            void work(async () => {
              await api(editing ? "/members/" + editing.id : "/members", {
                method: editing ? "PATCH" : "POST",
                ...json(values),
              });
              setEditing(null);
              form.reset();
            });
          }}
        >
          <h3>
            {editing ? "Edit member permissions" : "Provision member account"}
          </h3>
          {!editing && (
            <>
              <label>
                Member email
                <input type="email" name="email" required maxLength={254} />
              </label>
              <label>
                Initial password
                <input
                  type="password"
                  name="password"
                  required
                  minLength={12}
                  maxLength={256}
                  autoComplete="new-password"
                />
              </label>
              <p className="field-help">
                Provision accounts privately over HTTPS. No email invitation
                service is connected.
              </p>
            </>
          )}
          <label>
            Role
            <select name="role" defaultValue={editing?.role || "staff"}>
              <option value="staff">
                Staff — own raw sessions, assigned tasks
              </option>
              <option value="manager">
                Manager — assigned stores and review
              </option>
              <option value="admin">Admin — organization administration</option>
            </select>
          </label>
          <fieldset>
            <legend>Store access</legend>
            {settings.stores.map((s) => (
              <label className="check-label" key={s.id}>
                <input
                  type="checkbox"
                  name="stores"
                  value={s.id}
                  defaultChecked={editing?.store_ids.includes(s.id) || false}
                />
                {s.name}
              </label>
            ))}
          </fieldset>
          {editing && (
            <label className="check-label">
              <input
                type="checkbox"
                name="active"
                defaultChecked={editing.active}
              />
              Account active
            </label>
          )}
          <div className="button-row">
            <button className="button primary small" disabled={busy}>
              {editing ? "Save permissions" : "Create member"}
            </button>
            {editing && (
              <button
                className="button secondary small"
                type="button"
                onClick={() => setEditing(null)}
              >
                Cancel member edit
              </button>
            )}
          </div>
        </form>
      )}
      {admin && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            void work(async () => {
              await api("/settings/retention", {
                method: "PATCH",
                ...json(
                  Object.fromEntries(
                    Object.entries(settings.retention_policy).map(([key]) => [
                      key,
                      Number(f.get(key)),
                    ]),
                  ),
                ),
              });
            });
          }}
        >
          <h3>Organization retention policy</h3>
          <p>
            Expired data is deleted by the worker. Shortening these periods can
            delete existing records; private backups and downloaded exports are
            separate copies.
          </p>
          {Object.entries(settings.retention_policy).map(([key, value]) => (
            <label key={key}>
              {human(key)}
              <input
                type="number"
                name={key}
                min={key === "raw_audio_hours" ? 0 : 1}
                max={key === "raw_audio_hours" ? 720 : 3650}
                defaultValue={value}
                required
              />
            </label>
          ))}
          <button className="button primary small" disabled={busy}>
            Save retention policy
          </button>
        </form>
      )}
      <Badge
        status={admin ? "administration_enabled" : "store_scoped_access"}
      />
    </section>
  );
}
