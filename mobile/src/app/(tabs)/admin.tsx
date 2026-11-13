import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from "react-native";
import {
  adminChance,
  adminRejections,
  adminSummary,
} from "../../api/endpoints";
import { explain } from "../../lib/errors";
import { Card, Note, colors, s } from "../../ui";

const pct = (x?: number | null) => `${((x ?? 0) * 100).toFixed(1)}%`;
const n2 = (x?: number | null) => (x ?? 0).toFixed(2);
function dur(sec?: number | null) {
  const v = Math.round(sec ?? 0);
  if (v < 90) return `${v}s`;
  if (v < 5400) return `${Math.round(v / 60)} min`;
  return `${(v / 3600).toFixed(1)} h`;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ minWidth: 104, gap: 2 }}>
      <Text style={{ fontSize: 20, fontWeight: "700", color: colors.text }}>
        {value}
      </Text>
      <Text style={s.muted}>{label}</Text>
    </View>
  );
}

function Bars({ values, labels }: { values: number[]; labels?: string[] }) {
  const max = Math.max(1, ...values);
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "flex-end",
        gap: 2,
        height: 84,
      }}
    >
      {values.map((v, i) => (
        <View key={i} style={{ flex: 1, alignItems: "center" }}>
          <View
            style={{
              width: "100%",
              height: Math.max(2, (v / max) * 64),
              backgroundColor: colors.primary,
              borderRadius: 2,
            }}
          />
          <Text style={{ fontSize: 9, color: colors.muted }}>
            {labels?.[i] ?? ""}
          </Text>
        </View>
      ))}
    </View>
  );
}

export default function Admin() {
  const [days, setDays] = useState(14);
  const opts = { refetchInterval: 30_000 };
  const sum = useQuery({
    queryKey: ["admin", "summary", days],
    queryFn: () => adminSummary(days),
    ...opts,
  });
  const rej = useQuery({
    queryKey: ["admin", "rejections", days],
    queryFn: () => adminRejections(days),
    ...opts,
  });
  const cha = useQuery({
    queryKey: ["admin", "chance", days],
    queryFn: () => adminChance(days),
    ...opts,
  });
  const refreshing = sum.isRefetching || rej.isRefetching || cha.isRefetching;
  const refresh = async (): Promise<void> => {
    await Promise.all([sum.refetch(), rej.refetch(), cha.refetch()]);
  };
  const firstError = sum.error ?? rej.error ?? cha.error;

  return (
    <ScrollView
      style={s.screen}
      contentContainerStyle={s.content}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={refresh} />
      }
    >
      <View style={s.wrap}>
        {[7, 14, 30].map((d) => (
          <Pressable
            key={d}
            onPress={() => setDays(d)}
            style={[s.chip, days === d && s.chipOn]}
          >
            <Text style={{ color: days === d ? "#fff" : colors.text }}>
              {d} days
            </Text>
          </Pressable>
        ))}
      </View>
      {firstError && <Note tone="error">{explain(firstError)}</Note>}
      {(sum.isLoading || rej.isLoading || cha.isLoading) && (
        <ActivityIndicator />
      )}

      {sum.data && (
        <Card>
          <Text style={s.title}>Utilization and waiting</Text>
          <View style={s.wrap}>
            <Stat label="utilization" value={pct(sum.data.utilization)} />
            <Stat
              label="Jain index (1 = equal)"
              value={n2(sum.data.jain_index)}
            />
            <Stat
              label="on waitlists now"
              value={String(sum.data.waitlist_length ?? 0)}
            />
            <Stat label="mean wait" value={dur(sum.data.wait_seconds?.mean)} />
            <Stat label="p95 wait" value={dur(sum.data.wait_seconds?.p95)} />
            <Stat label="max wait" value={dur(sum.data.wait_seconds?.max)} />
          </View>
        </Card>
      )}

      {rej.data && (
        <Card>
          <Text style={s.title}>Who gets rejected, and why</Text>
          <View style={s.wrap}>
            <Stat label="attempts" value={String(rej.data.attempts)} />
            <Stat label="confirmed" value={String(rej.data.confirmed)} />
            <Stat label="waitlisted" value={String(rej.data.waitlisted)} />
            <Stat
              label="rejected"
              value={`${rej.data.rejected} (${pct(rej.data.rejection_rate)})`}
            />
            <Stat
              label="users rejected"
              value={String(rej.data.users_rejected)}
            />
          </View>
          {Object.entries(rej.data.by_reason ?? {}).map(([reason, count]) => (
            <Text key={reason} style={s.muted}>
              {reason}: {count}
            </Text>
          ))}
          <Text style={[s.title, { marginTop: 8 }]}>By user group</Text>
          {(rej.data.by_group ?? []).map((g) => (
            <Text key={g.user_group} style={s.muted}>
              {g.user_group}: {g.rejected} of {g.attempts} rejected (
              {pct(g.rejection_rate)})
            </Text>
          ))}
          <Text style={[s.title, { marginTop: 8 }]}>
            Rejections by hour (UTC)
          </Text>
          <Bars
            values={rej.data.by_hour_utc ?? []}
            labels={(rej.data.by_hour_utc ?? []).map((_, i) =>
              i % 3 === 0 ? String(i) : "",
            )}
          />
        </Card>
      )}

      {cha.data && (
        <Card>
          <Text style={s.title}>Chance of getting a seat, per user</Text>
          <Note>
            Share of each user's attempts that ended with a seat (immediately or
            by waitlist promotion).
          </Note>
          <View style={s.wrap}>
            <Stat label="mean" value={pct(cha.data.chance_mean)} />
            <Stat label="median" value={pct(cha.data.chance_median)} />
            <Stat label="10th percentile" value={pct(cha.data.chance_p10)} />
            <Stat label="lowest" value={pct(cha.data.chance_min)} />
            <Stat label="Gini (0 = equal)" value={n2(cha.data.chance_gini)} />
            <Stat
              label="users below half the mean"
              value={pct(cha.data.chance_low_share)}
            />
          </View>
          <Text style={[s.title, { marginTop: 8 }]}>
            Users by chance (0–100% in tens)
          </Text>
          <Bars
            values={cha.data.histogram ?? []}
            labels={(cha.data.histogram ?? []).map((_, i) => `${i * 10}`)}
          />
          {(cha.data.by_group ?? []).map((g) => (
            <Text key={g.user_group} style={s.muted}>
              {g.user_group}: {g.users} users, mean chance {pct(g.mean_chance)}
            </Text>
          ))}
        </Card>
      )}
    </ScrollView>
  );
}
