import { ConfigProvider} from '@/contexts/ConfigContext'
import type { ReactNode } from 'react'
import { ThemeProvider } from '@/contexts/ThemeContext'
import { LoggingProvider } from '@/contexts/LoggingContext'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AnalyticsPage from '@/analytics/page'
import AlertsPage from '@/alerts/page'
import AiAssistantPage from '@/ai-assistant/page'
import HistoryPage from '@/history/page'
import LandingPage from '@/pages/LandingPage'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import CitizenEntryPage from '@/pages/CitizenEntryPage'
import AssessFloodRiskPage from '@/pages/AssessFloodRiskPage'
import PredictionPage from '@/pages/PredictionPage'
import PublicFloodMapPage from '@/pages/PublicFloodMapPage'
import CitizenFloodMapPage from '@/pages/CitizenFloodMapPage'
import HistoricalEventsPage from '@/pages/HistoricalEventsPage'
import ReportsPage from '@/pages/ReportsPage'
import FeedbackPage from '@/pages/FeedbackPage'
import AdminSubmissionsPage from '@/pages/AdminSubmissionsPage'
import SafetyPage from '@/pages/SafetyPage'
import AdminDashboardPage from '@/dashboard/page'
import { getSession, isCitizen } from '@/lib/session'

function RoleGate({ role, children }: { role: 'admin' | 'citizen'; children: ReactNode }) {
  try {
    const user = getSession()
    if (!user || user.role !== role) return <Navigate to="/login" replace />
  } catch {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

function CitizenGate({ children }: { children: ReactNode }) {
  try {
    const user = getSession()
    if (!isCitizen(user)) {
      return <Navigate to="/login" replace />
    }
  } catch {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

function AppContent() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public entry pages */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/landing" element={<LandingPage />} />
        <Route path="/flood-map" element={<CitizenFloodMapPage />} />
        <Route path="/public-flood-map" element={<PublicFloodMapPage />} />
        <Route path="/assess-flood-risk" element={<AssessFloodRiskPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        {/* Protected citizen & workspace pages */}
        <Route path="/citizen" element={<CitizenGate><CitizenEntryPage /></CitizenGate>} />
        <Route path="/citizen-entry" element={<CitizenGate><CitizenEntryPage /></CitizenGate>} />
        <Route path="/prediction" element={<CitizenGate><PredictionPage /></CitizenGate>} />
        {/* The citizen dashboard is the same real-data workspace used by the
            /citizen entry route.  The old dashboard/page.tsx is an admin
            mock/template and must never be exposed to citizens. */}
        <Route path="/dashboard" element={<CitizenGate><CitizenEntryPage /></CitizenGate>} />
        <Route path="/analytics" element={<CitizenGate><AnalyticsPage /></CitizenGate>} />
        <Route path="/alerts" element={<CitizenGate><AlertsPage /></CitizenGate>} />
        <Route path="/ai-assistant" element={<CitizenGate><AiAssistantPage /></CitizenGate>} />
        <Route path="/risk-map" element={<CitizenGate><CitizenFloodMapPage /></CitizenGate>} />
        <Route path="/history" element={<CitizenGate><HistoryPage /></CitizenGate>} />
        <Route path="/historical-events" element={<CitizenGate><HistoricalEventsPage /></CitizenGate>} />
        <Route path="/reports" element={<CitizenGate><ReportsPage /></CitizenGate>} />
        <Route path="/feedback" element={<CitizenGate><FeedbackPage /></CitizenGate>} />
        <Route path="/safety" element={<CitizenGate><SafetyPage /></CitizenGate>} />
        <Route path="/admin/submissions" element={<RoleGate role="admin"><AdminSubmissionsPage /></RoleGate>} />
        <Route path="/unified-dashboard" element={<Navigate to="/admin-dashboard" replace />} />
        <Route
          path="/admin-dashboard"
          element={
            <RoleGate role="admin">
              <AdminDashboardPage />
            </RoleGate>
          }
        />
        <Route
          path="/admin-dashboard/:tab"
          element={
            <RoleGate role="admin">
              <AdminDashboardPage />
            </RoleGate>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

function App() {
  return (
    <ConfigProvider>
      <LoggingProvider>
        <ThemeProvider>
          <AppContent />
        </ThemeProvider>
      </LoggingProvider>
    </ConfigProvider>
  )
}

export default App
