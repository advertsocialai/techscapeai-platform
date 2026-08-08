import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './lib/auth'
import DashboardLayout from './features/layout/DashboardLayout'
import LoginPage from './features/auth/LoginPage'
import SignupPage from './features/auth/SignupPage'
import ForgotPasswordPage from './features/auth/ForgotPasswordPage'
import ResetPasswordPage from './features/auth/ResetPasswordPage'
import MissionControlPage from './features/mission-control/MissionControlPage'
import JourneyBoardPage from './features/journey-board/JourneyBoardPage'
import GuestStoryPage from './features/guest-story/GuestStoryPage'
import BookingsPage from './features/bookings/BookingsPage'
import PlaybooksPage from './features/playbooks/PlaybooksPage'
import LiveCallPage from './features/live-call/LiveCallPage'
import LiveCallDetailPage from './features/live-call/LiveCallDetailPage'
import PackagesPage from './features/revenue/PackagesPage'
import PaymentLinksPage from './features/revenue/PaymentLinksPage'
import WhatsAppPage from './features/comms/WhatsAppPage'
import FollowUpsPage from './features/comms/FollowUpsPage'
import ReportsPage from './features/reports/ReportsPage'
import CostPage from './features/reports/CostPage'
import ReportSchedulesPage from './features/reports/ReportSchedulesPage'
import TeamPage from './features/team/TeamPage'
import ActivityLogPage from './features/team/ActivityLogPage'
import AiConfigPage from './features/playbooks/AiConfigPage'
import EmpirePage from './features/admin/EmpirePage'

function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth()
  const location = useLocation()

  if (loading) return <div className="loading-block">Loading…</div>
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route
        element={
          <RequireAuth>
            <DashboardLayout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<MissionControlPage />} />
        <Route path="/journey-board" element={<JourneyBoardPage />} />
        <Route path="/journey-board/:leadId" element={<GuestStoryPage />} />
        <Route path="/bookings" element={<BookingsPage />} />
        <Route path="/packages" element={<PackagesPage />} />
        <Route path="/payment-links" element={<PaymentLinksPage />} />
        <Route path="/whatsapp" element={<WhatsAppPage />} />
        <Route path="/follow-ups" element={<FollowUpsPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/cost" element={<CostPage />} />
        <Route path="/report-schedules" element={<ReportSchedulesPage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="/activity" element={<ActivityLogPage />} />
        <Route path="/playbooks" element={<PlaybooksPage />} />
        <Route path="/ai-config" element={<AiConfigPage />} />
        <Route path="/empire" element={<EmpirePage />} />
        <Route path="/live-call" element={<LiveCallPage />} />
        <Route path="/live-call/:callId" element={<LiveCallDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
