import type { IconName, Palette } from "../theme";

type Meta = { icon: IconName; fg: string; bg: string; title: string };

/** Icon, colours and headline for each notification type (inbox rows and the toast), in the active theme. */
export function notifyMeta(type: string, c: Palette): Meta {
  switch (type) {
    case "BookingConfirmed":
      return {
        icon: "checkmark-circle",
        fg: c.ok,
        bg: c.okSoft,
        title: "Booking confirmed",
      };
    case "BookingPromoted":
      return {
        icon: "arrow-up-circle",
        fg: c.ok,
        bg: c.okSoft,
        title: "You got a place",
      };
    case "BookingWaitlisted":
      return {
        icon: "hourglass",
        fg: c.warn,
        bg: c.warnSoft,
        title: "Added to waitlist",
      };
    case "BookingCancelled":
      return {
        icon: "close-circle",
        fg: c.muted,
        bg: c.neutralSoft,
        title: "Booking cancelled",
      };
    case "BookingExpired":
      return {
        icon: "time",
        fg: c.muted,
        bg: c.neutralSoft,
        title: "Waitlist expired",
      };
    default:
      return {
        icon: "notifications",
        fg: c.primary,
        bg: c.primarySoft,
        title: "Update",
      };
  }
}
