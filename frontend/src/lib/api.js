import { supabase } from "./supabase";

// Without VITE_API_URL (the local demo), use port 8000 on whatever host served the app,
// so it also works from a phone on the same wifi.
const BASE = import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`;
// Render's free tier can take up to a minute to wake, so be patient.
const TIMEOUT_MS = 75_000;

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function describe(detail) {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => (typeof d === "string" ? d : d.msg)).join(". ");
  return null;
}

async function request(method, path, body) {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      signal: ctrl.signal,
      headers: {
        ...(body !== undefined && { "Content-Type": "application/json" }),
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Couldn't reach the server. Check your connection and try again.");
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 204) return null;
  const json = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, describe(json?.detail) || `Request failed (${res.status})`);
  return json;
}

export const api = {
  get: (p) => request("GET", p),
  put: (p, b) => request("PUT", p, b),
  post: (p, b) => request("POST", p, b ?? {}),
  patch: (p, b) => request("PATCH", p, b),
  del: (p, b) => request("DELETE", p, b),
};

// Fire-and-forget: starts waking a sleeping server while the user is still reading the screen.
export function warmUp() {
  fetch(BASE + "/health").catch(() => {});
}
