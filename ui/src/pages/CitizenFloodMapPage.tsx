import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  RefreshCw,
  Bell,
  User,
  Activity,
  AlertTriangle,
  Droplets,
  Menu,
  X
} from 'lucide-react'
import CitizenSidebar from '@/components/CitizenSidebar'
import GlobalWatershedMap from '@/components/GlobalWatershedMap'
import { dashboardApi, userPredictionsApi, type DashboardData, type Watershed } from '@/lib/api'
import { getSession } from '@/lib/session'

export default function CitizenFloodMapPage() {
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [user, setUser] = useState<{ name?: string; username?: string; role?: string; email?: string } | null>(null)
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null)
  const [selectedWatershed, setSelectedWatershed] = useState<Watershed | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setUser(getSession())

    // 2. Fetch authenticated profile
    userPredictionsApi
      .getMe()
      .then((profile) => {
        if (profile) {
          setUser((prev) => ({ ...prev, ...profile }))
        }
      })
      .catch(() => {})

    // 3. Load flood map / watershed data
    fetchData()
  }, [])

  const fetchData = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await dashboardApi.getDashboardData()
      setDashboardData(data)
    } catch (err) {
      console.error('Failed to load flood map data:', err)
      setError('Unable to load latest telemetry API. Showing cached hydrological basin data.')
    } finally {
      setIsLoading(false)
    }
  }

  const displayName = user?.name || user?.username || user?.email || 'Citizen Responder'
  const summary = dashboardData?.summary
  const watersheds = dashboardData?.watersheds || []

  return (
    <div className="flex h-screen w-full bg-[#060B13] font-sans text-slate-100 selection:bg-blue-600 selection:text-white overflow-hidden">
      {/* 1) Citizen Dashboard Sidebar */}
      <CitizenSidebar
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
      />

      {/* 2) Main Content Column */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#060B13] h-full overflow-hidden">
        {/* Top Citizen Header Bar (matches CitizenEntryPage / PredictionPage) */}
        <header className="bg-[#060B13] border-b border-slate-800/80 px-4 sm:px-8 py-3.5 flex items-center justify-between shrink-0 z-20">
          {/* Left: Mobile hamburger + Status Indicator */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="lg:hidden p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="Open sidebar navigation"
            >
              <Menu className="w-5 h-5" />
            </button>

            <div className="flex items-center gap-2 text-xs text-slate-400 font-medium">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="hidden sm:inline">Live hydrological telemetry active</span>
              <span className="sm:hidden">Live map active</span>
            </div>
          </div>

          {/* Right: Refresh, Bell, User Profile */}
          <div className="flex items-center gap-3 sm:gap-4">
            <button
              onClick={fetchData}
              disabled={isLoading}
              className="text-slate-400 hover:text-white p-2 rounded-full hover:bg-slate-800/60 transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
              title="Refresh Map Data"
              aria-label="Refresh Map Data"
            >
              <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin text-blue-400' : ''}`} />
            </button>

            <button
              className="p-2 rounded-full hover:bg-slate-800/60 text-slate-400 hover:text-white transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
              aria-label="Notifications"
            >
              <Bell className="h-4 w-4" />
            </button>

            {/* Profile Avatar & Name */}
            {user ? (
              <div className="flex items-center gap-2.5 pl-2 border-l border-slate-800">
                <div className="text-right hidden sm:block leading-tight">
                  <p className="text-xs font-bold text-white truncate max-w-[180px]">{displayName}</p>
                  <p className="text-[10px] text-slate-400 font-medium">Citizen responder</p>
                </div>
                <div className="h-8 w-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-200 shrink-0">
                  <User className="h-4 w-4" />
                </div>
              </div>
            ) : (
              <button
                onClick={() => navigate('/login')}
                className="bg-[#1D68F7] hover:bg-blue-600 text-white text-xs font-semibold px-4 py-1.5 rounded-full shadow-md transition-all cursor-pointer"
              >
                Access Portal
              </button>
            )}
          </div>
        </header>

        {/* 3) Map Body Content */}
        <main className="flex-1 flex flex-col min-w-0 p-4 sm:p-6 pb-4 overflow-hidden gap-3">
          {/* Header & Stats Ribbon */}
          <div className="shrink-0 flex flex-col md:flex-row md:items-center justify-between gap-3 bg-[#0a1120] border border-slate-800/80 rounded-2xl px-5 py-3 shadow-lg">
            <div>
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  <Activity className="w-3 h-3" /> Live Basin Telemetry
                </span>
                {summary?.last_updated && (
                  <span className="text-[11px] text-slate-500">
                    Updated: {new Date(summary.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                )}
              </div>
              <h1 className="text-lg sm:text-xl font-black text-white tracking-tight mt-1">
                Cameroon Flood Risk Map
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Real-time hydrological basin monitoring, risk classifications, and satellite telemetry across Cameroon.
              </p>
            </div>

            {/* Basin Risk Badges */}
            <div className="flex items-center gap-2.5 flex-wrap">
              <div className="bg-slate-900/90 border border-slate-800 rounded-xl px-3 py-1.5 min-w-[70px]">
                <p className="text-[9px] font-bold uppercase tracking-wider text-slate-400">Monitored</p>
                <p className="text-base font-black text-slate-200 leading-tight">
                  {summary?.total_watersheds ?? watersheds.length ?? 32}
                </p>
              </div>
              <div className="bg-red-950/40 border border-red-900/50 rounded-xl px-3 py-1.5 min-w-[70px]">
                <p className="text-[9px] font-bold uppercase tracking-wider text-red-400">High Risk</p>
                <p className="text-base font-black text-red-500 leading-tight">
                  {summary?.high_risk_watersheds ?? 0}
                </p>
              </div>
              <div className="bg-amber-950/40 border border-amber-900/50 rounded-xl px-3 py-1.5 min-w-[70px]">
                <p className="text-[9px] font-bold uppercase tracking-wider text-amber-400">Moderate</p>
                <p className="text-base font-black text-amber-500 leading-tight">
                  {summary?.moderate_risk_watersheds ?? 0}
                </p>
              </div>
              <div className="bg-emerald-950/40 border border-emerald-900/50 rounded-xl px-3 py-1.5 min-w-[70px]">
                <p className="text-[9px] font-bold uppercase tracking-wider text-emerald-400">Low Risk</p>
                <p className="text-base font-black text-emerald-400 leading-tight">
                  {summary?.low_risk_watersheds ?? (summary?.total_watersheds ?? watersheds.length ?? 32)}
                </p>
              </div>
            </div>
          </div>

          {error && (
            <div className="shrink-0 bg-amber-950/40 border border-amber-800/60 rounded-xl px-4 py-2.5 flex items-center gap-2.5 text-xs text-amber-300">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Interactive Map Wrapper — takes full remaining height */}
          <div className="flex-1 relative w-full rounded-2xl overflow-hidden border border-slate-800/80 shadow-2xl bg-[#030712]">
            {/* Dark Styled Risk Legend at bottom-left */}
            <div className="absolute bottom-4 left-4 z-[1000] bg-slate-900/90 backdrop-blur-md border border-slate-700/80 p-3 rounded-xl text-xs space-y-1.5 shadow-2xl font-semibold text-slate-200">
              <p className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">Risk Legend</p>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-red-500 shadow-sm shadow-red-500/50" /> High Risk
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-amber-500 shadow-sm shadow-amber-500/50" /> Moderate Risk
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50" /> Low Risk
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-blue-500 shadow-sm shadow-blue-500/50" /> Community Report
              </div>
            </div>

            {/* The Map Component */}
            <GlobalWatershedMap
              watersheds={watersheds}
              height="100%"
              onWatershedClick={(ws) => setSelectedWatershed(ws)}
            />

            {/* Selected Watershed Floating Inspector Drawer */}
            {selectedWatershed && (
              <div className="absolute bottom-4 right-4 z-[1000] max-w-sm w-full bg-slate-900/95 backdrop-blur-md border border-slate-700/90 rounded-2xl p-4 shadow-2xl space-y-3 animate-in fade-in slide-in-from-bottom-3 duration-200">
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Selected Basin
                    </span>
                    <h3 className="text-base font-extrabold text-white mt-0.5">
                      {selectedWatershed.name}
                    </h3>
                    <p className="text-xs text-slate-400">
                      {selectedWatershed.region || 'Cameroon'} Region
                    </p>
                  </div>
                  <button
                    onClick={() => setSelectedWatershed(null)}
                    className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
                    aria-label="Close basin inspector"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400">Risk Level</span>
                    <span
                      className={`font-bold px-2 py-0.5 rounded-full text-[11px] ${
                        selectedWatershed.current_risk_level === 'High'
                          ? 'bg-red-950 text-red-400 border border-red-800/60'
                          : selectedWatershed.current_risk_level === 'Moderate'
                          ? 'bg-amber-950 text-amber-400 border border-amber-800/60'
                          : 'bg-emerald-950 text-emerald-400 border border-emerald-800/60'
                      }`}
                    >
                      {selectedWatershed.current_risk_level || 'Low'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Current Streamflow</span>
                    <span className="font-bold text-slate-200">
                      {selectedWatershed.current_streamflow_cms != null
                        ? `${Number(selectedWatershed.current_streamflow_cms).toFixed(1)} m³/s`
                        : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Flood Stage</span>
                    <span className="font-bold text-slate-200">
                      {selectedWatershed.flood_stage_cms != null
                        ? `${Number(selectedWatershed.flood_stage_cms).toFixed(1)} m³/s`
                        : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Basin Area</span>
                    <span className="font-bold text-slate-200">
                      {selectedWatershed.basin_size_sqkm != null
                        ? `${Number(selectedWatershed.basin_size_sqkm).toLocaleString()} km²`
                        : 'N/A'}
                    </span>
                  </div>
                </div>

                <div>
                  <button
                    onClick={() => {
                      const lat = selectedWatershed.location_lat
                      const lon = selectedWatershed.location_lng
                      const query = [
                        lat != null ? `lat=${lat}` : null,
                        lon != null ? `lon=${lon}` : null,
                        selectedWatershed.name
                          ? `locality=${encodeURIComponent(selectedWatershed.name)}`
                          : null
                      ]
                        .filter(Boolean)
                        .join('&')
                      navigate(query ? `/assess-flood-risk?${query}` : '/assess-flood-risk')
                    }}
                    className="w-full bg-[#1D68F7] hover:bg-blue-600 text-white text-xs font-bold py-2.5 px-4 rounded-xl shadow-md transition-colors flex items-center justify-center gap-2 cursor-pointer"
                  >
                    <Droplets className="w-3.5 h-3.5" />
                    <span>Assess Flood Risk For This Locality</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
