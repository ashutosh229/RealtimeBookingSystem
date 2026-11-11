import { Stack } from "expo-router";
import { useState } from "react";
import { Text, TextInput, View } from "react-native";
import { useAuth } from "../auth/AuthContext";
import { explain } from "../lib/errors";
import { Button, Note, s } from "../ui";

export default function Login() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("student1@campus.test");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("password123");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email.trim(), password);
      else await register(email.trim(), name.trim() || "Student", password);
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={[s.screen, { justifyContent: "center", padding: 24 }]}>
      <Stack.Screen
        options={{ title: mode === "login" ? "Sign in" : "Create account" }}
      />
      <View
        style={{ gap: 12, maxWidth: 480, width: "100%", alignSelf: "center" }}
      >
        <Text style={s.h1}>RealTime Booking</Text>
        <TextInput
          style={s.input}
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          placeholder="Email"
        />
        {mode === "register" && (
          <TextInput
            style={s.input}
            value={name}
            onChangeText={setName}
            placeholder="Name"
          />
        )}
        <TextInput
          style={s.input}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          placeholder="Password (8+ characters)"
        />
        {error && <Note tone="error">{error}</Note>}
        <Button
          title={mode === "login" ? "Sign in" : "Create account"}
          onPress={submit}
          busy={busy}
        />
        <Button
          kind="ghost"
          title={
            mode === "login" ? "Create an account" : "I already have an account"
          }
          onPress={() => {
            setMode(mode === "login" ? "register" : "login");
            setError(null);
          }}
        />
      </View>
    </View>
  );
}
