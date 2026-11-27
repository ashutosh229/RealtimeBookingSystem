import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ApiError, newIdempotencyKey } from "../../api/client";
import {
  createBooking,
  getAvailability,
  getResource,
} from "../../api/endpoints";
import { explain } from "../../lib/errors";
import {
  addDays,
  fmtDay,
  fmtTime,
  hhmm,
  ymdInZone,
  ymdParts,
} from "../../lib/time";
import {
  Button,
  Callout,
  Card,
  ErrorBox,
  Icon,
  IconButton,
  InfoRow,
  Loading,
  MAX_WIDTH,
  POLICY_TEXT,
  SectionTitle,
  TYPE_LABEL,
  TypeIcon,
  colors,
  isHovered,
  radius,
  s,
  space,
} from "../../ui";

type Sel = { from: number; to: number } | null;
const DAYS = 14;

function Legend() {
  const item = (bg: string, border: string, label: string) => (
    <View style={[s.hstack, { gap: 6 }]}>
      <View
        style={{
          width: 12,
          height: 12,
          borderRadius: 4,
          backgroundColor: bg,
          borderWidth: 1,
          borderColor: border,
        }}
      />
      <Text style={[s.muted, { fontSize: 12 }]}>{label}</Text>
    </View>
  );
  return (
    <View style={[s.wrap, { gap: space.md }]}>
      {item(colors.card, colors.line, "Free")}
      {item(colors.warnSoft, "#FCD34D", "Full · waitlist")}
      {item(colors.primary, colors.primary, "Selected")}
      {item("#F1F5F9", "#F1F5F9", "Past")}
    </View>
  );
}

export default function ResourceScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const insets = useSafeAreaInsets();
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
  const dayOver =
    slots.length > 0 &&
    slots.every((sl) => new Date(sl.start_time).getTime() <= now);
  const freeCount = slots.filter(
    (sl) => new Date(sl.start_time).getTime() > now && sl.available >= qty,
  ).length;

  function tap(i: number) {
    if (!r) return;
    setErr(null);
    const len = sel ? sel.to - sel.from + 1 : 0;
    if (sel && i >= sel.from && i <= sel.to) {
      // Tapping a selected end slot shrinks the range; tapping the only slot clears it.
      if (len === 1) setSel(null);
      else if (i === sel.to) setSel({ from: sel.from, to: i - 1 });
      else if (i === sel.from) setSel({ from: i + 1, to: sel.to });
      else setSel({ from: i, to: i });
    } else if (sel && i === sel.to + 1 && len < r.max_slots_per_booking)
      setSel({ from: sel.from, to: i });
    else if (sel && i === sel.from - 1 && len < r.max_slots_per_booking)
      setSel({ from: i, to: sel.to });
    else setSel({ from: i, to: i });
  }

  async function submit() {
    if (!r || !chosen.length) return;
    const body = {
      resource_id: id,
      start_time: chosen[0].start_time,
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

  if (resQ.isLoading) return <Loading label="Loading…" />;
  if (!r)
    return (
      <View style={[s.screen, s.content]}>
        <ErrorBox message={explain(resQ.error)} onRetry={resQ.refetch} />
      </View>
    );

  const unit = r.type === "COMPUTE_POOL" ? "units" : "seats";

  return (
    <View style={s.screen}>
      <Stack.Screen options={{ title: r.name }} />
      <ScrollView contentContainerStyle={[s.content, { paddingBottom: 140 }]}>
        <Card>
          <View style={[s.hstack, { gap: space.md }]}>
            <TypeIcon type={r.type} size={52} />
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={s.h2}>{r.name}</Text>
              <Text style={s.muted}>{TYPE_LABEL[r.type]}</Text>
            </View>
          </View>
          <View style={{ marginTop: space.sm }}>
            <InfoRow
              icon="time-outline"
              label="Open"
              value={`${hhmm(r.open_time)}–${hhmm(r.close_time)}`}
            />
            {r.type !== "SEAT" && (
              <InfoRow
                icon="people-outline"
                label="Capacity"
                value={`${r.capacity} ${unit}`}
              />
            )}
            <InfoRow
              icon="hourglass-outline"
              label="Booking length"
              value={`${r.slot_minutes} min slots, up to ${r.max_slots_per_booking}`}
            />
            <InfoRow
              icon="ribbon-outline"
              label="Waitlist"
              value={POLICY_TEXT[r.policy_name] ?? r.policy_name}
              last
            />
          </View>
        </Card>

        <SectionTitle title="Choose a day" />
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={[s.hstack, { gap: space.sm }]}>
            {Array.from({ length: DAYS }, (_, i) => {
              const p = ymdParts(addDays(today, i));
              const on = offset === i;
              return (
                <Pressable
                  key={i}
                  onPress={() => setOffset(i)}
                  accessibilityRole="button"
                  accessibilityState={{ selected: on }}
                  style={(st) => {
                    const hovered = isHovered(st);
                    return [
                      {
                        width: 60,
                        paddingVertical: 10,
                        borderRadius: radius.md,
                        alignItems: "center",
                        gap: 2,
                        borderWidth: 1,
                        borderColor: on ? colors.primary : colors.line,
                        backgroundColor: on ? colors.primary : colors.card,
                      },
                      hovered && !on && { borderColor: "#C7D2FE" },
                    ];
                  }}
                >
                  <Text
                    style={{
                      fontSize: 12,
                      fontWeight: "600",
                      color: on ? "#C7D2FE" : colors.muted,
                    }}
                  >
                    {i === 0 ? "Today" : p.wk}
                  </Text>
                  <Text
                    style={{
                      fontSize: 20,
                      fontWeight: "800",
                      color: on ? "#fff" : colors.text,
                    }}
                  >
                    {p.day}
                  </Text>
                  <Text
                    style={{
                      fontSize: 11,
                      color: on ? "#C7D2FE" : colors.faint,
                    }}
                  >
                    {p.mon}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </ScrollView>

        {r.max_quantity_per_booking > 1 && (
          <Card>
            <View style={s.row}>
              <View style={{ flex: 1 }}>
                <Text style={s.title}>How many {unit}?</Text>
                <Text style={s.muted}>
                  Up to {r.max_quantity_per_booking} per booking
                </Text>
              </View>
              <View style={[s.hstack, { gap: space.md }]}>
                <IconButton
                  icon="remove"
                  label="Fewer"
                  onPress={() => setQty(Math.max(1, qty - 1))}
                  disabled={qty <= 1}
                />
                <Text style={[s.h2, { minWidth: 28, textAlign: "center" }]}>
                  {qty}
                </Text>
                <IconButton
                  icon="add"
                  label="More"
                  onPress={() =>
                    setQty(Math.min(r.max_quantity_per_booking, qty + 1))
                  }
                  disabled={qty >= r.max_quantity_per_booking}
                />
              </View>
            </View>
          </Card>
        )}

        <SectionTitle
          title={`Times · ${fmtDay(day)}`}
          right={
            availQ.data ? (
              <Text style={[s.muted, { fontSize: 12 }]}>
                {freeCount} free · updated{" "}
                {new Date(availQ.data.as_of).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </Text>
            ) : undefined
          }
        />
        <Text style={[s.muted, { marginTop: -4 }]}>
          Tap a time, then tap the next one to make it longer (up to{" "}
          {r.max_slots_per_booking} slots).
        </Text>
        <Legend />
        {availQ.isLoading && <Loading />}
        {availQ.isError && (
          <ErrorBox message={explain(availQ.error)} onRetry={availQ.refetch} />
        )}
        {availQ.data && slots.length === 0 && (
          <Callout icon="moon-outline">
            Closed on this day. Pick another date.
          </Callout>
        )}
        {dayOver && offset < DAYS - 1 && (
          <View style={{ gap: space.sm }}>
            <Callout icon="moon-outline">
              No more times today. Bookings open for the next {DAYS - 1} days.
            </Callout>
            <Button
              kind="secondary"
              icon="arrow-forward"
              title={offset === 0 ? "See tomorrow" : "See the next day"}
              onPress={() => setOffset(offset + 1)}
            />
          </View>
        )}
        <View style={[s.wrap, { gap: space.sm }]}>
          {slots.map((sl, i) => {
            const past = new Date(sl.start_time).getTime() <= now;
            const full = sl.available < qty;
            const on = !!sel && i >= sel.from && i <= sel.to;
            const few =
              !full &&
              r.type !== "SEAT" &&
              sl.available <= Math.max(1, r.capacity * 0.2);
            const bg = on
              ? colors.primary
              : past
                ? "#F1F5F9"
                : full
                  ? colors.warnSoft
                  : colors.card;
            const border = on
              ? colors.primary
              : past
                ? "#F1F5F9"
                : full
                  ? "#FCD34D"
                  : colors.line;
            const sub = past
              ? "Past"
              : full
                ? "Full · waitlist"
                : r.type === "SEAT"
                  ? "Free"
                  : `${sl.available} left`;
            return (
              <Pressable
                key={sl.start_time}
                disabled={past}
                onPress={() => tap(i)}
                accessibilityRole="button"
                accessibilityState={{ selected: on, disabled: past }}
                accessibilityLabel={`${fmtTime(sl.start_time, tz)}, ${sub}`}
                style={(st) => {
                  const hovered = isHovered(st);
                  return [
                    {
                      width: "31.5%",
                      paddingVertical: 10,
                      borderRadius: radius.md,
                      alignItems: "center",
                      gap: 2,
                      backgroundColor: bg,
                      borderWidth: 1,
                      borderColor: border,
                    },
                    hovered && !on && !past && { borderColor: colors.primary },
                  ];
                }}
              >
                <Text
                  style={{
                    fontSize: 16,
                    fontWeight: "700",
                    color: on ? "#fff" : past ? colors.faint : colors.text,
                  }}
                >
                  {fmtTime(sl.start_time, tz)}
                </Text>
                <Text
                  style={{
                    fontSize: 12,
                    fontWeight: "600",
                    color: on
                      ? "#C7D2FE"
                      : past
                        ? colors.faint
                        : full
                          ? colors.warn
                          : few
                            ? colors.warn
                            : colors.ok,
                  }}
                >
                  {sub}
                </Text>
              </Pressable>
            );
          })}
        </View>
        {err && <ErrorBox message={err} />}
      </ScrollView>

      <View
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: colors.card,
          borderTopWidth: 1,
          borderTopColor: colors.line,
          paddingBottom: Math.max(insets.bottom, space.md),
          paddingTop: space.md,
          paddingHorizontal: space.lg,
          boxShadow: "0px -4px 16px rgba(15, 23, 42, 0.06)",
        }}
      >
        <View
          style={[
            s.row,
            {
              maxWidth: MAX_WIDTH - space.lg * 2,
              width: "100%",
              alignSelf: "center",
              gap: space.md,
            },
          ]}
        >
          <View style={{ flex: 1, gap: 2 }}>
            {chosen.length ? (
              <>
                <Text style={s.title} numberOfLines={1}>
                  {fmtTime(chosen[0].start_time, tz)}–{fmtTime(endIso, tz)}
                  {qty > 1 ? ` · ${qty} ${unit}` : ""}
                </Text>
                <View style={[s.hstack, { gap: 4 }]}>
                  {anyFull && (
                    <Icon
                      name="hourglass-outline"
                      size={13}
                      color={colors.warn}
                    />
                  )}
                  <Text
                    style={[
                      s.muted,
                      { fontSize: 13 },
                      anyFull && { color: colors.warn },
                    ]}
                    numberOfLines={2}
                  >
                    {anyFull
                      ? "Full: you'll join the waitlist and be moved in automatically"
                      : `${fmtDay(day)} · ${chosen.length * r.slot_minutes} min`}
                  </Text>
                </View>
              </>
            ) : (
              <Text style={s.muted}>Select a time to continue</Text>
            )}
          </View>
          <Button
            title={anyFull ? "Join waitlist" : "Book now"}
            icon={anyFull ? "hourglass-outline" : "checkmark"}
            onPress={submit}
            disabled={!chosen.length}
            busy={busy}
            style={{ minWidth: 150 }}
          />
        </View>
      </View>
    </View>
  );
}
