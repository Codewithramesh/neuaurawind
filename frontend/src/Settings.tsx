import { useState } from "react";
import { Headphones, Sparkles, ShieldCheck, Smartphone } from "lucide-react";
import { useResource } from "./useResource";
import { SectionTitle, ErrorNotice, Badge } from "./ui";
import { api, json, human } from "./api";
import type { Settings } from "./types";

export function SettingsPage({ onChange }: { onChange: () => Promise<void> }) {
  const { data, error, refresh } = useResource<Settings>("/settings", 15000);
  const [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  if (!data) return <ErrorNotice message={error} />;
  return (
    <>
      <SectionTitle
        eyebrow="YOUR WORKSPACE, YOUR WAY"
        title="Settings"
        description="Business context, processing engines, and privacy."
      />
      <ErrorNotice message={error || message} />
      <div className="settings-grid">
        <form
          className="panel settings-panel"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setMessage("");
            const f = new FormData(e.currentTarget);
            try {
              await api("/settings/profile", {
                method: "PATCH",
                ...json({
                  name: f.get("name"),
                  industry: f.get("industry"),
                  categories: String(f.get("categories"))
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                }),
              });
              await refresh();
              await onChange();
            } catch (e) {
              setMessage((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <h2>Business profile</h2>
          <p>Give your intelligence the right context.</p>
          <label>
            Business name
            <input
              name="name"
              defaultValue={data.organization.name}
              required
              maxLength={120}
            />
          </label>
          <label>
            Industry
            <select name="industry" defaultValue={data.organization.industry}>
              {["restaurant", "retail", "hospitality", "service"].map((i) => (
                <option key={i} value={i}>
                  {human(i)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Additional extraction categories
            <input
              name="categories"
              defaultValue={data.organization.categories.join(", ")}
              placeholder="loyalty_request, accessibility"
            />
          </label>
          <p className="field-help">
            Comma-separated lowercase names. Built-in feedback, complaint,
            preference, request, sales, and operational categories are always
            available.
          </p>
          <button className="button primary small" disabled={busy || !["owner","admin"].includes(data.role)}>
            Save profile
          </button>
        </form>
        <section className="panel settings-panel">
          <h2>Intelligence engines</h2>
          <p>Both engines must be ready for full analysis.</p>
          <div className="engine">
            <span className="engine-icon">
              <Headphones size={21} />
            </span>
            <div>
              <strong>Local speech-to-text</strong>
              <small>{data.transcription.model} · CPU</small>
            </div>
            <Badge
              status={data.transcription.ready ? "ready" : "setup_required"}
            />
          </div>
          {!data.transcription.ready && (
            <p>Follow the local model setup steps in the setup guide. On Windows, run Download models.cmd in the project folder.</p>
          )}
          <div className="engine">
            <span className="engine-icon">
              <Sparkles size={21} />
            </span>
            <div>
              <strong>{human(data.extraction.provider)} extraction</strong>
              <small>{data.extraction.model}</small>
            </div>
            <Badge
              status={data.extraction.ready ? "ready" : "setup_required"}
            />
          </div>
          <p className="field-help">
            For local AI, install Ollama, run <code>ollama serve</code>, then{" "}
            <code>ollama pull {data.extraction.model}</code>. Model downloads
            can require several GB. Configure provider and model in{" "}
            <code>.env</code>, then restart. See{" "}
            <code>docs/LOCAL_SETUP.md</code>.
          </p>
          <span className="privacy-label">
            <ShieldCheck size={15} />
            {data.extraction.cloud_enabled
              ? "Cloud processing explicitly enabled"
              : "Remote AI disabled · transcripts stay local"}
          </span>
        </section>
        <section className="panel settings-panel">
          <h2>Privacy & retention</h2>
          <div className="setting-row">
            <span>Conversation retention</span>
            <strong>{data.retention_days} days</strong>
          </div>
          <div className="setting-row">
            <span>Keep audio after transcription</span>
            <strong>{data.retain_audio ? "Enabled" : "Disabled"}</strong>
          </div>
          <div className="setting-row">
            <span>Recording limit</span>
            <strong>{data.max_duration_seconds / 60} minutes</strong>
          </div>
          <div className="setting-row">
            <span>Upload limit</span>
            <strong>{data.max_upload_mb} MB</strong>
          </div>
          <p className="field-help">
            Audio is held while transcription is pending or failed so you can
            retry. When retention is disabled, it is removed after a transcript
            is saved. Deleting a conversation removes its transcript, insights,
            tasks, and audio. Change retention in <code>.env</code>.
          </p>
        </section>
        <section className="panel settings-panel phone-guide">
          <Smartphone size={25} />
          <h2>Take a test on your phone</h2>
          <p>
            Microphone capture needs trusted HTTPS. Use the private Tailscale
            Serve setup in <code>docs/PHONE_TESTING.md</code> to reach this computer
            securely.
          </p>
          <p className="field-help">
            Mobile layout support does not verify a phone’s microphone. Test
            recording on your actual iPhone or Android browser.
          </p>
        </section>
      </div>
    </>
  );
}
