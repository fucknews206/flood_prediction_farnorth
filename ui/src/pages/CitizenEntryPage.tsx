import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  MapPin,
  Maximize2,
  Camera,
  History,
  Map as MapIcon,
  RefreshCw,
  Bell,
  User,
  Plus,
  ChevronDown,
  X,
  Loader2,
  ArrowRight
} from 'lucide-react'

import CitizenSidebar from '@/components/CitizenSidebar'
import {
  userPredictionsApi,
  farNorthRiskApi,
  telemetryApi,
  type UserPredictionRecord,
  type TelemetrySource
} from '@/lib/api'

// Available Far North localities
const FAR_NORTH_LOCALITIES = [
  'Doukoula',
  'Kousséri',
  'Maroua',
  'Yagoua',
  'Blangoua',
  'Maga',
  'Zina',
  'Kaélé',
  'Mora',
  'Mokolo',
  'Waza',
  'Bogo',
  'Guidiguis'
]

export default function CitizenEntryPage() {
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  // Authenticated user state
  const [user, setUser] = useState<{ name?: string; username?: string; role?: string; email?: string } | null>(null)

  // Location & Prediction state
  // State A: locality = null
  // State B: locality = string, latestPrediction = null (or not for this locality)
  // State C: locality = string, latestPrediction = record for this locality
  const [selectedLocality, setSelectedLocality] = useState<string | null>(null)
  const [latestPrediction, setLatestPrediction] = useState<UserPredictionRecord | null>(null)
  const [predictionLoading, setPredictionLoading] = useState(true)

  // 7-day forecast state
  const [forecastTrajectory, setForecastTrajectory] = useState<any[]>([])
  const [, setForecastLoading] = useState(false)
  const [activeTrajectoryTab, setActiveTrajectoryTab] = useState<'7days' | 'historical'>('7days')

  // Modals & UI states
  const [locationModalOpen, setLocationModalOpen] = useState(false)
  const [dataSourcesExpanded, setDataSourcesExpanded] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)

  // Telemetry status
  const [telemetrySources, setTelemetrySources] = useState<TelemetrySource[] | null>(null)
  const [telemetryLoading, setTelemetryLoading] = useState(false)

  useEffect(() => {
    // 1. Initial user from localStorage
    const stored = localStorage.getItem('aquaguard_user')
    if (stored) {
      try {
        const parsed = JSON.parse(stored)
        setUser(parsed)
      } catch {
        // ignore
      }
    }

    // 2. Fetch authenticated profile
    userPredictionsApi.getMe().then((profile) => {
      if (profile) {
        setUser((prev) => ({ ...prev, ...profile }))
      }
    }).catch(() => {})

    // 3. Load latest prediction
    loadDashboardData()

    // 4. Fetch real-time telemetry status
    fetchTelemetryStatus()
  }, [])

  const fetchTelemetryStatus = async () => {
    setTelemetryLoading(true)
    try {
      const result = await telemetryApi.status()
      if (result?.sources) {
        setTelemetrySources(result.sources)
      }
    } catch {
      // leave as null — will show offline state
    } finally {
      setTelemetryLoading(false)
    }
  }

  const loadDashboardData = async () => {
    setPredictionLoading(true)
    setIsRefreshing(true)
    try {
      const res = await userPredictionsApi.getLatest()
      const pred = res?.prediction

      if (pred && pred.locality) {
        // We have a verified prediction
        setLatestPrediction(pred)
        setSelectedLocality(pred.locality)
        await loadForecast(pred.locality)
      } else {
        // State A: No locality selected
        setLatestPrediction(null)
        setSelectedLocality(null)
        setForecastTrajectory([])
      }
    } catch {
      setLatestPrediction(null)
      setSelectedLocality(null)
      setForecastTrajectory([])
    } finally {
      setPredictionLoading(false)
      setIsRefreshing(false)
    }
  }

  const loadForecast = async (locality: string) => {
    setForecastLoading(true)
    try {
      const data = await farNorthRiskApi.forecast(locality)
      if (data && Array.isArray(data.trajectory) && data.trajectory.length > 0) {
        setForecastTrajectory(data.trajectory)
      } else {
        setForecastTrajectory([])
      }
    } catch {
      setForecastTrajectory([])
    } finally {
      setForecastLoading(false)
    }
  }

  const handleSelectLocality = async (locality: string) => {
    setSelectedLocality(locality)
    setLocationModalOpen(false)

    // Check if current prediction matches this locality
    if (latestPrediction && latestPrediction.locality === locality) {
      // State C
      await loadForecast(locality)
    } else {
      // State B: Location selected, but no prediction run yet for it
      setLatestPrediction(null)
      await loadForecast(locality)
    }
  }

  const handleClearLocality = () => {
    setSelectedLocality(null)
    setLatestPrediction(null)
    setForecastTrajectory([])
    setLocationModalOpen(false)
  }

  // Display user properties
  const displayName = user?.name || user?.username || 'jeanongoubolo'
  const userGreetingName = displayName.includes('@') ? displayName.split('@')[0] : displayName

  // Dynamic greeting time
  const currentHour = new Date().getHours()
  const greetingTime = currentHour < 12 ? 'Good morning' : currentHour < 18 ? 'Good afternoon' : 'Good evening'

  // Computed Risk States
  const hasLocality = Boolean(selectedLocality)
  const hasPrediction = Boolean(latestPrediction && latestPrediction.locality === selectedLocality)

  const isHighRisk = latestPrediction?.risk_level?.toLowerCase().includes('high')
  const isModerateRisk = latestPrediction?.risk_level?.toLowerCase().includes('mod')
  const riskColor = isHighRisk ? '#EF4444' : isModerateRisk ? '#F59E0B' : '#10B981'

  // Default trajectory for the dashboard chart when no real data loaded yet
  const DEFAULT_TRAJECTORY = (() => {
    const today = new Date()
    return [0.246, 0.251, 0.315, 0.338, 0.276, 0.248, 0.235].map((prob, i) => {
      const d = new Date(today); d.setDate(d.getDate() + i)
      return { date: d.toISOString().split('T')[0], classifier_probability: prob, option_b_threshold_flag: i === 2 || i === 3 }
    })
  })()

  const chartTrajectory = forecastTrajectory.length > 0 ? forecastTrajectory : DEFAULT_TRAJECTORY

  // Trajectory SVG coordinates computation (probability-based)
  const chartW = 560, chartH = 80, padX = 20
  const maxProb = Math.max(0.1, ...chartTrajectory.map(p => Number(p.classifier_probability || 0)))
  const trajectoryPoints = chartTrajectory.map((p, idx) => ({
    x: chartTrajectory.length > 1 ? padX + (idx / (chartTrajectory.length - 1)) * (chartW - padX * 2) : chartW / 2,
    y: chartH - Math.max(8, (Number(p.classifier_probability || 0) / maxProb) * (chartH - 12)),
    prob: Number(p.classifier_probability || 0),
    elevated: Boolean(p.option_b_threshold_flag),
    point: p
  }))

  const pathD = trajectoryPoints.reduce((acc, pt, i) => {
    if (i === 0) return `M ${pt.x},${pt.y}`
    const prev = trajectoryPoints[i - 1]
    const cx = (prev.x + pt.x) / 2
    return `${acc} C ${cx},${prev.y} ${cx},${pt.y} ${pt.x},${pt.y}`
  }, '')
  const areaD = pathD + ` L ${trajectoryPoints[trajectoryPoints.length-1].x},${chartH} L ${trajectoryPoints[0].x},${chartH} Z`

  return (
    <div className="flex min-h-screen w-full bg-[#060B13] font-sans text-slate-100 selection:bg-blue-600 selection:text-white">
      {/* 1) Sidebar takes full height, goes right away to the end */}
      <CitizenSidebar
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#060B13]">
        {/* Top Header Bar */}
        <header className="bg-[#060B13] border-b border-slate-800/80 px-6 sm:px-8 py-3.5 flex items-center justify-between sticky top-0 z-20">
          {/* Status Indicator (Issue #6: subtle, calm, accurate status wording) */}
          <div className="flex items-center gap-2 text-xs text-slate-400 font-medium">
            <span className="h-2 w-2 rounded-full bg-slate-400" />
            <span>Live status unavailable</span>
          </div>

          {/* Right Controls: Refresh, Bell, User Profile */}
          <div className="flex items-center gap-4">
            <button
              onClick={loadDashboardData}
              className="text-slate-400 hover:text-white p-2 rounded-full hover:bg-slate-800/60 transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
              title="Refresh Dashboard Data"
              aria-label="Refresh Dashboard Data"
            >
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin text-blue-400' : ''}`} />
            </button>

            <button
              className="p-2 rounded-full hover:bg-slate-800/60 text-slate-400 hover:text-white transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
              aria-label="Notifications"
            >
              <Bell className="h-4 w-4" />
            </button>

            {/* Profile Avatar & Name */}
            <div className="flex items-center gap-2.5 pl-2">
              <div className="text-right hidden sm:block leading-tight">
                <p className="text-xs font-bold text-white">{displayName}</p>
                <p className="text-[10px] text-slate-400 font-medium">Citizen responder</p>
              </div>
              <div className="h-8 w-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-200">
                <User className="h-4 w-4" />
              </div>
            </div>
          </div>
        </header>

        {/* Dashboard Body Content */}
        <main className="flex-1 p-6 sm:p-8 space-y-6 max-w-7xl w-full mx-auto">
          {/* Main Greeting & Canonical Top CTA */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
                {greetingTime}, {userGreetingName}.
              </h1>
              <p className="text-xs sm:text-sm text-slate-400 font-medium mt-1">
                Your flood-risk dashboard.
              </p>
            </div>

            {/* Issue #2 Canonical CTA: + Assess flood risk */}
            <button
              onClick={() => navigate('/assess-flood-risk')}
              className="bg-[#1D68F7] hover:bg-blue-600 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-md shadow-blue-600/20 flex items-center gap-1.5 transition-all self-start sm:self-auto cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
            >
              <Plus className="w-4 h-4" />
              <span>Assess flood risk</span>
            </button>
          </div>

          {/* Location Context Bar (Issue #1: consistent geographic state) */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 py-3 px-4 rounded-xl bg-[#0A101D] border border-slate-800/80 text-xs">
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-2 text-white font-semibold">
                <MapPin className="w-4 h-4 text-slate-400" />
                <span>
                  {hasLocality ? `${selectedLocality} · Far North Region` : 'No locality selected'}
                </span>
              </div>
              <span className="text-slate-400 font-medium hidden sm:inline">
                Coverage: Far North Region
              </span>
              <span className="text-slate-500">
                Last updated: {hasPrediction && latestPrediction?.created_at ? new Date(latestPrediction.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
              </span>
            </div>

            <button
              onClick={() => setLocationModalOpen(true)}
              className="text-[#1D68F7] hover:text-blue-400 font-semibold transition-colors cursor-pointer text-left self-start sm:self-auto"
            >
              {hasLocality ? 'Change location' : 'Choose location'}
            </button>
          </div>

          {/* Middle 2-Column Section: Left Assessment Card + Right Map Card */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Column: Current Flood-Risk Assessment (5 cols) */}
            <div className="lg:col-span-5 bg-[#0A101D] border border-slate-800/80 rounded-2xl p-6 flex flex-col justify-between min-h-[300px]">
              <div>
                <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                  Current flood-risk assessment
                </p>

                {predictionLoading ? (
                  <div className="py-12 flex flex-col items-center justify-center gap-2 text-slate-400">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                    <span className="text-xs">Loading flood-risk assessment...</span>
                  </div>
                ) : !hasLocality ? (
                  /* STATE A: NO LOCATION SELECTED (Image 3 exact match) */
                  <div className="pt-6 space-y-3">
                    <h2 className="text-2xl font-bold text-white tracking-tight">
                      No locality selected
                    </h2>
                    <p className="text-xs text-slate-400 leading-relaxed max-w-sm">
                      Choose a location to begin your flood-risk assessment.
                    </p>
                    <div className="pt-4">
                      <button
                        onClick={() => setLocationModalOpen(true)}
                        className="bg-[#1D68F7] hover:bg-blue-600 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-md shadow-blue-600/20 flex items-center gap-2 transition-all cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
                      >
                        <MapPin className="w-3.5 h-3.5" />
                        <span>Choose location</span>
                      </button>
                    </div>
                  </div>
                ) : !hasPrediction ? (
                  /* STATE B: LOCATION SELECTED, NO PREDICTION YET */
                  <div className="pt-6 space-y-3">
                    <div>
                      <h2 className="text-2xl font-bold text-white tracking-tight">
                        {selectedLocality}
                      </h2>
                      <p className="text-xs text-slate-400 font-medium">
                        Far North Region
                      </p>
                    </div>
                    <div className="pt-2">
                      <span className="inline-block px-2.5 py-1 rounded-md text-[11px] font-semibold bg-slate-800/80 text-slate-300 border border-slate-700/60">
                        Location selected · No assessment has been run yet.
                      </span>
                    </div>
                    <div className="pt-4">
                      {/* Issue #2: canonical action [Assess flood risk] */}
                      <button
                        onClick={() => navigate('/assess-flood-risk')}
                        className="bg-[#1D68F7] hover:bg-blue-600 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-md shadow-blue-600/20 flex items-center gap-2 transition-all cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>Assess flood risk</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  /* STATE C: LOCATION SELECTED + PREDICTION AVAILABLE */
                  <div className="pt-4 space-y-4">
                    <div>
                      <h2 className="text-xl font-bold text-white tracking-tight">
                        {selectedLocality}
                      </h2>
                      <p className="text-xs text-slate-400 font-medium">
                        Far North Region
                      </p>
                    </div>

                    <div className="flex items-baseline gap-3 pt-1">
                      <span
                        className="text-4xl font-extrabold tracking-tight"
                        style={{ color: riskColor }}
                      >
                        {latestPrediction?.risk_level?.toUpperCase()}
                      </span>
                      <span className="text-xs text-slate-400 font-medium">
                        risk level
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-4 pt-3 border-t border-slate-800/80">
                      <div>
                        <p className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                          Flood probability
                        </p>
                        <p className="text-lg font-extrabold text-white mt-0.5">
                          {Number(latestPrediction?.estimated_risk_percent || 0).toFixed(1)}%
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">
                          Prediction confidence
                        </p>
                        <p className="text-lg font-extrabold text-white mt-0.5">
                          {Number(latestPrediction?.confidence_score || 0).toFixed(0)}%
                        </p>
                      </div>
                    </div>

                    <div className="pt-2 text-xs text-slate-400">
                      Forecast period: <span className="text-slate-200 font-semibold">{latestPrediction?.forecast_period || 'Next 24–72 hours'}</span>
                    </div>
                  </div>
                )}
              </div>

              {hasPrediction && (
                <div className="pt-4 flex items-center gap-3">
                  <button
                    onClick={() => navigate('/prediction')}
                    className="text-xs font-bold text-[#1D68F7] hover:text-blue-400 flex items-center gap-1 transition-colors"
                  >
                    <span>View assessment details</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>

            {/* Right Column: Cameroon Overview / Map View (7 cols, Image 3 exact match) */}
            <div className="lg:col-span-7 bg-[#0A101D] border border-slate-800/80 rounded-2xl p-5 flex flex-col justify-between min-h-[300px]">
              <div>
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-bold text-slate-200">
                      {hasLocality ? `${selectedLocality} map view` : 'Cameroon overview'}
                    </h3>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      {hasLocality ? 'Far North Region' : 'No locality selected'}
                    </p>
                  </div>
                  <button
                    onClick={() => navigate('/flood-map')}
                    className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800/60 transition-colors"
                    title="Open Full Map"
                  >
                    <Maximize2 className="w-4 h-4" />
                  </button>
                </div>

                {/* Map Display Container */}
                <div className="mt-4 rounded-xl overflow-hidden border border-slate-800/90 relative h-48 sm:h-52 bg-slate-900 flex items-center justify-center">
                  {/* Subtle terrain relief background */}
                  <div
                    className="absolute inset-0 bg-cover bg-center opacity-30 grayscale"
                    style={{ backgroundImage: 'url(/cameroon_hero_map.png)' }}
                  />

                  {/* Active Pin if location is selected */}
                  {hasLocality ? (
                    <div className="relative z-10 flex flex-col items-center gap-1 bg-[#060B13]/90 backdrop-blur-sm px-3 py-1.5 rounded-lg border border-slate-700/80 shadow-lg">
                      <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: riskColor }} />
                        <span className="text-xs font-bold text-white">{selectedLocality}</span>
                      </div>
                      <span className="text-[10px] text-slate-400">
                        {hasPrediction ? `${latestPrediction?.risk_level} Risk` : 'Ready for assessment'}
                      </span>
                    </div>
                  ) : (
                    /* State A neutral loading / non-selected state */
                    <div className="relative z-10 text-xs text-slate-400 font-medium flex items-center gap-2">
                      <span className="text-slate-400">Loading map data...</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Map Footer Bar: Legend & Link */}
              <div className="flex items-center justify-between pt-3 border-t border-slate-800/80 text-xs">
                <div className="flex items-center gap-4 text-slate-400">
                  <span className="flex items-center gap-1.5 text-[11px]">
                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                    Low
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px]">
                    <span className="w-2 h-2 rounded-full bg-amber-400" />
                    Moderate
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px]">
                    <span className="w-2 h-2 rounded-full bg-rose-500" />
                    High
                  </span>
                </div>

                <button
                  onClick={() => navigate('/flood-map')}
                  className="text-xs font-semibold text-[#1D68F7] hover:text-blue-400 transition-colors"
                >
                  View flood map
                </button>
              </div>
            </div>
          </div>

          {/* Quick Actions Row (3 Cards matching Image 3) */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <button
              onClick={() => navigate('/reports')}
              className="bg-[#0A101D] hover:bg-[#0F172A] border border-slate-800/80 p-4 rounded-2xl flex items-center gap-3.5 text-left transition-all cursor-pointer group focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
            >
              <div className="w-10 h-10 rounded-xl bg-slate-800/60 border border-slate-700/60 flex items-center justify-center text-slate-300 group-hover:text-blue-400 transition-colors shrink-0">
                <Camera className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-white group-hover:text-blue-400 transition-colors">
                  Submit a flood report
                </h4>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Share photos and conditions near you
                </p>
              </div>
            </button>

            <button
              onClick={() => navigate('/flood-map')}
              className="bg-[#0A101D] hover:bg-[#0F172A] border border-slate-800/80 p-4 rounded-2xl flex items-center gap-3.5 text-left transition-all cursor-pointer group focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
            >
              <div className="w-10 h-10 rounded-xl bg-slate-800/60 border border-slate-700/60 flex items-center justify-center text-slate-300 group-hover:text-blue-400 transition-colors shrink-0">
                <MapIcon className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-white group-hover:text-blue-400 transition-colors">
                  View flood map
                </h4>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Explore risk zones across the region
                </p>
              </div>
            </button>

            <button
              onClick={() => navigate('/history')}
              className="bg-[#0A101D] hover:bg-[#0F172A] border border-slate-800/80 p-4 rounded-2xl flex items-center gap-3.5 text-left transition-all cursor-pointer group focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
            >
              <div className="w-10 h-10 rounded-xl bg-slate-800/60 border border-slate-700/60 flex items-center justify-center text-slate-300 group-hover:text-blue-400 transition-colors shrink-0">
                <History className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-white group-hover:text-blue-400 transition-colors">
                  Assessment history
                </h4>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Review your past assessments
                </p>
              </div>
            </button>
          </div>

          {/* Risk Trajectory Section (Issue #3: Compact Empty State ~160-220px!) */}
          <div className="bg-[#0A101D] border border-slate-800/80 rounded-2xl p-5 space-y-4">
            {/* Header with 7 days / Historical Toggles */}
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-white">Risk trajectory</h3>
                <p className="text-[11px] text-slate-400 mt-0.5">Far North prediction model</p>
              </div>

              <div className="flex items-center bg-[#060B13] p-1 rounded-xl border border-slate-800/80">
                <button
                  onClick={() => setActiveTrajectoryTab('7days')}
                  className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
                    activeTrajectoryTab === '7days'
                      ? 'bg-slate-800 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  7 days
                </button>
                <button
                  onClick={() => setActiveTrajectoryTab('historical')}
                  className={`px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
                    activeTrajectoryTab === 'historical'
                      ? 'bg-slate-800 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  Historical
                </button>
              </div>
            </div>

            {/* Content: Line chart always shown (default data when no forecast yet) */}
            <div className="pt-3 border-t border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between mb-1">
                <p className="text-[10px] text-slate-500 font-mono">
                  RF Probability · {forecastTrajectory.length > 0 ? selectedLocality || 'Far North' : 'Reference baseline'}
                </p>
                <button
                  onClick={() => navigate('/prediction')}
                  className="text-[10px] font-semibold text-[#1D68F7] hover:text-blue-400 transition-colors"
                >
                  Full forecast →
                </button>
              </div>
              <div className="relative rounded-xl overflow-hidden border border-slate-800/60 bg-slate-950/60">
                <svg className="w-full" viewBox={`0 0 ${chartW} ${chartH + 4}`} preserveAspectRatio="none" style={{ height: '80px' }}>
                  <defs>
                    <linearGradient id="dashProbGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#1D68F7" stopOpacity="0.3" />
                      <stop offset="100%" stopColor="#1D68F7" stopOpacity="0.02" />
                    </linearGradient>
                  </defs>
                  {trajectoryPoints.filter(p => p.elevated).map((p, i) => (
                    <rect
                      key={i}
                      x={p.x - (chartW / chartTrajectory.length / 2)}
                      y={0}
                      width={chartW / chartTrajectory.length}
                      height={chartH}
                      fill="#ef4444"
                      opacity={0.08}
                    />
                  ))}
                  <path d={areaD} fill="url(#dashProbGrad)" />
                  <path d={pathD} fill="none" stroke="#1D68F7" strokeWidth="2" strokeLinejoin="round" />
                  {trajectoryPoints.map((p, i) => (
                    <circle
                      key={i}
                      cx={p.x}
                      cy={p.y}
                      r={3}
                      fill={p.elevated ? '#ef4444' : '#1D68F7'}
                      stroke="#060B13"
                      strokeWidth="1.5"
                    />
                  ))}
                </svg>
                <div className="flex justify-between px-3 pb-2 -mt-1">
                  {chartTrajectory.map((p, i) => {
                    const d = new Date(p.date)
                    const label = i === 0 ? 'Today' : d.toLocaleDateString('en-US', { weekday: 'short' })
                    return <span key={i} className="text-[9px] font-mono text-slate-500">{label}</span>
                  })}
                </div>
              </div>
              {forecastTrajectory.length === 0 && (
                <p className="text-[10px] text-slate-500 text-center pt-1">
                  Showing reference baseline · <button onClick={() => navigate('/assess-flood-risk')} className="text-[#1D68F7] hover:text-blue-400 underline">Assess a locality</button> to see real data
                </p>
              )}
            </div>
          </div>

          {/* Data Sources Accordion — live telemetry status */}
          <div className="bg-[#0A101D] border border-slate-800/80 rounded-2xl overflow-hidden">
            <button
              onClick={() => {
                setDataSourcesExpanded(!dataSourcesExpanded)
                // Refresh status on expand
                if (!dataSourcesExpanded && !telemetryLoading) fetchTelemetryStatus()
              }}
              className="w-full p-4 flex items-center justify-between text-left cursor-pointer hover:bg-slate-800/30 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
              aria-expanded={dataSourcesExpanded}
            >
              <div>
                <h4 className="text-xs font-bold text-white">Data sources</h4>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  {telemetryLoading
                    ? 'Checking live status…'
                    : telemetrySources === null
                    ? '3 sources · status unknown'
                    : `${telemetrySources.filter(s => s.online).length} of ${telemetrySources.length} sources online`}
                </p>
              </div>
              <ChevronDown
                className={`w-4 h-4 text-slate-400 transition-transform ${
                  dataSourcesExpanded ? 'rotate-180 text-white' : ''
                }`}
              />
            </button>

            {dataSourcesExpanded && (
              <div className="px-4 pb-4 pt-2 border-t border-slate-800/60 space-y-1 text-xs text-slate-400">
                {telemetryLoading ? (
                  <div className="flex items-center gap-2 py-3 text-slate-500">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Checking data source availability…</span>
                  </div>
                ) : telemetrySources === null ? (
                  // Could not reach backend at all
                  ['Open-Meteo High-Resolution Precipitation', 'GloFAS River Discharge Monitoring', 'NASA OPERA Sentinel-1 Dynamic Surface Water'].map((label, i, arr) => (
                    <div key={label} className={`flex items-center justify-between py-1.5 ${
                      i < arr.length - 1 ? 'border-b border-slate-800/40' : ''
                    }`}>
                      <span>{label}</span>
                      <span className="text-slate-500 text-[11px]">Status unknown</span>
                    </div>
                  ))
                ) : (
                  telemetrySources.map((src, i) => (
                    <div key={src.label} className={`flex items-center justify-between py-1.5 ${
                      i < telemetrySources.length - 1 ? 'border-b border-slate-800/40' : ''
                    }`}>
                      <span className="flex items-center gap-1.5">
                        <span className={`inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                          src.online ? 'bg-emerald-400' : 'bg-red-500'
                        }`} />
                        {src.label}
                      </span>
                      <span className={`text-[11px] font-mono ${
                        src.online ? 'text-emerald-400' : 'text-red-400'
                      }`}>
                        {src.online
                          ? `Live · ${src.latency_ms != null ? `${src.latency_ms} ms` : 'OK'}`
                          : 'Offline'}
                      </span>
                    </div>
                  ))
                )}
                <button
                  onClick={(e) => { e.stopPropagation(); fetchTelemetryStatus() }}
                  disabled={telemetryLoading}
                  className="mt-2 flex items-center gap-1.5 text-[10px] text-slate-500 hover:text-slate-300 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${telemetryLoading ? 'animate-spin' : ''}`} />
                  Refresh status
                </button>
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Choose Location Modal (Issue #1: allows setting / switching locality state) */}
      {locationModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-[#0E1522] border border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-white">Choose your locality</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Select a locality in the Far North region
                </p>
              </div>
              <button
                onClick={() => setLocationModalOpen(false)}
                className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
                aria-label="Close locality selector"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto pr-1">
              {FAR_NORTH_LOCALITIES.map((loc) => (
                <button
                  key={loc}
                  onClick={() => handleSelectLocality(loc)}
                  className={`p-2.5 rounded-xl text-xs font-semibold text-left transition-all border ${
                    selectedLocality === loc
                      ? 'bg-[#1D68F7] text-white border-blue-500'
                      : 'bg-slate-900/60 text-slate-300 border-slate-800 hover:bg-slate-800 hover:text-white'
                  }`}
                >
                  <MapPin className="w-3.5 h-3.5 inline mr-1.5 text-slate-400" />
                  {loc}
                </button>
              ))}
            </div>

            <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between">
              {selectedLocality && (
                <button
                  onClick={handleClearLocality}
                  className="text-xs text-rose-400 hover:text-rose-300 font-semibold"
                >
                  Clear location
                </button>
              )}
              <button
                onClick={() => setLocationModalOpen(false)}
                className="ml-auto text-xs bg-slate-800 hover:bg-slate-700 text-white font-semibold px-4 py-2 rounded-xl transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
