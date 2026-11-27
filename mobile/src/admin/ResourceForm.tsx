/**
 * Create / edit form for a resource. Type, slot length and timezone are fixed once a resource exists
 * (the server rejects changing them, since booked slots depend on them), so they are shown read-only on edit.
 */
import { useState } from "react";
import { Text, View } from "react-native";
import type {
  Policy,
  Resource,
  ResourceCreate,
  ResourceType,
  ResourceUpdate,
} from "../api/generated";
import { hhmm } from "../lib/time";
import {
  Button,
  Card,
  Chip,
  ErrorBox,
  Field,
  POLICY_TEXT,
  SectionTitle,
  Segmented,
  TYPE_LABEL,
  s,
  space,
} from "../ui";

const SLOT_CHOICES = [15, 30, 60, 120] as const;
const POLICIES: [Policy, string][] = [
  ["FIFO", "First come"],
  ["FAIR_SHARE", "Fair share"],
  ["FAIR_SHARE_Q", "Fair · peak"],
  ["FAIR_SHARE_D", "Fair · decay"],
];
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;

const deviceZone = () => {
  try {
    const z = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata";
    return z === "Asia/Calcutta" ? "Asia/Kolkata" : z; // some browsers still report the old name
  } catch {
    return "Asia/Kolkata";
  }
};

type Values = {
  name: string;
  type: ResourceType;
  capacity: string;
  slot_minutes: (typeof SLOT_CHOICES)[number];
  open_time: string;
  close_time: string;
  timezone: string;
  max_slots_per_booking: string;
  max_quantity_per_booking: string;
  policy_name: Policy;
  groups: string;
  lat: string;
  lon: string;
};

function initial(r?: Resource): Values {
  return {
    name: r?.name ?? "",
    type: r?.type ?? "ROOM",
    capacity: String(r?.capacity ?? 10),
    slot_minutes: r?.slot_minutes ?? 60,
    open_time: r ? hhmm(r.open_time) : "08:00",
    close_time: r ? hhmm(r.close_time) : "20:00",
    timezone: r?.timezone ?? deviceZone(),
    max_slots_per_booking: String(r?.max_slots_per_booking ?? 4),
    max_quantity_per_booking: String(r?.max_quantity_per_booking ?? 1),
    policy_name: r?.policy_name ?? "FAIR_SHARE",
    groups: (r?.eligible_groups ?? []).join(", "),
    lat: r?.lat != null ? String(r.lat) : "",
    lon: r?.lon != null ? String(r.lon) : "",
  };
}

const int = (x: string) => (/^\d+$/.test(x.trim()) ? Number(x.trim()) : NaN);
const num = (x: string) => (x.trim() === "" ? null : Number(x.trim()));

/** Client-side checks that mirror the server's, so most mistakes show before submitting. */
function problems(v: Values): string[] {
  const out: string[] = [];
  const cap = int(v.capacity);
  const qty = int(v.max_quantity_per_booking);
  if (!v.name.trim()) out.push("Give the resource a name.");
  if (!(cap >= 1)) out.push("Capacity must be a whole number of at least 1.");
  if (v.type === "SEAT" && cap !== 1) out.push("A seat always has capacity 1.");
  if (!(int(v.max_slots_per_booking) >= 1))
    out.push("Max slots per booking must be at least 1.");
  if (!(qty >= 1)) out.push("Max quantity per booking must be at least 1.");
  else if (qty > cap)
    out.push("Max quantity per booking cannot exceed capacity.");
  if (v.type === "SEAT" && qty !== 1)
    out.push("A seat is booked one at a time (max quantity 1).");
  if (!TIME.test(v.open_time) || !TIME.test(v.close_time))
    out.push("Use 24-hour HH:MM for opening and closing times.");
  else if (v.open_time >= v.close_time)
    out.push("Opening time must be before closing time.");
  const lat = num(v.lat);
  const lon = num(v.lon);
  if ((lat === null) !== (lon === null))
    out.push("Give both latitude and longitude, or neither.");
  if (lat !== null && !(lat >= -90 && lat <= 90))
    out.push("Latitude must be between -90 and 90.");
  if (lon !== null && !(lon >= -180 && lon <= 180))
    out.push("Longitude must be between -180 and 180.");
  return out;
}

function toBody(v: Values) {
  return {
    name: v.name.trim(),
    capacity: int(v.capacity),
    open_time: v.open_time,
    close_time: v.close_time,
    max_slots_per_booking: int(v.max_slots_per_booking),
    max_quantity_per_booking: int(v.max_quantity_per_booking),
    policy_name: v.policy_name,
    eligible_groups: v.groups
      .split(",")
      .map((g) => g.trim().toLowerCase())
      .filter(Boolean),
    ...(num(v.lat) !== null ? { lat: num(v.lat)!, lon: num(v.lon)! } : {}),
  };
}

export function ResourceForm({
  resource,
  submitLabel,
  busy,
  serverError,
  onSubmit,
}: {
  resource?: Resource;
  submitLabel: string;
  busy: boolean;
  serverError?: string | null;
  onSubmit: (body: ResourceCreate | ResourceUpdate) => void;
}) {
  const editing = !!resource;
  const [v, setV] = useState<Values>(() => initial(resource));
  const [tried, setTried] = useState(false);
  const set =
    <K extends keyof Values>(k: K) =>
    (x: Values[K]) =>
      setV((p) => ({ ...p, [k]: x }));
  const errs = problems(v);

  function submit() {
    setTried(true);
    if (errs.length) return;
    const body = toBody(v);
    if (editing) onSubmit(body as ResourceUpdate);
    else
      onSubmit({
        ...body,
        type: v.type,
        slot_minutes: v.slot_minutes,
        timezone: v.timezone.trim(),
      } as ResourceCreate);
  }

  return (
    <View style={{ gap: space.md }}>
      <SectionTitle title="Basics" />
      <Card style={{ gap: space.md }}>
        <Field
          label="Name"
          icon="text-outline"
          value={v.name}
          onChangeText={set("name")}
          placeholder="e.g. Central Library · Seat A-14"
        />
        <View style={{ gap: 6 }}>
          <Text style={s.label}>Type</Text>
          {editing ? (
            <Text style={s.body}>
              {TYPE_LABEL[v.type]} (fixed once created)
            </Text>
          ) : (
            <Segmented<ResourceType>
              options={[
                ["SEAT", "Seat"],
                ["ROOM", "Room"],
                ["COMPUTE_POOL", "Compute"],
              ]}
              value={v.type}
              onChange={(t) =>
                setV((p) =>
                  t === "SEAT"
                    ? {
                        ...p,
                        type: t,
                        capacity: "1",
                        max_quantity_per_booking: "1",
                      }
                    : { ...p, type: t },
                )
              }
            />
          )}
        </View>
        <Field
          label={
            v.type === "COMPUTE_POOL" ? "Capacity (units)" : "Capacity (seats)"
          }
          icon="people-outline"
          value={v.capacity}
          onChangeText={set("capacity")}
          keyboardType="number-pad"
          editable={v.type !== "SEAT"}
        />
        {editing && (
          <Text style={[s.muted, { fontSize: 13, marginTop: -6 }]}>
            Capacity cannot go below what is already booked in future slots.
          </Text>
        )}
      </Card>

      <SectionTitle title="Opening hours and slots" />
      <Card style={{ gap: space.md }}>
        <View style={[s.hstack, { gap: space.md }]}>
          <View style={{ flex: 1 }}>
            <Field
              label="Opens"
              icon="sunny-outline"
              value={v.open_time}
              onChangeText={set("open_time")}
              placeholder="08:00"
              maxLength={5}
            />
          </View>
          <View style={{ flex: 1 }}>
            <Field
              label="Closes"
              icon="moon-outline"
              value={v.close_time}
              onChangeText={set("close_time")}
              placeholder="20:00"
              maxLength={5}
            />
          </View>
        </View>
        <View style={{ gap: 6 }}>
          <Text style={s.label}>Slot length</Text>
          {editing ? (
            <Text style={s.body}>
              {v.slot_minutes} minutes (fixed once created)
            </Text>
          ) : (
            <View style={s.wrap}>
              {SLOT_CHOICES.map((m) => (
                <Chip
                  key={m}
                  label={`${m} min`}
                  active={v.slot_minutes === m}
                  onPress={() => set("slot_minutes")(m)}
                />
              ))}
            </View>
          )}
        </View>
        {editing ? (
          <Text style={s.muted}>
            Timezone: {v.timezone} (fixed once created)
          </Text>
        ) : (
          <Field
            label="Timezone (IANA)"
            icon="globe-outline"
            value={v.timezone}
            onChangeText={set("timezone")}
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="Asia/Kolkata"
          />
        )}
        <View style={[s.hstack, { gap: space.md }]}>
          <View style={{ flex: 1 }}>
            <Field
              label="Max slots per booking"
              value={v.max_slots_per_booking}
              onChangeText={set("max_slots_per_booking")}
              keyboardType="number-pad"
            />
          </View>
          <View style={{ flex: 1 }}>
            <Field
              label="Max quantity per booking"
              value={v.max_quantity_per_booking}
              onChangeText={set("max_quantity_per_booking")}
              keyboardType="number-pad"
              editable={v.type !== "SEAT"}
            />
          </View>
        </View>
      </Card>

      <SectionTitle title="Waitlist policy" />
      <Card style={{ gap: space.sm }}>
        <View style={s.wrap}>
          {POLICIES.map(([p, label]) => (
            <Chip
              key={p}
              label={label}
              active={v.policy_name === p}
              onPress={() => set("policy_name")(p)}
            />
          ))}
        </View>
        <Text style={s.muted}>{POLICY_TEXT[v.policy_name]}</Text>
      </Card>

      <SectionTitle title="Who and where" />
      <Card style={{ gap: space.md }}>
        <Field
          label="Eligible groups"
          icon="people-circle-outline"
          value={v.groups}
          onChangeText={set("groups")}
          autoCapitalize="none"
          placeholder="Empty = everyone (e.g. ug, pg, faculty)"
        />
        <View style={[s.hstack, { gap: space.md }]}>
          <View style={{ flex: 1 }}>
            <Field
              label="Latitude"
              icon="location-outline"
              value={v.lat}
              onChangeText={set("lat")}
              keyboardType="numbers-and-punctuation"
              placeholder="optional"
            />
          </View>
          <View style={{ flex: 1 }}>
            <Field
              label="Longitude"
              value={v.lon}
              onChangeText={set("lon")}
              keyboardType="numbers-and-punctuation"
              placeholder="optional"
            />
          </View>
        </View>
        <Text style={[s.muted, { fontSize: 13 }]}>
          Coordinates let students find this place with “Near me”.
        </Text>
      </Card>

      {tried && errs.length > 0 && <ErrorBox message={errs.join("\n")} />}
      {serverError && <ErrorBox message={serverError} />}
      <Button
        title={submitLabel}
        icon="checkmark"
        onPress={submit}
        busy={busy}
      />
    </View>
  );
}
