import { useInfiniteQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { ActivityIndicator, FlatList, Text, View } from "react-native";
import { useResourceMap } from "../../api/hooks";
import { listMyBookings } from "../../api/endpoints";
import { explain } from "../../lib/errors";
import { fmtDateTime, fmtTime } from "../../lib/time";
import { Badge, Button, Card, Note, s } from "../../ui";

export default function Bookings() {
  const router = useRouter();
  const rmap = useResourceMap();
  const q = useInfiniteQuery({
    queryKey: ["bookings"],
    queryFn: ({ pageParam }) => listMyBookings(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <View style={s.screen}>
      {q.isLoading && <ActivityIndicator style={{ marginTop: 24 }} />}
      {q.isError && <Note tone="error">{explain(q.error)}</Note>}
      <FlatList
        data={items}
        keyExtractor={(b) => b.booking_id}
        refreshing={q.isRefetching}
        onRefresh={q.refetch}
        contentContainerStyle={s.content}
        ListEmptyComponent={
          !q.isLoading ? <Note>No bookings yet.</Note> : undefined
        }
        ListFooterComponent={
          q.hasNextPage ? (
            <Button
              kind="ghost"
              title="Load more"
              onPress={() => q.fetchNextPage()}
              busy={q.isFetchingNextPage}
            />
          ) : undefined
        }
        renderItem={({ item }) => {
          const r = rmap.get(item.resource_id);
          const tz = r?.timezone ?? "UTC";
          return (
            <Card
              onPress={() =>
                router.push(`/booking/${item.booking_id}` as never)
              }
            >
              <View style={s.row}>
                <Text style={s.title}>{r?.name ?? "Booking"}</Text>
                <Badge status={item.status} />
              </View>
              <Text style={s.muted}>
                {fmtDateTime(item.start_time, tz)} –{" "}
                {fmtTime(item.end_time, tz)}
                {item.quantity > 1 ? ` · ×${item.quantity}` : ""}
              </Text>
              {item.status === "WAITLISTED" && (
                <Text style={s.muted}>
                  Queue position {item.waitlist_position ?? "—"}
                </Text>
              )}
            </Card>
          );
        }}
      />
    </View>
  );
}
