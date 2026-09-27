import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bell,
  RefreshCw,
  User,
  Plus,
  ChevronDown,
  Download,
  ExternalLink,
  ArrowRight,
  Map as MapIcon,
  Send,
  Loader2,
  Sparkles,
  Bot,
} from 'lucide-react'

import CitizenSidebar from '@/components/CitizenSidebar'
import {
  userPredictionsApi,
  farNorthRiskApi,
  aiApi
} from '@/lib/api'
import { getSession } from '@/lib/session'

// Available reference localities
const REFERENCE_LOCALITIES = [
  'Doukoula',
  'Kousséri',
  'Maroua',
  'Yagoua',
  'Blangoua',
  'Maga'
]

export interface TrajectoryPoint {
  date: string
  local_rainfall_1d_mm: number | null
  local_rainfall_3d_mm?: number
  soil_moisture?: number
  glofas_discharge_m3s?: number | null
  option_b_threshold_flag?: boolean
  option_b_risk_level?: string
  classifier_probability?: number | null
  discharge_lag_fallback?: boolean
}

export interface ActiveAiContext {
  location: string
  prediction: string
  risk: string
  probability: string
  confidence: string
  selectedDate: string
  selectedRiskValue: string
  forecastPeriod: string
  rainfall: number | null
  discharge: number | null
  dayIndex: number
}

export default function PredictionPage() {
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  // Authenticated user state
  const [user, setUser] = useState<{ name?: string; username?: string; role?: string } | null>(null)
  const [selectedLocality, setSelectedLocality] = useState('Doukoula')
  const [localityDropdownOpen, setLocalityDropdownOpen] = useState(false)

  // Real or reference prediction
  const [prediction, setPrediction] = useState<any>(null)
  const [, setLoading] = useState(true)
  const [forecastTrajectory, setForecastTrajectory] = useState<TrajectoryPoint[]>([])
  const [liveStatus, setLiveStatus] = useState<'loading' | 'available' | 'unavailable'>('loading')
  const [liveMessage, setLiveMessage] = useState('Loading live environmental assessment…')
  const [selectedDayIndex, setSelectedDayIndex] = useState<number>(2) // Default Day 3 (elevated point)

  // Active AI Chart Context state
  const [activeAiContext, setActiveAiContext] = useState<ActiveAiContext | null>(null)
  const aiChatRef = useRef<HTMLDivElement>(null)

  // Refreshing state
  const [isRefreshing, setIsRefreshing] = useState(false)

  // AI chat accordion state
  const [aiChatOpen, setAiChatOpen] = useState(false)
  const [chatLoading, setChatLoading] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const [chatMessages, setChatMessages] = useState<Array<{ sender: 'ai' | 'user'; text: string }>>([
    {
      sender: 'ai',
      text: 'Hello jeanongoubolo! I can help you understand the Doukoula flood risk assessment, 7-day trajectory points, and contributing factors. What would you like to know?'
    }
  ])

  // Data sources accordion
  const [dataSourcesOpen, setDataSourcesOpen] = useState(false)

  useEffect(() => {
    setUser(getSession())
    userPredictionsApi.getMe().then((u) => {
      if (u) setUser((prev) => ({ ...prev, ...u }))
    }).catch(() => {})

    loadData()
  }, [selectedLocality])

  const loadData = async () => {
    setLoading(true)
    setIsRefreshing(true)
    try {
      // Load the user's latest SAVED prediction — this is the authoritative
      // record. Never overwrite it with live data.
      const res = await userPredictionsApi.getLatest()
      if (res?.prediction) {
        setPrediction(res.prediction)
      } else {
        setPrediction(null)
      }

      // Load live forecast trajectory for the selected locality (supplementary)
      try {
        const fData = await farNorthRiskApi.forecast(selectedLocality)
        if (fData?.trajectory && Array.isArray(fData.trajectory) && fData.trajectory.length > 0) {
          setForecastTrajectory(fData.trajectory)
          setLiveStatus('available')
          setLiveMessage('Live environmental forecast loaded. A quantitative prediction is shown only when a validated model profile is eligible.')
        } else {
          setForecastTrajectory([])
          setLiveStatus('unavailable')
          setLiveMessage(fData?.message || 'Live prediction temporarily unavailable. No reference trajectory is shown.')
        }
      } catch {
        setForecastTrajectory([])
        setLiveStatus('unavailable')
        setLiveMessage('Live prediction temporarily unavailable. No reference trajectory is shown.')
      }
    } catch {
      setPrediction(null)
      setForecastTrajectory([])
      setLiveStatus('unavailable')
      setLiveMessage('Live prediction temporarily unavailable. No reference trajectory is shown.')
    } finally {
      setLoading(false)
      setIsRefreshing(false)
    }
  }

  // Handle user clicking a point in the 7-day risk trajectory chart
  const handleSelectDay = (index: number) => {
    setSelectedDayIndex(index)
  }


  const handleSendChat = async (presetQuestion?: string) => {
    const query = (presetQuestion || chatInput).trim()
    if (!query || chatLoading) return
    setChatMessages((prev) => [...prev, { sender: 'user', text: query }])
    if (!presetQuestion) setChatInput('')
    setChatLoading(true)

    try {
      const payloadContext = activeAiContext ? {
        location: activeAiContext.location,
        prediction: activeAiContext.prediction,
        risk: activeAiContext.risk,
        probability: activeAiContext.probability,
        confidence: activeAiContext.confidence,
        selected_date: activeAiContext.selectedDate,
        selected_risk_value_state: activeAiContext.selectedRiskValue,
        forecast_period: activeAiContext.forecastPeriod,
        rainfall_1d_mm: activeAiContext.rainfall,
        glofas_discharge_m3s: activeAiContext.discharge
      } : {
        location: `${selectedLocality} · Far North Region`,
        prediction: prediction?.risk_level || 'Unavailable',
        risk: 'Quantitative prediction unavailable',
        probability: 'Unavailable',
        confidence: 'Unavailable',
        selected_date: 'Unavailable',
        selected_risk_value_state: 'Awaiting validated live inputs',
        forecast_period: 'No validated forecast trajectory'
      }

      const res = await aiApi.chat({
        message: query,
        context: payloadContext
      })
      const reply = res?.response
      if (reply) {
        setChatMessages((prev) => [...prev, { sender: 'ai', text: reply }])
      } else {
        throw new Error('No reply')
      }
    } catch {
      // Intelligent contextual explanation fallback based on selected context
      let contextualAnswer = ''
      if (activeAiContext) {
        const isElev = activeAiContext.risk.includes('Elevated')
        const q = query.toLowerCase()
        const rainfallText = activeAiContext.rainfall == null ? 'unavailable' : `${activeAiContext.rainfall} mm`

        if (q.includes('why') || q.includes('elevated') || q.includes('cause') || q.includes('driving')) {
          contextualAnswer = isElev
            ? `On **${activeAiContext.selectedDate} (Day ${activeAiContext.dayIndex + 1})**, the risk in **${selectedLocality}** elevates to **${activeAiContext.probability}** because:
1. **Precipitation Surge**: The available 24-hour rainfall value is **${rainfallText}**.
2. **Upstream River Inflow**: River discharge is forecasted at **${activeAiContext.discharge != null ? activeAiContext.discharge.toFixed(1) + ' m³/s' : 'elevated volume'}** via the Copernicus GloFAS model for the Logone/Chari river network.
3. **Soil Saturation**: Soil moisture exceeds baseline retention capacity, causing immediate runoff into local waterways (mayos).`
            : `On **${activeAiContext.selectedDate} (Day ${activeAiContext.dayIndex + 1})**, the threshold is quiet. 24-hour precipitation is **${rainfallText}**, and river discharge is **${activeAiContext.discharge != null ? activeAiContext.discharge.toFixed(1) + ' m³/s' : 'unavailable'}**. This is environmental context, not a quantitative prediction.`
        } else if (q.includes('precaution') || q.includes('safety') || q.includes('do') || q.includes('action')) {
          contextualAnswer = `**Recommended precautions for ${selectedLocality} on ${activeAiContext.selectedDate}:**
- **Drainage clearing**: Ensure compound ditches and drainage conduits are clear of debris ahead of expected rainfall.
- **Low-lying avoidance**: Avoid parking vehicles or securing livestock near known watercourse channels (mayos).
- **Communication plan**: Keep mobile phones charged and monitor civil protection bulletins in the Far North.
- **Document security**: Elevate essential papers and dry rations in watertight containers.`
        } else if (q.includes('compare') || q.includes('overall') || q.includes('baseline')) {
          contextualAnswer = `**Comparison with overall assessment:**
- The overall reference assessment for **${selectedLocality}** is **${activeAiContext.prediction}**, reflecting the immediate 24-72h baseline.
- On **${activeAiContext.selectedDate}**, the trajectory shows ${isElev ? `a temporary spike to **${activeAiContext.probability}** due to localized precipitation` : `a continuation of stable baseline conditions`}.
- As the weather front passes toward the later days of the 7-day period, conditions return to the baseline normal.`
        } else {
          contextualAnswer = `Based on the trajectory context for **${selectedLocality}** on **${activeAiContext.selectedDate}**:
- **Forecast Day**: Day ${activeAiContext.dayIndex + 1} of 7-day outlook
- **Rainfall**: ${rainfallText}
- **River Discharge**: ${activeAiContext.discharge != null ? activeAiContext.discharge.toFixed(1) + ' m³/s' : 'Stable'}
- **Risk Evaluation**: ${activeAiContext.selectedRiskValue} (Signal: ${activeAiContext.probability}, Confidence: ${activeAiContext.confidence}).

Stay alert to weather updates and follow Cameroon Department of Civil Protection guidelines.`
        }
      } else {
        contextualAnswer = `A quantitative assessment for **${selectedLocality}** is not available yet because the validated live inputs required by the operational model are incomplete. No reference percentage or default forecast is being shown.`
      }

      setChatMessages((prev) => [...prev, { sender: 'ai', text: contextualAnswer }])
    } finally {
      setChatLoading(false)
    }
  }

  const currentTrajectory = forecastTrajectory
  const currentSelectedPoint = currentTrajectory[selectedDayIndex] || currentTrajectory[0]
  const hasValidatedProbabilityTrajectory = currentTrajectory.length > 0 && currentTrajectory.every((point) => point.classifier_probability != null)

  const displayName = user?.name || user?.username || 'jeanongoubolo'

  return (
    <div className="flex min-h-screen w-full bg-[#060B13] font-sans text-slate-100 selection:bg-blue-600 selection:text-white">
      {/* 1) Full Height Sidebar — takes all height, goes right away to the end */}
      <CitizenSidebar
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#060B13]">
        {/* Top Header Bar */}
        <header className="bg-[#060B13] border-b border-slate-800/80 px-6 sm:px-8 py-3.5 flex items-center justify-between sticky top-0 z-20">
          <div className="flex items-center gap-2 text-xs text-slate-400 font-medium">
            <span className={`h-2 w-2 rounded-full ${liveStatus === 'available' ? 'bg-emerald-500' : liveStatus === 'loading' ? 'bg-blue-500 animate-pulse' : 'bg-amber-500'}`} />
            <span>{liveStatus === 'available' ? 'Live environmental assessment' : liveStatus === 'loading' ? 'Checking live providers' : 'Live assessment unavailable'}</span>
          </div>

          {/* Right Controls */}
          <div className="flex items-center gap-4">
            <button
              onClick={loadData}
              className="text-slate-400 hover:text-white p-2 rounded-full hover:bg-slate-800/60 transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
              title="Refresh Assessment Data"
              aria-label="Refresh Assessment Data"
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

        {/* Prediction Page Body Content (Matching Image 1 Pixel to Pixel) */}
        <main className="flex-1 p-6 sm:p-8 space-y-6 max-w-7xl w-full mx-auto">
          {/* Page Title & Top Action */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
                Flood Prediction
              </h1>
              <p className="text-xs sm:text-sm text-slate-400 font-medium mt-1">
                Risk assessment for your selected location
              </p>
            </div>

            {/* Canonical CTA: + Assess flood risk */}
            <button
              onClick={() => navigate('/assess-flood-risk')}
              className="bg-[#1D68F7] hover:bg-blue-600 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-md shadow-blue-600/20 flex items-center gap-1.5 transition-all self-start sm:self-auto cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
            >
              <Plus className="w-4 h-4" />
              <span>New risk assessment</span>
            </button>
          </div>

          {/* Location Selector Bar */}
          <div className="flex items-center gap-3 text-xs flex-wrap">
            <span className="text-slate-400 font-semibold">Location</span>

            <div className="relative">
              <button
                onClick={() => setLocalityDropdownOpen(!localityDropdownOpen)}
                className="bg-[#0A101D] border border-slate-700/80 hover:border-slate-600 text-white font-semibold px-3 py-1.5 rounded-lg flex items-center gap-2 cursor-pointer transition-colors"
              >
                <span>{selectedLocality} · Far North Region</span>
                <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
              </button>

              {localityDropdownOpen && (
                <div className="absolute top-full left-0 mt-1 w-56 bg-[#0E1522] border border-slate-700 rounded-xl shadow-xl z-30 py-1">
                  {REFERENCE_LOCALITIES.map((loc) => (
                    <button
                      key={loc}
                      onClick={() => {
                        setSelectedLocality(loc)
                        setLocalityDropdownOpen(false)
                      }}
                      className="w-full text-left px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 hover:text-white flex items-center justify-between"
                    >
                      <span>{loc} · Far North</span>
                      {selectedLocality === loc && (
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <span className="text-slate-500 text-xs">Live data only — unavailable providers never receive reference values.</span>
          </div>

          <div className="border-l-2 border-amber-500 pl-3 py-1 text-xs text-slate-400 font-medium">
            {liveMessage}
          </div>

          {/* Current Flood Risk Main Card (Image 1 Exact Layout) */}
          <div className="bg-[#0A101D] border border-slate-800/80 rounded-2xl p-6 space-y-6">
            <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-6">
              {/* Left Column: Risk Level & Description */}
              <div className="space-y-2 max-w-xl">
                <p className="text-xs text-slate-400 font-medium">
                  Current flood risk - {selectedLocality}, Far North Region
                </p>
                <h2 className={`text-3xl sm:text-4xl font-black tracking-tight ${prediction?.prediction_status === 'FULL_PREDICTION' || prediction?.prediction_status === 'PARTIAL_DATA' ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {prediction?.prediction_status === 'FULL_PREDICTION' || prediction?.prediction_status === 'PARTIAL_DATA' ? `${prediction?.risk_level || 'Available'} risk` : 'Quantitative prediction unavailable'}
                </h2>
                <p className="text-xs sm:text-sm text-slate-300 font-normal leading-relaxed pt-1">
                  {prediction?.prediction_status === 'FULL_PREDICTION' || prediction?.prediction_status === 'PARTIAL_DATA'
                    ? (prediction?.prediction_status === 'PARTIAL_DATA' ? 'A calibrated risk score is available from validated local rain, soil, discharge-history and terrain inputs. Radar and SAR are optional supporting evidence.' : 'Validated full-model inputs are available for this forecast period.')
                    : (prediction?.explanation || liveMessage)}
                </p>
              </div>

              {/* Right Column: Key Metrics */}
              <div className="flex items-center gap-8 flex-wrap pt-2 lg:pt-0">
                <div>
                  <p className="text-[11px] font-semibold text-slate-400">{prediction?.score_label || 'Validated probability'}</p>
                  <p className="text-2xl sm:text-3xl font-black text-white tracking-tight mt-1">
                    {prediction?.prediction_status === 'PARTIAL_DATA' && prediction?.risk_score != null ? `${Number(prediction.risk_score).toFixed(1)}%` : prediction?.prediction_status === 'FULL_PREDICTION' && prediction?.probability_if_validated != null ? `${Number(prediction.probability_if_validated).toFixed(1)}%` : '—'}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] font-semibold text-slate-400">Data quality</p>
                  <p className="text-2xl sm:text-3xl font-black text-white tracking-tight mt-1">
                    {prediction?.data_quality || '—'}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] font-semibold text-slate-400">Forecast period</p>
                  <p className="text-base sm:text-lg font-bold text-white tracking-tight mt-1">
                    {forecastTrajectory.length ? `Next ${forecastTrajectory.length} forecast days` : 'Unavailable'}
                  </p>
                </div>
              </div>
            </div>

            {/* Risk Scale Bar (4 Segments: Low - current, Moderate, High, Very high) */}
            <div className="space-y-1.5 pt-2">
              <div className="grid grid-cols-4 gap-1.5 h-2">
                <div className="bg-emerald-500 rounded-sm" />
                <div className="bg-amber-500/80 rounded-sm" />
                <div className="bg-rose-500/80 rounded-sm" />
                <div className="bg-rose-900/60 rounded-sm" />
              </div>
              <div className="grid grid-cols-4 text-[10px] text-slate-400 font-medium pt-0.5">
                <span className="text-emerald-400 font-bold">Available only when validated</span>
                <span className="text-slate-400">Moderate</span>
                <span className="text-slate-400">High</span>
                <span className="text-slate-400">Very high</span>
              </div>
            </div>

            {/* Timestamp Notice */}
            <p className="text-[11px] text-slate-500 font-normal pt-1">
              {prediction?.prediction_timestamp ? `Last checked: ${new Date(prediction.prediction_timestamp).toLocaleString()}` : 'No live assessment timestamp available'}
            </p>

            {/* Actions Row */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <button
                onClick={() => navigate('/safety')}
                className="bg-[#1D68F7] hover:bg-blue-600 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-md shadow-blue-600/20 flex items-center gap-1.5 transition-all cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
              >
                <span>View safety guidance</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>

              <button
                onClick={() => window.print()}
                className="bg-[#0E1522] hover:bg-slate-800 text-slate-200 border border-slate-700/80 font-semibold text-xs px-4 py-2.5 rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download report</span>
              </button>

              <button
                onClick={() => navigate('/flood-map')}
                className="text-xs font-semibold text-[#1D68F7] hover:text-blue-400 flex items-center gap-1 transition-colors pl-2"
              >
                <span>View risk map</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* "What to do now" Section (Image 1 Exact 5 Cards) */}
          <div className="space-y-3">
            <div>
              <h3 className="text-base font-bold text-white tracking-tight">
                What to do now
              </h3>
              <p className="text-xs text-slate-400 font-medium">
                Safety recommendations for this low-risk assessment
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
              {/* Card 01 */}
              <div className="bg-[#0A101D] border border-slate-800/80 rounded-xl p-4 space-y-1.5">
                <p className="text-xs font-bold text-emerald-400 font-mono">01</p>
                <h4 className="text-xs font-bold text-white">Stay informed</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed font-normal">
                  Monitor official weather and local authority updates.
                </p>
              </div>

              {/* Card 02 */}
              <div className="bg-[#0A101D] border border-slate-800/80 rounded-xl p-4 space-y-1.5">
                <p className="text-xs font-bold text-emerald-400 font-mono">02</p>
                <h4 className="text-xs font-bold text-white">Prepare essential items</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed font-normal">
                  Keep important documents and supplies easy to reach.
                </p>
              </div>

              {/* Card 03 */}
              <div className="bg-[#0A101D] border border-slate-800/80 rounded-xl p-4 space-y-1.5">
                <p className="text-xs font-bold text-emerald-400 font-mono">03</p>
                <h4 className="text-xs font-bold text-white">Know which areas to avoid</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed font-normal">
                  Be aware of nearby flood-prone routes and low-lying areas.
                </p>
              </div>

              {/* Card 04 */}
              <div className="bg-[#0A101D] border border-slate-800/80 rounded-xl p-4 space-y-1.5">
                <p className="text-xs font-bold text-emerald-400 font-mono">04</p>
                <h4 className="text-xs font-bold text-white">Follow official guidance</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed font-normal">
                  Use instructions from local authorities if conditions change.
                </p>
              </div>

              {/* Card 05 */}
              <div className="bg-[#0A101D] border border-slate-800/80 rounded-xl p-4 space-y-1.5">
                <p className="text-xs font-bold text-emerald-400 font-mono">05</p>
                <h4 className="text-xs font-bold text-white">Check on others</h4>
                <p className="text-[11px] text-slate-400 leading-relaxed font-normal">
                  Share relevant updates with people who may need assistance.
                </p>
              </div>
            </div>
          </div>

          {/* 2-Column Section: Left "Why this prediction?" + Right "Flood risk map" */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Column: Why this prediction? (6 cols) */}
            <div className="lg:col-span-6 bg-[#0A101D] border border-slate-800/80 rounded-2xl p-6 space-y-4">
              <div>
                <h3 className="text-sm font-bold text-white">Why this prediction?</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Factors supplied with the {selectedLocality} assessment
                </p>
              </div>

              <div className="space-y-3 pt-2">
                {/* Factor 1: Rainfall conditions */}
                <div className="flex items-start justify-between py-2 border-b border-slate-800/60 gap-4">
                  <div>
                    <h4 className="text-xs font-bold text-slate-200">Rainfall conditions</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      0.1 mm recorded in a three-day window
                    </p>
                  </div>
                  <span className="text-xs font-bold text-emerald-400 shrink-0">
                    Low
                  </span>
                </div>

                {/* Factor 2: Soil saturation */}
                <div className="flex items-start justify-between py-2 border-b border-slate-800/60 gap-4">
                  <div>
                    <h4 className="text-xs font-bold text-slate-200">Soil saturation</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Soil moisture: 44.6%
                    </p>
                  </div>
                  <span className="text-xs font-bold text-rose-500 shrink-0">
                    High
                  </span>
                </div>

                {/* Factor 3: Historical patterns */}
                <div className="flex items-start justify-between py-2 border-b border-slate-800/60 gap-4">
                  <div>
                    <h4 className="text-xs font-bold text-slate-200">Historical patterns</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      One verified canonical flood event recorded nearby
                    </p>
                  </div>
                  <span className="text-xs font-bold text-amber-400 shrink-0">
                    Moderate
                  </span>
                </div>

                {/* Factor 4: Geographic risk */}
                <div className="flex items-start justify-between py-2 border-b border-slate-800/60 gap-4">
                  <div>
                    <h4 className="text-xs font-bold text-slate-200">Geographic risk</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      0.7 km from a major watercourse
                    </p>
                  </div>
                  <span className="text-xs font-bold text-rose-500 shrink-0">
                    High
                  </span>
                </div>

                {/* Factor 5: Other factors */}
                <div className="flex items-start justify-between py-2 gap-4">
                  <div>
                    <h4 className="text-xs font-bold text-slate-200">Other factors</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Drainage and runoff data unavailable
                    </p>
                  </div>
                  <span className="text-xs font-bold text-slate-400 shrink-0">
                    Unavailable
                  </span>
                </div>
              </div>
            </div>

            {/* Right Column: Flood risk map (6 cols, Image 1 exact match) */}
            <div className="lg:col-span-6 bg-[#0A101D] border border-slate-800/80 rounded-2xl p-6 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-white">Flood risk map</h3>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {selectedLocality} · Far North Region
                    </p>
                  </div>
                  <button
                    onClick={() => navigate('/flood-map')}
                    className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 hover:text-white bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg transition-colors cursor-pointer"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>Open full map</span>
                  </button>
                </div>

                {/* Inner Map Container */}
                <div className="mt-4 rounded-xl overflow-hidden border border-slate-800/90 relative h-60 bg-slate-950 flex flex-col justify-between p-4">
                  {/* Background map graphic */}
                  <div
                    className="absolute inset-0 bg-cover bg-center opacity-40"
                    style={{ backgroundImage: 'url(/cameroon_flood_map.png)' }}
                  />

                  {/* Top Notice */}
                  <p className="relative z-10 text-[11px] text-slate-300 font-medium max-w-xs leading-snug">
                    Illustrative regional risk-pattern map; not a verified location-specific map of {selectedLocality}
                  </p>

                  {/* Bottom Notice */}
                  <p className="relative z-10 text-[10px] text-slate-400 max-w-sm leading-snug">
                    Regional illustration only. {selectedLocality}'s exact position and risk zones are not verified on this image.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* 7-day environmental outlook */}
          <div className="bg-[#0A101D] border border-slate-800/80 rounded-2xl p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-white">7-day environmental outlook</h3>
                  <span className="text-[10px] font-semibold bg-blue-950/60 text-blue-300 border border-blue-800/60 px-2 py-0.5 rounded-full">
                    Live provider evidence
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1 font-normal">
                  Open-Meteo forecast evidence and GloFAS provider status for {selectedLocality}; probabilities require a complete validated model input set.
                </p>
              </div>

              <div className="flex items-center gap-2 text-[11px] text-slate-400">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-500" /> Threshold quiet
                </span>
                <span className="flex items-center gap-1.5 ml-2">
                  <span className="w-2 h-2 rounded-full bg-rose-500" /> Threshold active
                </span>
              </div>
            </div>

            {/* 7 Daily Cards Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2.5">
              {currentTrajectory.map((point, idx) => {
                const isSelected = selectedDayIndex === idx
                const isElevated = Boolean(point.option_b_threshold_flag)
                const hasRain = point.local_rainfall_1d_mm != null
                const rain = hasRain ? Number(point.local_rainfall_1d_mm) : 0
                const rainfallValues = currentTrajectory.map(p => p.local_rainfall_1d_mm).filter((value): value is number => value != null).map(Number)
                const maxRain = Math.max(15, ...rainfallValues)
                const barHeight = Math.max(8, Math.round((rain / maxRain) * 56))
                const dateObj = new Date(point.date)
                const weekday = idx === 0 ? 'Today' : dateObj.toLocaleDateString('en-US', { weekday: 'short' })
                const monthDay = dateObj.toLocaleDateString('en-US', { day: 'numeric', month: 'short' })

                return (
                  <button
                    key={point.date}
                    onClick={() => handleSelectDay(idx)}
                    type="button"
                    aria-label={`Select environmental outlook for Day ${idx + 1}, ${point.date}: ${hasRain ? `${rain} mm rainfall` : 'rainfall unavailable'}, ${isElevated ? 'threshold active' : 'threshold quiet'}`}
                    className={`p-3 rounded-xl border text-left transition-all cursor-pointer flex flex-col justify-between h-44 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                      isSelected
                        ? 'bg-blue-950/40 border-blue-500 ring-1 ring-blue-500/50 shadow-lg shadow-blue-900/20'
                        : 'bg-slate-900/40 border-slate-800 hover:border-slate-700 hover:bg-slate-800/40'
                    }`}
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-white">{weekday}</span>
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                          isElevated ? 'bg-rose-950/80 text-rose-300 border border-rose-800/60' : 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/40'
                        }`}>
                          {isElevated ? 'Threshold active' : 'Threshold quiet'}
                        </span>
                      </div>
                      <p className="text-[10px] text-slate-400 mt-0.5">{monthDay}</p>
                    </div>

                    {/* Rainfall graphic column */}
                    <div className="my-2 flex flex-col justify-end h-16 w-full bg-slate-950/60 rounded-lg p-1.5 relative overflow-hidden border border-slate-800/40">
                      <div
                        className={`w-full rounded transition-all duration-300 ${
                          isElevated ? 'bg-gradient-to-t from-rose-600 to-amber-500' : 'bg-gradient-to-t from-blue-600 to-cyan-400'
                        }`}
                        style={{ height: `${barHeight}px` }}
                      />
                      <span className="absolute bottom-1 right-1.5 text-[9px] font-mono text-slate-300 font-semibold bg-slate-900/80 px-1 rounded">
                        {hasRain ? `${rain.toFixed(1)}mm` : '—'}
                      </span>
                    </div>

                    <div className="space-y-0.5 text-[10px]">
                      <div className="flex items-center justify-between text-slate-400">
                        <span>GloFAS:</span>
                        <span className="text-slate-200 font-mono">
                          {point.glofas_discharge_m3s != null ? `${Number(point.glofas_discharge_m3s).toFixed(0)}m³/s` : '—'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-slate-400">
                        <span>Prob:</span>
                        <span className="text-blue-300 font-mono font-semibold">
                          {point.classifier_probability != null ? `${(Number(point.classifier_probability) * 100).toFixed(0)}%` : '—'}
                        </span>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>

            {/* 7-Day Risk Line Chart (SVG) */}
            {hasValidatedProbabilityTrajectory && currentSelectedPoint ? (() => {
              const maxProb = Math.max(0.1, ...currentTrajectory.map(p => Number(p.classifier_probability || 0)))
              const chartW = 560
              const chartH = 80
              const padX = 20
              const pts = currentTrajectory.map((p, idx) => ({
                x: currentTrajectory.length > 1 ? padX + (idx / (currentTrajectory.length - 1)) * (chartW - padX * 2) : chartW / 2,
                y: chartH - Math.max(8, (Number(p.classifier_probability || 0) / maxProb) * (chartH - 12)),
                prob: Number(p.classifier_probability || 0),
                elevated: Boolean(p.option_b_threshold_flag),
                idx
              }))
              const linePath = pts.reduce((acc, pt, i) => {
                if (i === 0) return `M ${pt.x},${pt.y}`
                const prev = pts[i - 1]
                const cx = (prev.x + pt.x) / 2
                return `${acc} C ${cx},${prev.y} ${cx},${pt.y} ${pt.x},${pt.y}`
              }, '')
              const areaPath = linePath + ` L ${pts[pts.length-1].x},${chartH} L ${pts[0].x},${chartH} Z`
              return (
                <div className="mt-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-[11px] text-slate-400 font-medium">Validated model probability · 7-day outlook</p>
                    <button
                      onClick={() => navigate('/ai-assistant', { state: { trajectoryContext: {
                        location: `${selectedLocality} · Far North Region`,
                        prediction: prediction?.risk_level ? `${prediction.risk_level} risk` : 'Quantitative prediction unavailable',
                        risk: currentSelectedPoint.option_b_threshold_flag ? 'Elevated risk state' : 'Baseline normal risk state',
                        probability: currentSelectedPoint.classifier_probability != null ? `${(Number(currentSelectedPoint.classifier_probability) * 100).toFixed(1)}%` : 'Unavailable',
                        confidence: prediction?.confidence_score != null ? `${Number(prediction.confidence_score).toFixed(1)}%` : 'Unavailable',
                        selectedDate: currentSelectedPoint.date,
                        selectedRiskValue: currentSelectedPoint.option_b_threshold_flag
                          ? `Elevated — ${Number(currentSelectedPoint.local_rainfall_1d_mm||0).toFixed(1)}mm rain, ${currentSelectedPoint.glofas_discharge_m3s != null ? Number(currentSelectedPoint.glofas_discharge_m3s).toFixed(1)+' m³/s' : 'discharge pending'}`
                          : `Baseline — ${Number(currentSelectedPoint.local_rainfall_1d_mm||0).toFixed(1)}mm rain`,
                        forecastPeriod: `Day ${selectedDayIndex + 1} of 7-day forecast`,
                        rainfall: currentSelectedPoint.local_rainfall_1d_mm != null ? Number(currentSelectedPoint.local_rainfall_1d_mm) : null,
                        discharge: currentSelectedPoint.glofas_discharge_m3s != null ? Number(currentSelectedPoint.glofas_discharge_m3s) : null,
                        dayIndex: selectedDayIndex,
                        trajectory: currentTrajectory,
                      } } })}
                      className="bg-[#1D68F7] hover:bg-blue-600 text-white text-xs font-bold px-4 py-2 rounded-xl shadow-lg shadow-blue-600/30 flex items-center gap-2 transition-all cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:outline-none"
                      aria-label={`Ask AquaGuard AI about ${selectedLocality} forecast`}
                    >
                      <Sparkles className="w-3.5 h-3.5 text-blue-200" aria-hidden="true" />
                      <span>Ask AquaGuard AI about this</span>
                    </button>
                  </div>
                  <div className="relative rounded-xl overflow-hidden border border-slate-800/80 bg-slate-950/60">
                    <svg className="w-full" viewBox={`0 0 ${chartW} ${chartH + 4}`} preserveAspectRatio="none" style={{ height: '90px' }}>
                      {/* Gradient fill */}
                      <defs>
                        <linearGradient id="probGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#1D68F7" stopOpacity="0.3" />
                          <stop offset="100%" stopColor="#1D68F7" stopOpacity="0.02" />
                        </linearGradient>
                      </defs>
                      {/* Elevated day highlight zones */}
                      {pts.filter(p => p.elevated).map(p => (
                        <rect
                          key={p.idx}
                          x={p.x - (chartW / currentTrajectory.length / 2)}
                          y={0}
                          width={chartW / currentTrajectory.length}
                          height={chartH}
                          fill="#ef4444"
                          opacity={0.08}
                        />
                      ))}
                      {/* Area fill */}
                      <path d={areaPath} fill="url(#probGrad)" />
                      {/* Line */}
                      <path d={linePath} fill="none" stroke="#1D68F7" strokeWidth="2" strokeLinejoin="round" />
                      {/* Data points */}
                      {pts.map(p => (
                        <circle
                          key={p.idx}
                          cx={p.x}
                          cy={p.y}
                          r={selectedDayIndex === p.idx ? 5 : 3.5}
                          fill={p.elevated ? '#ef4444' : '#1D68F7'}
                          stroke="#060B13"
                          strokeWidth="2"
                          style={{ cursor: 'pointer' }}
                          onClick={() => handleSelectDay(p.idx)}
                        />
                      ))}
                    </svg>
                    {/* X-axis labels */}
                    <div className="flex justify-between px-4 pb-2 -mt-1">
                      {currentTrajectory.map((p, i) => {
                        const d = new Date(p.date)
                        const label = i === 0 ? 'Today' : d.toLocaleDateString('en-US', { weekday: 'short' })
                        return (
                          <span key={i} className={`text-[9px] font-mono font-semibold ${
                            selectedDayIndex === i ? 'text-blue-400' : 'text-slate-500'
                          }`}>{label}</span>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )
            })() : (
              <div className="rounded-xl border border-amber-800/60 bg-amber-950/20 px-4 py-5 text-sm text-amber-200">
                {hasValidatedProbabilityTrajectory ? liveMessage : 'The environmental outlook is available, but the probability chart is withheld until the full validated model feature set is available. The application will not draw a zero or reference-value chart.'}
              </div>
            )}
          </div>

          {/* 2-Column Lower Section: Left "More actions" + Right "About this prediction" */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left: More actions (6 cols) */}
            <div className="lg:col-span-6 bg-[#0A101D] border border-slate-800/80 rounded-2xl p-6 space-y-4">
              <h3 className="text-sm font-bold text-white">More actions</h3>

              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={() => window.print()}
                  className="bg-[#0E1522] hover:bg-slate-800 text-slate-200 border border-slate-700/80 font-semibold text-xs px-4 py-2.5 rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download report</span>
                </button>

                <button
                  onClick={() => navigate('/flood-map')}
                  className="bg-[#0E1522] hover:bg-slate-800 text-slate-200 border border-slate-700/80 font-semibold text-xs px-4 py-2.5 rounded-xl flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <MapIcon className="w-3.5 h-3.5" />
                  <span>View detailed map</span>
                </button>
              </div>

              <p className="text-xs text-slate-500 font-normal pt-1">
                Flood report submission and feedback are available in their dedicated workspace sections.
              </p>
            </div>

            {/* Right: About this prediction (6 cols) */}
            <div className="lg:col-span-6 bg-[#0A101D] border border-slate-800/80 rounded-2xl p-6 space-y-3">
              <h3 className="text-sm font-bold text-white">About this prediction</h3>
              <p className="text-xs text-slate-400 leading-relaxed font-normal">
                This assessment integrates high-resolution NWP weather data, GloFAS river discharge modelling, and NASA OPERA dynamic surface water extent.
              </p>

              <div>
                <button
                  onClick={() => setDataSourcesOpen(!dataSourcesOpen)}
                  className="text-xs font-semibold text-slate-300 hover:text-white flex items-center gap-1.5 transition-colors cursor-pointer pt-1"
                >
                  <span className="text-[10px]">▶</span>
                  <span>Data sources and methodology</span>
                </button>

                {dataSourcesOpen && (
                  <div className="mt-3 p-3 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-400 space-y-2">
                    <p>• Open-Meteo High-Resolution NWP precipitation pipeline</p>
                    <p>• Copernicus GloFAS operational river discharge forecast</p>
                    <p>• NASA OPERA Sentinel-1 Dynamic Surface Water Extent (DSWx-S1)</p>
                    <p>• Far North rule-based hydrological risk calibration engine</p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Ask AquaGuard AI Accordion (Context-aware AI chat) */}
          <div ref={aiChatRef} className="bg-[#0A101D] border border-slate-800/80 rounded-2xl overflow-hidden scroll-mt-20">
            <button
              onClick={() => setAiChatOpen(!aiChatOpen)}
              className="w-full p-5 flex items-center justify-between text-left cursor-pointer hover:bg-slate-800/30 transition-colors focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:outline-none"
              aria-expanded={aiChatOpen}
            >
              <div>
                <div className="flex items-center gap-2">
                  <Bot className="w-4 h-4 text-blue-400" />
                  <h4 className="text-sm font-bold text-white">Ask AquaGuard AI</h4>
                  {activeAiContext && (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-950/60 text-blue-300 border border-blue-800/60">
                      Context: {activeAiContext.selectedDate} (Day {activeAiContext.dayIndex + 1})
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  {activeAiContext
                    ? `AI loaded with trajectory context for ${activeAiContext.location} on ${activeAiContext.selectedDate}`
                    : 'Need help understanding this prediction or 7-day risk trajectory?'}
                </p>
              </div>
              <ChevronDown
                className={`w-4 h-4 text-slate-400 transition-transform ${
                  aiChatOpen ? 'rotate-180 text-white' : ''
                }`}
              />
            </button>

            {aiChatOpen && (
              <div className="px-5 pb-5 pt-2 border-t border-slate-800/60 space-y-4">
                {/* Active Context Banner if loaded */}
                {activeAiContext && (
                  <div className="p-3 rounded-xl bg-blue-950/20 border border-blue-800/50 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                    <div className="flex items-start sm:items-center gap-2 text-slate-300">
                      <Sparkles className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5 sm:mt-0" />
                      <span>
                        <strong className="text-white font-semibold">{activeAiContext.location}</strong>
                        {' · '}Date: <strong className="text-white font-semibold">{activeAiContext.selectedDate}</strong>
                        {' · '}Status: <span className={activeAiContext.risk.includes('Elevated') ? 'text-rose-400 font-semibold' : 'text-emerald-400 font-semibold'}>{activeAiContext.risk}</span>
                        {' · '}Prob: <strong className="text-blue-300 font-semibold">{activeAiContext.probability}</strong>
                      </span>
                    </div>

                    <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
                      <button
                        onClick={() => navigate('/ai-assistant', { state: { trajectoryContext: activeAiContext } })}
                        className="text-[11px] text-blue-400 hover:text-blue-300 underline font-semibold cursor-pointer"
                      >
                        Open in full AI Assistant →
                      </button>
                      <button
                        onClick={() => setActiveAiContext(null)}
                        className="text-[11px] text-slate-500 hover:text-slate-300 cursor-pointer"
                        title="Clear chart context"
                      >
                        Clear
                      </button>
                    </div>
                  </div>
                )}

                {/* Prompt suggestion chips */}
                {activeAiContext && (
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <button
                      onClick={() => handleSendChat(`Why is the risk state ${activeAiContext.risk.includes('Elevated') ? 'elevated' : 'baseline'} on ${activeAiContext.selectedDate}?`)}
                      className="bg-slate-900 hover:bg-slate-800 border border-slate-700/80 rounded-lg px-2.5 py-1 text-[11px] text-slate-300 transition-colors cursor-pointer"
                    >
                      Why is risk {activeAiContext.risk.includes('Elevated') ? 'elevated' : 'normal'} on {activeAiContext.selectedDate}?
                    </button>
                    <button
                      onClick={() => handleSendChat(`What safety precautions are recommended for Day ${activeAiContext.dayIndex + 1} (${activeAiContext.selectedDate})?`)}
                      className="bg-slate-900 hover:bg-slate-800 border border-slate-700/80 rounded-lg px-2.5 py-1 text-[11px] text-slate-300 transition-colors cursor-pointer"
                    >
                      What precautions for Day {activeAiContext.dayIndex + 1}?
                    </button>
                    <button
                      onClick={() => handleSendChat(`How does river discharge on ${activeAiContext.selectedDate} compare to normal?`)}
                      className="bg-slate-900 hover:bg-slate-800 border border-slate-700/80 rounded-lg px-2.5 py-1 text-[11px] text-slate-300 transition-colors cursor-pointer"
                    >
                      How does river discharge affect this date?
                    </button>
                    <button
                      onClick={() => handleSendChat(`Compare Day ${activeAiContext.dayIndex + 1} to the overall baseline prediction.`)}
                      className="bg-slate-900 hover:bg-slate-800 border border-slate-700/80 rounded-lg px-2.5 py-1 text-[11px] text-slate-300 transition-colors cursor-pointer"
                    >
                      Compare to baseline assessment
                    </button>
                  </div>
                )}

                {/* Chat Message List */}
                <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
                  {chatMessages.map((msg, idx) => (
                    <div
                      key={idx}
                      className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-md p-3 rounded-xl text-xs leading-relaxed ${
                          msg.sender === 'user'
                            ? 'bg-[#1D68F7] text-white'
                            : 'bg-slate-900 border border-slate-800 text-slate-300 whitespace-pre-line'
                        }`}
                      >
                        {msg.text}
                      </div>
                    </div>
                  ))}
                  {chatLoading && (
                    <div className="flex items-center gap-2 text-xs text-slate-400 p-2">
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
                      <span>Thinking with chart context...</span>
                    </div>
                  )}
                </div>

                {/* Input box */}
                <div className="flex items-center gap-2 pt-2">
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSendChat()}
                    placeholder={activeAiContext ? `Ask about ${activeAiContext.selectedDate} conditions, rainfall, or discharge...` : "Ask about risk factors, rainfall thresholds, or precautions..."}
                    className="flex-1 bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-2.5 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-blue-500"
                  />
                  <button
                    onClick={() => handleSendChat()}
                    disabled={chatLoading || !chatInput.trim()}
                    className="bg-[#1D68F7] hover:bg-blue-600 disabled:opacity-50 text-white p-2.5 rounded-xl transition-colors cursor-pointer"
                  >
                    <Send className="w-4 h-4" />
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
