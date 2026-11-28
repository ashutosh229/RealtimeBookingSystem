import { useRouter } from "expo-router";
import { useEffect } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Icon, radius, space } from "../ui";
import { notifyMeta } from "./meta";
import { useNotifications } from "./NotificationsContext";
import { useTheme } from "../theme";

export function Banner() {
  const { colors } = useTheme();
  const { banner, dismissBanner, markRead } = useNotifications();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  useEffect(() => {
    if (!banner) return;
    const t = setTimeout(dismissBanner, 6000);
    return () => clearTimeout(t);
  }, [banner, dismissBanner]);
  if (!banner) return null;
  const bid =
    typeof banner.payload.booking_id === "string"
      ? banner.payload.booking_id
      : null;
  const m = notifyMeta(banner.type, colors);
  return (
    <View
      pointerEvents="box-none"
      style={[
        styles.wrap,
        { top: Platform.OS === "web" ? 12 : insets.top + 8 },
      ]}
    >
      <Pressable
        accessibilityRole="alert"
        style={({ pressed }) => [
          styles.banner,
          {
            borderLeftColor: m.fg,
            backgroundColor: colors.card,
            boxShadow: colors.shadowRaised,
            borderColor: colors.lineSoft,
          },
          pressed && { opacity: 0.9 },
        ]}
        onPress={() => {
          markRead(banner.id);
          dismissBanner();
          router.push((bid ? `/booking/${bid}` : "/notifications") as never);
        }}
      >
        <View style={[styles.icon, { backgroundColor: m.bg }]}>
          <Icon name={m.icon} size={20} color={m.fg} />
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={[styles.title, { color: colors.text }]}>{m.title}</Text>
          <Text
            style={[styles.text, { color: colors.muted }]}
            numberOfLines={2}
          >
            {String(banner.payload.message ?? banner.type)}
          </Text>
        </View>
        <Pressable
          onPress={dismissBanner}
          hitSlop={10}
          accessibilityLabel="Dismiss"
        >
          <Icon name="close" size={18} color={colors.faint} />
        </Pressable>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: "absolute",
    left: 12,
    right: 12,
    zIndex: 100,
    alignItems: "center",
  },
  banner: {
    width: "100%",
    maxWidth: 520,
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderLeftWidth: 4,
    padding: space.md,
    elevation: 8,
  },
  icon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  title: { fontWeight: "700", fontSize: 15 },
  text: { fontSize: 14 },
});
