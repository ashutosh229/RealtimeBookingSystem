import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Stack, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, ScrollView, Text, View } from "react-native";
import { cancelBooking, getBooking, getResource } from "../../api/endpoints";
import { explain } from "../../lib/errors";
import { fmtDateTime, fmtTime } from "../../lib/time";
import { Badge, Button, Card, Note, s } from "../../ui";

export default function BookingScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
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
  const tz = rq.data?.timezone ?? "UTC";
  const cancel = useMutation({
    mutationFn: () => cancelBooking(id),
    onSuccess: () => {
      for (const key of ["booking", "bookings", "availability"])
        qc.invalidateQueries({ queryKey: [key] });
      setConfirm(false);
    },
  });

  if (bq.isLoading) return <ActivityIndicator style={{ marginTop: 40 }} />;
  if (!b) return <Note tone="error">{explain(bq.error)}</Note>;
  const active = b.status === "CONFIRMED" || b.status === "WAITLISTED";

  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content}>
      <Stack.Screen options={{ title: "Booking" }} />
      <Card>
        <View style={s.row}>
          <Text style={s.title}>{rq.data?.name ?? "Booking"}</Text>
          <Badge status={b.status} />
        </View>
        <Text style={s.muted}>
          {fmtDateTime(b.start_time, tz)} – {fmtTime(b.end_time, tz)} ({tz})
          {b.quantity > 1 ? ` · ×${b.quantity}` : ""}
        </Text>
        {b.status === "WAITLISTED" && (
          <>
            <Text style={s.title}>
              Queue position: {b.waitlist_position ?? "—"}
            </Text>
            <Note>
              {rq.data?.policy_name === "FIFO"
                ? "First come, first served."
                : "Order depends on recent usage, so this position is an estimate."}
              {b.expires_at
                ? ` The waitlist closes at ${fmtTime(b.expires_at, tz)}.`
                : ""}
            </Note>
            <Note>
              You will be confirmed automatically if a place frees up.
            </Note>
          </>
        )}
      </Card>

      {active && !confirm && (
        <Button
          kind="danger"
          title={
            b.status === "WAITLISTED" ? "Leave waitlist" : "Cancel booking"
          }
          onPress={() => setConfirm(true)}
        />
      )}
      {active && confirm && (
        <Card>
          <Text style={s.title}>Are you sure?</Text>
          {cancel.isError && <Note tone="error">{explain(cancel.error)}</Note>}
          <View style={s.row}>
            <Button
              kind="ghost"
              title="Keep it"
              onPress={() => setConfirm(false)}
            />
            <Button
              kind="danger"
              title="Yes, cancel"
              onPress={() => cancel.mutate()}
              busy={cancel.isPending}
            />
          </View>
        </Card>
      )}

      <Text style={s.title}>History</Text>
      {(b.history ?? []).map((h, i) => (
        <Card key={i}>
          <Text style={s.muted}>
            {h.from_status ? `${h.from_status} → ` : ""}
            {h.to_status}
            {h.reason ? ` (${h.reason})` : ""}
          </Text>
          <Text style={s.muted}>{fmtDateTime(h.created_at, tz)}</Text>
        </Card>
      ))}
    </ScrollView>
  );
}
