import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { ApiError } from "../../api/client";
import {
  adminAllocations,
  adminWaitlist,
  deactivateResource,
  getResource,
  updateResource,
} from "../../api/endpoints";
import type { ResourceUpdate } from "../../api/generated";
import { ResourceForm } from "../../admin/ResourceForm";
import { explain } from "../../lib/errors";
import { ago, fmtDateTime, fmtTime } from "../../lib/time";
import {
  Button,
  Callout,
  Card,
  EmptyState,
  ErrorBox,
  Loading,
  SectionTitle,
  Segmented,
  TYPE_LABEL,
  Tag,
  TypeIcon,
  colors,
  s,
  space,
} from "../../ui";

type Tab = "edit" | "waitlist" | "decisions";

const DECISION: Record<string, { label: string; fg: string; bg: string }> = {
  ADMIT: { label: "Admitted", fg: colors.ok, bg: colors.okSoft },
  PROMOTE: { label: "Promoted", fg: colors.ok, bg: colors.okSoft },
  REJECT_FULL: {
    label: "Rejected · full",
    fg: colors.danger,
    bg: colors.dangerSoft,
  },
  SKIP_INELIGIBLE: { label: "Skipped", fg: colors.warn, bg: colors.warnSoft },
};

export default function ManageResource() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("edit");
  const [confirm, setConfirm] = useState<null | "plain" | "force">(null);
  const [saved, setSaved] = useState(false);
  const rq = useQuery({
    queryKey: ["resource", id],
    queryFn: () => getResource(id),
  });
  const r = rq.data;
  const tz = r?.timezone ?? "UTC";
  const wq = useQuery({
    queryKey: ["admin", "waitlist", id],
    queryFn: () => adminWaitlist(id),
    enabled: tab === "waitlist",
    refetchInterval: 15_000,
  });
  const aq = useQuery({
    queryKey: ["admin", "allocations", id],
    queryFn: () => adminAllocations(id),
    enabled: tab === "decisions",
  });

  const refreshAll = () => {
    for (const key of [
      "resource",
      "resources",
      "resources-all",
      "admin-resources",
      "availability",
    ])
      qc.invalidateQueries({ queryKey: [key] });
  };
  const save = useMutation({
    mutationFn: (body: ResourceUpdate) => updateResource(id, body),
    onSuccess: () => {
      refreshAll();
      setSaved(true);
    },
  });
  const deactivate = useMutation({
    mutationFn: (force: boolean) => deactivateResource(id, force),
    onSuccess: () => {
      refreshAll();
      setConfirm(null);
    },
    onError: (e) => {
      // Upcoming bookings block a plain deactivation: offer the forced one, which cancels them.
      if (e instanceof ApiError && e.code === "HAS_ACTIVE_BOOKINGS")
        setConfirm("force");
    },
  });

  if (rq.isLoading) return <Loading label="Loading resource…" />;
  if (!r)
    return (
      <View style={[s.screen, s.content]}>
        <ErrorBox message={explain(rq.error)} onRetry={rq.refetch} />
      </View>
    );

  return (
    <ScrollView
      style={s.screen}
      contentContainerStyle={[s.content, { paddingBottom: space.xxl }]}
      keyboardShouldPersistTaps="handled"
    >
      <Stack.Screen options={{ title: "Manage resource" }} />
      <Card>
        <View style={[s.hstack, { gap: space.md }]}>
          <TypeIcon type={r.type} size={52} />
          <View style={{ flex: 1, gap: 4 }}>
            <Text style={s.h2} numberOfLines={2}>
              {r.name}
            </Text>
            <View style={[s.hstack, { gap: 6, flexWrap: "wrap" }]}>
              <Tag label={TYPE_LABEL[r.type]} />
              {r.active ? (
                <Tag
                  icon="checkmark-circle-outline"
                  label="Active"
                  tone="primary"
                />
              ) : (
                <Tag icon="pause-circle-outline" label="Inactive" />
              )}
            </View>
          </View>
        </View>
        {r.active && (
          <Button
            kind="ghost"
            size="sm"
            icon="eye-outline"
            title="See what students see"
            onPress={() => router.push(`/resource/${r.resource_id}` as never)}
            style={{ alignSelf: "flex-start", marginTop: space.xs }}
          />
        )}
      </Card>

      <Segmented<Tab>
        options={[
          ["edit", "Settings"],
          ["waitlist", "Waitlist"],
          ["decisions", "Decisions"],
        ]}
        value={tab}
        onChange={setTab}
      />

      {tab === "edit" && (
        <>
          {!r.active && (
            <Callout icon="pause-circle-outline">
              This resource is inactive: students cannot see or book it.
            </Callout>
          )}
          {saved && !save.isPending && (
            <Callout tone="ok">Changes saved.</Callout>
          )}
          <ResourceForm
            key={`${r.resource_id}-${r.name}-${r.capacity}`}
            resource={r}
            submitLabel="Save changes"
            busy={save.isPending}
            serverError={save.isError ? explain(save.error) : null}
            onSubmit={(body) => {
              setSaved(false);
              save.mutate(body as ResourceUpdate);
            }}
          />

          {r.active && (
            <>
              <SectionTitle title="Danger zone" />
              {!confirm ? (
                <Button
                  kind="dangerGhost"
                  icon="pause-circle-outline"
                  title="Deactivate resource"
                  onPress={() => setConfirm("plain")}
                />
              ) : (
                <Card style={{ borderColor: "#FECACA", gap: space.md }}>
                  <Text style={s.title}>
                    {confirm === "force"
                      ? "Cancel upcoming bookings and deactivate?"
                      : "Deactivate this resource?"}
                  </Text>
                  <Text style={s.muted}>
                    {confirm === "force"
                      ? "It has upcoming bookings or waitlist entries. They will all be cancelled and their owners notified."
                      : "Students will no longer see it or be able to book it. Past bookings are kept."}
                  </Text>
                  {deactivate.isError &&
                    !(
                      deactivate.error instanceof ApiError &&
                      deactivate.error.code === "HAS_ACTIVE_BOOKINGS"
                    ) && <ErrorBox message={explain(deactivate.error)} />}
                  <View style={[s.hstack, { gap: space.sm }]}>
                    <Button
                      kind="secondary"
                      title="Keep it"
                      onPress={() => {
                        setConfirm(null);
                        deactivate.reset();
                      }}
                      style={{ flex: 1 }}
                    />
                    <Button
                      kind="danger"
                      title={
                        confirm === "force"
                          ? "Cancel all & deactivate"
                          : "Deactivate"
                      }
                      busy={deactivate.isPending}
                      onPress={() => deactivate.mutate(confirm === "force")}
                      style={{ flex: 1 }}
                    />
                  </View>
                </Card>
              )}
            </>
          )}
        </>
      )}

      {tab === "waitlist" && (
        <>
          {wq.isLoading && <Loading />}
          {wq.isError && (
            <ErrorBox message={explain(wq.error)} onRetry={wq.refetch} />
          )}
          {wq.data && wq.data.length === 0 && (
            <EmptyState
              icon="hourglass-outline"
              title="Nobody is waiting"
              message="Active waitlist entries for this resource appear here, in the order the policy will serve them."
            />
          )}
          {wq.data && wq.data.length > 0 && (
            <>
              <Text style={s.section}>
                {wq.data.length} waiting
                {wq.data.some((w) => w.position_is_estimate)
                  ? " · fair-share order is an estimate"
                  : ""}
              </Text>
              {wq.data.map((w) => (
                <Card
                  key={w.waitlist_id}
                  onPress={() =>
                    router.push(`/booking/${w.booking_id}` as never)
                  }
                >
                  <View style={[s.hstack, { gap: space.md }]}>
                    <Text style={[s.h2, { minWidth: 44, color: colors.warn }]}>
                      #{w.position ?? "—"}
                    </Text>
                    <View style={{ flex: 1 }}>
                      <Text style={s.title}>
                        {fmtDateTime(w.start_time, tz)}–
                        {fmtTime(w.end_time, tz)}
                      </Text>
                      <Text style={s.muted}>
                        Booking {w.booking_id.slice(0, 8).toUpperCase()}
                      </Text>
                    </View>
                  </View>
                </Card>
              ))}
            </>
          )}
        </>
      )}

      {tab === "decisions" && (
        <>
          <Text style={s.muted}>
            Every admission, promotion and skip, with the policy and the inputs
            it used (newest first).
          </Text>
          {aq.isLoading && <Loading />}
          {aq.isError && (
            <ErrorBox message={explain(aq.error)} onRetry={aq.refetch} />
          )}
          {aq.data && aq.data.length === 0 && (
            <EmptyState icon="git-branch-outline" title="No decisions yet" />
          )}
          {(aq.data ?? []).map((d) => {
            const m = DECISION[d.decision_type] ?? DECISION.ADMIT;
            const inputs = Object.entries(d.inputs ?? {})
              .filter(([, v]) => typeof v !== "object")
              .slice(0, 4);
            return (
              <Card key={d.id} style={{ gap: 6 }}>
                <View style={s.row}>
                  <View style={[s.badge, { backgroundColor: m.bg }]}>
                    <Text
                      style={{ color: m.fg, fontWeight: "700", fontSize: 12 }}
                    >
                      {m.label}
                    </Text>
                  </View>
                  <Text style={[s.muted, { fontSize: 12 }]}>
                    {ago(d.decided_at)}
                  </Text>
                </View>
                <Text style={s.body}>
                  {d.policy_name} v{d.policy_version}
                  {d.reason ? ` · ${d.reason}` : ""}
                </Text>
                {inputs.length > 0 && (
                  <Text style={[s.muted, { fontSize: 12 }]}>
                    {inputs.map(([k, v]) => `${k}=${String(v)}`).join("  ·  ")}
                  </Text>
                )}
              </Card>
            );
          })}
        </>
      )}
    </ScrollView>
  );
}
