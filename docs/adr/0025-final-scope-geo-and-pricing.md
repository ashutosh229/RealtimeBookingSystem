# ADR-0025: Final scope of geolocation (O7) and pricing (O8)

Status: Accepted | Date: 2026-11-27 | Refines ADR-0008 and ADR-0009

## Context
ADR-0008 and ADR-0009 deferred pricing and geolocation until the core was stable. It is stable and deployed (ADR-0021), so both need a final answer. The allotted VM runs PostgreSQL from apt without PostGIS, and the semester has no room for a live payment-like subsystem.

## Decision
Geolocation: `GET /resources` takes `lat`, `lon` and `radius_m` (all three or none, radius up to 50 km) and returns the eligible resources within the radius, nearest first, each with `distance_m`, in one page without a cursor. Distance is the haversine great-circle distance computed in SQL after a latitude/longitude bounding-box prefilter (the HLD section 29 fallback), so no PostGIS is needed. The user's position is a query parameter and is never stored. Distance only orders and filters results; it never changes eligibility or allocation (I5). The same endpoint also gains `available_from` / `available_to`: only resources with no fully booked slot overlapping that half-open window.

Pricing: final scope is simulation-only. The credit wallet with backlog-sensitive prices from ADR-0018 is the pricing experiment (O8) and is evaluated in the simulator. No live credit tables, no `PRICING_ENABLED` flag and no live price display are built.

## Consequences
Rationale: both objectives are covered with the least new moving parts; the geo query runs on the stack the course provides, and the pricing evidence comes from the same reproducible traces as the fairness study.
Cost accepted: without a spatial index the radius query scans the bounding box, which is fine at campus scale (hundreds of resources) but not at city scale; radius results are capped at `limit` with no further pages; the free-window filter ignores operating hours and booking horizon, so a listed resource can still refuse a request for other reasons; pricing effects are simulated, not observed on real users.
