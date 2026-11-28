import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Text,
  View,
} from "react-native";
import { useAuth } from "../auth/AuthContext";
import { explain } from "../lib/errors";
import { Button, ErrorBox, Field, Icon, Segmented, radius, space } from "../ui";
import { useTheme } from "../theme";

type Mode = "login" | "register";

export default function Login() {
  const { colors, s, shadow } = useTheme();
  const { login, register } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const tooShort =
    mode === "register" && password.length > 0 && password.length < 8;
  const canSubmit =
    email.includes("@") &&
    password.length > 0 &&
    !tooShort &&
    (mode === "login" || name.trim().length > 0);

  async function submit() {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email.trim(), password);
      else await register(email.trim(), name.trim(), password);
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={s.screen}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={{
          flexGrow: 1,
          justifyContent: "center",
          padding: space.xl,
        }}
        keyboardShouldPersistTaps="handled"
      >
        <View
          style={{
            width: "100%",
            maxWidth: 420,
            alignSelf: "center",
            gap: space.xl,
          }}
        >
          <View style={{ alignItems: "center", gap: space.sm }}>
            <View
              style={{
                width: 64,
                height: 64,
                borderRadius: 20,
                backgroundColor: colors.primary,
                alignItems: "center",
                justifyContent: "center",
                ...shadow,
              }}
            >
              <Icon name="calendar" size={30} color={colors.onPrimary} />
            </View>
            <Text style={[s.h1, { marginTop: space.sm }]}>
              RealTime Booking
            </Text>
            <Text style={[s.muted, { textAlign: "center", fontSize: 15 }]}>
              Reserve library seats, lab rooms and compute time on campus,
              fairly.
            </Text>
          </View>

          <View
            style={{
              backgroundColor: colors.card,
              borderRadius: radius.lg,
              padding: space.xl,
              gap: space.lg,
              borderWidth: 1,
              borderColor: colors.lineSoft,
              ...shadow,
            }}
          >
            <Segmented<Mode>
              options={[
                ["login", "Sign in"],
                ["register", "Create account"],
              ]}
              value={mode}
              onChange={(m) => {
                setMode(m);
                setError(null);
              }}
            />
            {mode === "register" && (
              <Field
                label="Full name"
                icon="person-outline"
                value={name}
                onChangeText={setName}
                placeholder="Your name"
                autoComplete="name"
                textContentType="name"
              />
            )}
            <Field
              label="College email"
              icon="mail-outline"
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              autoComplete="email"
              textContentType="emailAddress"
              placeholder="you@college.edu"
            />
            <View style={{ gap: 6 }}>
              <Field
                label="Password"
                icon="lock-closed-outline"
                secure
                value={password}
                onChangeText={setPassword}
                placeholder={
                  mode === "register"
                    ? "At least 8 characters"
                    : "Your password"
                }
                autoComplete={
                  mode === "register" ? "new-password" : "current-password"
                }
                textContentType={
                  mode === "register" ? "newPassword" : "password"
                }
                onSubmitEditing={submit}
                returnKeyType="go"
              />
              {tooShort && (
                <Text style={{ color: colors.warn, fontSize: 13 }}>
                  Use at least 8 characters.
                </Text>
              )}
            </View>
            {error && <ErrorBox message={error} />}
            <Button
              title={mode === "login" ? "Sign in" : "Create account"}
              icon={mode === "login" ? "log-in-outline" : "person-add-outline"}
              onPress={submit}
              disabled={!canSubmit}
              busy={busy}
            />
          </View>

          <Text style={[s.muted, { textAlign: "center", fontSize: 13 }]}>
            Bookings are confirmed instantly when space is free. When it is
            full, join the waitlist and you will be moved in automatically.
          </Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
