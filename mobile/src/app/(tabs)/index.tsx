import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  Text,
  TextInput,
  View,
} from "react-native";
import { listResources } from "../../api/endpoints";
import type { Resource } from "../../api/generated";
import { explain } from "../../lib/errors";
import { Card, Note, TYPE_LABEL, s } from "../../ui";

const FILTERS: [string, string][] = [
  ["ALL", "All"],
  ["SEAT", "Seats"],
  ["ROOM", "Rooms"],
  ["COMPUTE_POOL", "Compute"],
];

export default function Resources() {
  const router = useRouter();
  const [type, setType] = useState("ALL");
  const [q, setQ] = useState("");
  const { data, isLoading, isError, error, refetch, isRefetching } = useQuery({
    queryKey: ["resources"],
    queryFn: () => listResources(true),
  });
  const items = useMemo(
    () =>
      (data ?? []).filter(
        (r: Resource) =>
          (type === "ALL" || r.type === type) &&
          r.name.toLowerCase().includes(q.trim().toLowerCase()),
      ),
    [data, type, q],
  );

  return (
    <View style={s.screen}>
      <View style={[s.content, { paddingBottom: 0 }]}>
        <TextInput
          style={s.input}
          value={q}
          onChangeText={setQ}
          placeholder="Search by name"
        />
        <View style={s.wrap}>
          {FILTERS.map(([key, label]) => (
            <Pressable
              key={key}
              onPress={() => setType(key)}
              style={[s.chip, type === key && s.chipOn]}
            >
              <Text style={{ color: type === key ? "#fff" : "#111827" }}>
                {label}
              </Text>
            </Pressable>
          ))}
        </View>
        {isLoading && <ActivityIndicator />}
        {isError && <Note tone="error">{explain(error)}</Note>}
      </View>
      <FlatList
        data={items}
        keyExtractor={(r) => r.resource_id}
        refreshing={isRefetching}
        onRefresh={refetch}
        contentContainerStyle={s.content}
        ListEmptyComponent={
          !isLoading ? <Note>No resources match.</Note> : undefined
        }
        renderItem={({ item }) => (
          <Card
            onPress={() =>
              router.push(`/resource/${item.resource_id}` as never)
            }
          >
            <Text style={s.title}>{item.name}</Text>
            <Text style={s.muted}>
              {TYPE_LABEL[item.type]}
              {item.type !== "SEAT"
                ? ` · capacity ${item.capacity}`
                : ""} · {item.slot_minutes}-min slots
            </Text>
            <Text style={s.muted}>
              Open {item.open_time}–{item.close_time} ({item.timezone})
            </Text>
          </Card>
        )}
      />
    </View>
  );
}
