import { useRouter } from "expo-router";
import { useEffect } from "react";
import { Platform, Pressable, StyleSheet, Text } from "react-native";
import { colors } from "../ui";
import { useNotifications } from "./NotificationsContext";

export function Banner() {
  const { banner, dismissBanner, markRead } = useNotifications();
  const router = useRouter();
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
  return (
    <Pressable
      style={styles.banner}
      onPress={() => {
        markRead(banner.id);
        dismissBanner();
        router.push((bid ? `/booking/${bid}` : "/notifications") as never);
      }}
    >
      <Text style={styles.text}>
        {String(banner.payload.message ?? banner.type)}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  banner: {
    position: "absolute",
    top: Platform.OS === "web" ? 8 : 48,
    left: 12,
    right: 12,
    zIndex: 100,
    elevation: 6,
    backgroundColor: colors.text,
    borderRadius: 10,
    padding: 14,
    maxWidth: 720,
    alignSelf: "center",
  },
  text: { color: "#fff", fontWeight: "600" },
});
