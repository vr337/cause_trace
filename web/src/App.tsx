import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { DictionaryPage } from "./pages/DictionaryPage";
import { EventsPage } from "./pages/EventsPage";
import { ReportsPage } from "./pages/ReportsPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/workbench" element={<WorkbenchPage />} />
        <Route path="/events" element={<EventsPage />} />
        <Route path="/dictionary" element={<DictionaryPage />} />
        <Route path="/reports" element={<ReportsPage />} />
      </Routes>
    </Layout>
  );
}
