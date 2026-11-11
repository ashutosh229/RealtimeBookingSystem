import { Platform } from "react-native";

// Android emulator reaches the host machine at 10.0.2.2; web and iOS use localhost.
const host = Platform.OS === "android" ? "10.0.2.2" : "localhost";
export const API_BASE =
  process.env.EXPO_PUBLIC_API_URL ?? `http://${host}:8080/v1`;
export const POLL_MS = 12000;
