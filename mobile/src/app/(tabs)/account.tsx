import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { myChance } from "../../api/endpoints";
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
const pct = (x?: number | null) =>
  x == null ? "—" : `${Math.round(x * 100)}%`;
const WINDOW_DAYS = 30;

/** Sub-theme 6 from the student's side: how often their attempts end with a place, against everyone's. */
function MyChanceCard() {
  const q = useQuery({
    queryKey: ["my-chance", WINDOW_DAYS],
    queryFn: () => myChance(WINDOW_DAYS),
    staleTime: 60_000,
  });
  const d = q.data;
  if (!d) return null;
  const mine = d.my_chance;
  const median = d.cohort_median;
  const note =
    mine == null
      ? "Book something and your success rate will appear here."
      : median == null
        ? "Not enough other bookings yet to compare."
        : mine >= median
          ? "You get a place at least as often as most students."
          : "You've been less lucky than most lately. Fair-share resources will give you priority on their waitlists.";
  return (
    <>
      <SectionTitle title={`Your chances · last ${WINDOW_DAYS} days`} />
      <Card style={{ gap: space.md }}>
        <View style={[s.hstack, { gap: space.lg }]}>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[s.muted, { fontSize: 13 }]}>You got a place</Text>
            <Text
              style={{ fontSize: 28, fontWeight: "800", color: colors.primary }}
            >
              {pct(mine)}
            </Text>
            <Text style={[s.muted, { fontSize: 12 }]}>
              {d.successes} of {d.attempts} attempts
            </Text>
          </View>
          <View
            style={{
              width: 1,
              alignSelf: "stretch",
              backgroundColor: colors.lineSoft,
            }}
          />
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[s.muted, { fontSize: 13 }]}>Typical student</Text>
            <Text
              style={{ fontSize: 28, fontWeight: "800", color: colors.text }}
            >
              {pct(median)}
            </Text>
            <Text style={[s.muted, { fontSize: 12 }]}>
              median of {d.cohort_users} students
            </Text>
          </View>
        </View>
        <Text style={[s.body, { fontSize: 14, lineHeight: 20 }]}>{note}</Text>
      </Card>
    </>
  );
}

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

      <MyChanceCard />

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
