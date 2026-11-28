import { useEffect, useState } from "react";

/** Current time, refreshed every `everyMs`, so countdowns and "open now" badges stay true. */
export function useNow(everyMs = 30_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), everyMs);
    return () => clearInterval(t);
  }, [everyMs]);
  return now;
}
