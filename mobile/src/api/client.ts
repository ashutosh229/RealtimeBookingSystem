import * as Crypto from "expo-crypto";
import { API_BASE } from "../config";
import { getItem, removeItem, setItem } from "../storage";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message);
  }
}

export const newIdempotencyKey = () => Crypto.randomUUID();

let onAuthLost: (() => void) | null = null;
export function setAuthLostHandler(fn: (() => void) | null) {
  onAuthLost = fn;
}

type Params = Record<string, string | number | boolean | undefined | null>;
type Opts = {
  method?: string;
  body?: unknown;
  params?: Params;
  idempotencyKey?: string;
};
export type Raw<T> = { status: number; data: T; headers: Headers };

function url(path: string, params?: Params) {
  const q = Object.entries(params ?? {})
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(
      ([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`,
    )
    .join("&");
  return `${API_BASE}${path}${q ? `?${q}` : ""}`;
}

async function send(
  path: string,
  opts: Opts,
  token: string | null,
): Promise<Response> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
  try {
    return await fetch(url(path, opts.params), {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "NETWORK", "Cannot reach the server");
  }
}

// Refresh tokens are single-use, so parallel 401s must share ONE refresh call.
// true = refreshed, false = refused (sign out), null = could not tell (network): do not sign out.
let refreshing: Promise<boolean | null> | null = null;
function refreshTokens(): Promise<boolean | null> {
  if (!refreshing) {
    refreshing = (async () => {
      const rt = await getItem("refresh_token");
      if (!rt) return false;
      try {
        const res = await fetch(url("/auth/refresh"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: rt }),
        });
        if (res.status === 401) return false;
        if (!res.ok) return null;
        const t = await res.json();
        await setItem("access_token", t.access_token);
        await setItem("refresh_token", t.refresh_token);
        return true;
      } catch {
        return null;
      }
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

export async function apiRaw<T>(
  path: string,
  opts: Opts = {},
): Promise<Raw<T>> {
  let res = await send(path, opts, await getItem("access_token"));
  if (res.status === 401 && !path.startsWith("/auth/")) {
    const ok = await refreshTokens();
    if (ok) {
      res = await send(path, opts, await getItem("access_token")); // same body and idempotency key
    } else if (ok === false) {
      await removeItem("access_token");
      await removeItem("refresh_token");
      onAuthLost?.();
    }
  }
  const data =
    res.status === 204 ? undefined : await res.json().catch(() => null);
  if (!res.ok) {
    const e = (
      data as {
        error?: { code?: string; message?: string; request_id?: string };
      } | null
    )?.error;
    throw new ApiError(
      res.status,
      e?.code ?? "UNKNOWN",
      e?.message ?? res.statusText,
      e?.request_id,
    );
  }
  return { status: res.status, data: data as T, headers: res.headers };
}

export async function api<T>(path: string, opts?: Opts): Promise<T> {
  return (await apiRaw<T>(path, opts)).data;
}
