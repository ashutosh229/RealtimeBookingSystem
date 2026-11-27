import { api, apiRaw, type Raw } from "./client";
import type {
  AllocationRecord,
  Availability,
  Booking,
  ChanceSummary,
  MetricsSummary,
  MyChance,
  RejectionSummary,
  Resource,
  ResourceCreate,
  ResourceUpdate,
  WaitlistEntry,
} from "./generated";

export type Page<T> = { items: T[]; next_cursor?: string | null };
export type BookingRequest = {
  resource_id: string;
  start_time: string;
  end_time: string;
  quantity: number;
  waitlist_if_full: boolean;
};

export const listResources = async (eligibleOnly: boolean) =>
  (
    await api<Page<Resource>>("/resources", {
      params: { limit: 100, eligible_only: eligibleOnly },
    })
  ).items;
export const getResource = (id: string) => api<Resource>(`/resources/${id}`);
export const getAvailability = (id: string, date: string) =>
  api<Availability>(`/resources/${id}/availability`, { params: { date } });
export const createBooking = (
  body: BookingRequest,
  key: string,
): Promise<Raw<Booking>> =>
  apiRaw<Booking>("/bookings", { method: "POST", body, idempotencyKey: key });
export const getBooking = (id: string) => api<Booking>(`/bookings/${id}`);
export const cancelBooking = (id: string) =>
  api<Booking>(`/bookings/${id}/cancel`, { method: "POST" });
export const listMyBookings = (cursor?: string) =>
  api<Page<Booking>>("/users/me/bookings", { params: { limit: 20, cursor } });
export const adminSummary = (days: number) =>
  api<MetricsSummary>("/admin/metrics/summary", {
    params: { window_days: days },
  });
export const adminRejections = (days: number) =>
  api<RejectionSummary>("/admin/metrics/rejections", {
    params: { window_days: days },
  });
export const adminChance = (days: number) =>
  api<ChanceSummary>("/admin/metrics/chance", {
    params: { window_days: days },
  });

/** Resources within radius_m of a point, nearest first; each item has distance_m. */
export const listNearby = async (lat: number, lon: number, radiusM: number) =>
  (
    await api<Page<Resource>>("/resources", {
      params: { lat, lon, radius_m: radiusM, limit: 100, eligible_only: true },
    })
  ).items;
export const myChance = (days: number) =>
  api<MyChance>("/users/me/chance", { params: { window_days: days } });

// Admin: resource management and inspection.
export const adminListResources = async () =>
  (
    await api<Page<Resource>>("/resources", {
      params: { limit: 100, eligible_only: false },
    })
  ).items;
export const createResource = (body: ResourceCreate) =>
  api<Resource>("/admin/resources", { method: "POST", body });
export const updateResource = (id: string, body: ResourceUpdate) =>
  api<Resource>(`/admin/resources/${id}`, { method: "PATCH", body });
export const deactivateResource = (id: string, force: boolean) =>
  api<Resource>(`/admin/resources/${id}/deactivate`, {
    method: "POST",
    body: { force },
  });
export const adminWaitlist = async (resourceId: string) =>
  (
    await api<Page<WaitlistEntry>>("/admin/waitlists", {
      params: { resource_id: resourceId, limit: 100 },
    })
  ).items;
export const adminAllocations = async (resourceId: string) =>
  (
    await api<Page<AllocationRecord>>("/admin/allocations", {
      params: { resource_id: resourceId, limit: 30 },
    })
  ).items;
