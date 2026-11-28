/**
 * Light and dark themes. Components read colours and styles through useTheme(), so switching the
 * theme re-renders everything with the new palette without losing the user's place in the app.
 */
import Ionicons from "@expo/vector-icons/Ionicons";
import { StatusBar } from "expo-status-bar";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ComponentProps,
  type ReactNode,
} from "react";
import {
  Platform,
  StyleSheet,
  useColorScheme,
  type ViewStyle,
} from "react-native";
import { getItem, setItem } from "./storage";

export type IconName = ComponentProps<typeof Ionicons>["name"];

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };
export const radius = { sm: 8, md: 12, lg: 16, pill: 999 };
export const MAX_WIDTH = 760;

export const light = {
  bg: "#F5F6FA",
  card: "#FFFFFF",
  cardAlt: "#F8FAFC",
  text: "#0F172A",
  body: "#334155",
  muted: "#64748B",
  faint: "#94A3B8",
  line: "#E2E8F0",
  lineSoft: "#EEF1F6",
  primary: "#4338CA",
  primaryHover: "#3730A3",
  primarySoft: "#EEF2FF",
  primaryText: "#3730A3",
  primaryBorder: "#C7D2FE",
  onPrimary: "#FFFFFF",
  onPrimaryMuted: "#C7D2FE",
  onPrimarySoft: "#E0E7FF",
  hero: "#4338CA",
  danger: "#DC2626",
  dangerHover: "#B91C1C",
  dangerSoft: "#FEF2F2",
  dangerBorder: "#FECACA",
  dangerText: "#991B1B",
  ok: "#047857",
  okSoft: "#ECFDF5",
  okText: "#065F46",
  live: "#10B981",
  warn: "#B45309",
  warnSoft: "#FFFBEB",
  warnBorder: "#FCD34D",
  warnBorderSoft: "#FDE68A",
  warnText: "#92400E",
  info: "#1D4ED8",
  infoSoft: "#EFF6FF",
  neutralSoft: "#F1F5F9",
  track: "#EEF1F6",
  segTrack: "#E9ECF3",
  segOn: "#FFFFFF",
  unreadBg: "#FAFBFF",
  focusRing: "rgba(67, 56, 202, 0.15)",
  shadow:
    "0px 1px 2px rgba(15, 23, 42, 0.04), 0px 4px 12px rgba(15, 23, 42, 0.05)",
  shadowRaised: "0px 8px 24px rgba(15, 23, 42, 0.16)",
  shadowBar: "0px -4px 16px rgba(15, 23, 42, 0.06)",
  segShadow: "0px 1px 3px rgba(15, 23, 42, 0.12)",
};

export type Palette = typeof light;

/** Deep navy rather than pure black: easier on the eyes, and cards still read as raised surfaces. */
export const dark: Palette = {
  bg: "#0B1120",
  card: "#121A2B",
  cardAlt: "#172033",
  text: "#F1F5F9",
  body: "#CBD5E1",
  muted: "#94A3B8",
  faint: "#64748B",
  line: "#263247",
  lineSoft: "#1C2536",
  primary: "#6366F1",
  primaryHover: "#4F46E5",
  primarySoft: "rgba(99, 102, 241, 0.16)",
  primaryText: "#A5B4FC",
  primaryBorder: "rgba(129, 140, 248, 0.45)",
  onPrimary: "#FFFFFF",
  onPrimaryMuted: "#C7D2FE",
  onPrimarySoft: "#E0E7FF",
  hero: "#3730A3",
  danger: "#EF4444",
  dangerHover: "#DC2626",
  dangerSoft: "rgba(239, 68, 68, 0.12)",
  dangerBorder: "rgba(239, 68, 68, 0.35)",
  dangerText: "#FCA5A5",
  ok: "#34D399",
  okSoft: "rgba(52, 211, 153, 0.12)",
  okText: "#6EE7B7",
  live: "#34D399",
  warn: "#FBBF24",
  warnSoft: "rgba(251, 191, 36, 0.12)",
  warnBorder: "rgba(251, 191, 36, 0.55)",
  warnBorderSoft: "rgba(251, 191, 36, 0.3)",
  warnText: "#FCD34D",
  info: "#60A5FA",
  infoSoft: "rgba(96, 165, 250, 0.12)",
  neutralSoft: "#1E293B",
  track: "#1E293B",
  segTrack: "#0F1626",
  segOn: "#243049",
  unreadBg: "#151F38",
  focusRing: "rgba(129, 140, 248, 0.3)",
  shadow: "0px 1px 2px rgba(0, 0, 0, 0.4), 0px 6px 16px rgba(0, 0, 0, 0.22)",
  shadowRaised: "0px 10px 30px rgba(0, 0, 0, 0.55)",
  shadowBar: "0px -4px 16px rgba(0, 0, 0, 0.35)",
  segShadow: "0px 1px 3px rgba(0, 0, 0, 0.5)",
};

function makeTypeMeta(c: Palette, isDark: boolean) {
  const t = (fg: string, bg: string, dfg: string, dbg: string) =>
    isDark ? { fg: dfg, bg: dbg } : { fg, bg };
  return {
    SEAT: {
      icon: "library-outline" as IconName,
      ...t("#4338CA", "#EEF2FF", "#A5B4FC", "rgba(99, 102, 241, 0.16)"),
    },
    ROOM: {
      icon: "people-outline" as IconName,
      ...t("#0F766E", "#F0FDFA", "#5EEAD4", "rgba(45, 212, 191, 0.14)"),
    },
    COMPUTE_POOL: {
      icon: "hardware-chip-outline" as IconName,
      ...t(c.warn, c.warnSoft, c.warn, c.warnSoft),
    },
  } as Record<string, { icon: IconName; fg: string; bg: string }>;
}

function makeStatusMeta(c: Palette) {
  return {
    CONFIRMED: {
      label: "Confirmed",
      fg: c.ok,
      bg: c.okSoft,
      icon: "checkmark-circle",
    },
    WAITLISTED: {
      label: "Waitlisted",
      fg: c.warn,
      bg: c.warnSoft,
      icon: "hourglass",
    },
    COMPLETED: { label: "Completed", fg: c.info, bg: c.infoSoft, icon: "flag" },
    CANCELLED: {
      label: "Cancelled",
      fg: c.muted,
      bg: c.neutralSoft,
      icon: "close-circle",
    },
    EXPIRED: { label: "Expired", fg: c.muted, bg: c.neutralSoft, icon: "time" },
    REQUESTED: {
      label: "Pending",
      fg: c.muted,
      bg: c.neutralSoft,
      icon: "ellipsis-horizontal-circle",
    },
  } as Record<
    string,
    { label: string; fg: string; bg: string; icon: IconName }
  >;
}

function makeStyles(c: Palette) {
  const shadow: ViewStyle = { boxShadow: c.shadow };
  return StyleSheet.create({
    screen: { flex: 1, backgroundColor: c.bg },
    content: {
      padding: space.lg,
      gap: space.md,
      maxWidth: MAX_WIDTH,
      width: "100%",
      alignSelf: "center",
    },
    card: {
      backgroundColor: c.card,
      borderRadius: radius.lg,
      padding: space.lg,
      borderWidth: 1,
      borderColor: c.lineSoft,
      gap: space.xs,
      ...shadow,
    },
    h1: { fontSize: 24, fontWeight: "800", color: c.text, letterSpacing: -0.3 },
    h2: { fontSize: 20, fontWeight: "800", color: c.text, letterSpacing: -0.2 },
    title: { fontSize: 16, fontWeight: "700", color: c.text },
    section: {
      fontSize: 13,
      fontWeight: "700",
      color: c.muted,
      textTransform: "uppercase",
      letterSpacing: 0.6,
    },
    body: { fontSize: 15, color: c.body },
    muted: { color: c.muted, fontSize: 14 },
    label: { fontSize: 14, fontWeight: "600", color: c.body },
    row: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      gap: space.sm,
    },
    hstack: { flexDirection: "row", alignItems: "center", gap: space.sm },
    wrap: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
    divider: { borderBottomWidth: 1, borderBottomColor: c.lineSoft },
    chip: {
      flexDirection: "row",
      alignItems: "center",
      gap: 6,
      paddingVertical: 8,
      paddingHorizontal: 14,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: c.line,
      backgroundColor: c.card,
    },
    chipOn: { backgroundColor: c.primary, borderColor: c.primary },
    segTrack: {
      flexDirection: "row",
      backgroundColor: c.segTrack,
      borderRadius: radius.md,
      padding: 4,
      gap: 4,
    },
    segItem: {
      flex: 1,
      alignItems: "center",
      paddingVertical: 8,
      borderRadius: radius.sm,
    },
    segOn: { backgroundColor: c.segOn, boxShadow: c.segShadow },
    inputWrap: {
      flexDirection: "row",
      alignItems: "center",
      gap: 10,
      borderWidth: 1,
      borderColor: c.line,
      borderRadius: radius.md,
      paddingHorizontal: 14,
      backgroundColor: c.card,
    },
    inputFocus: {
      borderColor: c.primary,
      boxShadow: `0px 0px 0px 3px ${c.focusRing}`,
    },
    input: {
      flex: 1,
      paddingVertical: 12,
      fontSize: 16,
      color: c.text,
      outlineStyle: "none",
    } as never,
    badge: {
      flexDirection: "row",
      alignItems: "center",
      gap: 4,
      paddingVertical: 4,
      paddingHorizontal: 10,
      borderRadius: radius.pill,
      alignSelf: "flex-start",
    },
    tag: {
      flexDirection: "row",
      alignItems: "center",
      gap: 4,
      paddingVertical: 3,
      paddingHorizontal: 8,
      borderRadius: radius.sm,
      backgroundColor: c.neutralSoft,
    },
    button: {
      flexDirection: "row",
      gap: space.sm,
      borderRadius: radius.md,
      borderWidth: 1,
      paddingVertical: 13,
      paddingHorizontal: 18,
      alignItems: "center",
      justifyContent: "center",
    },
    iconButton: {
      width: 40,
      height: 40,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: c.line,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: c.card,
    },
    infoRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: space.md,
      paddingVertical: space.md,
    },
    infoIcon: {
      width: 32,
      height: 32,
      borderRadius: radius.sm,
      backgroundColor: c.primarySoft,
      alignItems: "center",
      justifyContent: "center",
    },
    empty: {
      alignItems: "center",
      gap: space.sm,
      paddingVertical: 48,
      paddingHorizontal: space.xl,
    },
    emptyIcon: {
      width: 64,
      height: 64,
      borderRadius: 32,
      backgroundColor: c.primarySoft,
      alignItems: "center",
      justifyContent: "center",
      marginBottom: space.xs,
    },
    errorBox: {
      flexDirection: "row",
      alignItems: "center",
      gap: 10,
      padding: space.md,
      borderRadius: radius.md,
      backgroundColor: c.dangerSoft,
      borderWidth: 1,
      borderColor: c.dangerBorder,
    },
    callout: {
      flexDirection: "row",
      gap: 10,
      padding: space.md,
      borderRadius: radius.md,
      alignItems: "flex-start",
    },
  });
}

function makeTheme(isDark: boolean) {
  const colors = isDark ? dark : light;
  return {
    isDark,
    colors,
    s: makeStyles(colors),
    shadow: { boxShadow: colors.shadow } as ViewStyle,
    typeMeta: makeTypeMeta(colors, isDark),
    statusMeta: makeStatusMeta(colors),
    headerOptions: {
      headerStyle: { backgroundColor: colors.card },
      headerTintColor: colors.text,
      headerTitleStyle: { fontWeight: "700" as const, fontSize: 17 },
      headerShadowVisible: false,
      contentStyle: { backgroundColor: colors.bg },
    },
  };
}

// Built once each; switching is just picking the other object.
const THEMES = { light: makeTheme(false), dark: makeTheme(true) };

export type Mode = "system" | "light" | "dark";
export type Theme = (typeof THEMES)["light"] & {
  mode: Mode;
  setMode: (m: Mode) => void;
};

const ThemeContext = createContext<Theme | null>(null);
const KEY = "theme_mode";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const [mode, setModeState] = useState<Mode>("system");

  useEffect(() => {
    getItem(KEY).then((m) => {
      if (m === "light" || m === "dark" || m === "system") setModeState(m);
    });
  }, []);

  const isDark = mode === "dark" || (mode === "system" && system === "dark");
  const base = isDark ? THEMES.dark : THEMES.light;

  // The page behind the app (web) should match, so overscroll and edges never flash white.
  useEffect(() => {
    if (Platform.OS !== "web" || typeof document === "undefined") return;
    document.body.style.backgroundColor = base.colors.bg;
    document.documentElement.style.colorScheme = isDark ? "dark" : "light";
    let meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.setAttribute("name", "theme-color");
      document.head.appendChild(meta);
    }
    meta.setAttribute("content", base.colors.card);
  }, [base, isDark]);

  const value = useMemo<Theme>(
    () => ({
      ...base,
      mode,
      setMode: (m: Mode) => {
        setModeState(m);
        setItem(KEY, m);
      },
    }),
    [base, mode],
  );

  return (
    <ThemeContext.Provider value={value}>
      <StatusBar style={isDark ? "light" : "dark"} />
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): Theme {
  const t = useContext(ThemeContext);
  if (!t) throw new Error("useTheme must be used inside ThemeProvider");
  return t;
}
