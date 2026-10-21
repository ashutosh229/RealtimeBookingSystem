import type { Resource } from "./generated";

export type { Resource };

const base = {
  slot_minutes: 60 as const,
  open_time: "08:00",
  close_time: "22:00",
  timezone: "UTC",
  policy_name: "FIFO" as const,
  active: true,
};

export const MOCK_RESOURCES: Resource[] = [
  {
    ...base,
    resource_id: "00000000-0000-0000-0000-000000000001",
    type: "SEAT",
    name: "Library Seat A1",
    capacity: 1,
    max_slots_per_booking: 4,
    max_quantity_per_booking: 1,
  },
  {
    ...base,
    resource_id: "00000000-0000-0000-0000-000000000002",
    type: "SEAT",
    name: "Library Seat A2",
    capacity: 1,
    max_slots_per_booking: 4,
    max_quantity_per_booking: 1,
  },
  {
    ...base,
    resource_id: "00000000-0000-0000-0000-000000000003",
    type: "ROOM",
    name: "Study Room 1",
    capacity: 6,
    max_slots_per_booking: 3,
    max_quantity_per_booking: 4,
  },
  {
    ...base,
    resource_id: "00000000-0000-0000-0000-000000000004",
    type: "ROOM",
    name: "CSE Lab",
    capacity: 20,
    max_slots_per_booking: 3,
    max_quantity_per_booking: 5,
  },
  {
    ...base,
    resource_id: "00000000-0000-0000-0000-000000000005",
    type: "COMPUTE_POOL",
    name: "GPU Cluster Pool",
    capacity: 64,
    max_slots_per_booking: 4,
    max_quantity_per_booking: 16,
  },
];
