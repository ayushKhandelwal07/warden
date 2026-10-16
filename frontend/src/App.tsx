import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Header, StatusBar } from "./components/Chrome";
import { api } from "./lib/api";
import { useApi } from "./lib/useApi";
import { Ask } from "./screens/Ask";
import { Upcoming } from "./screens/Upcoming";

export default function App() {
  const health = useApi(api.health);
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg">
        <StatusBar health={health.data} error={health.error} />
        <Header browserUrl={health.data?.browser_url} />
        <main>
          <Routes>
            <Route path="/" element={<Ask />} />
            <Route
              path="/impact"
              element={<Upcoming title="PR impact" message="Pick a pull request and Warden will show what it can break, who should review it, and which past incidents it resembles. This screen is wired up with the impact flow." />}
            />
            <Route
              path="/approvals"
              element={<Upcoming title="Approvals" message="Nothing waiting. Fixes, PR comments and issues the agent proposes will wait here for your approval before anything touches GitHub." />}
            />
            <Route
              path="/tools"
              element={<Upcoming title="Tools" message="The graph tools the agent can call (reachability, blast radius, experts, ownership) will be listed here, each runnable by hand." />}
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
