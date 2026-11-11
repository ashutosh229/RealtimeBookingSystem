import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { ApiError, newIdempotencyKey } from "../../api/client";
import {
  createBooking,
  getAvailability,
  getResource,
} from "../../api/endpoints";
import { explain } from "../../lib/errors";
import { addDays, fmtDay, fmtTime, ymdInZone } from "../../lib/time";
import { Button, Card, Note, TYPE_LABEL, colors, s } from "../../ui";

type Sel = { from: number; to: number } | null;

export default function ResourceScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const resQ = useQuery({
    queryKey: ["resource", id],
    queryFn: () => getResource(id),
  });
  const r = resQ.data;
  const tz = r?.timezone ?? "UTC";
  const today = r ? ymdInZone(new Date(), tz) : "";
  const [offset, setOffset] = useState(0);
  const day = today ? addDays(today, offset) : "";
  const availQ = useQuery({
    queryKey: ["availability", id, day],
    queryFn: () => getAvailability(id, day),
    enabled: !!r && !!day,
    refetchInterval: 15_000,
  });
  const slots = availQ.data?.slots ?? [];
  const [sel, setSel] = useState<Sel>(null);
  const [qty, setQty] = useState(1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const attempt = useRef<{ fp: string; key: string } | null>(null);

  useEffect(() => {
    setSel(null);
    setErr(null);
  }, [day]);

  const now = Date.now();
  const chosen = sel ? slots.slice(sel.from, sel.to + 1) : [];
  const anyFull = chosen.some((sl) => sl.available < qty);
  const endIso =
    chosen.length && r
      ? new Date(
          new Date(chosen[chosen.length - 1].start_time).getTime() +
            r.slot_minutes * 60_000,
        ).toISOString()
      : "";

  function tap(i: number) {
    if (!r) return;
    setErr(null);
    const len = sel ? sel.to - sel.from + 1 : 0;
    if (sel && i === sel.to + 1 && len < r.max_slots_per_booking)
      setSel({ from: sel.from, to: i });
    else if (sel && i === sel.from - 1 && len < r.max_slots_per_booking)
      setSel({ from: i, to: sel.to });
    else setSel({ from: i, to: i });
  }

  async function submit() {
    if (!r || !chosen.length) return;
    const start = chosen[0].start_time;
    const body = {
      resource_id: id,
      start_time: start,
      end_time: endIso,
      quantity: qty,
      waitlist_if_full: anyFull,
    };
    // One key per attempt. A retry of the SAME request after a network error or 503 reuses it, so the server
    // returns the original result instead of booking twice. Any definitive answer starts a fresh attempt.
    const fp = JSON.stringify(body);
    if (attempt.current?.fp !== fp)
      attempt.current = { fp, key: newIdempotencyKey() };
    setBusy(true);
    setErr(null);
    try {
      const { data } = await createBooking(body, attempt.current.key);
      attempt.current = null;
      qc.invalidateQueries({ queryKey: ["availability", id] });
      qc.invalidateQueries({ queryKey: ["bookings"] });
      router.replace(`/booking/${data.booking_id}` as never);
    } catch (e) {
      const retryable =
        e instanceof ApiError &&
        (e.status === 0 || e.status === 503 || e.status === 429);
      if (!retryable) attempt.current = null;
      setErr(explain(e));
      qc.invalidateQueries({ queryKey: ["availability", id] });
    } finally {
      setBusy(false);
    }
  }

  if (resQ.isLoading) return <ActivityIndicator style={{ marginTop: 40 }} />;
  if (!r) return <Note tone="error">{explain(resQ.error)}</Note>;

  return (
    <ScrollView style={s.screen} contentContainerStyle={s.content}>
      <Stack.Screen options={{ title: r.name }} />
      <Card>
        <Text style={s.title}>{r.name}</Text>
        <Text style={s.muted}>
          {TYPE_LABEL[r.type]} · open {r.open_time}–{r.close_time} ({tz}) · up
          to {r.max_slots_per_booking} slots
        </Text>
        <Text style={s.muted}>
          Waitlist order:{" "}
          {r.policy_name === "FIFO"
            ? "first come, first served"
            : "fewer recent bookings first, then longest wait"}
        </Text>
      </Card>

      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View style={s.wrap}>
          {Array.from({ length: 14 }, (_, i) => (
            <Pressable
              key={i}
              onPress={() => setOffset(i)}
              style={[s.chip, offset === i && s.chipOn]}
            >
              <Text style={{ color: offset === i ? "#fff" : colors.text }}>
                {i === 0 ? "Today" : fmtDay(addDays(today, i))}
              </Text>
            </Pressable>
          ))}
        </View>
      </ScrollView>

      {r.max_quantity_per_booking > 1 && (
        <View style={s.row}>
          <Text style={s.title}>Quantity</Text>
          <View style={[s.row, { gap: 12 }]}>
            <Button
              kind="ghost"
              title="−"
              onPress={() => setQty(Math.max(1, qty - 1))}
              disabled={qty <= 1}
            />
            <Text style={s.title}>{qty}</Text>
            <Button
              kind="ghost"
              title="+"
              onPress={() =>
                setQty(Math.min(r.max_quantity_per_booking, qty + 1))
              }
              disabled={qty >= r.max_quantity_per_booking}
            />
          </View>
        </View>
      )}

      {availQ.isLoading && <ActivityIndicator />}
      {availQ.isError && <Note tone="error">{explain(availQ.error)}</Note>}
      <View style={s.wrap}>
        {slots.map((sl, i) => {
          const past = new Date(sl.start_time).getTime() <= now;
          const full = sl.available < qty;
          const on = !!sel && i >= sel.from && i <= sel.to;
          return (
            <Pressable
              key={sl.start_time}
              disabled={past}
              onPress={() => tap(i)}
              style={[
                s.chip,
                { minWidth: 92, alignItems: "center" },
                full && { borderColor: colors.warn },
                past && { opacity: 0.35 },
                on && s.chipOn,
              ]}
            >
              <Text
                style={{ color: on ? "#fff" : colors.text, fontWeight: "600" }}
              >
                {fmtTime(sl.start_time, tz)}
              </Text>
              <Text
                style={{
                  color: on ? "#fff" : full ? colors.warn : colors.muted,
                  fontSize: 12,
                }}
              >
                {full
                  ? "Full"
                  : r.type === "SEAT"
                    ? "Free"
                    : `${sl.available} left`}
              </Text>
            </Pressable>
          );
        })}
      </View>
      {availQ.data && (
        <Note>Updated {new Date(availQ.data.as_of).toLocaleTimeString()}</Note>
      )}

      {chosen.length > 0 && (
        <Card>
          <Text style={s.title}>
            {fmtDay(day)} · {fmtTime(chosen[0].start_time, tz)}–
            {fmtTime(endIso, tz)}
            {qty > 1 ? ` · ×${qty}` : ""}
          </Text>
          {anyFull && (
            <Note>
              Some selected slots are full. You will join the waitlist and be
              confirmed automatically if a place frees up.
            </Note>
          )}
        </Card>
      )}
      {err && <Note tone="error">{err}</Note>}
      <Button
        title={anyFull ? "Join waitlist" : "Book"}
        onPress={submit}
        disabled={!chosen.length}
        busy={busy}
      />
    </ScrollView>
  );
}
