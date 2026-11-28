/**
 * Design system: tokens and shared components. Every screen builds on these, so the look stays consistent.
 */
import Ionicons from "@expo/vector-icons/Ionicons";
import { useState, type ComponentProps, type ReactNode } from "react";
import Animated, { FadeInDown } from "react-native-reanimated";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type PressableStateCallbackType,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from "react-native";

/** Web-only hover state, which react-native-web adds to Pressable but the types omit. */
export const isHovered = (st: PressableStateCallbackType) =>
  (st as { hovered?: boolean }).hovered === true;

export type IconName = ComponentProps<typeof Ionicons>["name"];

export const colors = {
  bg: "#F5F6FA",
  card: "#FFFFFF",
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
  danger: "#DC2626",
  dangerSoft: "#FEF2F2",
  ok: "#047857",
  okSoft: "#ECFDF5",
  warn: "#B45309",
  warnSoft: "#FFFBEB",
  info: "#1D4ED8",
  infoSoft: "#EFF6FF",
};

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };
export const radius = { sm: 8, md: 12, lg: 16, pill: 999 };
export const shadow: ViewStyle = {
  boxShadow:
    "0px 1px 2px rgba(15, 23, 42, 0.04), 0px 4px 12px rgba(15, 23, 42, 0.05)",
};
export const MAX_WIDTH = 760;

export const TYPE_LABEL: Record<string, string> = {
  SEAT: "Study seat",
  ROOM: "Room",
  COMPUTE_POOL: "Compute pool",
};

export const TYPE_META: Record<
  string,
  { icon: IconName; fg: string; bg: string }
> = {
  SEAT: { icon: "library-outline", fg: "#4338CA", bg: "#EEF2FF" },
  ROOM: { icon: "people-outline", fg: "#0F766E", bg: "#F0FDFA" },
  COMPUTE_POOL: { icon: "hardware-chip-outline", fg: "#B45309", bg: "#FFFBEB" },
};

export const STATUS_META: Record<
  string,
  { label: string; fg: string; bg: string; icon: IconName }
> = {
  CONFIRMED: {
    label: "Confirmed",
    fg: colors.ok,
    bg: colors.okSoft,
    icon: "checkmark-circle",
  },
  WAITLISTED: {
    label: "Waitlisted",
    fg: colors.warn,
    bg: colors.warnSoft,
    icon: "hourglass",
  },
  COMPLETED: {
    label: "Completed",
    fg: colors.info,
    bg: colors.infoSoft,
    icon: "flag",
  },
  CANCELLED: {
    label: "Cancelled",
    fg: colors.muted,
    bg: "#F1F5F9",
    icon: "close-circle",
  },
  EXPIRED: { label: "Expired", fg: colors.muted, bg: "#F1F5F9", icon: "time" },
  REQUESTED: {
    label: "Pending",
    fg: colors.muted,
    bg: "#F1F5F9",
    icon: "ellipsis-horizontal-circle",
  },
};

/** "ug" -> "UG", "faculty" -> "Faculty". */
export const groupLabel = (g?: string) =>
  !g ? "—" : g.length <= 3 ? g.toUpperCase() : g[0].toUpperCase() + g.slice(1);

export const POLICY_TEXT: Record<string, string> = {
  FIFO: "First come, first served",
  FAIR_SHARE: "Fair share: people with fewer recent bookings go first",
  FAIR_SHARE_Q: "Fair share: frequent peak-time winners wait a little longer",
  FAIR_SHARE_D: "Fair share: recent bookings count more than older ones",
};

export function Icon({
  name,
  size = 18,
  color = colors.muted,
}: {
  name: IconName;
  size?: number;
  color?: string;
}) {
  return <Ionicons name={name} size={size} color={color} />;
}

export function Badge({
  status,
  size = "sm",
}: {
  status: string;
  size?: "sm" | "md";
}) {
  const m = STATUS_META[status] ?? STATUS_META.REQUESTED;
  const md = size === "md";
  return (
    <View
      style={[
        s.badge,
        { backgroundColor: m.bg },
        md && { paddingVertical: 6, paddingHorizontal: 12 },
      ]}
    >
      <Icon name={m.icon} size={md ? 16 : 13} color={m.fg} />
      <Text style={{ color: m.fg, fontSize: md ? 14 : 12, fontWeight: "700" }}>
        {m.label}
      </Text>
    </View>
  );
}

export function Tag({
  label,
  icon,
  tone = "neutral",
}: {
  label: string;
  icon?: IconName;
  tone?: "neutral" | "primary";
}) {
  const fg = tone === "primary" ? colors.primaryText : colors.body;
  return (
    <View
      style={[
        s.tag,
        tone === "primary" && { backgroundColor: colors.primarySoft },
      ]}
    >
      {icon && <Icon name={icon} size={13} color={fg} />}
      <Text style={{ color: fg, fontSize: 12, fontWeight: "600" }}>
        {label}
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
  if (!onPress) return <View style={[s.card, style]}>{children}</View>;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={(st) => {
        const { pressed } = st;
        const hovered = isHovered(st);
        return [
          s.card,
          hovered && { borderColor: "#C7D2FE" },
          pressed && { opacity: 0.85, transform: [{ scale: 0.995 }] },
          style,
        ];
      }}
    >
      {children}
    </Pressable>
  );
}

export function TypeIcon({ type, size = 44 }: { type: string; size?: number }) {
  const m = TYPE_META[type] ?? TYPE_META.SEAT;
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.3,
        backgroundColor: m.bg,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Icon name={m.icon} size={size * 0.5} color={m.fg} />
    </View>
  );
}

type ButtonKind = "primary" | "secondary" | "danger" | "ghost" | "dangerGhost";

export function Button({
  title,
  onPress,
  disabled,
  busy,
  kind = "primary",
  icon,
  size = "md",
  style,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
  kind?: ButtonKind;
  icon?: IconName;
  size?: "sm" | "md";
  style?: StyleProp<ViewStyle>;
}) {
  const look: Record<
    ButtonKind,
    { bg: string; fg: string; border: string; hover: string }
  > = {
    primary: {
      bg: colors.primary,
      fg: "#fff",
      border: colors.primary,
      hover: colors.primaryHover,
    },
    secondary: {
      bg: colors.card,
      fg: colors.text,
      border: colors.line,
      hover: "#F8FAFC",
    },
    danger: {
      bg: colors.danger,
      fg: "#fff",
      border: colors.danger,
      hover: "#B91C1C",
    },
    ghost: {
      bg: "transparent",
      fg: colors.primary,
      border: "transparent",
      hover: colors.primarySoft,
    },
    dangerGhost: {
      bg: colors.card,
      fg: colors.danger,
      border: "#FECACA",
      hover: colors.dangerSoft,
    },
  };
  const l = look[kind];
  const off = disabled || busy;
  return (
    <Pressable
      onPress={onPress}
      disabled={off}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!busy }}
      style={(st) => {
        const { pressed } = st;
        const hovered = isHovered(st);
        return [
          s.button,
          size === "sm" && { paddingVertical: 8, paddingHorizontal: 12 },
          {
            backgroundColor: hovered && !off ? l.hover : l.bg,
            borderColor: l.border,
            opacity: disabled ? 0.45 : pressed ? 0.85 : 1,
          },
          style,
        ];
      }}
    >
      {busy ? (
        <ActivityIndicator color={l.fg} />
      ) : (
        <>
          {icon && (
            <Icon name={icon} size={size === "sm" ? 16 : 18} color={l.fg} />
          )}
          <Text
            style={{
              color: l.fg,
              fontWeight: "700",
              fontSize: size === "sm" ? 14 : 16,
            }}
          >
            {title}
          </Text>
        </>
      )}
    </Pressable>
  );
}

export function IconButton({
  icon,
  onPress,
  disabled,
  label,
}: {
  icon: IconName;
  onPress: () => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityLabel={label}
      accessibilityRole="button"
      style={(st) => {
        const { pressed } = st;
        const hovered = isHovered(st);
        return [
          s.iconButton,
          hovered && { backgroundColor: colors.primarySoft },
          (pressed || disabled) && { opacity: disabled ? 0.4 : 0.7 },
        ];
      }}
    >
      <Icon name={icon} size={20} color={colors.primary} />
    </Pressable>
  );
}

export function Chip({
  label,
  active,
  onPress,
  count,
  icon,
}: {
  label: string;
  active?: boolean;
  onPress: () => void;
  count?: number;
  icon?: IconName;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: !!active }}
      style={(st) => {
        const hovered = isHovered(st);
        return [
          s.chip,
          hovered && !active && { borderColor: "#C7D2FE" },
          active && s.chipOn,
        ];
      }}
    >
      {icon && (
        <Icon name={icon} size={15} color={active ? "#fff" : colors.body} />
      )}
      <Text
        style={{
          color: active ? "#fff" : colors.body,
          fontWeight: "600",
          fontSize: 14,
        }}
      >
        {label}
      </Text>
      {count !== undefined && (
        <Text
          style={{
            color: active ? "#C7D2FE" : colors.faint,
            fontWeight: "600",
            fontSize: 13,
          }}
        >
          {count}
        </Text>
      )}
    </Pressable>
  );
}

/** Two to four equal options in one rounded track. */
export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
}: {
  options: [T, string][];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <View style={s.segTrack}>
      {options.map(([k, label]) => {
        const on = k === value;
        return (
          <Pressable
            key={String(k)}
            onPress={() => onChange(k)}
            accessibilityRole="tab"
            accessibilityState={{ selected: on }}
            style={[s.segItem, on && s.segOn]}
          >
            <Text
              style={{
                fontWeight: "700",
                fontSize: 14,
                color: on ? colors.text : colors.muted,
              }}
            >
              {label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Field({
  label,
  icon,
  secure,
  style,
  ...rest
}: TextInputProps & { label?: string; icon?: IconName; secure?: boolean }) {
  const [focus, setFocus] = useState(false);
  const [hidden, setHidden] = useState(true);
  return (
    <View style={{ gap: 6 }}>
      {label && <Text style={s.label}>{label}</Text>}
      <View style={[s.inputWrap, focus && s.inputFocus]}>
        {icon && (
          <Icon
            name={icon}
            size={18}
            color={focus ? colors.primary : colors.faint}
          />
        )}
        <TextInput
          {...rest}
          secureTextEntry={secure && hidden}
          placeholderTextColor={colors.faint}
          onFocus={(e) => {
            setFocus(true);
            rest.onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocus(false);
            rest.onBlur?.(e);
          }}
          style={[s.input, style]}
        />
        {secure && (
          <Pressable
            onPress={() => setHidden(!hidden)}
            accessibilityLabel={hidden ? "Show password" : "Hide password"}
            hitSlop={8}
          >
            <Icon name={hidden ? "eye-outline" : "eye-off-outline"} size={18} />
          </Pressable>
        )}
      </View>
    </View>
  );
}

export function SectionTitle({
  title,
  right,
}: {
  title: string;
  right?: ReactNode;
}) {
  return (
    <View style={[s.row, { marginTop: space.sm }]}>
      <Text style={s.section}>{title}</Text>
      {right}
    </View>
  );
}

export function InfoRow({
  icon,
  label,
  value,
  last,
}: {
  icon: IconName;
  label: string;
  value: ReactNode;
  last?: boolean;
}) {
  return (
    <View style={[s.infoRow, !last && s.divider]}>
      <View style={s.infoIcon}>
        <Icon name={icon} size={16} color={colors.primary} />
      </View>
      <Text style={[s.muted, { flex: 1 }]}>{label}</Text>
      <View style={{ flexShrink: 1, alignItems: "flex-end" }}>
        {typeof value === "string" ? (
          <Text style={[s.body, { fontWeight: "600", textAlign: "right" }]}>
            {value}
          </Text>
        ) : (
          value
        )}
      </View>
    </View>
  );
}

export function EmptyState({
  icon,
  title,
  message,
  action,
}: {
  icon: IconName;
  title: string;
  message?: string;
  action?: ReactNode;
}) {
  return (
    <View style={s.empty}>
      <View style={s.emptyIcon}>
        <Icon name={icon} size={28} color={colors.primary} />
      </View>
      <Text style={[s.title, { textAlign: "center" }]}>{title}</Text>
      {message && (
        <Text style={[s.muted, { textAlign: "center", maxWidth: 320 }]}>
          {message}
        </Text>
      )}
      {action}
    </View>
  );
}

export function ErrorBox({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <View style={s.errorBox}>
      <Icon name="alert-circle" size={20} color={colors.danger} />
      <Text style={{ color: "#991B1B", flex: 1, fontSize: 14 }}>{message}</Text>
      {onRetry && (
        <Button kind="ghost" size="sm" title="Retry" onPress={onRetry} />
      )}
    </View>
  );
}

export function Callout({
  children,
  tone = "info",
  icon,
}: {
  children: ReactNode;
  tone?: "info" | "warn" | "ok";
  icon?: IconName;
}) {
  const m = {
    info: {
      bg: colors.primarySoft,
      fg: colors.primaryText,
      icon: "information-circle" as IconName,
    },
    warn: {
      bg: colors.warnSoft,
      fg: "#92400E",
      icon: "hourglass-outline" as IconName,
    },
    ok: {
      bg: colors.okSoft,
      fg: "#065F46",
      icon: "checkmark-circle" as IconName,
    },
  }[tone];
  return (
    <View style={[s.callout, { backgroundColor: m.bg }]}>
      <Icon name={icon ?? m.icon} size={18} color={m.fg} />
      <Text style={{ color: m.fg, flex: 1, fontSize: 14, lineHeight: 20 }}>
        {children}
      </Text>
    </View>
  );
}

export function Loading({ label }: { label?: string }) {
  return (
    <View style={{ padding: space.xxl, alignItems: "center", gap: space.sm }}>
      <ActivityIndicator color={colors.primary} />
      {label && <Text style={s.muted}>{label}</Text>}
    </View>
  );
}

export function Avatar({ name, size = 56 }: { name?: string; size?: number }) {
  const initials =
    (name ?? "?")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase())
      .join("") || "?";
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: colors.primary,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Text style={{ color: "#fff", fontWeight: "800", fontSize: size * 0.36 }}>
        {initials}
      </Text>
    </View>
  );
}

/** Kept for older call sites: small inline text in a tone. */
export function Note({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: "muted" | "error" | "ok";
}) {
  const color =
    tone === "error" ? colors.danger : tone === "ok" ? colors.ok : colors.muted;
  return (
    <Text style={{ color, fontSize: 14, lineHeight: 20 }}>{children}</Text>
  );
}

export const headerOptions = {
  headerStyle: { backgroundColor: colors.card },
  headerTintColor: colors.text,
  headerTitleStyle: { fontWeight: "700" as const, fontSize: 17 },
  headerShadowVisible: false,
  contentStyle: { backgroundColor: colors.bg },
};

export const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: {
    padding: space.lg,
    gap: space.md,
    maxWidth: MAX_WIDTH,
    width: "100%",
    alignSelf: "center",
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    padding: space.lg,
    borderWidth: 1,
    borderColor: colors.lineSoft,
    gap: space.xs,
    ...shadow,
  },
  h1: {
    fontSize: 24,
    fontWeight: "800",
    color: colors.text,
    letterSpacing: -0.3,
  },
  h2: {
    fontSize: 20,
    fontWeight: "800",
    color: colors.text,
    letterSpacing: -0.2,
  },
  title: { fontSize: 16, fontWeight: "700", color: colors.text },
  section: {
    fontSize: 13,
    fontWeight: "700",
    color: colors.muted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  body: { fontSize: 15, color: colors.body },
  muted: { color: colors.muted, fontSize: 14 },
  label: { fontSize: 14, fontWeight: "600", color: colors.body },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: space.sm,
  },
  hstack: { flexDirection: "row", alignItems: "center", gap: space.sm },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  divider: { borderBottomWidth: 1, borderBottomColor: colors.lineSoft },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.card,
  },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  segTrack: {
    flexDirection: "row",
    backgroundColor: "#E9ECF3",
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
  segOn: {
    backgroundColor: colors.card,
    boxShadow: "0px 1px 3px rgba(15, 23, 42, 0.12)",
  },
  inputWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.md,
    paddingHorizontal: 14,
    backgroundColor: colors.card,
  },
  inputFocus: {
    borderColor: colors.primary,
    boxShadow: "0px 0px 0px 3px rgba(67, 56, 202, 0.15)",
  },
  input: {
    flex: 1,
    paddingVertical: 12,
    fontSize: 16,
    color: colors.text,
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
    backgroundColor: "#F1F5F9",
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
    borderColor: colors.line,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.card,
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
    backgroundColor: colors.primarySoft,
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
    backgroundColor: colors.primarySoft,
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
    backgroundColor: colors.dangerSoft,
    borderWidth: 1,
    borderColor: "#FECACA",
  },
  callout: {
    flexDirection: "row",
    gap: 10,
    padding: space.md,
    borderRadius: radius.md,
    alignItems: "flex-start",
  },
});

/** Fades and slides a list item in; later items wait a little longer (capped so long lists stay quick). */
export function Appear({
  index = 0,
  children,
}: {
  index?: number;
  children: ReactNode;
}) {
  return (
    <Animated.View
      entering={FadeInDown.duration(260).delay(Math.min(index, 8) * 40)}
    >
      {children}
    </Animated.View>
  );
}

/** Grey placeholder shaped like a resource or booking card, shown while data loads. */
export function SkeletonCard() {
  const bar = (w: number | `${number}%`, h = 12) => (
    <View
      style={{
        width: w,
        height: h,
        borderRadius: 6,
        backgroundColor: "#EEF1F6",
      }}
    />
  );
  return (
    <View style={[s.card, { flexDirection: "row", gap: space.md }]}>
      <View
        style={{
          width: 44,
          height: 44,
          borderRadius: 13,
          backgroundColor: "#EEF1F6",
        }}
      />
      <View style={{ flex: 1, gap: 8, paddingTop: 2 }}>
        {bar("60%", 14)}
        {bar("35%")}
        {bar("80%")}
      </View>
    </View>
  );
}

export function ProgressBar({
  value,
  color = colors.primary,
  height = 6,
}: {
  value: number;
  color?: string;
  height?: number;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <View
      style={{
        height,
        borderRadius: height / 2,
        backgroundColor: "#EEF1F6",
        overflow: "hidden",
      }}
    >
      <View
        style={{
          width: `${pct}%`,
          height,
          borderRadius: height / 2,
          backgroundColor: color,
        }}
      />
    </View>
  );
}

/** Small coloured dot plus text, e.g. "Open · closes 22:00". */
export function StatusDot({ on, label }: { on: boolean; label: string }) {
  return (
    <View style={[s.hstack, { gap: 6 }]}>
      <View
        style={{
          width: 8,
          height: 8,
          borderRadius: 4,
          backgroundColor: on ? "#10B981" : colors.faint,
        }}
      />
      <Text
        style={{
          fontSize: 13,
          fontWeight: "600",
          color: on ? colors.ok : colors.muted,
        }}
      >
        {label}
      </Text>
    </View>
  );
}
