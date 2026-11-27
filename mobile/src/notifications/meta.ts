import { colors, type IconName } from "../ui";

type Meta = { icon: IconName; fg: string; bg: string; title: string };

/** Icon, colours and headline for each notification type (inbox rows and the toast). */
export const NOTIFY_META: Record<string, Meta> = {
  BookingConfirmed: {
    icon: "checkmark-circle",
    fg: colors.ok,
    bg: colors.okSoft,
    title: "Booking confirmed",
  },
  BookingPromoted: {
    icon: "arrow-up-circle",
    fg: colors.ok,
    bg: colors.okSoft,
    title: "You got a place",
  },
  BookingWaitlisted: {
    icon: "hourglass",
    fg: colors.warn,
    bg: colors.warnSoft,
    title: "Added to waitlist",
  },
  BookingCancelled: {
    icon: "close-circle",
    fg: colors.muted,
    bg: "#F1F5F9",
    title: "Booking cancelled",
  },
  BookingExpired: {
    icon: "time",
    fg: colors.muted,
    bg: "#F1F5F9",
    title: "Waitlist expired",
  },
};

export const notifyMeta = (type: string): Meta =>
  NOTIFY_META[type] ?? {
    icon: "notifications",
    fg: colors.primary,
    bg: colors.primarySoft,
    title: "Update",
  };
