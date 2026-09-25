import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { api } from './api';
import { RealtimeProvider } from './context/RealtimeContext';
import LoginPage from './LoginPage';
import DashboardPage from './DashboardPage';
import ProductsPage from './ProductsPage';
import SettingsPage from './SettingsPage';
import InboxPage from './InboxPage';
import CampaignsPage from './CampaignsPage';
import UsersPage from './UsersPage';
import GroupsPage from './GroupsPage';
import DevicesPage from './DevicesPage';
import AIStudioPage from './AIStudioPage';

/**
 * Auth guard — redirects to /login if no JWT token present.
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!api.isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function App() {
  return (
    <BrowserRouter>
      <RealtimeProvider>
        <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/products"
          element={
            <ProtectedRoute>
              <ProductsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <SettingsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/inbox"
          element={
            <ProtectedRoute>
              <InboxPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/logs"
          element={<Navigate to="/inbox" replace />}
        />
        <Route
          path="/campaigns"
          element={
            <ProtectedRoute>
              <CampaignsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/users"
          element={
            <ProtectedRoute>
              <UsersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/groups"
          element={
            <ProtectedRoute>
              <GroupsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/devices"
          element={
            <ProtectedRoute>
              <DevicesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/ai-studio"
          element={
            <ProtectedRoute>
              <AIStudioPage />
            </ProtectedRoute>
          }
        />
        {/* Catch-all redirect */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </RealtimeProvider>
    </BrowserRouter>
  );
}

export default App;
