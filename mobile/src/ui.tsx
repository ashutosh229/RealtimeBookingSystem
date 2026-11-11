import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from "react-native";

export const colors = {
  bg: "#f5f6f8",
  card: "#ffffff",
  text: "#111827",
  muted: "#6b7280",
  line: "#e5e7eb",
  primary: "#2563eb",
  danger: "#b91c1c",
  ok: "#15803d",
  warn: "#b45309",
};

export const TYPE_LABEL: Record<string, string> = {
  SEAT: "Seat",
  ROOM: "Room",
  COMPUTE_POOL: "Compute pool",
};

const STATUS: Record<string, [string, string]> = {
  CONFIRMED: ["#dcfce7", "#166534"],
  WAITLISTED: ["#fef3c7", "#92400e"],
  CANCELLED: ["#e5e7eb", "#374151"],
  COMPLETED: ["#dbeafe", "#1e40af"],
  EXPIRED: ["#e5e7eb", "#374151"],
  REQUESTED: ["#e5e7eb", "#374151"],
};

export function Badge({ status }: { status: string }) {
  const [bg, fg] = STATUS[status] ?? STATUS.REQUESTED;
  return (
    <View style={[s.badge, { backgroundColor: bg }]}>
      <Text style={{ color: fg, fontSize: 12, fontWeight: "700" }}>
        {status}
      </Text>
    </View>
  );
}

export function Card({
  children,
  onPress,
  style,
}: {
  children: ReactNode;
  onPress?: () => void;
  style?: StyleProp<ViewStyle>;
}) {
  const body = <View style={[s.card, style]}>{children}</View>;
  return onPress ? <Pressable onPress={onPress}>{body}</Pressable> : body;
}

export function Button({
  title,
  onPress,
  disabled,
  busy,
  kind = "primary",
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  kind?: "primary" | "danger" | "ghost";
}) {
  const bg =
    kind === "primary"
      ? colors.primary
      : kind === "danger"
        ? colors.danger
        : "transparent";
  const fg = kind === "ghost" ? colors.primary : "#fff";
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || busy}
      style={[
        s.button,
        { backgroundColor: bg, opacity: disabled || busy ? 0.5 : 1 },
        kind === "ghost" && s.ghost,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={fg} />
      ) : (
        <Text style={{ color: fg, fontWeight: "700", fontSize: 16 }}>
          {title}
        </Text>
      )}
    </Pressable>
  );
}

export function Note({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: "muted" | "error" | "ok";
}) {
  const color =
    tone === "error" ? colors.danger : tone === "ok" ? colors.ok : colors.muted;
  return <Text style={{ color, fontSize: 14 }}>{children}</Text>;
}

export const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: {
    padding: 16,
    gap: 12,
    maxWidth: 720,
    width: "100%",
    alignSelf: "center",
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.line,
    gap: 4,
  },
  h1: { fontSize: 20, fontWeight: "700", color: colors.text },
  title: { fontSize: 16, fontWeight: "600", color: colors.text },
  muted: { color: colors.muted, fontSize: 14 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.card,
  },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  input: {
    borderWidth: 1,
    borderColor: "#bbb",
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    backgroundColor: "#fff",
  },
  badge: { paddingVertical: 2, paddingHorizontal: 8, borderRadius: 10 },
  button: {
    borderRadius: 8,
    padding: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  ghost: { borderWidth: 1, borderColor: colors.primary },
});
