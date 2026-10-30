import { useState } from "react";
import { Plus, Cpu, ShieldCheck } from "lucide-react";
import { useResource } from "./useResource";
import { SectionTitle, ErrorNotice, Empty, Badge } from "./ui";
import { api, json, dateLabel, getStoreScope } from "./api";
import type { Device } from "./types";

export function DevicesPage({ canAdmin = false }: { canAdmin?: boolean }) {
  const { data, error, refresh } = useResource<Device[]>("/devices");
  const [add, setAdd] = useState(false),
    [credential, setCredential] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <>
      <SectionTitle
        eyebrow="ONE PLATFORM. EVERY SOURCE."
        title="Capture devices"
        description="Registered identities and observed HTTP activity. Physical wearable transport is unverified."
        action={
          canAdmin && (
            <button className="button primary" onClick={() => setAdd(true)}>
              <Plus size={17} /> Register device
            </button>
          )
        }
      />
      <ErrorNotice message={error || message} />
      {credential && (
        <div className="credential-box">
          <h3>Save this device credential</h3>
          <p>Shown once. Store it securely on the authorized device.</p>
          <code>{credential}</code>
          <button
            className="button small secondary"
            onClick={() => setCredential("")}
          >
            I’ve saved it
          </button>
        </div>
      )}
      {add && (
        <form
          className="panel device-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setMessage("");
            const f = new FormData(e.currentTarget);
            try {
              const result = await api<Device & { credential: string }>(
                "/devices/register",
                {
                  method: "POST",
                  ...json({
                    name: f.get("name"),
                    model: f.get("model"),
                    device_type: "wearable",
                    simulated: f.get("simulated") === "on",
                    store_id: getStoreScope() || null,
                  }),
                },
              );
              setCredential(result.credential);
              setAdd(false);
              await refresh();
            } catch (e) {
              setMessage((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="form-row">
            <label>
              Device name
              <input
                name="name"
                required
                maxLength={100}
                placeholder="Store wearable 01"
              />
            </label>
            <label>
              Hardware model
              <input
                name="model"
                required
                maxLength={100}
                placeholder="Prototype or simulator"
              />
            </label>
          </div>
          <label className="checkbox-label">
            <input type="checkbox" name="simulated" /> This is a development
            simulator
          </label>
          <div className="button-row">
            <button className="button primary small" disabled={busy}>
              Register securely
            </button>
            <button
              type="button"
              className="button secondary small"
              onClick={() => setAdd(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
      <div className="device-grid">
        {data?.map((d) => (
          <article className="panel device-card" key={d.id}>
            <div className="device-card-top">
              <span className="empty-icon">
                <Cpu size={24} />
              </span>
              <Badge status={d.connection} />
            </div>
            <h3>{d.name}</h3>
            <p>
              {d.model}
              {d.firmware ? ` · ${d.firmware}` : ""}
            </p>
            {d.simulated && (
              <span className="subtle-tag">
                SIMULATED · software controls, no connected hardware
              </span>
            )}
            <dl>
              <div>
                <dt>Last seen</dt>
                <dd>
                  {d.last_seen
                    ? dateLabel(d.last_seen)
                    : "No HTTP activity reported"}
                </dd>
              </div>
              <div>
                <dt>Battery</dt>
                <dd>
                  {d.battery === null
                    ? "Not reported"
                    : `${d.battery}%${d.simulated ? " (simulated)" : ""}`}
                </dd>
              </div>
              <div>
                <dt>Device ID</dt>
                <dd className="device-id">{d.id}</dd>
              </div>
            </dl>
            <p className="field-help">
              Physical recording indicator: unverified.{" "}
              {d.simulated
                ? "Only software controls and real file transfer are supported."
                : "No hardware command transport is integrated."}
            </p>
            {canAdmin && d.status === "authorized" && (
              <button
                className="text-button danger"
                onClick={async () => {
                  if (
                    !confirm(
                      "Revoke this device? Its credential will stop working immediately.",
                    )
                  )
                    return;
                  try {
                    await api(`/devices/${d.id}/revoke`, { method: "POST" });
                    await refresh();
                  } catch (e) {
                    setMessage((e as Error).message);
                  }
                }}
              >
                Revoke authorization
              </button>
            )}
          </article>
        ))}
      </div>
      {!data?.length && (
        <section className="panel">
          <Empty
            icon={Cpu}
            title="Ready for what comes next"
            description="Register a simulator today or a wearable tomorrow. Authenticated device audio follows the same processing path as browser recordings."
            action={
              <span className="subtle-tag">
                HTTP uploads · checksums · resumable chunks
              </span>
            }
          />
        </section>
      )}
      <div className="info-strip">
        <ShieldCheck size={20} />
        <p>
          Every device has its own revocable credential. No shared firmware
          secret. See <code>docs/HARDWARE_INTEGRATION.md</code> to connect a
          prototype.
        </p>
      </div>
    </>
  );
}
