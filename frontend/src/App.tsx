import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Header } from "./components/Chrome";
import { api } from "./lib/api";
import { useApi } from "./lib/useApi";
import { Ask } from "./screens/Ask";
import { Home } from "./screens/Home";
import { Approvals } from "./screens/Approvals";
import { PrImpact } from "./screens/PrImpact";
import { Sync } from "./screens/Sync";
import { Tools } from "./screens/Tools";

export default function App() {
  const health = useApi(api.health);
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-bg">
        <Header health={health.data} error={health.error} />
        <main className="pb-14 sm:pb-0">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/ask" element={<Ask />} />
            <Route path="/impact" element={<PrImpact />} />
            <Route path="/approvals" element={<Approvals />} />
            <Route path="/tools" element={<Tools />} />
            <Route path="/sync" element={<Sync />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
