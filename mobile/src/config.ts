import { Platform } from 'react-native';

export const USE_MOCK = (process.env.EXPO_PUBLIC_USE_MOCK ?? 'true') === 'true';

// Android emulator reaches the host machine at 10.0.2.2; web and iOS use localhost.
const host = Platform.OS === 'android' ? '10.0.2.2' : 'localhost';
export const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? `http://${host}:8080/v1`;