/** Resource-local calendar date (YYYY-MM-DD) of an instant. */
export function ymdInZone(d: Date, tz: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

export function addDays(ymd: string, n: number): string {
  const [y, m, d] = ymd.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

export const fmtTime = (iso: string, tz: string) =>
  new Date(iso).toLocaleTimeString("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
  });

export const fmtDateTime = (iso: string, tz: string) =>
  new Date(iso).toLocaleString("en-GB", {
    timeZone: tz,
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

/** Calendar parts of an instant in a zone, for date blocks: { wk: "Thu", day: "26", mon: "Nov" }. */
export function dateParts(iso: string, tz: string) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    weekday: "short",
    day: "numeric",
    month: "short",
  }).formatToParts(new Date(iso));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return { wk: get("weekday"), day: get("day"), mon: get("month") };
}

/** Parts of a YYYY-MM-DD date, for the date strip. */
export function ymdParts(ymd: string) {
  const [y, m, d] = ymd.split("-").map(Number);
  return dateParts(new Date(Date.UTC(y, m - 1, d, 12)).toISOString(), "UTC");
}

/** "just now", "5 min ago", "3 h ago", "yesterday", or a date. */
export function ago(iso: string): string {
  const sec = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} h ago`;
  if (sec < 172800) return "yesterday";
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });
}

/** "09:00" from "09:00:00". */
export const hhmm = (t: string) => t.slice(0, 5);

export function fmtDay(ymd: string): string {
  const [y, m, d] = ymd.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}
