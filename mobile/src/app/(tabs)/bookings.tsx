import { useInfiniteQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useState } from "react";
import { FlatList, Text, View } from "react-native";
import { useResourceMap } from "../../api/hooks";
import { listMyBookings } from "../../api/endpoints";
import type { Booking, Resource } from "../../api/generated";
import { explain } from "../../lib/errors";
import { dateParts, dayLabel, fmtTime, until } from "../../lib/time";
import { useNow } from "../../lib/useNow";
import {
  Appear,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Icon,
  Segmented,
  SkeletonCard,
  radius,
  space,
} from "../../ui";
import { useTheme } from "../../theme";

type View_ = "upcoming" | "past";
type Row =
  | { kind: "header"; key: string; label: string; count: number }
  | { kind: "booking"; key: string; b: Booking; index: number };

const isUpcoming = (b: Booking, now: number) =>
  (b.status === "CONFIRMED" || b.status === "WAITLISTED") &&
  new Date(b.end_time).getTime() > now;

const monthLabel = (iso: string, tz: string) =>
  new Date(iso).toLocaleDateString("en-GB", {
    timeZone: tz,
    month: "long",
    year: "numeric",
  });

/** Interleave section headers ("Today", "Tomorrow", "Sat 30 Nov" / "November 2026") with bookings. */
function withHeaders(list: Booking[], label: (b: Booking) => string): Row[] {
  const rows: Row[] = [];
  let current = "";
  let header: Extract<Row, { kind: "header" }> | null = null;
  list.forEach((b, index) => {
    const l = label(b);
    if (l !== current) {
      current = l;
      header = { kind: "header", key: `h-${l}`, label: l, count: 0 };
      rows.push(header);
    }
    header!.count += 1;
    rows.push({ kind: "booking", key: b.booking_id, b, index });
  });
  return rows;
}

function BookingRow({
  b,
  r,
  now,
  onPress,
}: {
  b: Booking;
  r?: Resource;
  now: Date;
  onPress: () => void;
}) {
  const { colors, s, typeMeta } = useTheme();
  const tz = r?.timezone ?? "UTC";
  const d = dateParts(b.start_time, tz);
  const meta = typeMeta[r?.type ?? "SEAT"];
  const active = isUpcoming(b, now.getTime());
  const startMs = new Date(b.start_time).getTime();
  const soon = active && startMs - now.getTime() < 24 * 3600_000;
  const started = active && startMs <= now.getTime();
  return (
    <Card onPress={onPress}>
      <View style={[s.hstack, { gap: space.md }]}>
        <View
          style={{
            width: 56,
            paddingVertical: 8,
            borderRadius: radius.md,
            alignItems: "center",
            backgroundColor: active ? meta.bg : colors.neutralSoft,
          }}
        >
          <Text
            style={{
              fontSize: 11,
              fontWeight: "700",
              color: active ? meta.fg : colors.muted,
            }}
          >
            {d.mon.toUpperCase()}
          </Text>
          <Text
            style={{
              fontSize: 22,
              fontWeight: "800",
              color: active ? colors.text : colors.muted,
            }}
          >
            {d.day}
          </Text>
          <Text style={{ fontSize: 11, color: colors.muted }}>{d.wk}</Text>
        </View>
        <View style={{ flex: 1, gap: 4 }}>
          <Text
            style={[s.title, !active && { color: colors.body }]}
            numberOfLines={1}
          >
            {r?.name ?? "Booking"}
          </Text>
          <View style={[s.hstack, { gap: 6 }]}>
            <Icon name="time-outline" size={14} />
            <Text style={s.muted}>
              {fmtTime(b.start_time, tz)}–{fmtTime(b.end_time, tz)}
              {b.quantity > 1 ? ` · ×${b.quantity}` : ""}
            </Text>
          </View>
          <View style={[s.hstack, { gap: space.sm, flexWrap: "wrap" }]}>
            <Badge status={b.status} />
            {b.status === "WAITLISTED" && b.waitlist_position != null && (
              <Text style={[s.muted, { fontSize: 13 }]}>
                #{b.waitlist_position} in queue
              </Text>
            )}
            {soon && b.status === "CONFIRMED" && (
              <Text
                style={{ fontSize: 13, fontWeight: "700", color: colors.ok }}
              >
                {started
                  ? "Happening now"
                  : `Starts ${until(b.start_time, now.getTime())}`}
              </Text>
            )}
          </View>
        </View>
        <Icon name="chevron-forward" size={20} color={colors.faint} />
      </View>
    </Card>
  );
}

export default function Bookings() {
  const { s } = useTheme();
  const router = useRouter();
  const rmap = useResourceMap();
  const now = useNow();
  const [view, setView] = useState<View_>("upcoming");
  const q = useInfiniteQuery({
    queryKey: ["bookings"],
    queryFn: ({ pageParam }) => listMyBookings(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  const all = q.data?.pages.flatMap((p) => p.items) ?? [];
  const t = now.getTime();
  const upcoming = all
    .filter((b) => isUpcoming(b, t))
    .sort((a, b) => a.start_time.localeCompare(b.start_time));
  const past = all.filter((b) => !isUpcoming(b, t));
  const tzOf = (b: Booking) => rmap.get(b.resource_id)?.timezone ?? "UTC";
  const rows =
    view === "upcoming"
      ? withHeaders(upcoming, (b) => dayLabel(b.start_time, tzOf(b), now))
      : withHeaders(past, (b) => monthLabel(b.start_time, tzOf(b)));

  return (
    <FlatList
      style={s.screen}
      data={rows}
      keyExtractor={(row) => row.key}
      refreshing={q.isRefetching}
      onRefresh={q.refetch}
      contentContainerStyle={s.content}
      ListHeaderComponent={
        <View style={{ gap: space.md, marginBottom: space.xs }}>
          <Segmented<View_>
            options={[
              ["upcoming", `Upcoming${q.data ? ` (${upcoming.length})` : ""}`],
              ["past", "Past & cancelled"],
            ]}
            value={view}
            onChange={setView}
          />
          {q.isError && (
            <ErrorBox message={explain(q.error)} onRetry={q.refetch} />
          )}
        </View>
      }
      ListEmptyComponent={
        q.isLoading ? (
          <View style={{ gap: space.md }}>
            {[0, 1, 2].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </View>
        ) : q.isError ? undefined : view === "upcoming" ? (
          <EmptyState
            icon="calendar-outline"
            title="No upcoming bookings"
            message="Find a seat, room or compute slot and it will show up here."
            action={
              <Button
                title="Browse places"
                icon="compass-outline"
                onPress={() => router.push("/" as never)}
                style={{ marginTop: space.sm }}
              />
            }
          />
        ) : (
          <EmptyState
            icon="archive-outline"
            title="Nothing here yet"
            message="Past and cancelled bookings appear here."
          />
        )
      }
      ListFooterComponent={
        q.hasNextPage ? (
          <Button
            kind="secondary"
            title="Load older bookings"
            onPress={() => q.fetchNextPage()}
            busy={q.isFetchingNextPage}
          />
        ) : undefined
      }
      renderItem={({ item: row }) =>
        row.kind === "header" ? (
          <View style={[s.row, { marginTop: space.sm }]}>
            <Text style={s.section}>{row.label}</Text>
            <Text style={[s.muted, { fontSize: 12 }]}>
              {row.count} {row.count === 1 ? "booking" : "bookings"}
            </Text>
          </View>
        ) : (
          <Appear index={row.index}>
            <BookingRow
              b={row.b}
              r={rmap.get(row.b.resource_id)}
              now={now}
              onPress={() =>
                router.push(`/booking/${row.b.booking_id}` as never)
              }
            />
          </Appear>
        )
      }
    />
  );
}
