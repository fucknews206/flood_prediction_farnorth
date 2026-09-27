import { useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  TrendingUp,
  MapPin,
  FileText,
  History,
  ShieldCheck,
  LogOut,
  MessageSquare,
  X,
  Bot
} from 'lucide-react'

interface CitizenSidebarProps {
  isOpen?: boolean
  onClose?: () => void
}

export default function CitizenSidebar({ isOpen = false, onClose }: CitizenSidebarProps) {
  const navigate = useNavigate()
  const location = useLocation()

  const currentPath = location.pathname

  const isCurrent = (path: string) => {
    if (path === '/dashboard') {
      return currentPath === '/dashboard' || currentPath === '/citizen' || currentPath === '/citizen-entry'
    }
    return currentPath === path
  }

  const handleNav = (path: string) => {
    navigate(path)
    if (onClose) onClose()
  }

  const handleLogout = () => {
    localStorage.removeItem('aquaguard_user')
    navigate('/login')
  }

  const navItemClass = (active: boolean) =>
    `w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl font-semibold text-xs transition-all cursor-pointer text-left focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none focus-visible:ring-offset-2 focus-visible:ring-offset-[#030712] ${
      active
        ? 'bg-[#1D68F7] text-white shadow-md shadow-blue-600/30'
        : 'text-slate-400 hover:text-white hover:bg-slate-800/50'
    }`

  const sidebarContent = (
    <div className="flex flex-col h-full justify-between">
      <div className="space-y-6">
        {/* Brand Header */}
        <div className="flex items-center justify-between">
          <div
            className="flex items-center gap-3 px-2 py-2 cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 rounded-xl"
            tabIndex={0}
            onClick={() => handleNav('/')}
            onKeyDown={(e) => e.key === 'Enter' && handleNav('/')}
            role="button"
            aria-label="AquaGuard AI Cameroon Flood Intelligence - Go to home"
          >
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-blue-500/20 shrink-0">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-white font-extrabold text-base tracking-tight leading-none">
                AquaGuard AI
              </h1>
              <p className="text-[9px] font-bold text-slate-400 tracking-wider uppercase mt-1">
                Cameroon Flood Intelligence
              </p>
            </div>
          </div>

          {onClose && (
            <button
              onClick={onClose}
              className="lg:hidden p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="Close sidebar navigation"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Navigation Sections */}
        <div className="space-y-4">
          {/* Section: Overview */}
          <div>
            <p className="text-[10px] font-bold tracking-wider text-slate-500 uppercase px-3.5 mb-1.5">
              Overview
            </p>
            <button
              onClick={() => handleNav('/dashboard')}
              className={navItemClass(isCurrent('/dashboard'))}
              aria-current={isCurrent('/dashboard') ? 'page' : undefined}
            >
              <LayoutDashboard className="h-4 w-4 shrink-0" />
              <span>Dashboard</span>
            </button>
          </div>

          {/* Section: Flood Intelligence */}
          <div>
            <p className="text-[10px] font-bold tracking-wider text-slate-500 uppercase px-3.5 mb-1.5">
              Flood Intelligence
            </p>
            <div className="space-y-1">
              <button
                onClick={() => handleNav('/prediction')}
                className={navItemClass(isCurrent('/prediction'))}
                aria-current={isCurrent('/prediction') ? 'page' : undefined}
              >
                <TrendingUp className="h-4 w-4 shrink-0" />
                <span>Flood Prediction</span>
              </button>

              <button
                onClick={() => handleNav('/flood-map')}
                className={navItemClass(isCurrent('/flood-map') || isCurrent('/risk-map'))}
                aria-current={isCurrent('/flood-map') ? 'page' : undefined}
              >
                <MapPin className="h-4 w-4 shrink-0" />
                <span>Flood map</span>
              </button>

              <button
                onClick={() => handleNav('/ai-assistant')}
                className={navItemClass(isCurrent('/ai-assistant'))}
                aria-current={isCurrent('/ai-assistant') ? 'page' : undefined}
              >
                <Bot className="h-4 w-4 shrink-0" />
                <span>AI Assistant</span>
              </button>
            </div>
          </div>

          {/* Section: My Information */}
          <div>
            <p className="text-[10px] font-bold tracking-wider text-slate-500 uppercase px-3.5 mb-1.5">
              My information
            </p>
            <div className="space-y-1">
              <button
                onClick={() => handleNav('/reports')}
                className={navItemClass(isCurrent('/reports'))}
                aria-current={isCurrent('/reports') ? 'page' : undefined}
              >
                <FileText className="h-4 w-4 shrink-0" />
                <span>Reports</span>
              </button>

              <button
                onClick={() => handleNav('/history')}
                className={navItemClass(isCurrent('/history'))}
                aria-current={isCurrent('/history') ? 'page' : undefined}
              >
                <History className="h-4 w-4 shrink-0" />
                <span>History</span>
              </button>

              <button
                onClick={() => handleNav('/safety')}
                className={navItemClass(isCurrent('/safety'))}
                aria-current={isCurrent('/safety') ? 'page' : undefined}
              >
                <ShieldCheck className="h-4 w-4 shrink-0" />
                <span>Safety</span>
              </button>

              <button
                onClick={() => handleNav('/feedback')}
                className={navItemClass(isCurrent('/feedback'))}
                aria-current={isCurrent('/feedback') ? 'page' : undefined}
              >
                <MessageSquare className="h-4 w-4 shrink-0" />
                <span>Feedback</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Sidebar: Log out */}
      <div className="pt-4 border-t border-slate-800/80">
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl font-semibold text-xs text-rose-400 hover:text-rose-300 hover:bg-rose-950/20 transition-all cursor-pointer focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:outline-none"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          <span>Log out</span>
        </button>
      </div>
    </div>
  )

  return (
    <>
      {/* Desktop Sticky Full-Height Sidebar (Takes all height, right away to the end) */}
      <aside className="hidden lg:flex flex-col w-64 bg-[#030712] border-r border-slate-800/80 select-none z-30 shrink-0 p-4 sticky top-0 h-screen overflow-hidden">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm lg:hidden transition-opacity"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Mobile Drawer Content */}
      <div
        className={`fixed top-0 bottom-0 left-0 z-50 w-64 bg-[#030712] border-r border-slate-800/80 p-4 transition-transform duration-200 ease-in-out lg:hidden ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {sidebarContent}
      </div>
    </>
  )
}
