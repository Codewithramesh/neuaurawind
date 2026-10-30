import { useState } from "react";
import { ArrowRight, Loader2, ShieldCheck } from "lucide-react";
import { Brand, ErrorNotice } from "./ui";
import { api, json } from "./api";

export function Auth({
  bootstrap,
  notice,
  onReady,
}: {
  bootstrap: boolean;
  notice: string;
  onReady: () => Promise<void>;
}) {
  const [error, setError] = useState(notice),
    [busy, setBusy] = useState(false),
    [created, setCreated] = useState(false);
  const setup = bootstrap && !created;
  return (
    <div className="auth-page">
      <div className="auth-story">
        <Brand />
        <div>
          <span className="eyebrow">EVERY CONVERSATION COUNTS</span>
          <h1>
            Listen closer.
            <br />
            See the bigger
            <br />
            <em>picture.</em>
          </h1>
          <p>
            Turn the conversations happening in your business into your next
            best decision.
          </p>
          <div className="auth-signal">
            {Array.from({ length: 38 }, (_, i) => (
              <span
                key={i}
                style={{ height: `${12 + ((i * 31 + i * i * 7) % 72)}px` }}
              />
            ))}
          </div>
        </div>
        <span className="auth-caption">
          <ShieldCheck size={16} /> Local first. Evidence connected. Wearable
          transport pending.
        </span>
      </div>
      <div className="auth-form-area">
        <form
          className="auth-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            const f = new FormData(e.currentTarget);
            try {
              if (setup) {
                await api("/bootstrap", {
                  method: "POST",
                  headers: { "X-Setup-Token": String(f.get("token")) },
                  ...json({
                    name: f.get("name"),
                    store_name: f.get("store_name"),
                    industry: f.get("industry"),
                    email: f.get("email"),
                    password: f.get("password"),
                  }),
                });
                setCreated(true);
              } else {
                await api("/auth/login", {
                  method: "POST",
                  ...json({
                    email: f.get("email"),
                    password: f.get("password"),
                  }),
                });
                await onReady();
              }
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <span className="eyebrow">
            {setup ? "LET’S GET YOU STARTED" : "YOUR BUSINESS, IN FOCUS"}
          </span>
          <h2>{setup ? "Create your workspace" : "Welcome back"}</h2>
          <p>
            {setup
              ? "A private home for your conversation intelligence."
              : "Sign in to see what your conversations are telling you."}
          </p>
          {created && (
            <div className="success-notice">
              Workspace created. Sign in with your new credentials.
            </div>
          )}
          {setup && (
            <>
              <label>
                Setup token
                <input
                  name="token"
                  type="password"
                  required
                  autoComplete="off"
                  placeholder="From local-data/setup-token"
                />
              </label>
              <p className="field-help">
                On your Desktop, open <strong>NEUAURA B2B</strong> and
                double-click <strong>Copy setup token</strong>, then
                paste here. This one-time token protects workspace creation.
              </p>
              <label>
                Business name
                <input
                  name="name"
                  required
                  maxLength={120}
                  placeholder="Your business"
                />
              </label>
              <label>
                First store name
                <input
                  name="store_name"
                  required
                  maxLength={120}
                  placeholder="e.g. Main café"
                />
              </label>
              <label>
                Industry
                <select name="industry">
                  <option value="restaurant">Restaurants & cafés</option>
                  <option value="retail">Retail & clothing</option>
                  <option value="hospitality">Hospitality</option>
                  <option value="service">Customer services</option>
                </select>
              </label>
            </>
          )}
          <label>
            Email
            <input
              name="email"
              type="email"
              required
              autoComplete="username"
              placeholder="you@yourbusiness.com"
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              required
              minLength={setup ? 12 : 1}
              maxLength={256}
              autoComplete={setup ? "new-password" : "current-password"}
              placeholder={
                setup ? "At least 12 characters" : "Enter your password"
              }
            />
          </label>
          <ErrorNotice message={error} />
          <button className="button primary full" disabled={busy}>
            {busy ? (
              <Loader2 className="spin" size={17} />
            ) : (
              <>
                {setup ? "Create workspace" : "Sign in"}
                <ArrowRight size={17} />
              </>
            )}
          </button>
          <div className="auth-note">
            <ShieldCheck size={15} />
            <span>
              Your data is stored on this computer. Recording always requires an
              explicit action and participant consent.
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}
