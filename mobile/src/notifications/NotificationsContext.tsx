import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AppState } from "react-native";
import { api } from "../api/client";
import type { Notification } from "../api/generated";
import { useAuth } from "../auth/AuthContext";
import { POLL_MS } from "../config";

type Ctx = {
  items: Notification[]; // newest first
  unread: number;
  banner: Notification | null;
  dismissBanner: () => void;
  markRead: (id: number) => Promise<void>;
};
const NotificationsContext = createContext<Ctx | null>(null);
const QUIET = new Set(["BookingConfirmed", "BookingWaitlisted"]); // the user just did these: no banner

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [items, setItems] = useState<Notification[]>([]);
  const [banner, setBanner] = useState<Notification | null>(null);
  const lastId = useRef(0);
  const primed = useRef(false); // the first poll loads history silently
  const busy = useRef(false);

  const poll = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      const added: Notification[] = [];
      for (let i = 0; i < 10; i++) {
        const page = await api<{ items: Notification[] }>(
          "/users/me/notifications",
          {
            params: { since: lastId.current, limit: 100 },
          },
        );
        if (!page.items.length) break;
        added.push(...page.items);
        lastId.current = page.items[page.items.length - 1].id;
        if (page.items.length < 100) break;
      }
      if (added.length) {
        setItems((prev) => [...[...added].reverse(), ...prev]);
        if (primed.current) {
          const loud = [...added].reverse().find((n) => !QUIET.has(n.type));
          if (loud) setBanner(loud);
          for (const key of ["bookings", "booking", "availability"])
            qc.invalidateQueries({ queryKey: [key] });
        }
      }
      primed.current = true;
    } catch {
      // offline or transient: the next tick retries
    } finally {
      busy.current = false;
    }
  }, [qc]);

  useEffect(() => {
    if (!user) {
      setItems([]);
      setBanner(null);
      lastId.current = 0;
      primed.current = false;
      return;
    }
    poll();
    const timer = setInterval(poll, POLL_MS);
    const sub = AppState.addEventListener(
      "change",
      (st) => st === "active" && poll(),
    );
    return () => {
      clearInterval(timer);
      sub.remove();
    };
  }, [user, poll]);

  const markRead = useCallback(async (id: number) => {
    setItems((prev) =>
      prev.map((n) =>
        n.id === id && !n.read_at
          ? { ...n, read_at: new Date().toISOString() }
          : n,
      ),
    );
    try {
      await api(`/users/me/notifications/${id}/read`, { method: "POST" });
    } catch {
      // harmless: it shows as read locally and the server copy catches up next time
    }
  }, []);

  const value = useMemo<Ctx>(
    () => ({
      items,
      unread: items.filter((n) => !n.read_at).length,
      banner,
      dismissBanner: () => setBanner(null),
      markRead,
    }),
    [items, banner, markRead],
  );
  return (
    <NotificationsContext.Provider value={value}>
      {children}
    </NotificationsContext.Provider>
  );
}

export function useNotifications(): Ctx {
  const ctx = useContext(NotificationsContext);
  if (!ctx)
    throw new Error(
      "useNotifications must be used inside NotificationsProvider",
    );
  return ctx;
}
