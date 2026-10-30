import { api, csrf, json } from "./api";
export interface AudioSubmission {
  blob: Blob;
  sourceType: "browser" | "upload";
  mime: string;
}
export interface AudioSourceAdapter {
  submission(): AudioSubmission;
}
export class UploadedAudioAdapter implements AudioSourceAdapter {
  constructor(private file: File) {}
  submission(): AudioSubmission {
    return {
      blob: this.file,
      sourceType: "upload",
      mime: this.file.type || "application/octet-stream",
    };
  }
}
export class BrowserMicrophoneAdapter implements AudioSourceAdapter {
  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];
  private captured: Blob | null = null;
  private starting = false;
  private generation = 0;
  async start(deviceId?: string) {
    if (
      this.starting ||
      this.stream ||
      (this.recorder && this.recorder.state !== "inactive")
    )
      throw new Error("A capture is already active");
    if (
      !window.isSecureContext ||
      !navigator.mediaDevices?.getUserMedia ||
      !window.MediaRecorder
    )
      throw new Error(
        "Microphone access needs localhost or a trusted HTTPS connection in a supported browser.",
      );
    this.starting = true;
    const generation = ++this.generation;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: deviceId ? { deviceId: { exact: deviceId } } : true,
      });
      if (generation !== this.generation) {
        stream.getTracks().forEach((track) => track.stop());
        throw new Error(
          "Capture was cancelled before microphone permission completed.",
        );
      }
      this.stream = stream;
      if (document.visibilityState === "hidden")
        throw new Error("Keep the app in the foreground before recording.");
      const mimeType = [
        "audio/webm;codecs=opus",
        "audio/mp4",
        "audio/ogg;codecs=opus",
      ].find((x) => MediaRecorder.isTypeSupported(x));
      this.recorder = new MediaRecorder(
        this.stream,
        mimeType ? { mimeType } : undefined,
      );
      this.chunks = [];
      this.captured = null;
      this.recorder.ondataavailable = (e) => {
        if (e.data.size) this.chunks.push(e.data);
      };
      this.recorder.start(1000);
    } catch (error) {
      this.release();
      throw error;
    } finally {
      this.starting = false;
    }
  }
  onError(callback: (message: string) => void) {
    if (this.recorder)
      this.recorder.onerror = () =>
        callback("The microphone stopped unexpectedly. Cancel and try again.");
    this.stream?.getTracks().forEach((track) => {
      track.onended = () =>
        callback("Microphone disconnected. Capture must be revalidated.");
    });
  }
  pause() {
    if (this.recorder?.state === "recording") this.recorder.pause();
  }
  resume() {
    if (this.recorder?.state === "paused") this.recorder.resume();
  }
  stop(): Promise<AudioSubmission> {
    return new Promise((resolve, reject) => {
      if (!this.recorder || this.recorder.state === "inactive") {
        reject(new Error("No active recording"));
        return;
      }
      this.recorder.onstop = () => {
        this.captured = new Blob(this.chunks, {
          type: this.recorder?.mimeType || "audio/webm",
        });
        this.release();
        if (!this.captured.size) {
          reject(
            new Error("The microphone produced an empty recording. Try again."),
          );
          return;
        }
        resolve(this.submission());
      };
      this.recorder.stop();
    });
  }
  cancel() {
    this.generation += 1;
    if (this.recorder && this.recorder.state !== "inactive") {
      this.recorder.onstop = null;
      this.recorder.stop();
    }
    this.release();
    this.chunks = [];
    this.captured = null;
  }
  private release() {
    this.stream?.getTracks().forEach((t) => {
      t.onended = null;
      t.stop();
    });
    this.stream = null;
  }
  submission(): AudioSubmission {
    if (!this.captured) throw new Error("Stop the recording first");
    return {
      blob: this.captured,
      sourceType: "browser",
      mime: this.captured.type,
    };
  }
}
export async function sha256(blob: Blob) {
  const bytes = await blob.arrayBuffer();
  return Array.from(
    new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
  )
    .map((x) => x.toString(16).padStart(2, "0"))
    .join("");
}
export async function uploadAudio(
  input: AudioSubmission,
  onProgress: (progress: number) => void,
  preparedSession?: { id: string; conversation_id: string },
): Promise<string> {
  if (!preparedSession)
    throw new Error(
      "Prepare the session and obtain participant consent before upload",
    );
  const session = preparedSession;
  const chunkSize = 4 * 1024 * 1024;
  const count = Math.ceil(input.blob.size / chunkSize);
  for (let i = 0; i < count; i++) {
    const chunk = input.blob.slice(i * chunkSize, (i + 1) * chunkSize);
    const hash = await sha256(chunk);
    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/v1/sessions/${session.id}/audio?sequence=${i}`);
      xhr.setRequestHeader(
        "Content-Type",
        input.mime || "application/octet-stream",
      );
      xhr.setRequestHeader("X-CSRF-Token", csrf);
      xhr.setRequestHeader("X-Chunk-SHA256", hash);
      xhr.upload.onprogress = (e) =>
        onProgress(
          Math.round(((i * chunkSize + e.loaded) / input.blob.size) * 95),
        );
      xhr.onerror = () =>
        reject(new Error("Upload interrupted. Keep this page open and retry."));
      xhr.timeout = 120000;
      xhr.ontimeout = () =>
        reject(new Error("Upload timed out. Retry to resume."));
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else {
          let message = "Audio upload failed";
          try {
            message = JSON.parse(xhr.responseText).detail.message || message;
          } catch {
            /* keep fallback */
          }
          reject(new Error(message));
        }
      };
      xhr.send(chunk);
    });
  }
  await api(`/sessions/${session.id}/complete`, {
    method: "POST",
    ...json({ sha256: await sha256(input.blob), total_chunks: count }),
  });
  onProgress(100);
  return session.conversation_id;
}
