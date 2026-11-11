import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, setAuthLostHandler } from "../api/client";
import type { User } from "../api/generated";
import { getItem, removeItem, setItem } from "../storage";

type Ctx = {
  ready: boolean;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, name: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};
const AuthContext = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    setAuthLostHandler(() => {
      qc.clear();
      setUser(null);
    });
    return () => setAuthLostHandler(null);
  }, [qc]);

  useEffect(() => {
    (async () => {
      try {
        if (await getItem("access_token"))
          setUser(await api<User>("/users/me"));
      } catch {
        setUser(null);
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const t = await api<{ access_token: string; refresh_token: string }>(
      "/auth/login",
      {
        method: "POST",
        body: { email, password },
      },
    );
    await setItem("access_token", t.access_token);
    await setItem("refresh_token", t.refresh_token);
    setUser(await api<User>("/users/me"));
  }, []);

  const register = useCallback(
    async (email: string, name: string, password: string) => {
      await api("/auth/register", {
        method: "POST",
        body: { email, name, password },
      });
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(async () => {
    await removeItem("access_token");
    await removeItem("refresh_token");
    qc.clear();
    setUser(null);
  }, [qc]);

  const value = useMemo(
    () => ({ ready, user, login, register, logout }),
    [ready, user, login, register, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Ctx {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
