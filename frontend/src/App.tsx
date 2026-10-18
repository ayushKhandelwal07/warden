import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell, ToProject } from "./components/AppShell";
import { AuthProvider } from "./lib/auth";
import { Ask } from "./screens/Ask";
import { AuthScreen, InviteScreen } from "./screens/AuthScreen";
import { Home } from "./screens/Home";
import { Landing } from "./screens/Landing";
import { Approvals } from "./screens/Approvals";
import { PrImpact } from "./screens/PrImpact";
import { Settings } from "./screens/Settings";
import { Sync } from "./screens/Sync";
import { Evaluation } from "./screens/Evaluation";
import { Tools } from "./screens/Tools";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<AuthScreen mode="login" />} />
          <Route path="/signup" element={<AuthScreen mode="signup" />} />
          <Route path="/invite/:token" element={<InviteScreen />} />
          <Route path="/app/:project" element={<AppShell />}>
            <Route index element={<Navigate to="home" replace />} />
            <Route path="home" element={<Home />} />
            <Route path="ask/:chatId?" element={<Ask />} />
            <Route path="impact/:runId?" element={<PrImpact />} />
            <Route path="approvals/:id?" element={<Approvals />} />
            <Route path="tools" element={<Tools />} />
            <Route path="sync" element={<Sync />} />
            <Route path="evaluation" element={<Evaluation />} />
            <Route path="settings/:section?" element={<Settings />} />
            <Route path="*" element={<Navigate to="home" replace />} />
          </Route>
          {["/home", "/ask", "/impact", "/approvals", "/tools", "/sync", "/evaluation"].map((p) => (
            <Route key={p} path={p} element={<ToProject path={p} />} />
          ))}
          {["/approvals/:id", "/impact/:id", "/ask/:id"].map((p) => (
            <Route key={p} path={p} element={<ToProject />} />
          ))}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
