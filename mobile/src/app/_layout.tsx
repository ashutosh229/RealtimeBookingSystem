import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Redirect, Stack, useSegments } from "expo-router";
import { AuthProvider, useAuth } from "../auth/AuthContext";
import { Banner } from "../notifications/Banner";
import { NotificationsProvider } from "../notifications/NotificationsContext";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 5_000 } },
});

function Gate() {
  const { ready, user } = useAuth();
  const segments = useSegments() as string[];
  if (!ready) return null;
  const onLogin = segments[0] === "login";
  if (!user && !onLogin) return <Redirect href="/login" />;
  if (user && onLogin) return <Redirect href="/" />;
  return (
    <>
      <Stack>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      </Stack>
      <Banner />
    </>
  );
}

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <NotificationsProvider>
          <Gate />
        </NotificationsProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
