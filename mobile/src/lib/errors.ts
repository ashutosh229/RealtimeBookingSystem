import { ApiError } from "../api/client";

const MSG: Record<string, string> = {
  CAPACITY_UNAVAILABLE:
    "That time is no longer available. Pick again, or join the waitlist.",
  USER_LIMIT_REACHED: "You have reached the booking limit for this resource.",
  NOT_ELIGIBLE: "Your account is not eligible to book this resource.",
  OUT_OF_HOURS: "That is outside opening hours.",
  OUT_OF_HORIZON: "That is too far ahead to book.",
  INVALID_INTERVAL: "That time selection is not valid.",
  QUANTITY_OUT_OF_RANGE: "That quantity is not allowed for this resource.",
  RESOURCE_INACTIVE: "This resource is not accepting bookings.",
  CANCELLATION_WINDOW_CLOSED: "This booking can no longer be cancelled.",
  RATE_LIMITED: "Too many requests. Try again shortly.",
  SERVICE_BUSY: "The server is busy. Try again in a moment.",
  NETWORK: "Cannot reach the server. Check your connection and try again.",
  INVALID_CREDENTIALS: "Invalid email or password.",
  EMAIL_TAKEN: "That email is already registered.",
};

export const explain = (e: unknown): string =>
  e instanceof ApiError ? (MSG[e.code] ?? e.message) : "Something went wrong.";
