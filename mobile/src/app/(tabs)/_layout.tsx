import Ionicons from "@expo/vector-icons/Ionicons";
import { Tabs } from "expo-router";
import type { ColorValue } from "react-native";
import { useAuth } from "../../auth/AuthContext";
import { useNotifications } from "../../notifications/NotificationsContext";
import { colors, headerOptions, type IconName } from "../../ui";

const icon =
  (name: IconName, active: IconName) =>
  ({
    color,
    focused,
    size,
  }: {
    color: ColorValue;
    focused: boolean;
    size: number;
  }) => (
    <Ionicons
      name={focused ? active : name}
      color={color as string}
      size={size - 2}
    />
  );

export default function TabsLayout() {
  const { unread } = useNotifications();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  return (
    <Tabs
      screenOptions={{
        ...headerOptions,
        sceneStyle: { backgroundColor: colors.bg },
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.faint,
        tabBarLabelStyle: { fontSize: 12, fontWeight: "600" },
        tabBarStyle: {
          backgroundColor: colors.card,
          borderTopColor: colors.line,
        },
        tabBarBadgeStyle: { backgroundColor: colors.danger, fontSize: 11 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Explore",
          headerTitle: "Book a space",
          tabBarIcon: icon("compass-outline", "compass"),
        }}
      />
      <Tabs.Screen
        name="bookings"
        options={{
          title: "Bookings",
          headerTitle: "My bookings",
          tabBarIcon: icon("calendar-outline", "calendar"),
        }}
      />
      <Tabs.Screen
        name="notifications"
        options={{
          title: "Inbox",
          tabBarIcon: icon("notifications-outline", "notifications"),
          tabBarBadge: unread > 0 ? (unread > 99 ? "99+" : unread) : undefined,
        }}
      />
      <Tabs.Screen
        name="admin"
        options={{
          title: "Admin",
          headerTitle: "Administration",
          href: isAdmin ? undefined : null,
          tabBarIcon: icon("stats-chart-outline", "stats-chart"),
        }}
      />
      <Tabs.Screen
        name="account"
        options={{
          title: "Account",
          tabBarIcon: icon("person-circle-outline", "person-circle"),
        }}
      />
    </Tabs>
  );
}
