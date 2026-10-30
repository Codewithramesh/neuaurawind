// These tests use explicit API/capture doubles; they do not verify a physical microphone.
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ParticipantConsent } from "./ParticipantConsent";
import { Recorder } from "./Recorder";
import { BrowserMicrophoneAdapter } from "./audio";
import type { Settings } from "./types";
import { api } from "./api";
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  api: vi.fn(),
}));
const mocked = vi.mocked(api);
const settings = {
  stores: [{ id: "s1", org_id: "o1", name: "Test store" }],
  max_duration_seconds: 600,
  max_upload_mb: 50,
  language: "en",
} as Settings;
let state = "awaiting_consent";
let valid = false;
const current = () => ({
  id: "c1",
  upload_session_id: "u1",
  title: "Test",
  purpose: "Test purpose",
  source_type: "browser",
  session_state: state,
  consent_version: 1,
  consent_valid: valid,
  participants: [
    {
      id: "p1",
      participant_ref: "Guest 1",
      status: valid ? "granted" : "pending",
    },
  ],
});
beforeEach(() => {
  localStorage.clear();
  state = "awaiting_consent";
  valid = false;
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  mocked.mockImplementation(async (path, options) => {
    if (path === "/devices") return [] as never;
    if (path === "/sessions")
      return {
        id: "u1",
        conversation_id: "c1",
        participant_links: [
          { id: "p1", participant_ref: "Guest 1", token: "private-test-token" },
        ],
      } as never;
    if (path === "/conversations/c1/transition") {
      const body = JSON.parse(String(options?.body));
      state = (
        {
          ready: "ready",
          start: "recording",
          pause: "paused",
          resume: "recording",
          interrupt: "interrupted",
          stop: "finalizing",
          cancel: "cancelled",
        } as Record<string, string>
      )[body.action];
      return current() as never;
    }
    if (path === "/conversations/c1") return current() as never;
    if (path === "/participant-consent")
      return {
        organization: "Test org",
        store: "Test store",
        participant_ref: "Guest 1",
        purpose: "Improve service",
        notice: "Recording and local AI. You can withdraw.",
        status: options?.method === "POST" ? "granted" : "pending",
        source: "phone_microphone",
        processing_location: "local computer",
        audio_retained: false,
        retention: {
          raw_audio_hours: 24,
          transcript_days: 30,
          derived_days: 30,
          consent_days: 30,
        },
      } as never;
    throw Error("Unexpected TEST API " + path);
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
  localStorage.clear();
});
async function prepare() {
  fireEvent.change(screen.getByLabelText("Conversation title"), {
    target: { value: "Authorized test" },
  });
  fireEvent.change(screen.getByLabelText("Session purpose"), {
    target: { value: "Investigate service" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Prepare session" }));
  await screen.findByText("Participant confirmations");
}
describe("participant decisions", () => {
  it("never prechecks or submits consent on page load", async () => {
    render(<ParticipantConsent token="test-token" />);
    const button = await screen.findByRole("button", {
      name: "I agree for myself",
    });
    expect(button).toBeDisabled();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(
      mocked.mock.calls.filter(([, o]) => o?.method === "POST"),
    ).toHaveLength(0);
  });
  it("submits only the participant’s explicit decision", async () => {
    render(<ParticipantConsent token="test-token" />);
    await screen.findByRole("checkbox");
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "I agree for myself" }));
    await screen.findByRole("button", { name: "Withdraw my consent" });
    expect(mocked).toHaveBeenCalledWith(
      "/participant-consent",
      expect.objectContaining({
        headers: { "X-Consent-Token": "test-token" },
        body: JSON.stringify({ decision: "grant", informed: true }),
      }),
    );
  });
});
describe("capture guardrails", () => {
  it("prepares without requesting the microphone and cannot start with incomplete consent", async () => {
    const start = vi.spyOn(BrowserMicrophoneAdapter.prototype, "start");
    render(
      <Recorder settings={settings} onClose={() => {}} onComplete={() => {}} />,
    );
    await prepare();
    expect(start).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", {
        name: "Validate consent and prepare capture",
      }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Start recording" }),
    ).not.toBeInTheDocument();
  });
  it("recovers an interrupted session without activating the microphone", async () => {
    state = "recording";
    valid = true;
    localStorage.setItem("neuaura-prepared-session", "c1");
    const start = vi.spyOn(BrowserMicrophoneAdapter.prototype, "start");
    render(
      <Recorder settings={settings} onClose={() => {}} onComplete={() => {}} />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Recover prepared session" }),
    );
    await waitFor(() => expect(state).toBe("interrupted"));
    expect(start).not.toHaveBeenCalled();
  });
  it("records a permission failure as an interruption", async () => {
    state = "ready";
    valid = true;
    vi.spyOn(BrowserMicrophoneAdapter.prototype, "start").mockRejectedValue(
      new DOMException("Microphone permission denied", "NotAllowedError"),
    );
    render(
      <Recorder settings={settings} onClose={() => {}} onComplete={() => {}} />,
    );
    await prepare();
    fireEvent.click(
      await screen.findByRole("button", { name: "Start recording" }),
    );
    await screen.findByText("Microphone permission denied");
    expect(state).toBe("interrupted");
  });
  it("stops capture immediately on a connection loss", async () => {
    state = "ready";
    valid = true;
    vi.spyOn(BrowserMicrophoneAdapter.prototype, "start").mockResolvedValue();
    const stop = vi
      .spyOn(BrowserMicrophoneAdapter.prototype, "stop")
      .mockResolvedValue({
        blob: new Blob(["TEST bytes"]),
        sourceType: "browser",
        mime: "audio/webm",
      });
    render(
      <Recorder settings={settings} onClose={() => {}} onComplete={() => {}} />,
    );
    await prepare();
    fireEvent.click(
      await screen.findByRole("button", { name: "Start recording" }),
    );
    await screen.findByText("RECORDING");
    await act(async () => {
      window.dispatchEvent(new Event("offline"));
    });
    await waitFor(() => expect(stop).toHaveBeenCalled());
    await waitFor(() => expect(state).toBe("interrupted"));
  });
});

describe("interruption recovery", () => {
  it("keeps a failed stop marked interrupted and reconciles the backend before revalidation", async () => {
    state = "ready";
    valid = true;
    vi.spyOn(BrowserMicrophoneAdapter.prototype, "start").mockResolvedValue();
    vi.spyOn(BrowserMicrophoneAdapter.prototype, "stop").mockResolvedValue({
      blob: new Blob(["TEST bytes"]),
      sourceType: "browser",
      mime: "audio/webm",
    });
    const implementation = mocked.getMockImplementation()!;
    mocked.mockImplementation((path, options) =>
      path.endsWith("/transition") &&
      JSON.parse(String(options?.body)).action === "stop"
        ? Promise.reject(new Error("TEST network failure"))
        : implementation(path, options),
    );
    render(
      <Recorder settings={settings} onClose={() => {}} onComplete={() => {}} />,
    );
    await prepare();
    fireEvent.click(
      await screen.findByRole("button", { name: "Start recording" }),
    );
    await screen.findByText("RECORDING");
    fireEvent.click(screen.getByRole("button", { name: "Stop recording" }));
    await screen.findByText(/Capture stopped locally/);
    expect(screen.queryByText("RECORDING")).not.toBeInTheDocument();
    expect(state).toBe("recording");
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Validate consent and prepare capture",
      }),
    );
    await waitFor(() => expect(state).toBe("ready"));
  });
  it("stops when a visible capture is backgrounded", async () => {
    state = "ready";
    valid = true;
    vi.spyOn(BrowserMicrophoneAdapter.prototype, "start").mockResolvedValue();
    const stop = vi
      .spyOn(BrowserMicrophoneAdapter.prototype, "stop")
      .mockResolvedValue({
        blob: new Blob(["TEST bytes"]),
        sourceType: "browser",
        mime: "audio/webm",
      });
    render(
      <Recorder settings={settings} onClose={() => {}} onComplete={() => {}} />,
    );
    await prepare();
    fireEvent.click(
      await screen.findByRole("button", { name: "Start recording" }),
    );
    await screen.findByText("RECORDING");
    vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await waitFor(() => expect(stop).toHaveBeenCalled());
    await waitFor(() => expect(state).toBe("interrupted"));
  });
});
