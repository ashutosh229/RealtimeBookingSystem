import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Redirect, Stack, useSegments } from "expo-router";
import { AuthProvider, useAuth } from "../auth/AuthContext";

const queryClient = new QueryClient();

function Gate() {
  const { ready, signedIn } = useAuth();
  const segments = useSegments() as string[];
  if (!ready) return null;
  const onLogin = segments[0] === "login";
  if (!signedIn && !onLogin) return <Redirect href="/login" />;
  if (signedIn && onLogin) return <Redirect href="/" />;
  return <Stack />;
}

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </QueryClientProvider>
  );
}
