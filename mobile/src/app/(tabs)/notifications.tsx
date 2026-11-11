import { useRouter } from "expo-router";
import { FlatList, Text, View } from "react-native";
import { useNotifications } from "../../notifications/NotificationsContext";
import { Card, Note, colors, s } from "../../ui";

export default function Inbox() {
  const router = useRouter();
  const { items, markRead } = useNotifications();
  return (
    <View style={s.screen}>
      <FlatList
        data={items}
        keyExtractor={(n) => String(n.id)}
        contentContainerStyle={s.content}
        ListEmptyComponent={<Note>No notifications yet.</Note>}
        renderItem={({ item }) => {
          const bid =
            typeof item.payload.booking_id === "string"
              ? item.payload.booking_id
              : null;
          return (
            <Card
              style={
                !item.read_at ? { borderColor: colors.primary } : undefined
              }
              onPress={() => {
                markRead(item.id);
                if (bid) router.push(`/booking/${bid}` as never);
              }}
            >
              <Text
                style={[s.title, { fontWeight: item.read_at ? "400" : "700" }]}
              >
                {String(item.payload.message ?? item.type)}
              </Text>
              <Text style={s.muted}>
                {new Date(item.created_at).toLocaleString()}
              </Text>
            </Card>
          );
        }}
      />
    </View>
  );
}
