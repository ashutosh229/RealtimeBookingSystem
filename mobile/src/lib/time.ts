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

/** "in 5 min", "in 2 h 10 min", "in 3 days" (future); "now" once it has started. */
export function until(iso: string, now = Date.now()): string {
  const min = Math.round((new Date(iso).getTime() - now) / 60000);
  if (min <= 0) return "now";
  if (min < 60) return `in ${min} min`;
  if (min < 24 * 60) {
    const h = Math.floor(min / 60);
    const m = min % 60;
    return m ? `in ${h} h ${m} min` : `in ${h} h`;
  }
  const d = Math.round(min / (24 * 60));
  return d === 1 ? "tomorrow" : `in ${d} days`;
}

/** "Today", "Tomorrow", or "Sat 30 Nov" for an instant, in the resource's zone. */
export function dayLabel(iso: string, tz: string, now = new Date()): string {
  const day = ymdInZone(new Date(iso), tz);
  const today = ymdInZone(now, tz);
  if (day === today) return "Today";
  if (day === addDays(today, 1)) return "Tomorrow";
  if (day === addDays(today, -1)) return "Yesterday";
  return fmtDay(day);
}

/** Wall-clock "HH:MM" right now in a zone. */
export function nowHHMM(tz: string, now = new Date()): string {
  return now.toLocaleTimeString("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}

/** Whether a place is open now, and the next change ("Closes 22:00" / "Opens 08:00"). */
export function openState(
  open: string,
  close: string,
  tz: string,
  now = new Date(),
): { open: boolean; label: string } {
  const t = nowHHMM(tz, now);
  const o = hhmm(open);
  const c = hhmm(close);
  if (t >= o && t < c) return { open: true, label: `Open · closes ${c}` };
  return {
    open: false,
    label: t < o ? `Closed · opens ${o}` : `Closed · opens ${o} tomorrow`,
  };
}

/** "60 min", "2 h", "1 h 30 min". */
export function fmtMinutes(min: number): string {
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}
