import * as Crypto from "expo-crypto";
import { API_BASE } from "../config";
import { getItem } from "../storage";

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

// Create ONE key per booking attempt and reuse it on retries (see HLD section 10).
export const newIdempotencyKey = () => Crypto.randomUUID();

type Opts = { method?: string; body?: unknown; idempotencyKey?: string };

export async function api<T>(path: string, opts: Opts = {}): Promise<T> {
  const token = await getItem("access_token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;

  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const e = data?.error;
    throw new ApiError(
      res.status,
      e?.code ?? "UNKNOWN",
      e?.message ?? res.statusText,
      e?.request_id,
    );
  }
  return data as T;
}
