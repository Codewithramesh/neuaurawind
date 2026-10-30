import { useEffect, useState } from "react";
import { api, human, json } from "./api";
import { Brand, ErrorNotice } from "./ui";
interface Notice {
  organization: string;
  store: string;
  purpose: string;
  source: string;
  notice: string;
  participant_ref: string;
  status: string;
  processing_location: string;
  audio_retained: boolean;
  retention: {
    raw_audio_hours: number;
    transcript_days: number;
    derived_days: number;
    consent_days: number;
  };
}
export function ParticipantConsent({
  token,
  onDone,
}: {
  token: string;
  onDone?: () => void;
}) {
  const [notice, setNotice] = useState<Notice | null>(null),
    [checked, setChecked] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    api<Notice>("/participant-consent", {
      headers: { "X-Consent-Token": token },
    })
      .then((n) => {
        if (live) setNotice(n);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [token]);
  async function decide(decision: string) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ status: string }>("/participant-consent", {
        method: "POST",
        headers: { "X-Consent-Token": token },
        ...json({ decision, informed: true }),
      });
      setNotice((n) => n && { ...n, status: result.status });
      onDone?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel participant-notice">
      <Brand />
      <h2>Participant consent</h2>
      <ErrorNotice message={error} />
      {notice && (
        <>
          <p>
            <strong>
              {notice.organization} · {notice.store}
            </strong>
          </p>
          <p>For: {notice.participant_ref}. Confirm only for yourself.</p>
          <p>
            <strong>Purpose:</strong> {notice.purpose}
          </p>
          <p>
            Source: {human(notice.source)} · Processing:{" "}
            {notice.processing_location}
          </p>
          <p>{notice.notice}</p>
          <p>
            Raw audio:{" "}
            {notice.audio_retained
              ? `up to ${notice.retention.raw_audio_hours} hours`
              : `removed after transcription; pending audio up to ${notice.retention.raw_audio_hours} hours`}
            . Transcript: {notice.retention.transcript_days} days. Findings:{" "}
            {notice.retention.derived_days} days. Consent evidence:{" "}
            {notice.retention.consent_days} days.
          </p>
          <p role="status">
            Your decision: <strong>{human(notice.status)}</strong>
          </p>
          {notice.status === "pending" && (
            <>
              <label className="consent-box">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => setChecked(e.target.checked)}
                />
                <span>
                  I have read this explanation and freely agree to recording,
                  transcription, AI analysis and the stated business use for
                  this session.
                </span>
              </label>
              <div className="button-row">
                <button
                  className="button primary"
                  disabled={!checked || busy}
                  onClick={() => void decide("grant")}
                >
                  I agree for myself
                </button>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => void decide("decline")}
                >
                  I do not agree
                </button>
              </div>
            </>
          )}
          {notice.status === "granted" && (
            <>
              <p>
                Keep this page or link if you wish to withdraw later. You can
                also tell the operator to stop.
              </p>
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => void decide("withdraw")}
              >
                Withdraw my consent
              </button>
            </>
          )}
        </>
      )}
    </section>
  );
}
