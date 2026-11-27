import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import * as Location from "expo-location";
import { useMemo, useState } from "react";
import { FlatList, Platform, ScrollView, Text, View } from "react-native";
import { listNearby, listResources } from "../../api/endpoints";
import type { Resource } from "../../api/generated";
import { useAuth } from "../../auth/AuthContext";
import { explain } from "../../lib/errors";
import { hhmm } from "../../lib/time";
import {
  Card,
  Chip,
  EmptyState,
  ErrorBox,
  Field,
  Icon,
  Loading,
  TYPE_LABEL,
  Tag,
  TypeIcon,
  colors,
  s,
  space,
  type IconName,
} from "../../ui";

const FILTERS: [string, string, IconName][] = [
  ["ALL", "All", "apps-outline"],
  ["SEAT", "Seats", "library-outline"],
  ["ROOM", "Rooms", "people-outline"],
  ["COMPUTE_POOL", "Compute", "hardware-chip-outline"],
];

const NEAR_RADIUS_M = 2000;

const fmtDistance = (m: number) =>
  m < 1000
    ? `${Math.max(10, Math.round(m / 10) * 10)} m`
    : `${(m / 1000).toFixed(1)} km`;

/** One-off position for "Near me". Never stored; it is only sent with that one search. */
async function currentPosition(): Promise<{ lat: number; lon: number }> {
  // Browsers only share location on HTTPS (or localhost); the campus server is plain HTTP.
  if (
    Platform.OS === "web" &&
    typeof window !== "undefined" &&
    !window.isSecureContext
  )
    throw new Error(
      "Your browser only shares location over a secure (HTTPS) connection. Use the Android app for Near me.",
    );
  const perm = await Location.requestForegroundPermissionsAsync();
  if (perm.status !== "granted")
    throw new Error(
      "Location permission was not given, so nearby places can't be shown.",
    );
  const pos = await Location.getCurrentPositionAsync({
    accuracy: Location.Accuracy.Balanced,
  });
  return { lat: pos.coords.latitude, lon: pos.coords.longitude };
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function ResourceCard({ r, onPress }: { r: Resource; onPress: () => void }) {
  return (
    <Card onPress={onPress}>
      <View style={[s.hstack, { gap: space.md, alignItems: "flex-start" }]}>
        <TypeIcon type={r.type} />
        <View style={{ flex: 1, gap: 6 }}>
          <Text style={s.title} numberOfLines={1}>
            {r.name}
          </Text>
          <Text style={s.muted}>
            {TYPE_LABEL[r.type]}
            {r.type !== "SEAT"
              ? ` · ${r.capacity} ${r.type === "ROOM" ? "seats" : "units"}`
              : ""}
          </Text>
          <View style={[s.wrap, { gap: 6, marginTop: 2 }]}>
            <Tag
              icon="time-outline"
              label={`${hhmm(r.open_time)}–${hhmm(r.close_time)}`}
            />
            <Tag
              icon="hourglass-outline"
              label={`${r.slot_minutes}-min slots`}
            />
            {r.policy_name !== "FIFO" && (
              <Tag icon="ribbon-outline" label="Fair queue" tone="primary" />
            )}
            {r.distance_m != null && (
              <Tag
                icon="navigate-outline"
                label={fmtDistance(r.distance_m)}
                tone="primary"
              />
            )}
          </View>
        </View>
        <Icon name="chevron-forward" size={20} color={colors.faint} />
      </View>
    </Card>
  );
}

export default function Explore() {
  const router = useRouter();
  const { user } = useAuth();
  const [type, setType] = useState("ALL");
  const [q, setQ] = useState("");
  const { data, isLoading, isError, error, refetch, isRefetching } = useQuery({
    queryKey: ["resources"],
    queryFn: () => listResources(true),
  });
  const [near, setNear] = useState<{ lat: number; lon: number } | null>(null);
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);
  const nearQ = useQuery({
    queryKey: ["resources", "near", near?.lat.toFixed(4), near?.lon.toFixed(4)],
    queryFn: () => listNearby(near!.lat, near!.lon, NEAR_RADIUS_M),
    enabled: !!near,
  });
  async function toggleNear() {
    setLocError(null);
    if (near) return setNear(null);
    setLocating(true);
    try {
      setNear(await currentPosition());
    } catch (e) {
      setLocError(
        e instanceof Error ? e.message : "Couldn't get your location.",
      );
    } finally {
      setLocating(false);
    }
  }
  const all = (near ? nearQ.data : data) ?? [];
  const counts = useMemo(() => {
    const c: Record<string, number> = { ALL: all.length };
    for (const r of all) c[r.type] = (c[r.type] ?? 0) + 1;
    return c;
  }, [all]);
  const items = useMemo(
    () =>
      all.filter(
        (r) =>
          (type === "ALL" || r.type === type) &&
          r.name.toLowerCase().includes(q.trim().toLowerCase()),
      ),
    [all, type, q],
  );
  const first = user?.name?.split(/\s+/)[0];

  const header = (
    <View style={{ gap: space.md, marginBottom: space.xs }}>
      <View style={{ gap: 4 }}>
        <Text style={s.h2}>
          {greeting()}
          {first ? `, ${first}` : ""}
        </Text>
        <Text style={s.muted}>
          Find a seat, room or compute slot and book it in seconds.
        </Text>
      </View>
      <Field
        icon="search"
        value={q}
        onChangeText={setQ}
        placeholder="Search by name"
        autoCorrect={false}
        returnKeyType="search"
      />
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View style={[s.hstack, { gap: space.sm }]}>
          <Chip
            label={locating ? "Locating…" : "Near me"}
            icon="navigate-outline"
            active={!!near}
            onPress={toggleNear}
          />
          {FILTERS.map(([key, label, ic]) => (
            <Chip
              key={key}
              label={label}
              icon={ic}
              active={type === key}
              count={data ? (counts[key] ?? 0) : undefined}
              onPress={() => setType(key)}
            />
          ))}
        </View>
      </ScrollView>
      {isError && <ErrorBox message={explain(error)} onRetry={refetch} />}
      {locError && <ErrorBox message={locError} />}
      {nearQ.isError && near && (
        <ErrorBox message={explain(nearQ.error)} onRetry={nearQ.refetch} />
      )}
      {(near ? nearQ.data : data) && (
        <Text style={s.section}>
          {items.length} {items.length === 1 ? "place" : "places"}
          {near
            ? ` within ${fmtDistance(NEAR_RADIUS_M)}, nearest first`
            : " available to you"}
        </Text>
      )}
    </View>
  );

  return (
    <FlatList
      style={s.screen}
      data={items}
      keyExtractor={(r) => r.resource_id}
      refreshing={isRefetching}
      onRefresh={refetch}
      contentContainerStyle={s.content}
      ListHeaderComponent={header}
      keyboardShouldPersistTaps="handled"
      ListEmptyComponent={
        isLoading || locating || (near && nearQ.isLoading) ? (
          <Loading label={locating ? "Finding you…" : "Loading places…"} />
        ) : isError || (near && nearQ.isError) ? undefined : near &&
          !all.length ? (
          <EmptyState
            icon="navigate-outline"
            title="Nothing close by"
            message={`No bookable places with a location within ${fmtDistance(NEAR_RADIUS_M)} of you. Turn off "Near me" to see everything.`}
          />
        ) : (
          <EmptyState
            icon="search-outline"
            title="Nothing matches"
            message={
              all.length
                ? "Try a different name or filter."
                : "There are no resources open to your account yet."
            }
          />
        )
      }
      renderItem={({ item }) => (
        <ResourceCard
          r={item}
          onPress={() => router.push(`/resource/${item.resource_id}` as never)}
        />
      )}
    />
  );
}
