export let csrf = "";
let storeScope = "";
export function setStoreScope(value: string) {
  storeScope = value;
}
export function getStoreScope() {
  return storeScope;
}
export function setCSRF(value: string) {
  csrf = value;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && typeof options.body === "string")
    headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", csrf);
  if (storeScope && !headers.has("X-Store-Id"))
    headers.set("X-Store-Id", storeScope);
  const response = await fetch("/api/v1" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    throw new ApiError(
      response.status,
      detail?.code || "REQUEST_FAILED",
      typeof detail === "string"
        ? detail
        : detail?.message ||
            (Array.isArray(detail)
              ? detail.map((x) => x.msg).join(". ")
              : "Request failed. Please try again."),
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export const json = (data: unknown): RequestInit => ({
  body: JSON.stringify(data),
});
export const human = (text: string) =>
  text.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
export const dateLabel = (date: string) =>
  new Date(date).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
export const durationLabel = (n: number) =>
  `${Math.floor(n / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(n % 60)
    .toString()
    .padStart(2, "0")}`;
