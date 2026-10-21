import { useQuery } from "@tanstack/react-query";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack } from "expo-router";
import { listResources, type Resource } from "../api/resources";
import { useAuth } from "../auth/AuthContext";

const LABEL: Record<Resource["type"], string> = {
  SEAT: "Seat",
  ROOM: "Room",
  COMPUTE_POOL: "Compute pool",
};

export default function Resources() {
  const { logout } = useAuth();
  const { data, isLoading, isError, error, refetch, isRefetching } = useQuery({
    queryKey: ["resources"],
    queryFn: listResources,
  });

  return (
    <View style={s.container}>
      <Stack.Screen
        options={{
          title: "Resources",
          headerRight: () => (
            <Pressable onPress={logout}>
              <Text style={s.link}>Sign out</Text>
            </Pressable>
          ),
        }}
      />
      {isLoading && <ActivityIndicator style={{ marginTop: 32 }} />}
      {isError && (
        <Text style={s.error}>Failed to load: {(error as Error).message}</Text>
      )}
      <FlatList
        data={data ?? []}
        keyExtractor={(r) => r.resource_id}
        refreshing={isRefetching}
        onRefresh={refetch}
        contentContainerStyle={{ gap: 12, padding: 16 }}
        renderItem={({ item }) => (
          <View style={s.card}>
            <Text style={s.name}>{item.name}</Text>
            <Text style={s.meta}>
              {LABEL[item.type]} · capacity {item.capacity} ·{" "}
              {item.slot_minutes}-min slots
            </Text>
            <Text style={s.meta}>
              Open {item.open_time}–{item.close_time} ({item.timezone})
            </Text>
          </View>
        )}
      />
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1 },
  card: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 10,
    padding: 14,
    backgroundColor: "#fff",
  },
  name: { fontSize: 17, fontWeight: "600" },
  meta: { color: "#555", marginTop: 2 },
  link: { color: "#2563eb", fontSize: 16 },
  error: { color: "#b91c1c", padding: 16 },
});
