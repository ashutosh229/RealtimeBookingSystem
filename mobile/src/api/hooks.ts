import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { listResources } from "./endpoints";

/** Every resource by id (names and timezones for the bookings list). */
export function useResourceMap() {
  const q = useQuery({
    queryKey: ["resources-all"],
    queryFn: () => listResources(false),
    staleTime: 60_000,
  });
  return useMemo(
    () => new Map((q.data ?? []).map((r) => [r.resource_id, r])),
    [q.data],
  );
}
