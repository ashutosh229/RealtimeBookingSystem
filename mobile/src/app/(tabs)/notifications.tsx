import { useRouter } from "expo-router";
import { FlatList, Text, View } from "react-native";
import type { Notification } from "../../api/generated";
import { ago } from "../../lib/time";
import { notifyMeta } from "../../notifications/meta";
import { useNotifications } from "../../notifications/NotificationsContext";
import {
  Appear,
  Button,
  Card,
  EmptyState,
  Icon,
  colors,
  s,
  space,
} from "../../ui";

type Row =
  | { kind: "header"; key: string; label: string }
  | { kind: "note"; key: string; n: Notification; index: number };

/** Newest first, split into "Today" and "Earlier" so fresh news stands out. */
function grouped(items: Notification[]): Row[] {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const rows: Row[] = [];
  let section = "";
  items.forEach((n, index) => {
    const label = new Date(n.created_at) >= start ? "Today" : "Earlier";
    if (label !== section) {
      section = label;
      rows.push({ kind: "header", key: `h-${label}`, label });
    }
    rows.push({ kind: "note", key: String(n.id), n, index });
  });
  return rows;
}

export default function Inbox() {
  const router = useRouter();
  const { items, unread, markRead } = useNotifications();

  return (
    <FlatList
      style={s.screen}
      data={grouped(items)}
      keyExtractor={(row) => row.key}
      contentContainerStyle={s.content}
      ListHeaderComponent={
        items.length ? (
          <View style={[s.row, { marginBottom: space.xs }]}>
            <Text style={s.section}>
              {unread ? `${unread} unread` : "All caught up"}
            </Text>
            {unread > 0 && (
              <Button
                kind="ghost"
                size="sm"
                icon="checkmark-done-outline"
                title="Mark all read"
                onPress={() =>
                  items.filter((n) => !n.read_at).forEach((n) => markRead(n.id))
                }
              />
            )}
          </View>
        ) : undefined
      }
      ListEmptyComponent={
        <EmptyState
          icon="notifications-outline"
          title="No notifications yet"
          message="We'll let you know here when a booking is confirmed, cancelled, or when you move up from a waitlist."
        />
      }
      renderItem={({ item: row }) => {
        if (row.kind === "header")
          return (
            <Text style={[s.section, { marginTop: space.sm }]}>
              {row.label}
            </Text>
          );
        const item = row.n;
        const m = notifyMeta(item.type);
        const bid =
          typeof item.payload.booking_id === "string"
            ? item.payload.booking_id
            : null;
        const isNew = !item.read_at;
        return (
          <Appear index={row.index}>
            <Card
              style={
                isNew
                  ? { borderColor: "#C7D2FE", backgroundColor: "#FAFBFF" }
                  : undefined
              }
              onPress={() => {
                markRead(item.id);
                if (bid) router.push(`/booking/${bid}` as never);
              }}
            >
              <View
                style={[s.hstack, { gap: space.md, alignItems: "flex-start" }]}
              >
                <View
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 20,
                    backgroundColor: m.bg,
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Icon name={m.icon} size={22} color={m.fg} />
                </View>
                <View style={{ flex: 1, gap: 2 }}>
                  <View style={s.row}>
                    <Text
                      style={[
                        s.title,
                        { fontSize: 15, flex: 1 },
                        !isNew && { fontWeight: "600" },
                      ]}
                    >
                      {m.title}
                    </Text>
                    <Text style={[s.muted, { fontSize: 12 }]}>
                      {ago(item.created_at)}
                    </Text>
                  </View>
                  <Text style={[s.muted, { lineHeight: 20 }]}>
                    {String(item.payload.message ?? item.type)}
                  </Text>
                </View>
                {isNew && (
                  <View
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 4,
                      backgroundColor: colors.primary,
                      marginTop: 6,
                    }}
                  />
                )}
              </View>
            </Card>
          </Appear>
        );
      }}
    />
  );
}
