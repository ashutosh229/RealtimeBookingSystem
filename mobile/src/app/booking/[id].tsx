import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { cancelBooking, getBooking, getResource } from "../../api/endpoints";
import { explain } from "../../lib/errors";
import { fmtDateTime, fmtTime } from "../../lib/time";
import {
  Badge,
  Button,
  Callout,
  Card,
  ErrorBox,
  InfoRow,
  Loading,
  SectionTitle,
  STATUS_META,
  TYPE_LABEL,
  TypeIcon,
  colors,
  radius,
  s,
  space,
} from "../../ui";

// Reason codes written by the backend in booking_status_history.
const REASON: Record<string, string> = {
  created: "Request received",
  user_cancel: "Cancelled by you",
  admin_cancel: "Cancelled by an administrator",
  promoted: "A place opened up and you were moved in",
  waitlist_expired: "The waitlist closed before a place opened",
};

export default function BookingScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const bq = useQuery({
    queryKey: ["booking", id],
    queryFn: () => getBooking(id),
    refetchInterval: (query) =>
      query.state.data?.status === "WAITLISTED" ? 10_000 : false,
  });
  const b = bq.data;
  const rq = useQuery({
    queryKey: ["resource", b?.resource_id],
    queryFn: () => getResource(b!.resource_id),
    enabled: !!b,
  });
  const r = rq.data;
  const tz = r?.timezone ?? "UTC";
  const cancel = useMutation({
    mutationFn: () => cancelBooking(id),
    onSuccess: () => {
      for (const key of ["booking", "bookings", "availability"])
        qc.invalidateQueries({ queryKey: [key] });
      setConfirm(false);
    },
  });

  if (bq.isLoading) return <Loading label="Loading booking…" />;
  if (!b)
    return (
      <View style={[s.screen, s.content]}>
        <ErrorBox message={explain(bq.error)} onRetry={bq.refetch} />
      </View>
    );
  const active = b.status === "CONFIRMED" || b.status === "WAITLISTED";
  const waiting = b.status === "WAITLISTED";
  const history = [...(b.history ?? [])].reverse();

  return (
    <ScrollView
      style={s.screen}
      contentContainerStyle={[s.content, { paddingBottom: space.xxl }]}
    >
      <Card style={{ gap: space.md }}>
        <View style={[s.hstack, { gap: space.md }]}>
          {r && <TypeIcon type={r.type} size={52} />}
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={s.h2} numberOfLines={2}>
              {r?.name ?? "Booking"}
            </Text>
            {r && <Text style={s.muted}>{TYPE_LABEL[r.type]}</Text>}
          </View>
        </View>
        <Badge status={b.status} size="md" />
        {b.status === "CONFIRMED" && (
          <Callout tone="ok">
            You're all set. Your place is reserved for the time below.
          </Callout>
        )}
      </Card>

      {waiting && (
        <Card
          style={{
            backgroundColor: colors.warnSoft,
            borderColor: "#FDE68A",
            gap: space.sm,
          }}
        >
          <View style={[s.hstack, { gap: space.lg }]}>
            <View
              style={{
                width: 64,
                height: 64,
                borderRadius: radius.lg,
                backgroundColor: colors.card,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Text
                style={{ fontSize: 11, color: colors.warn, fontWeight: "700" }}
              >
                QUEUE
              </Text>
              <Text
                style={{ fontSize: 24, fontWeight: "800", color: colors.text }}
              >
                #{b.waitlist_position ?? "—"}
              </Text>
            </View>
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={s.title}>You're on the waitlist</Text>
              <Text style={[s.body, { fontSize: 14, lineHeight: 20 }]}>
                You'll be confirmed automatically if a place frees up, and we'll
                notify you.
                {r && r.policy_name !== "FIFO"
                  ? " Order depends on recent usage, so your position is an estimate."
                  : ""}
              </Text>
            </View>
          </View>
          {b.expires_at && (
            <Text style={[s.muted, { color: "#92400E" }]}>
              The waitlist closes at {fmtTime(b.expires_at, tz)}.
            </Text>
          )}
        </Card>
      )}

      <Card style={{ paddingVertical: space.xs }}>
        <InfoRow
          icon="calendar-outline"
          label="When"
          value={fmtDateTime(b.start_time, tz)}
        />
        <InfoRow
          icon="time-outline"
          label="Until"
          value={`${fmtTime(b.end_time, tz)} (${tz})`}
        />
        {b.quantity > 1 && (
          <InfoRow
            icon="people-outline"
            label="Quantity"
            value={String(b.quantity)}
          />
        )}
        <InfoRow
          icon="create-outline"
          label="Booked"
          value={fmtDateTime(b.created_at, tz)}
        />
        <InfoRow
          icon="pricetag-outline"
          label="Reference"
          value={b.booking_id.slice(0, 8).toUpperCase()}
          last
        />
      </Card>

      {active && !confirm && (
        <Button
          kind="dangerGhost"
          icon={waiting ? "exit-outline" : "close-circle-outline"}
          title={waiting ? "Leave waitlist" : "Cancel booking"}
          onPress={() => setConfirm(true)}
        />
      )}
      {active && confirm && (
        <Card style={{ borderColor: "#FECACA", gap: space.md }}>
          <Text style={s.title}>
            {waiting ? "Leave the waitlist?" : "Cancel this booking?"}
          </Text>
          <Text style={s.muted}>
            {waiting
              ? "You'll lose your place in the queue."
              : "Your place will be offered to the next person in line. This can't be undone."}
          </Text>
          {cancel.isError && <ErrorBox message={explain(cancel.error)} />}
          <View style={[s.hstack, { gap: space.sm }]}>
            <Button
              kind="secondary"
              title="Keep it"
              onPress={() => setConfirm(false)}
              style={{ flex: 1 }}
            />
            <Button
              kind="danger"
              title={waiting ? "Leave" : "Yes, cancel"}
              onPress={() => cancel.mutate()}
              busy={cancel.isPending}
              style={{ flex: 1 }}
            />
          </View>
        </Card>
      )}
      {!active && (
        <Button
          kind="secondary"
          icon="refresh-outline"
          title="Book this place again"
          onPress={() => router.push(`/resource/${b.resource_id}` as never)}
        />
      )}

      {history.length > 0 && (
        <>
          <SectionTitle title="Activity" />
          <Card>
            {history.map((h, i) => {
              const m = STATUS_META[h.to_status] ?? STATUS_META.REQUESTED;
              const last = i === history.length - 1;
              return (
                <View
                  key={i}
                  style={[
                    s.hstack,
                    { alignItems: "flex-start", gap: space.md },
                  ]}
                >
                  <View style={{ alignItems: "center", width: 20 }}>
                    <View
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: 6,
                        marginTop: 4,
                        backgroundColor: m.fg,
                        borderWidth: 3,
                        borderColor: m.bg,
                      }}
                    />
                    {!last && (
                      <View
                        style={{
                          width: 2,
                          flex: 1,
                          minHeight: 28,
                          backgroundColor: colors.line,
                        }}
                      />
                    )}
                  </View>
                  <View
                    style={{
                      flex: 1,
                      paddingBottom: last ? 0 : space.md,
                      gap: 2,
                    }}
                  >
                    <Text style={[s.body, { fontWeight: "700" }]}>
                      {m.label}
                    </Text>
                    {h.reason && (
                      <Text style={s.muted}>
                        {REASON[h.reason] ?? h.reason}
                      </Text>
                    )}
                    <Text style={[s.muted, { fontSize: 12 }]}>
                      {fmtDateTime(h.created_at, tz)}
                    </Text>
                  </View>
                </View>
              );
            })}
          </Card>
        </>
      )}
    </ScrollView>
  );
}
