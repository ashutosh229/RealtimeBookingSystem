import { Tabs } from "expo-router";
import { useAuth } from "../../auth/AuthContext";
import { useNotifications } from "../../notifications/NotificationsContext";

export default function TabsLayout() {
  const { unread } = useNotifications();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const noIcon = () => null;
  return (
    <Tabs
      screenOptions={{
        tabBarIcon: noIcon,
        tabBarIconStyle: { display: "none" },
        tabBarLabelStyle: { fontSize: 14 },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Resources" }} />
      <Tabs.Screen name="bookings" options={{ title: "My bookings" }} />
      <Tabs.Screen
        name="notifications"
        options={{
          title: "Inbox",
          tabBarBadge: unread > 0 ? unread : undefined,
        }}
      />
      <Tabs.Screen
        name="admin"
        options={{ title: "Admin", href: isAdmin ? undefined : null }}
      />
      <Tabs.Screen name="account" options={{ title: "Account" }} />
    </Tabs>
  );
}
