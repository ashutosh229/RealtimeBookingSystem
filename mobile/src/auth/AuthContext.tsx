import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { USE_MOCK } from "../config";
import { ApiError, api } from "../api/client";
import { getItem, removeItem, setItem } from "../storage";

type Ctx = {
  ready: boolean;
  signedIn: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    getItem("access_token").then((t) => {
      setSignedIn(!!t);
      setReady(true);
    });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    if (USE_MOCK) {
      if (!email.endsWith("@campus.test") || password !== "password123") {
        throw new ApiError(
          401,
          "INVALID_CREDENTIALS",
          "Invalid email or password",
        );
      }
      await setItem("access_token", "mock-token");
    } else {
      const t = await api<{ access_token: string; refresh_token: string }>(
        "/auth/login",
        {
          method: "POST",
          body: { email, password },
        },
      );
      await setItem("access_token", t.access_token);
      await setItem("refresh_token", t.refresh_token);
    }
    setSignedIn(true);
  }, []);

  const logout = useCallback(async () => {
    await removeItem("access_token");
    await removeItem("refresh_token");
    setSignedIn(false);
  }, []);

  const value = useMemo(
    () => ({ ready, signedIn, login, logout }),
    [ready, signedIn, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Ctx {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
