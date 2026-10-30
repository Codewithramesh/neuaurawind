import { useState, useRef, useEffect, useCallback } from "react";
import {
  X,
  Mic,
  Pause,
  Play,
  Square,
  Loader2,
  ShieldCheck,
} from "lucide-react";
import { useDialog } from "./useDialog";
import { ErrorNotice, Badge } from "./ui";
import { api, json, durationLabel, human } from "./api";
import {
  BrowserMicrophoneAdapter,
  UploadedAudioAdapter,
  uploadAudio,
} from "./audio";
import type { AudioSubmission } from "./audio";
import type {
  ConversationDetail,
  Device,
  ParticipantLink,
  Settings,
} from "./types";
import { ParticipantConsent } from "./ParticipantConsent";
const recoveryKey = "neuaura-prepared-session";
export function Recorder({
  settings,
  onClose,
  onComplete,
}: {
  settings: Settings | null;
  onClose: () => void;
  onComplete: (id: string) => void;
}) {
  const dialogRef = useDialog(),
    adapter = useRef(new BrowserMicrophoneAdapter()),
    active = useRef(false),
    mounted = useRef(true),
    preparationKey = useRef(crypto.randomUUID()),
    interruptedLocally = useRef(false);
  const [session, setSession] = useState<ConversationDetail | null>(null),
    [links, setLinks] = useState<ParticipantLink[]>([]),
    [participant, setParticipant] = useState<string | null>(null),
    [title, setTitle] = useState(""),
    [purpose, setPurpose] = useState(""),
    [refs, setRefs] = useState("Participant 1"),
    [store, setStore] = useState(settings?.stores[0]?.id || ""),
    [source, setSource] = useState("browser"),
    [deviceId, setDeviceId] = useState(""),
    [devices, setDevices] = useState<Device[]>([]),
    [conditions, setConditions] = useState(false),
    [busy, setBusy] = useState(false),
    [uploading, setUploading] = useState(false),
    [error, setError] = useState(""),
    [input, setInput] = useState<AudioSubmission | null>(null),
    [url, setURL] = useState(""),
    [seconds, setSeconds] = useState(0),
    [progress, setProgress] = useState(0),
    [recover, setRecover] = useState(() => localStorage.getItem(recoveryKey));
  const latest = useRef(session);
  latest.current = session;
  const limit = settings?.max_duration_seconds || 600;
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      adapter.current.cancel();
      active.current = false;
    };
  }, []);
  useEffect(() => {
    let live = true;
    void api<Device[]>("/devices", { headers: { "X-Store-Id": store } })
      .then((rows) => {
        if (live) setDevices(rows);
      })
      .catch(() => {
        if (live) setDevices([]);
      });
    return () => {
      live = false;
    };
  }, [store]);
  useEffect(() => {
    if (!session) preparationKey.current = crypto.randomUUID();
  }, [title, purpose, refs, store, source, deviceId]);
  useEffect(() => {
    if (
      active.current &&
      session &&
      (!session.consent_valid ||
        !["recording", "paused"].includes(session.session_state))
    ) {
      active.current = false;
      adapter.current.cancel();
      setInput(null);
      setError("Capture stopped because consent or session state changed.");
    }
  }, [session?.consent_valid, session?.session_state]);
  useEffect(() => {
    if (!input) return;
    const u = URL.createObjectURL(input.blob);
    setURL(u);
    return () => URL.revokeObjectURL(u);
  }, [input]);
  const refresh = useCallback(async (id: string) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const data = await api<ConversationDetail>("/conversations/" + id, {
        signal: controller.signal,
      });
      if (mounted.current)
        setSession(
          interruptedLocally.current &&
            ["recording", "paused", "ready"].includes(data.session_state)
            ? { ...data, session_state: "interrupted" }
            : data,
        );
      return data;
    } finally {
      clearTimeout(timer);
    }
  }, []);
  async function move(action: string, confirmed = false) {
    let current = await api<ConversationDetail>(
      "/conversations/" + latest.current!.id,
    );
    if (
      action === "ready" &&
      interruptedLocally.current &&
      ["recording", "paused", "ready"].includes(current.session_state)
    ) {
      current = await api<ConversationDetail>(
        `/conversations/${current.id}/transition`,
        {
          method: "POST",
          ...json({
            action: "interrupt",
            expected_state: current.session_state,
            consent_version: current.consent_version,
          }),
        },
      );
    }
    const data = await api<ConversationDetail>(
      `/conversations/${current.id}/transition`,
      {
        method: "POST",
        ...json({
          action,
          expected_state: current.session_state,
          consent_version: current.consent_version,
          conditions_confirmed: confirmed,
        }),
      },
    );
    if (action === "ready") interruptedLocally.current = false;
    setSession((previous) => (previous ? { ...previous, ...data } : data));
    return data;
  }
  const interrupt = useCallback(
    async (message: string) => {
      if (!active.current) return;
      active.current = false;
      interruptedLocally.current = true;
      setSession((previous) =>
        previous ? { ...previous, session_state: "interrupted" } : previous,
      );
      try {
        const audio = await adapter.current.stop();
        if (mounted.current) setInput(audio);
      } catch {
        adapter.current.cancel();
      }
      setError(message);
      setConditions(false);
      const current = latest.current;
      if (current)
        try {
          const fresh = await api<ConversationDetail>(
            "/conversations/" + current.id,
          );
          if (["recording", "paused", "ready"].includes(fresh.session_state))
            await api(`/conversations/${current.id}/transition`, {
              method: "POST",
              ...json({
                action: "interrupt",
                expected_state: fresh.session_state,
                consent_version: fresh.consent_version,
              }),
            });
          await refresh(current.id);
        } catch {
          /* Server recovery marks interrupted capture; never auto-resume. */
        }
    },
    [refresh],
  );
  useEffect(() => {
    if (!session?.id) return;
    const timer = setInterval(() => {
      void refresh(session.id)
        .then((data) => {
          if (
            active.current &&
            (!data.consent_valid ||
              !["recording", "paused"].includes(data.session_state))
          ) {
            active.current = false;
            adapter.current.cancel();
            setInput(null);
            setError(
              "Capture stopped because consent or session state changed.",
            );
          }
        })
        .catch(() => {
          void interrupt(
            "Connection lost. Capture stopped; reconnect and revalidate consent before continuing.",
          );
        });
    }, 2000);
    return () => clearInterval(timer);
  }, [session?.id, refresh, interrupt]);
  useEffect(() => {
    if (!session || !["recording", "paused"].includes(session.session_state))
      return;
    const timer = setInterval(() => {
      void api(`/conversations/${session.id}/capture-heartbeat`, {
        method: "POST",
        ...json({
          state: session.session_state,
          consent_version: session.consent_version,
        }),
      }).catch((error) => {
        if (error?.code !== "STATE_CONFLICT")
          void interrupt(
            "Capture connection could not be confirmed. Recording stopped; revalidate before continuing.",
          );
      });
    }, 5000);
    return () => clearInterval(timer);
  }, [
    session?.id,
    session?.session_state,
    session?.consent_version,
    interrupt,
  ]);
  useEffect(() => {
    const hidden = () => {
        if (document.hidden)
          void interrupt(
            "The app was backgrounded. Capture stopped; revalidate before continuing.",
          );
      },
      offline = () =>
        void interrupt(
          "Network disconnected. Capture stopped; reconnect before continuing.",
        ),
      before = (e: BeforeUnloadEvent) => {
        if (active.current || uploading) {
          e.preventDefault();
          e.returnValue = "";
        }
      };
    document.addEventListener("visibilitychange", hidden);
    window.addEventListener("offline", offline);
    window.addEventListener("beforeunload", before);
    return () => {
      document.removeEventListener("visibilitychange", hidden);
      window.removeEventListener("offline", offline);
      window.removeEventListener("beforeunload", before);
    };
  }, [interrupt, uploading]);
  useEffect(() => {
    if (session?.session_state !== "recording") return;
    const timer = setInterval(() => setSeconds((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [session?.session_state]);
  async function action(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      if (active.current)
        await interrupt(
          (e as Error).message +
            " Capture stopped; revalidate before continuing.",
        );
      else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function stop() {
    active.current = false;
    const audio = source === "device" ? input : await adapter.current.stop();
    if (audio) setInput(audio);
    try {
      await move("stop");
    } catch (error) {
      interruptedLocally.current = true;
      setSession((previous) =>
        previous ? { ...previous, session_state: "interrupted" } : previous,
      );
      throw new Error(
        "Capture stopped locally. Reconnect and revalidate before finalizing. " +
          (error as Error).message,
      );
    } finally {
      setConditions(false);
    }
  }
  useEffect(() => {
    if (seconds >= limit && active.current) void action(stop);
  }, [seconds, limit]);
  async function cancel() {
    adapter.current.cancel();
    active.current = false;
    if (
      session &&
      !["processing", "needs_review", "approved", "cancelled"].includes(
        session.session_state,
      )
    )
      await move("cancel");
    localStorage.removeItem(recoveryKey);
    onClose();
  }
  const capturing =
    session && ["recording", "paused"].includes(session.session_state);
  return (
    <div className="modal-backdrop">
      <section
        ref={dialogRef}
        className="modal recorder-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="record-title"
      >
        <div className="modal-heading">
          <div>
            <span className="eyebrow">CONSENT-CONTROLLED CAPTURE</span>
            <h2 id="record-title">New conversation</h2>
          </div>
          <button
            className="icon-button"
            aria-label="Close recorder"
            disabled={busy || uploading}
            onClick={() => void action(cancel)}
          >
            <X size={20} />
          </button>
        </div>
        <ErrorNotice message={error} />
        {!session ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action(async () => {
                const created = await api<{
                  id: string;
                  conversation_id: string;
                  participant_links: ParticipantLink[];
                }>("/sessions", {
                  method: "POST",
                  headers: { "Idempotency-Key": preparationKey.current },
                  ...json({
                    title,
                    purpose,
                    store_id: store,
                    participant_refs: refs
                      .split(",")
                      .map((x) => x.trim())
                      .filter(Boolean),
                    source_type: source,
                    device_id: source === "device" ? deviceId : null,
                  }),
                });
                setLinks(created.participant_links);
                localStorage.setItem(recoveryKey, created.conversation_id);
                setRecover(null);
                await refresh(created.conversation_id);
              });
            }}
          >
            {recover && (
              <div className="processing-notice">
                <div>
                  <p>
                    A prepared session can be recovered. Audio held only in
                    browser memory is lost after reload.
                  </p>
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() =>
                      void action(async () => {
                        const old = await refresh(recover);
                        setSource(old.source_type);
                        setTitle(old.title);
                        setStore(old.store_id);
                        setPurpose(old.purpose);
                        if (
                          ["recording", "paused"].includes(old.session_state)
                        ) {
                          await api(`/conversations/${old.id}/transition`, {
                            method: "POST",
                            ...json({
                              action: "interrupt",
                              expected_state: old.session_state,
                              consent_version: old.consent_version,
                            }),
                          });
                          await refresh(old.id);
                        }
                        setRecover(null);
                      })
                    }
                  >
                    Recover prepared session
                  </button>
                </div>
              </div>
            )}
            <label>
              Store
              <select
                value={store}
                onChange={(e) => setStore(e.target.value)}
                required
              >
                <option value="">Select store</option>
                {settings?.stores.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Conversation title
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                maxLength={160}
              />
            </label>
            <label>
              Session purpose
              <textarea
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                minLength={3}
                maxLength={500}
                required
                placeholder="Explain the specific business use"
              />
            </label>
            <label>
              Participant references
              <input
                value={refs}
                onChange={(e) => setRefs(e.target.value)}
                required
                placeholder="Guest 1, Staff 1"
              />
            </label>
            <p className="field-help">
              List every participant, including the operator if speaking. Use
              short references; names are unnecessary. The roster must match the
              people actually present.
            </p>
            <label>
              Capture source
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                <option value="browser">Computer / browser microphone</option>
                <option value="phone_microphone">
                  Phone microphone — temporary capture
                </option>
                <option value="upload">Uploaded authorized test audio</option>
                <option value="device">
                  Simulated wearable audio transfer
                </option>
              </select>
            </label>
            {source === "device" && (
              <>
                <label>
                  Development device
                  <select
                    value={deviceId}
                    onChange={(e) => setDeviceId(e.target.value)}
                    required
                  >
                    <option value="">Select simulator</option>
                    {devices
                      .filter(
                        (d) =>
                          d.simulated &&
                          d.store_id === store &&
                          d.status === "authorized",
                      )
                      .map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name} · SIMULATED
                        </option>
                      ))}
                  </select>
                </label>
                <p className="field-help">
                  No physical wearable is connected. This exercises session
                  controls and transfer of a real audio file only.
                </p>
              </>
            )}
            <button className="button primary" disabled={busy || !store}>
              {busy ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <ShieldCheck size={16} />
              )}{" "}
              Prepare session
            </button>
          </form>
        ) : (
          <>
            <div className="detail-meta">
              <Badge status={session.session_state} />
              <span>{human(session.source_type)}</span>
              <span>{session.purpose}</span>
            </div>
            <section className="consent-roster">
              <h3>Participant confirmations</h3>
              <p>
                Hand the phone to each participant or give them their private
                link. The operator’s confirmation cannot establish everyone’s
                consent.
              </p>
              {(session.participants || []).map((p) => (
                <div className="setting-row" key={p.id}>
                  <span>
                    {p.participant_ref} · {human(p.status)}
                  </span>
                  {links.find((l) => l.id === p.id) && (
                    <button
                      className="text-button"
                      disabled={!!capturing}
                      onClick={() =>
                        setParticipant(links.find((l) => l.id === p.id)!.token)
                      }
                    >
                      Participant review
                    </button>
                  )}
                </div>
              ))}
              {links.map((l) => (
                <p key={l.id} className="field-help">
                  {l.participant_ref}:{" "}
                  <a
                    href={`${location.origin}/#consent/${l.token}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open private confirmation link
                  </a>
                </p>
              ))}
              {participant && (
                <>
                  <ParticipantConsent
                    key={participant}
                    token={participant}
                    onDone={() => void refresh(session.id)}
                  />
                  <button
                    className="text-button"
                    onClick={() => setParticipant(null)}
                  >
                    Return to operator controls
                  </button>
                </>
              )}
              {!capturing &&
                !["processing", "approved", "cancelled"].includes(
                  session.session_state,
                ) && (
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() =>
                      void action(async () => {
                        const result = await api<{
                          participant_links: ParticipantLink[];
                        }>(`/conversations/${session.id}/participants`, {
                          method: "POST",
                          ...json({
                            participant_refs: session.participants?.length
                              ? session.participants.map(
                                  (p) => p.participant_ref,
                                )
                              : refs.split(",").map((x) => x.trim()),
                          }),
                        });
                        setLinks(result.participant_links);
                        await refresh(session.id);
                      })
                    }
                  >
                    Request fresh participant confirmations
                  </button>
                )}
            </section>
            {![
              "processing",
              "needs_review",
              "approved",
              "cancelled",
              "failed",
            ].includes(session.session_state) && (
              <label className="consent-box">
                <input
                  type="checkbox"
                  checked={conditions}
                  disabled={!!capturing && session.session_state !== "paused"}
                  onChange={(e) => setConditions(e.target.checked)}
                />
                <span>
                  I have rechecked the participant roster and consent, source
                  availability, and visible recording status. Keep this app
                  open; backgrounding or a lost connection interrupts capture.
                </span>
              </label>
            )}
            {["awaiting_consent", "draft", "interrupted"].includes(
              session.session_state,
            ) && (
              <button
                className="button primary"
                disabled={busy || !conditions || !session.consent_valid}
                onClick={() =>
                  void action(async () => {
                    await move("ready", conditions);
                  })
                }
              >
                Validate consent and prepare capture
              </button>
            )}
            {["ready", "recording", "paused"].includes(
              session.session_state,
            ) && (
              <div
                className={`record-surface ${capturing ? "is-recording" : ""}`}
              >
                <div className="record-status" role="status">
                  {session.session_state === "recording" ? (
                    <>
                      <i className="record-dot" /> RECORDING
                      {source === "device" ? " · SIMULATED CONTROLS" : ""}
                    </>
                  ) : (
                    human(session.session_state).toUpperCase()
                  )}
                </div>
                <strong className="record-time">
                  {durationLabel(seconds)}
                </strong>
                <div className="record-controls">
                  {session.session_state === "ready" &&
                    ["browser", "phone_microphone"].includes(source) &&
                    !input && (
                      <button
                        className="button primary"
                        disabled={busy}
                        onClick={() =>
                          void action(async () => {
                            await move("start");
                            try {
                              await adapter.current.start();
                              active.current = true;
                              adapter.current.onError(
                                (message) => void interrupt(message),
                              );
                              setSeconds(0);
                            } catch (e) {
                              await move("interrupt");
                              throw e;
                            }
                          })
                        }
                      >
                        <Mic size={16} /> Start recording
                      </button>
                    )}
                  {session.session_state === "ready" && source === "device" && (
                    <button
                      className="button primary"
                      disabled={busy}
                      onClick={() =>
                        void action(async () => {
                          await move("start");
                        })
                      }
                    >
                      Simulate capture start
                    </button>
                  )}
                  {session.session_state === "recording" && (
                    <button
                      className="button secondary"
                      disabled={busy}
                      onClick={() =>
                        void action(async () => {
                          adapter.current.pause();
                          setConditions(false);
                          await move("pause");
                        })
                      }
                    >
                      <Pause size={16} /> Pause
                    </button>
                  )}
                  {session.session_state === "paused" && (
                    <button
                      className="button secondary"
                      disabled={busy || !conditions}
                      onClick={() =>
                        void action(async () => {
                          await move("resume", conditions);
                          adapter.current.resume();
                        })
                      }
                    >
                      <Play size={16} /> Resume
                    </button>
                  )}
                  {capturing && (
                    <button
                      className="button dark"
                      disabled={busy}
                      onClick={() => void action(stop)}
                    >
                      <Square size={14} /> Stop recording
                    </button>
                  )}
                  {session.session_state === "ready" &&
                    (source === "upload" || input) && (
                      <button
                        className="button primary"
                        disabled={busy}
                        onClick={() =>
                          void action(async () => {
                            await move("stop");
                          })
                        }
                      >
                        Finalize authorized audio
                      </button>
                    )}
                </div>
              </div>
            )}
            {session.session_state === "finalizing" && (
              <>
                <p>
                  Capture stopped. Validate and transfer your {human(source)}{" "}
                  audio.
                </p>
                {(source === "upload" || source === "device") && (
                  <label>
                    Choose authorized audio file
                    <input
                      aria-label="Choose audio file"
                      type="file"
                      accept="audio/*,.m4a,.webm,.wav,.mp3,.flac,.ogg,.mp4"
                      disabled={uploading}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (!file) return;
                        if (
                          !file.size ||
                          file.size >
                            (settings?.max_upload_mb || 50) * 1024 * 1024
                        ) {
                          setError(
                            "Choose a nonempty audio file within the upload limit.",
                          );
                          return;
                        }
                        setInput(new UploadedAudioAdapter(file).submission());
                      }}
                    />
                  </label>
                )}
                {input && (
                  <>
                    <audio controls src={url} />
                    <button
                      className="button primary"
                      disabled={busy || uploading}
                      onClick={() =>
                        void action(async () => {
                          setUploading(true);
                          try {
                            const id = await uploadAudio(input, setProgress, {
                              id: session.upload_session_id,
                              conversation_id: session.id,
                            });
                            localStorage.removeItem(recoveryKey);
                            onComplete(id);
                          } finally {
                            setUploading(false);
                          }
                        })
                      }
                    >
                      Analyze conversation
                    </button>
                  </>
                )}
                {uploading && (
                  <div role="status">
                    Uploading {progress}%<progress max={100} value={progress} />
                  </div>
                )}
              </>
            )}
            {["processing", "needs_review", "approved", "failed"].includes(
              session.session_state,
            ) && (
              <button
                className="button primary"
                onClick={() => {
                  localStorage.removeItem(recoveryKey);
                  onComplete(session.id);
                }}
              >
                Open processing and review
              </button>
            )}
            <div className="modal-footer">
              <button
                className="text-button danger"
                disabled={busy || uploading}
                onClick={() => void action(cancel)}
              >
                Cancel session
              </button>
              <button
                className="text-button danger"
                disabled={busy}
                onClick={() =>
                  void action(async () => {
                    adapter.current.cancel();
                    active.current = false;
                    setInput(null);
                    await api(`/conversations/${session.id}/withdraw-consent`, {
                      method: "POST",
                    });
                    await refresh(session.id);
                  })
                }
              >
                Stop and withdraw consent
              </button>
            </div>
          </>
        )}
        <p className="record-privacy">
          <ShieldCheck size={14} /> No automatic microphone activation.
          Interrupted browser audio is not guaranteed to survive reload.
        </p>
      </section>
    </div>
  );
}
