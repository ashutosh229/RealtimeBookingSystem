import { useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { useAuth } from "../../auth/AuthContext";
import { API_BASE } from "../../config";
import {
  Avatar,
  Button,
  Card,
  Icon,
  InfoRow,
  SectionTitle,
  Tag,
  colors,
  groupLabel,
  s,
  space,
  type IconName,
} from "../../ui";

const cap = (x?: string) => (x ? x[0].toUpperCase() + x.slice(1) : "—");

export default function Account() {
  const { user, logout } = useAuth();
  const [busy, setBusy] = useState(false);
  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content}>
      <Card
        style={{
          alignItems: "center",
          paddingVertical: space.xl,
          gap: space.sm,
        }}
      >
        <Avatar name={user?.name} size={72} />
        <Text style={[s.h2, { marginTop: space.xs }]}>{user?.name}</Text>
        <Text style={s.muted}>{user?.email}</Text>
        <View style={[s.hstack, { marginTop: space.xs }]}>
          <Tag
            icon={
              user?.role === "admin"
                ? "shield-checkmark-outline"
                : "school-outline"
            }
            label={user?.role === "admin" ? "Administrator" : "Student"}
            tone="primary"
          />
          <Tag icon="people-outline" label={groupLabel(user?.user_group)} />
        </View>
      </Card>

      <SectionTitle title="Account details" />
      <Card style={{ paddingVertical: space.xs }}>
        <InfoRow icon="mail-outline" label="Email" value={user?.email ?? "—"} />
        <InfoRow
          icon="people-outline"
          label="Group"
          value={groupLabel(user?.user_group)}
        />
        <InfoRow icon="key-outline" label="Role" value={cap(user?.role)} last />
      </Card>

      <SectionTitle title="How booking works" />
      <Card style={{ gap: space.sm }}>
        {[
          [
            "flash-outline",
            "If a slot is free, your booking is confirmed straight away.",
          ],
          [
            "hourglass-outline",
            "If it's full, join the waitlist. You'll be moved in automatically when a place frees up.",
          ],
          [
            "ribbon-outline",
            "On fair-share resources, people who've had fewer recent bookings get priority.",
          ],
          [
            "close-circle-outline",
            "Can't make it? Cancel early so someone else can use the space.",
          ],
        ].map(([icon, text]) => (
          <View
            key={text}
            style={[s.hstack, { alignItems: "flex-start", gap: space.md }]}
          >
            <View
              style={{
                width: 28,
                height: 28,
                borderRadius: 14,
                backgroundColor: colors.primarySoft,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Icon name={icon as IconName} size={15} color={colors.primary} />
            </View>
            <Text style={[s.body, { flex: 1, fontSize: 14, lineHeight: 20 }]}>
              {text}
            </Text>
          </View>
        ))}
      </Card>

      <Button
        kind="dangerGhost"
        icon="log-out-outline"
        title="Sign out"
        busy={busy}
        onPress={async () => {
          setBusy(true);
          await logout();
        }}
        style={{ marginTop: space.sm }}
      />
      <Text style={[s.muted, { textAlign: "center", fontSize: 12 }]}>
        RealTime Booking ·{" "}
        {API_BASE.replace(/^https?:\/\//, "").replace(/\/v1$/, "")}
      </Text>
    </ScrollView>
  );
}
