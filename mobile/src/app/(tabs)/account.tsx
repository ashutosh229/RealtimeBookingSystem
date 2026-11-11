import { Text, View } from "react-native";
import { useAuth } from "../../auth/AuthContext";
import { API_BASE } from "../../config";
import { Button, Card, s } from "../../ui";

export default function Account() {
  const { user, logout } = useAuth();
  return (
    <View style={[s.screen, s.content]}>
      <Card>
        <Text style={s.title}>{user?.name}</Text>
        <Text style={s.muted}>{user?.email}</Text>
        <Text style={s.muted}>
          Group: {user?.user_group} · Role: {user?.role}
        </Text>
        <Text style={s.muted}>Server: {API_BASE}</Text>
      </Card>
      <Button kind="danger" title="Sign out" onPress={logout} />
    </View>
  );
}
