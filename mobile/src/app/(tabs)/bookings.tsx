import { useInfiniteQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useState } from "react";
import { FlatList, Text, View } from "react-native";
import { useResourceMap } from "../../api/hooks";
import { listMyBookings } from "../../api/endpoints";
import type { Booking } from "../../api/generated";
import { explain } from "../../lib/errors";
import { dateParts, fmtTime } from "../../lib/time";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Icon,
  Loading,
  Segmented,
  TYPE_META,
  colors,
  radius,
  s,
  space,
} from "../../ui";

type View_ = "upcoming" | "past";

const isUpcoming = (b: Booking) =>
  (b.status === "CONFIRMED" || b.status === "WAITLISTED") &&
  new Date(b.end_time).getTime() > Date.now();

export default function Bookings() {
  const router = useRouter();
  const rmap = useResourceMap();
  const [view, setView] = useState<View_>("upcoming");
  const q = useInfiniteQuery({
    queryKey: ["bookings"],
    queryFn: ({ pageParam }) => listMyBookings(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  const all = q.data?.pages.flatMap((p) => p.items) ?? [];
  const upcoming = all
    .filter(isUpcoming)
    .sort((a, b) => a.start_time.localeCompare(b.start_time));
  const past = all.filter((b) => !isUpcoming(b));
  const items = view === "upcoming" ? upcoming : past;

  return (
    <FlatList
      style={s.screen}
      data={items}
      keyExtractor={(b) => b.booking_id}
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
          <Loading label="Loading your bookings…" />
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
      renderItem={({ item }) => {
        const r = rmap.get(item.resource_id);
        const tz = r?.timezone ?? "UTC";
        const d = dateParts(item.start_time, tz);
        const meta = TYPE_META[r?.type ?? "SEAT"];
        const dim = !isUpcoming(item);
        return (
          <Card
            onPress={() => router.push(`/booking/${item.booking_id}` as never)}
          >
            <View style={[s.hstack, { gap: space.md }]}>
              <View
                style={{
                  width: 56,
                  paddingVertical: 8,
                  borderRadius: radius.md,
                  alignItems: "center",
                  backgroundColor: dim ? "#F1F5F9" : meta.bg,
                }}
              >
                <Text
                  style={{
                    fontSize: 11,
                    fontWeight: "700",
                    color: dim ? colors.muted : meta.fg,
                  }}
                >
                  {d.mon.toUpperCase()}
                </Text>
                <Text
                  style={{
                    fontSize: 22,
                    fontWeight: "800",
                    color: dim ? colors.muted : colors.text,
                  }}
                >
                  {d.day}
                </Text>
                <Text style={{ fontSize: 11, color: colors.muted }}>
                  {d.wk}
                </Text>
              </View>
              <View style={{ flex: 1, gap: 4 }}>
                <Text
                  style={[s.title, dim && { color: colors.body }]}
                  numberOfLines={1}
                >
                  {r?.name ?? "Booking"}
                </Text>
                <View style={[s.hstack, { gap: 6 }]}>
                  <Icon name="time-outline" size={14} />
                  <Text style={s.muted}>
                    {fmtTime(item.start_time, tz)}–{fmtTime(item.end_time, tz)}
                    {item.quantity > 1 ? ` · ×${item.quantity}` : ""}
                  </Text>
                </View>
                <View style={[s.hstack, { gap: space.sm, flexWrap: "wrap" }]}>
                  <Badge status={item.status} />
                  {item.status === "WAITLISTED" &&
                    item.waitlist_position != null && (
                      <Text style={[s.muted, { fontSize: 13 }]}>
                        #{item.waitlist_position} in queue
                      </Text>
                    )}
                </View>
              </View>
              <Icon name="chevron-forward" size={20} color={colors.faint} />
            </View>
          </Card>
        );
      }}
    />
  );
}
