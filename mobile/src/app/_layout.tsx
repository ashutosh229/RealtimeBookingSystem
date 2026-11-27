import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Redirect, Stack, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { View } from "react-native";
import { AuthProvider, useAuth } from "../auth/AuthContext";
import { Banner } from "../notifications/Banner";
import { NotificationsProvider } from "../notifications/NotificationsContext";
import { Loading, colors, headerOptions } from "../ui";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 5_000 } },
});

function Gate() {
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
    <>
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
    </>
  );
}

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar style="dark" />
      <AuthProvider>
        <NotificationsProvider>
          <Gate />
        </NotificationsProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
