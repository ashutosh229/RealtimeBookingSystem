# ADR-0011: Mobile stack and targets
Status: Accepted | Date: 2026-10-21

## Context
The system needs a mobile client. The team has no Mac, no iPhone, and no budget for paid developer accounts (Apple Developer Program, Play Console).

## Decision
- Build the client with Expo, React Native, and TypeScript, one codebase.
- Supported targets: **Android** (Expo Go in development, APK built with EAS or locally for demos) and **web** (Expo web build, also used for the admin screens).
- **iOS is out of scope for v1.** It cannot be built, signed, or tested without a Mac, an iPhone, and a paid account. iPhone users can use the web build in Safari.
- No push notifications in v1 (see ADR-0012). The app polls for status instead.
- Use only cross-platform components; avoid native-only modules so the web build keeps working. Test every screen on Android and web.

## Consequences
Rationale: a single TypeScript codebase fits a three-person team, and the API client is generated from the OpenAPI file.
Cost accepted: no native iOS app and no push notifications. The demo needs either a running dev server or a hosted backend, plus an installed APK or a browser.
