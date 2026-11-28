/**
 * Design system: tokens and shared components. Every screen builds on these, so the look stays consistent.
 */
import Ionicons from "@expo/vector-icons/Ionicons";
import { useState, type ComponentProps, type ReactNode } from "react";
import Animated, { FadeInDown } from "react-native-reanimated";
import {
  ActivityIndicator,
  Pressable,
  Text,
  TextInput,
  View,
  type PressableStateCallbackType,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from "react-native";
import { MAX_WIDTH, radius, space, useTheme, type IconName } from "./theme";

export { MAX_WIDTH, radius, space, useTheme, type IconName } from "./theme";

/** Web-only hover state, which react-native-web adds to Pressable but the types omit. */
export const isHovered = (st: PressableStateCallbackType) =>
  (st as { hovered?: boolean }).hovered === true;

export const TYPE_LABEL: Record<string, string> = {
  SEAT: "Study seat",
  ROOM: "Room",
  COMPUTE_POOL: "Compute pool",
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
  color,
}: {
  name: IconName;
  size?: number;
  color?: string;
}) {
  const { colors } = useTheme();
  color = color ?? colors.muted;
  return <Ionicons name={name} size={size} color={color} />;
}

export function Badge({
  status,
  size = "sm",
}: {
  status: string;
  size?: "sm" | "md";
}) {
  const { s, statusMeta } = useTheme();
  const m = statusMeta[status] ?? statusMeta.REQUESTED;
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
  const { colors, s } = useTheme();
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
  const { colors, s } = useTheme();
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
          hovered && { borderColor: colors.primaryBorder },
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
  const { typeMeta } = useTheme();
  const m = typeMeta[type] ?? typeMeta.SEAT;
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
  const { colors, s } = useTheme();
  const look: Record<
    ButtonKind,
    { bg: string; fg: string; border: string; hover: string }
  > = {
    primary: {
      bg: colors.primary,
      fg: colors.onPrimary,
      border: colors.primary,
      hover: colors.primaryHover,
    },
    secondary: {
      bg: colors.card,
      fg: colors.text,
      border: colors.line,
      hover: colors.cardAlt,
    },
    danger: {
      bg: colors.danger,
      fg: colors.onPrimary,
      border: colors.danger,
      hover: colors.dangerHover,
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
      border: colors.dangerBorder,
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
  const { colors, s } = useTheme();
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
  const { colors, s } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: !!active }}
      style={(st) => {
        const hovered = isHovered(st);
        return [
          s.chip,
          hovered && !active && { borderColor: colors.primaryBorder },
          active && s.chipOn,
        ];
      }}
    >
      {icon && (
        <Icon
          name={icon}
          size={15}
          color={active ? colors.onPrimary : colors.body}
        />
      )}
      <Text
        style={{
          color: active ? colors.onPrimary : colors.body,
          fontWeight: "600",
          fontSize: 14,
        }}
      >
        {label}
      </Text>
      {count !== undefined && (
        <Text
          style={{
            color: active ? colors.onPrimaryMuted : colors.faint,
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
  const { colors, s } = useTheme();
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
  const { colors, s } = useTheme();
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
  const { s } = useTheme();
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
  const { colors, s } = useTheme();
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
  const { colors, s } = useTheme();
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
  const { colors, s } = useTheme();
  return (
    <View style={s.errorBox}>
      <Icon name="alert-circle" size={20} color={colors.danger} />
      <Text style={{ color: colors.dangerText, flex: 1, fontSize: 14 }}>
        {message}
      </Text>
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
  const { colors, s } = useTheme();
  const m = {
    info: {
      bg: colors.primarySoft,
      fg: colors.primaryText,
      icon: "information-circle" as IconName,
    },
    warn: {
      bg: colors.warnSoft,
      fg: colors.warnText,
      icon: "hourglass-outline" as IconName,
    },
    ok: {
      bg: colors.okSoft,
      fg: colors.okText,
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
  const { colors, s } = useTheme();
  return (
    <View style={{ padding: space.xxl, alignItems: "center", gap: space.sm }}>
      <ActivityIndicator color={colors.primary} />
      {label && <Text style={s.muted}>{label}</Text>}
    </View>
  );
}

export function Avatar({ name, size = 56 }: { name?: string; size?: number }) {
  const { colors } = useTheme();
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
      <Text
        style={{
          color: colors.onPrimary,
          fontWeight: "800",
          fontSize: size * 0.36,
        }}
      >
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
  const { colors } = useTheme();
  const color =
    tone === "error" ? colors.danger : tone === "ok" ? colors.ok : colors.muted;
  return (
    <Text style={{ color, fontSize: 14, lineHeight: 20 }}>{children}</Text>
  );
}

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
  const { colors, s } = useTheme();
  const bar = (w: number | `${number}%`, h = 12) => (
    <View
      style={{
        width: w,
        height: h,
        borderRadius: 6,
        backgroundColor: colors.track,
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
          backgroundColor: colors.track,
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
  color,
  height = 6,
}: {
  value: number;
  color?: string;
  height?: number;
}) {
  const { colors } = useTheme();
  color = color ?? colors.primary;
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <View
      style={{
        height,
        borderRadius: height / 2,
        backgroundColor: colors.track,
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
  const { colors, s } = useTheme();
  return (
    <View style={[s.hstack, { gap: 6 }]}>
      <View
        style={{
          width: 8,
          height: 8,
          borderRadius: 4,
          backgroundColor: on ? colors.live : colors.faint,
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
