import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { MerchantProvider } from "./app/MerchantContext";
import { AppShell } from "./layouts/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { OpportunitiesListPage } from "./pages/OpportunitiesListPage";
import { OpportunityDetailPage } from "./pages/OpportunityDetailPage";
import { AgentPage } from "./pages/AgentPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SimulatorPage } from "./pages/SimulatorPage";
import { CampaignsListPage } from "./pages/CampaignsListPage";
import { CampaignDetailPage } from "./pages/CampaignDetailPage";
import { FailureLabPage } from "./pages/FailureLabPage";
import { BuyerPage } from "./pages/BuyerPage";
import { CheckoutPage } from "./pages/CheckoutPage";
import { CustomersPage } from "./pages/CustomersPage";
import { ProductsPage } from "./pages/ProductsPage";
import { AuditLedgerPage } from "./pages/AuditLedgerPage";
import { ControlRoomPage } from "./pages/ControlRoomPage";
import { LoginPage } from "./pages/LoginPage";
import { DataUploadPage } from "./pages/DataUploadPage";
import { MissionPage } from "./pages/MissionPage";
import { NotificationsPage } from "./pages/NotificationsPage";

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <MerchantProvider>
        <BrowserRouter>
          <AppShell>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/mission" element={<MissionPage />} />
              <Route path="/notifications" element={<NotificationsPage />} />
              <Route path="/opportunities" element={<OpportunitiesListPage />} />
              <Route path="/opportunities/:opportunityId" element={<OpportunityDetailPage />} />
              <Route path="/simulator/:opportunityId" element={<SimulatorPage />} />
              <Route path="/campaigns" element={<CampaignsListPage />} />
              <Route path="/campaigns/:campaignId" element={<CampaignDetailPage />} />
              <Route path="/customers" element={<CustomersPage />} />
              <Route path="/products" element={<ProductsPage />} />
              <Route path="/agent" element={<AgentPage />} />
              <Route path="/shop" element={<BuyerPage />} />
              <Route path="/shop/checkout" element={<CheckoutPage />} />
              <Route path="/approvals" element={<ApprovalsPage />} />
              <Route path="/audit" element={<AuditLedgerPage />} />
              <Route path="/control-room" element={<ControlRoomPage />} />
              <Route path="/failure-lab" element={<FailureLabPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/data-upload" element={<DataUploadPage />} />
              <Route path="/login" element={<LoginPage />} />
            </Routes>
          </AppShell>
        </BrowserRouter>
      </MerchantProvider>
    </QueryClientProvider>
  );
}

export default App;
