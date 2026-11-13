import { api, apiRaw, type Raw } from "./client";
import type {
  Availability,
  Booking,
  Resource,
  MetricsSummary,
  RejectionSummary,
  ChanceSummary,
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
