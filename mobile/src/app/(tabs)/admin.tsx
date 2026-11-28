import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useState } from "react";
import { FlatList, RefreshControl, ScrollView, Text, View } from "react-native";
import {
  adminChance,
  adminListResources,
  adminRejections,
  adminSummary,
} from "../../api/endpoints";
import { hhmm } from "../../lib/time";
import { explain } from "../../lib/errors";
import {
  Button,
  Card,
  EmptyState,
  ErrorBox,
  Icon,
  Loading,
  MAX_WIDTH,
  Segmented,
  TYPE_LABEL,
  Tag,
  TypeIcon,
  groupLabel,
  radius,
  space,
  type IconName,
} from "../../ui";
import { useTheme } from "../../theme";

const pct = (x?: number | null) => `${((x ?? 0) * 100).toFixed(1)}%`;
const n2 = (x?: number | null) => (x ?? 0).toFixed(2);
function dur(sec?: number | null) {
  const v = Math.round(sec ?? 0);
  if (v < 90) return `${v}s`;
  if (v < 5400) return `${Math.round(v / 60)} min`;
  return `${(v / 3600).toFixed(1)} h`;
}
const REASONS: Record<string, string> = {
  CAPACITY_UNAVAILABLE: "Full, no waitlist",
  USER_LIMIT_REACHED: "User limit reached",
  NOT_ELIGIBLE: "Not eligible",
  OUT_OF_HOURS: "Outside opening hours",
  OUT_OF_HORIZON: "Too far ahead",
  INVALID_INTERVAL: "Invalid time",
  QUANTITY_OUT_OF_RANGE: "Quantity not allowed",
  RESOURCE_INACTIVE: "Resource inactive",
  RATE_LIMITED: "Rate limited (surge)",
  SERVICE_BUSY: "Server busy",
};

/** One headline number. `tone` colours the value by whether it is good. */
function Kpi({
  icon,
  label,
  value,
  hint,
  tone,
}: {
  icon: IconName;
  label: string;
  value: string;
  hint?: string;
  tone?: "good" | "warn" | "bad";
}) {
  const { colors, s } = useTheme();
  const fg =
    tone === "good"
      ? colors.ok
      : tone === "warn"
        ? colors.warn
        : tone === "bad"
          ? colors.danger
          : colors.text;
  return (
    <View
      style={{
        flexGrow: 1,
        flexBasis: 150,
        padding: space.md,
        borderRadius: radius.md,
        backgroundColor: colors.cardAlt,
        gap: 4,
      }}
    >
      <View style={[s.hstack, { gap: 6 }]}>
        <Icon name={icon} size={15} color={colors.muted} />
        <Text style={[s.muted, { fontSize: 13 }]}>{label}</Text>
      </View>
      <Text
        style={{
          fontSize: 24,
          fontWeight: "800",
          color: fg,
          letterSpacing: -0.3,
        }}
      >
        {value}
      </Text>
      {hint && (
        <Text style={{ fontSize: 12, color: colors.faint }}>{hint}</Text>
      )}
    </View>
  );
}

function Panel({
  icon,
  title,
  subtitle,
  children,
}: {
  icon: IconName;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  const { colors, s } = useTheme();
  return (
    <Card style={{ gap: space.md }}>
      <View style={[s.hstack, { gap: space.md, alignItems: "flex-start" }]}>
        <View
          style={{
            width: 36,
            height: 36,
            borderRadius: radius.sm,
            backgroundColor: colors.primarySoft,
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Icon name={icon} size={18} color={colors.primary} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>{title}</Text>
          {subtitle && (
            <Text style={[s.muted, { fontSize: 13, lineHeight: 18 }]}>
              {subtitle}
            </Text>
          )}
        </View>
      </View>
      {children}
    </Card>
  );
}

/** Label, value and a proportional bar: for breakdowns by reason or group. */
function BarRow({
  label,
  value,
  frac,
  color,
}: {
  label: string;
  value: string;
  frac: number;
  color?: string;
}) {
  const { colors, s } = useTheme();
  color = color ?? colors.primary;
  return (
    <View style={{ gap: 6 }}>
      <View style={s.row}>
        <Text style={[s.body, { fontSize: 14, flex: 1 }]} numberOfLines={1}>
          {label}
        </Text>
        <Text style={[s.body, { fontSize: 14, fontWeight: "700" }]}>
          {value}
        </Text>
      </View>
      <View
        style={{
          height: 8,
          borderRadius: 4,
          backgroundColor: colors.track,
          overflow: "hidden",
        }}
      >
        <View
          style={{
            height: 8,
            borderRadius: 4,
            width: `${Math.max(2, Math.min(100, frac * 100))}%`,
            backgroundColor: color,
          }}
        />
      </View>
    </View>
  );
}

function Histogram({
  values,
  labels,
  color,
}: {
  values: number[];
  labels: string[];
  color?: string;
}) {
  const { colors } = useTheme();
  color = color ?? colors.primary;
  const max = Math.max(1, ...values);
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "flex-end",
        gap: 3,
        height: 120,
      }}
    >
      {values.map((v, i) => (
        <View key={i} style={{ flex: 1, alignItems: "center", gap: 4 }}>
          <View
            style={{
              width: "100%",
              height: Math.max(3, (v / max) * 92),
              backgroundColor: v ? color : colors.line,
              borderTopLeftRadius: 4,
              borderTopRightRadius: 4,
            }}
          />
          <Text style={{ fontSize: 10, color: colors.faint }}>{labels[i]}</Text>
        </View>
      ))}
    </View>
  );
}

function Insights() {
  const { colors, s } = useTheme();
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
  const loading = sum.isLoading || rej.isLoading || cha.isLoading;

  const jain = sum.data?.jain_index ?? 0;
  const reasons = Object.entries(rej.data?.by_reason ?? {}).sort(
    (a, b) => b[1] - a[1],
  );
  const reasonMax = Math.max(1, ...reasons.map(([, c]) => c));

  return (
    <ScrollView
      style={s.screen}
      contentContainerStyle={[s.content, { paddingBottom: space.xxl }]}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={refresh} />
      }
    >
      <View style={[s.row, { flexWrap: "wrap" }]}>
        <View style={{ gap: 2, flexShrink: 1 }}>
          <Text style={s.h2}>Allocation health</Text>
          <Text style={s.muted}>
            Live from the booking database · refreshes every 30 s
          </Text>
        </View>
        <View style={{ minWidth: 240 }}>
          <Segmented<number>
            options={[
              [7, "7 days"],
              [14, "14 days"],
              [30, "30 days"],
            ]}
            value={days}
            onChange={setDays}
          />
        </View>
      </View>
      {firstError && (
        <ErrorBox message={explain(firstError)} onRetry={refresh} />
      )}
      {loading && <Loading label="Crunching numbers…" />}

      {sum.data && (
        <Panel
          icon="speedometer-outline"
          title="Utilization and waiting"
          subtitle="How fully places are used, and how long people wait for them."
        >
          <View style={[s.wrap, { gap: space.sm }]}>
            <Kpi
              icon="pie-chart-outline"
              label="Utilization"
              value={pct(sum.data.utilization)}
            />
            <Kpi
              icon="ribbon-outline"
              label="Fairness (Jain)"
              value={n2(jain)}
              hint="1.00 = perfectly equal"
              tone={jain >= 0.85 ? "good" : jain >= 0.6 ? "warn" : "bad"}
            />
            <Kpi
              icon="people-outline"
              label="On waitlists now"
              value={String(sum.data.waitlist_length ?? 0)}
            />
            <Kpi
              icon="time-outline"
              label="Mean wait"
              value={dur(sum.data.wait_seconds?.mean)}
            />
            <Kpi
              icon="trending-up-outline"
              label="95th pct wait"
              value={dur(sum.data.wait_seconds?.p95)}
            />
            <Kpi
              icon="alarm-outline"
              label="Longest wait"
              value={dur(sum.data.wait_seconds?.max)}
            />
          </View>
        </Panel>
      )}

      {rej.data && (
        <Panel
          icon="shield-outline"
          title="Who gets turned away, and why"
          subtitle="Every booking attempt in the window, including ones that were refused."
        >
          <View style={[s.wrap, { gap: space.sm }]}>
            <Kpi
              icon="enter-outline"
              label="Attempts"
              value={String(rej.data.attempts)}
            />
            <Kpi
              icon="checkmark-circle-outline"
              label="Confirmed"
              value={String(rej.data.confirmed)}
              tone="good"
            />
            <Kpi
              icon="hourglass-outline"
              label="Waitlisted"
              value={String(rej.data.waitlisted)}
            />
            <Kpi
              icon="close-circle-outline"
              label="Rejected"
              value={String(rej.data.rejected)}
              hint={`${pct(rej.data.rejection_rate)} of attempts · ${rej.data.users_rejected} users`}
              tone={
                rej.data.rejection_rate > 0.3
                  ? "bad"
                  : rej.data.rejection_rate > 0.1
                    ? "warn"
                    : undefined
              }
            />
          </View>
          {reasons.length > 0 && (
            <View style={{ gap: space.md }}>
              <Text style={s.section}>By reason</Text>
              {reasons.map(([reason, count]) => (
                <BarRow
                  key={reason}
                  label={REASONS[reason] ?? reason}
                  value={String(count)}
                  frac={count / reasonMax}
                  color={colors.danger}
                />
              ))}
            </View>
          )}
          {(rej.data.by_group ?? []).length > 0 && (
            <View style={{ gap: space.md }}>
              <Text style={s.section}>Rejection rate by group</Text>
              {rej.data.by_group.map((g) => (
                <BarRow
                  key={g.user_group}
                  label={`${groupLabel(g.user_group)} · ${g.rejected}/${g.attempts}`}
                  value={pct(g.rejection_rate)}
                  frac={g.rejection_rate}
                  color={colors.warn}
                />
              ))}
            </View>
          )}
          <View style={{ gap: space.sm }}>
            <Text style={s.section}>Rejections by hour of day (UTC)</Text>
            <Histogram
              values={rej.data.by_hour_utc ?? []}
              labels={(rej.data.by_hour_utc ?? []).map((_, i) =>
                i % 3 === 0 ? String(i) : "",
              )}
              color={colors.danger}
            />
          </View>
        </Panel>
      )}

      {cha.data && (
        <Panel
          icon="dice-outline"
          title="Each person's chance of getting a place"
          subtitle="Share of each user's attempts that ended with a place, straight away or from the waitlist."
        >
          <View style={[s.wrap, { gap: space.sm }]}>
            <Kpi
              icon="analytics-outline"
              label="Average chance"
              value={pct(cha.data.chance_mean)}
            />
            <Kpi
              icon="git-commit-outline"
              label="Median"
              value={pct(cha.data.chance_median)}
            />
            <Kpi
              icon="arrow-down-outline"
              label="Bottom 10%"
              value={pct(cha.data.chance_p10)}
            />
            <Kpi
              icon="remove-circle-outline"
              label="Lowest"
              value={pct(cha.data.chance_min)}
            />
            <Kpi
              icon="ribbon-outline"
              label="Inequality (Gini)"
              value={n2(cha.data.chance_gini)}
              hint="0.00 = everyone equal"
              tone={
                cha.data.chance_gini <= 0.2
                  ? "good"
                  : cha.data.chance_gini <= 0.4
                    ? "warn"
                    : "bad"
              }
            />
            <Kpi
              icon="alert-circle-outline"
              label="Left behind"
              value={pct(cha.data.chance_low_share)}
              hint="below half the average chance"
            />
          </View>
          <View style={{ gap: space.sm }}>
            <Text style={s.section}>Users by chance of success</Text>
            <Histogram
              values={cha.data.histogram ?? []}
              labels={(cha.data.histogram ?? []).map((_, i) => `${i * 10}%`)}
            />
          </View>
          {(cha.data.by_group ?? []).length > 0 && (
            <View style={{ gap: space.md }}>
              <Text style={s.section}>Average chance by group</Text>
              {cha.data.by_group.map((g) => (
                <BarRow
                  key={g.user_group}
                  label={`${groupLabel(g.user_group)} · ${g.users} users`}
                  value={pct(g.mean_chance)}
                  frac={g.mean_chance}
                  color={colors.ok}
                />
              ))}
            </View>
          )}
        </Panel>
      )}
    </ScrollView>
  );
}

function ManageResources() {
  const { colors, s } = useTheme();
  const router = useRouter();
  const q = useQuery({
    queryKey: ["admin-resources"],
    queryFn: adminListResources,
  });
  const items = [...(q.data ?? [])].sort(
    (a, b) =>
      Number(b.active) - Number(a.active) || a.name.localeCompare(b.name),
  );
  return (
    <FlatList
      style={s.screen}
      data={items}
      keyExtractor={(r) => r.resource_id}
      refreshing={q.isRefetching}
      onRefresh={q.refetch}
      contentContainerStyle={[s.content, { paddingTop: 0 }]}
      ListHeaderComponent={
        <View style={{ gap: space.md, marginBottom: space.xs }}>
          <View style={[s.row, { flexWrap: "wrap" }]}>
            <View style={{ gap: 2, flexShrink: 1 }}>
              <Text style={s.h2}>Resources</Text>
              <Text style={s.muted}>
                {q.data
                  ? `${q.data.filter((r) => r.active).length} active · ${q.data.filter((r) => !r.active).length} inactive`
                  : "Seats, rooms and compute pools"}
              </Text>
            </View>
            <Button
              title="New resource"
              icon="add"
              size="sm"
              onPress={() => router.push("/manage/new" as never)}
            />
          </View>
          {q.isError && (
            <ErrorBox message={explain(q.error)} onRetry={q.refetch} />
          )}
        </View>
      }
      ListEmptyComponent={
        q.isLoading ? (
          <Loading label="Loading resources…" />
        ) : q.isError ? undefined : (
          <EmptyState
            icon="cube-outline"
            title="No resources yet"
            message="Create the first seat, room or compute pool students can book."
          />
        )
      }
      renderItem={({ item: r }) => (
        <Card
          onPress={() => router.push(`/manage/${r.resource_id}` as never)}
          style={!r.active ? { opacity: 0.7 } : undefined}
        >
          <View style={[s.hstack, { gap: space.md }]}>
            <TypeIcon type={r.type} />
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={s.title} numberOfLines={1}>
                {r.name}
              </Text>
              <View style={[s.wrap, { gap: 6 }]}>
                <Tag label={TYPE_LABEL[r.type]} />
                {r.type !== "SEAT" && (
                  <Tag icon="people-outline" label={String(r.capacity)} />
                )}
                <Tag
                  icon="time-outline"
                  label={`${hhmm(r.open_time)}–${hhmm(r.close_time)}`}
                />
                {!r.active && (
                  <Tag icon="pause-circle-outline" label="Inactive" />
                )}
                {(r.eligible_groups ?? []).length > 0 && (
                  <Tag
                    icon="lock-closed-outline"
                    label={(r.eligible_groups ?? []).map(groupLabel).join(", ")}
                  />
                )}
              </View>
            </View>
            <Icon name="chevron-forward" size={20} color={colors.faint} />
          </View>
        </Card>
      )}
    />
  );
}

type Mode = "insights" | "resources";

export default function Admin() {
  const { s } = useTheme();
  const [mode, setMode] = useState<Mode>("insights");
  return (
    <View style={s.screen}>
      <View
        style={{
          paddingHorizontal: space.lg,
          paddingTop: space.lg,
          paddingBottom: mode === "resources" ? space.md : 0,
          maxWidth: MAX_WIDTH,
          width: "100%",
          alignSelf: "center",
        }}
      >
        <Segmented<Mode>
          options={[
            ["insights", "Insights"],
            ["resources", "Resources"],
          ]}
          value={mode}
          onChange={setMode}
        />
      </View>
      {mode === "insights" ? <Insights /> : <ManageResources />}
    </View>
  );
}
