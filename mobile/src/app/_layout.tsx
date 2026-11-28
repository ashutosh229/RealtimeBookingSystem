import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  DarkTheme,
  DefaultTheme,
  ThemeProvider as NavThemeProvider,
  Redirect,
  Stack,
  useSegments,
} from "expo-router";
import { View } from "react-native";
import { AuthProvider, useAuth } from "../auth/AuthContext";
import { Banner } from "../notifications/Banner";
import { NotificationsProvider } from "../notifications/NotificationsContext";
import { Loading } from "../ui";
import { ThemeProvider, useTheme } from "../theme";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 5_000 } },
});

function Gate() {
  const { colors, headerOptions, isDark } = useTheme();
  // Navigation draws its own backgrounds (behind screens, during transitions); give it our palette too.
  const base = isDark ? DarkTheme : DefaultTheme;
  const navTheme = {
    ...base,
    colors: {
      ...base.colors,
      primary: colors.primary,
      background: colors.bg,
      card: colors.card,
      text: colors.text,
      border: colors.line,
      notification: colors.danger,
    },
  };
  const { ready, user } = useAuth();
  const segments = useSegments() as string[];
  if (!ready)
    return (
      <View
        style={{
          flex: 1,
          justifyContent: "center",
          backgroundColor: colors.bg,
        }}
      >
        <Loading />
      </View>
    );
  const onLogin = segments[0] === "login";
  if (!user && !onLogin) return <Redirect href="/login" />;
  if (user && onLogin) return <Redirect href="/" />;
  return (
    <NavThemeProvider value={navTheme}>
      <Stack screenOptions={{ ...headerOptions, headerBackTitle: "Back" }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen
          name="login"
          options={{ headerShown: false, title: "Sign in" }}
        />
        <Stack.Screen name="resource/[id]" options={{ title: "Book" }} />
        <Stack.Screen
          name="booking/[id]"
          options={{ title: "Booking details" }}
        />
        <Stack.Screen name="manage/new" options={{ title: "New resource" }} />
        <Stack.Screen
          name="manage/[id]"
          options={{ title: "Manage resource" }}
        />
      </Stack>
      <Banner />
    </NavThemeProvider>
  );
}

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <NotificationsProvider>
            <Gate />
          </NotificationsProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
