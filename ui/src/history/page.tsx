import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Calendar,
  MapPin,
  BarChart2,
  Download,
  FileText,
  TrendingUp,
  BookOpen,
  Filter,
  X,
  Search,
  Clock,
  AlertTriangle,
  ArrowRight,
  RefreshCw,
  Check,
  ChevronDown,
  Menu,
  Info,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  LineChart,
  Line,
  ReferenceLine,
} from 'recharts'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'

import CitizenSidebar from '@/components/CitizenSidebar'
import {
  userPredictionsApi,
  communityReportsApi,
  historicalEventsApi,
  type UserPredictionRecord,
  type CommunityReport,
  type HistoricalFloodEvent,
} from '@/lib/api'

// ─────────────────────────────────────────────────────────────────────────────
// CONSTANTS & DESIGN TOKENS
// ─────────────────────────────────────────────────────────────────────────────

const SEVERITY_COLORS: Record<string, string> = {
  low: '#22B981',
  moderate: '#D89B3F',
  high: '#E05A64',
  'very high': '#991B1B',
  critical: '#7F1D1D',
  unspecified: '#737D89',
}

const SEVERITY_BADGE: Record<string, string> = {
  low: 'text-emerald-300 bg-emerald-950/40 border-emerald-800/60',
  moderate: 'text-amber-300 bg-amber-950/40 border-amber-800/60',
  high: 'text-rose-300 bg-rose-950/40 border-rose-800/60',
  'very high': 'text-red-200 bg-red-950/60 border-red-700/60',
  critical: 'text-red-100 bg-red-950/80 border-red-600/70',
  unspecified: 'text-slate-300 bg-slate-800/40 border-slate-700/60',
}

const CHART_TOOLTIP_STYLE = {
  borderRadius: '6px',
  border: '1px solid #252B33',
  background: '#181D23',
  color: '#F1F3F5',
  fontSize: '12px',
  boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
  padding: '8px 12px',
}

const normSev = (s?: string) => (s || 'unspecified').trim().toLowerCase()

// ─────────────────────────────────────────────────────────────────────────────
// BACKWARD-COMPATIBLE EXPORT
// ─────────────────────────────────────────────────────────────────────────────
export const AssistantSidebar = () => <CitizenSidebar />

// ─────────────────────────────────────────────────────────────────────────────
// SKELETON COMPONENTS (Loading states per section)
// ─────────────────────────────────────────────────────────────────────────────

function ChartSkeleton({ height = 220 }: { height?: number }) {
  return (
    <div
      className="w-full rounded-md bg-[#0F1216] animate-pulse"
      style={{ height }}
      aria-busy="true"
      aria-label="Loading chart data"
    />
  )
}

function RowSkeleton() {
  return (
    <div className="py-3 space-y-2 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-3 w-48 bg-[#252B33] rounded" />
        <div className="h-4 w-16 bg-[#252B33] rounded-full" />
      </div>
      <div className="h-2.5 w-full bg-[#1A1F28] rounded" />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CUSTOM TOOLTIP COMPONENTS (consistent across charts)
// ─────────────────────────────────────────────────────────────────────────────

const YearTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div style={CHART_TOOLTIP_STYLE}>
      <p className="text-[#737D89] text-[11px] mb-0.5">Year</p>
      <p className="text-[#F1F3F5] font-semibold text-sm">{label}</p>
      <p className="text-[#2563EB] text-[11px] mt-1">
        {payload[0].value} verified {payload[0].value === 1 ? 'event' : 'events'}
      </p>
    </div>
  )
}

const DivisionTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div style={CHART_TOOLTIP_STYLE}>
      <p className="text-[#737D89] text-[11px] mb-0.5">Division</p>
      <p className="text-[#F1F3F5] font-semibold text-sm">{payload[0]?.payload?.division}</p>
      <p className="text-[#60A5FA] text-[11px] mt-1">
        {payload[0].value} documented {payload[0].value === 1 ? 'occurrence' : 'occurrences'}
      </p>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// FILTER PILL (shows current state visually)
// ─────────────────────────────────────────────────────────────────────────────

interface FilterPillProps {
  icon: React.ReactNode
  label: string
  value: string
  children: React.ReactNode
  active?: boolean
  id: string
}

function FilterPill({ icon, label, value, children, active, id }: FilterPillProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        id={id}
        onClick={() => setOpen(o => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`flex items-center gap-1.5 h-8 px-3 rounded-md border text-xs font-medium transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB] ${
          active
            ? 'bg-[#2563EB]/10 border-[#2563EB]/40 text-[#60A5FA]'
            : 'bg-[#0F1216] border-[#252B33] text-[#A7AFB9] hover:border-[#353D47] hover:text-[#F1F3F5]'
        }`}
      >
        <span className="text-[#737D89]">{icon}</span>
        <span className="text-[#737D89] hidden sm:inline">{label}:</span>
        <span className={`font-semibold truncate max-w-[120px] ${active ? 'text-[#93C5FD]' : 'text-[#F1F3F5]'}`}>
          {value}
        </span>
        <ChevronDown className={`w-3 h-3 text-[#737D89] transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-1 z-50 bg-[#181D23] border border-[#252B33] rounded-lg shadow-xl py-1 min-w-[180px]">
          {children}
        </div>
      )}
    </div>
  )
}

interface FilterOptionProps {
  selected: boolean
  onClick: () => void
  children: React.ReactNode
}

function FilterOption({ selected, onClick, children }: FilterOptionProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 text-xs transition-colors cursor-pointer hover:bg-[#252B33] ${
        selected ? 'text-[#60A5FA] font-semibold' : 'text-[#A7AFB9]'
      }`}
    >
      <span className="flex items-center gap-2">
        {selected && <span className="w-1 h-1 rounded-full bg-[#2563EB] inline-block" />}
        {!selected && <span className="w-1 h-1 rounded-full inline-block" />}
        {children}
      </span>
    </button>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN PAGE COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

export default function HistoryPage() {
  const navigate = useNavigate()

  // ── Data states ──────────────────────────────────────────────────────────
  const [predictions, setPredictions] = useState<UserPredictionRecord[]>([])
  const [reports, setReports] = useState<CommunityReport[]>([])
  const [events, setEvents] = useState<HistoricalFloodEvent[]>([])

  // ── Loading & error states ───────────────────────────────────────────────
  const [loadingPredictions, setLoadingPredictions] = useState(true)
  const [loadingReports, setLoadingReports] = useState(true)
  const [loadingEvents, setLoadingEvents] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  // ── Filters ──────────────────────────────────────────────────────────────
  const [dateRange, setDateRange] = useState<string>('all')
  const [selectedRegion, setSelectedRegion] = useState<string>('Far North')
  const [selectedDivision, setSelectedDivision] = useState<string>('all')
  const [selectedIntensity, setSelectedIntensity] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')

  // ── Methodology Modal state ──────────────────────────────────────────────
  const [methodologyOpen, setMethodologyOpen] = useState(false)

  // ── UI state ─────────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<'predictions' | 'reports' | 'events'>('events')
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const [toastType, setToastType] = useState<'success' | 'error'>('success')
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  // ── Toast helper ─────────────────────────────────────────────────────────
  const showToast = useCallback((msg: string, type: 'success' | 'error' = 'success') => {
    setToastMessage(msg)
    setToastType(type)
    setTimeout(() => setToastMessage(null), 3500)
  }, [])

  // ── Data fetching ────────────────────────────────────────────────────────
  const fetchData = useCallback(async () => {
    setLoadError(null)
    setLoadingPredictions(true)
    setLoadingReports(true)
    setLoadingEvents(true)

    try {
      const predRes = await userPredictionsApi.list(50).catch(() => ({ predictions: [] }))
      setPredictions(predRes.predictions || [])
    } finally {
      setLoadingPredictions(false)
    }

    try {
      const repRes = await communityReportsApi.getMyReports(50).catch(() => ({ reports: [] }))
      setReports(repRes.reports || [])
    } finally {
      setLoadingReports(false)
    }

    try {
      const evRes = await historicalEventsApi.list(500).catch(() => ({ events: [] }))
      setEvents(evRes.events || [])
    } catch {
      setLoadError('Unable to load historical flood records.')
      setEvents([])
    } finally {
      setLoadingEvents(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  // ── Derived data ─────────────────────────────────────────────────────────
  const availableDivisions = useMemo(() => {
    const set = new Set<string>()
    events.forEach(e => {
      const raw = e.division || e.region
      if (raw) {
        const cleaned = raw.split('(')[0].trim()
        if (cleaned.includes(';')) {
          cleaned.split(';').forEach(p => {
            const trimmed = p.trim()
            if (trimmed && !trimmed.includes('UNKNOWN')) {
              set.add(trimmed.includes('Diamar') ? 'Diamaré' : trimmed)
            }
          })
        } else if (!cleaned.includes('UNKNOWN')) {
          set.add(cleaned.includes('Diamar') ? 'Diamaré' : cleaned)
        }
      }
    })
    return Array.from(set).sort()
  }, [events])

  const filteredEvents = useMemo(() => {
    return events.filter(e => {
      const yr = Number(String(e.year || e.date || '').slice(0, 4))
      if (dateRange === '2020-2026' && (yr < 2020 || yr > 2026)) return false
      if (dateRange === '2015-2019' && (yr < 2015 || yr > 2019)) return false
      if (dateRange === '2010-2014' && (yr < 2010 || yr > 2014)) return false
      if (dateRange === '2005-2009' && (yr < 2005 || yr > 2009)) return false

      if (selectedRegion !== 'all') {
        const reg = (e.region || 'Far North').toLowerCase()
        if (!reg.includes(selectedRegion.toLowerCase())) return false
      }

      if (selectedDivision !== 'all') {
        const div = (e.division || e.region || '').toLowerCase()
        if (!div.includes(selectedDivision.toLowerCase())) return false
      }

      if (selectedIntensity !== 'all') {
        if (normSev(e.severity) !== selectedIntensity.toLowerCase()) return false
      }

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const text = [e.locality, e.division, e.region, e.severity, e.description, e.source, e.date, String(e.year || '')]
          .filter(Boolean).join(' ').toLowerCase()
        if (!text.includes(q)) return false
      }
      return true
    })
  }, [events, dateRange, selectedRegion, selectedDivision, selectedIntensity, searchQuery])

  // ── Chart 1: Events by Year (Line chart — temporal trend) ────────────────
  const eventsByYear = useMemo(() => {
    const yearCounts: Record<string, number> = {}
    filteredEvents.forEach(e => {
      const year = String(e.year || e.date || '').slice(0, 4)
      if (/^\d{4}$/.test(year)) {
        yearCounts[year] = (yearCounts[year] || 0) + 1
      }
    })
    return Object.entries(yearCounts)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([year, count]) => ({ year, events: count }))
  }, [filteredEvents])

  // ── Chart 2: Severity distribution ──────────────────────────────────────
  const severityDistribution = useMemo(() => {
    if (filteredEvents.length === 0) return []
    const counts: Record<string, number> = {}
    filteredEvents.forEach(e => {
      const sev = (e.severity || 'Unspecified').trim()
      const cap = sev.charAt(0).toUpperCase() + sev.slice(1).toLowerCase()
      counts[cap] = (counts[cap] || 0) + 1
    })
    const total = filteredEvents.length
    return Object.entries(counts)
      .map(([name, count]) => {
        const norm = name.toLowerCase()
        const color = SEVERITY_COLORS[norm] || SEVERITY_COLORS.unspecified
        const percent = Math.round((count / total) * 100)
        return { name, count, percent, color }
      })
      .sort((a, b) => b.count - a.count)
  }, [filteredEvents])

  // ── Chart 3: Division frequency (horizontal bar) ─────────────────────────
  const eventsByDivision = useMemo(() => {
    const counts: Record<string, number> = {}
    filteredEvents.forEach(e => {
      const raw = e.division || e.region || 'Unspecified'
      const cleaned = raw.split('(')[0].trim()
      if (cleaned.includes(';')) {
        const parts = cleaned.split(';').map(p => p.trim()).filter(Boolean)
        parts.forEach(p => {
          const norm = p.includes('Diamar') ? 'Diamaré' : p
          counts[norm] = (counts[norm] || 0) + 1
        })
      } else {
        const norm = cleaned.includes('Diamar') ? 'Diamaré' : (cleaned.includes('UNKNOWN') ? 'Unspecified' : cleaned)
        counts[norm] = (counts[norm] || 0) + 1
      }
    })
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .map(([division, count]) => ({ division, count }))
  }, [filteredEvents])

  // ── Filter helpers ───────────────────────────────────────────────────────
  const hasActiveFilters =
    dateRange !== 'all' || selectedRegion !== 'Far North' || selectedDivision !== 'all' || selectedIntensity !== 'all' || searchQuery.trim() !== ''

  const handleClearFilters = () => {
    setDateRange('all')
    setSelectedRegion('Far North')
    setSelectedDivision('all')
    setSelectedIntensity('all')
    setSearchQuery('')
  }

  const dateRangeLabel: Record<string, string> = {
    all: '2005–2026',
    '2020-2026': '2020–2026',
    '2015-2019': '2015–2019',
    '2010-2014': '2010–2014',
    '2005-2009': '2005–2009',
  }

  const regionLabel: Record<string, string> = {
    'Far North': 'Far North',
    'North': 'North',
    'Adamawa': 'Adamawa',
    'Centre': 'Centre',
    'Littoral': 'Littoral',
    all: 'All Regions',
  }

  const intensityLabel: Record<string, string> = {
    all: 'All Levels',
    critical: 'Critical',
    'very high': 'Very High',
    high: 'High',
    moderate: 'Moderate',
    low: 'Low',
  }

  // ── CSV Export ───────────────────────────────────────────────────────────
  const handleExportCSV = () => {
    if (filteredEvents.length === 0) {
      showToast('No events to export under current filters.', 'error')
      return
    }
    const headers = ['Event ID', 'Year', 'Date', 'Locality', 'Division', 'Region', 'Severity', 'Description', 'Source']
    const rows = filteredEvents.map(e => [
      e.event_id || '',
      e.year || '',
      e.date || '',
      `"${(e.locality || '').replace(/"/g, '""')}"`,
      `"${(e.division || '').replace(/"/g, '""')}"`,
      `"${(e.region || '').replace(/"/g, '""')}"`,
      `"${(e.severity || '').replace(/"/g, '""')}"`,
      `"${(e.description || '').replace(/"/g, '""')}"`,
      `"${(e.source || '').replace(/"/g, '""')}"`,
    ])
    const csvContent =
      'data:text/csv;charset=utf-8,' +
      [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const link = document.createElement('a')
    link.setAttribute('href', encodeURI(csvContent))
    link.setAttribute(
      'download',
      `aquaguard_floods_${selectedRegion}_${selectedDivision}_${dateRange}_${selectedIntensity}.csv`
    )
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    showToast('CSV exported successfully.')
  }

  const handleGenerateReport = () => {
    window.print()
    showToast('Report generated successfully.')
  }

  // ── Percentage sum validation (must total 100%) ───────────────────────────
  const percentSum = severityDistribution.reduce((s, d) => s + d.percent, 0)
  const percentValid = filteredEvents.length === 0 || Math.abs(percentSum - 100) <= 1

  return (
    <div className="flex min-h-screen w-full bg-[#0B0D10] font-sans text-[#F1F3F5] selection:bg-blue-600 selection:text-white">
      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <CitizenSidebar isOpen={mobileSidebarOpen} onClose={() => setMobileSidebarOpen(false)} />

      {/* ── Main content ────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* ── Toast ───────────────────────────────────────────────────────── */}
        {toastMessage && (
          <div
            role="status"
            aria-live="polite"
            className={`fixed top-4 right-4 z-50 border text-white text-xs font-semibold px-4 py-3 rounded-lg shadow-xl flex items-center gap-2 transition-all duration-200 ${
              toastType === 'success'
                ? 'bg-[#181D23] border-[#22B981]/70'
                : 'bg-[#181D23] border-rose-500/70'
            }`}
          >
            {toastType === 'success' ? (
              <Check className="w-3.5 h-3.5 text-[#22B981] shrink-0" />
            ) : (
              <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
            )}
            <span>{toastMessage}</span>
          </div>
        )}

        {/* ── Top navigation bar ──────────────────────────────────────────── */}
        <header
          className="flex h-12 shrink-0 items-center justify-between border-b border-[#252B33] bg-[#0F1216] px-5 sticky top-0 z-20"
          role="banner"
        >
          {/* Left: Mobile menu + Breadcrumb */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileSidebarOpen(true)}
              className="lg:hidden p-1.5 text-[#737D89] hover:text-white rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
              aria-label="Open navigation menu"
            >
              <Menu className="w-4 h-4" />
            </button>

            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink
                    onClick={() => navigate('/dashboard')}
                    className="text-xs text-[#737D89] hover:text-[#F1F3F5] cursor-pointer transition-colors"
                  >
                    AquaGuard AI
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator className="text-[#4A5568]" />
                <BreadcrumbItem>
                  <BreadcrumbPage className="text-xs font-semibold text-[#F1F3F5]">
                    History
                  </BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </div>

          {/* Right: Search + scope indicator + refresh */}
          <div className="flex items-center gap-3">
            {/* Search — hidden on small screens */}
            <div className="relative hidden md:block">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-[#737D89] pointer-events-none" />
              <input
                type="search"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search events, divisions, locations…"
                aria-label="Search historical flood events"
                className="bg-[#14181D] border border-[#252B33] rounded-md pl-8 pr-8 py-1.5 text-xs text-[#F1F3F5] placeholder-[#4A5568] focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB]/30 w-60 transition-colors"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear search"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-[#737D89] hover:text-[#F1F3F5] transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>

            {/* Scope indicator */}
            <div
              className="flex items-center gap-1.5 text-[11px] font-medium text-[#A7AFB9] bg-[#14181D] border border-[#252B33] px-2.5 py-1 rounded-md"
              title="Analysis geographic scope"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-[#2563EB] shrink-0" aria-hidden="true" />
              <span>Far North Region</span>
            </div>

            {/* Refresh */}
            <button
              onClick={fetchData}
              aria-label="Refresh catalogue records"
              title="Refresh catalogue records"
              className="p-1.5 text-[#737D89] hover:text-[#F1F3F5] hover:bg-[#181D23] rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${loadingEvents ? 'animate-spin text-[#2563EB]' : ''}`}
                aria-hidden="true"
              />
            </button>
          </div>
        </header>

        {/* ── Analytical body ──────────────────────────────────────────────── */}
        <main
          id="main-content"
          className="flex-1 px-6 sm:px-8 py-7 space-y-7 max-w-7xl w-full mx-auto"
        >

          {/* ── PAGE HEADER ────────────────────────────────────────────────── */}
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div>
              <h1 className="text-[28px] font-bold text-[#F1F3F5] tracking-tight leading-none">
                Historical Flood Analysis
              </h1>
              <p className="text-sm text-[#737D89] mt-2 font-normal leading-relaxed">
                Your predictions, submitted reports and verified historical flood events.
              </p>
              {/* Explicit scope tag — always visible */}
              <div className="flex items-center gap-1.5 mt-3">
                <span className="text-[11px] text-[#737D89]">Analysis scope</span>
                <span className="text-[#4A5568] text-[11px]">·</span>
                <span className="text-[11px] font-semibold text-[#A7AFB9]">
                  {selectedRegion === 'all' ? 'All Regions' : `${selectedRegion} Region`}
                </span>
                <span className="text-[#4A5568] text-[11px] ml-2">·</span>
                <button
                  onClick={() => setMethodologyOpen(true)}
                  className="text-[11px] text-[#2563EB] hover:text-blue-400 flex items-center gap-1 font-medium transition-colors cursor-pointer focus-visible:outline-none focus-visible:underline"
                  aria-label="Learn about the historical catalogue methodology"
                >
                  <BookOpen className="w-3 h-3" aria-hidden="true" />
                  Learn about the historical catalogue →
                </button>
              </div>
            </div>

            {/* Secondary actions */}
            <div className="flex items-center gap-2 self-start shrink-0">
              <button
                onClick={handleExportCSV}
                aria-label="Export filtered data as CSV"
                className="h-8 bg-[#14181D] hover:bg-[#1A1F28] border border-[#252B33] text-[#A7AFB9] hover:text-[#F1F3F5] text-xs font-semibold px-3 rounded-md flex items-center gap-1.5 transition-colors cursor-pointer focus-visible:ring-2 focus-visible:ring-[#2563EB] focus-visible:outline-none"
              >
                <Download className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Export CSV</span>
              </button>

              <button
                onClick={handleGenerateReport}
                aria-label="Generate analysis report for current filter selection"
                className="h-8 bg-[#2563EB] hover:bg-[#1D55D4] text-white text-xs font-semibold px-3 rounded-md flex items-center gap-1.5 transition-colors cursor-pointer shadow-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0D10] focus-visible:ring-[#2563EB] focus-visible:outline-none"
              >
                <FileText className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Generate Report</span>
              </button>
            </div>
          </div>

          {/* ── FILTER TOOLBAR ──────────────────────────────────────────────── */}
          <section
            aria-label="Analysis filters"
            className="bg-[#14181D] border border-[#252B33] rounded-lg px-4 py-3 flex flex-col md:flex-row md:items-center justify-between gap-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              {/* Label */}
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-[#737D89] mr-1">
                <Filter className="w-3 h-3" aria-hidden="true" />
                <span>Filters</span>
              </div>

              {/* Date Range filter */}
              <FilterPill
                id="filter-date"
                icon={<Calendar className="w-3 h-3" />}
                label="Date"
                value={dateRangeLabel[dateRange] || 'All Years'}
                active={dateRange !== 'all'}
              >
                {Object.entries(dateRangeLabel).map(([val, lbl]) => (
                  <FilterOption
                    key={val}
                    selected={dateRange === val}
                    onClick={() => setDateRange(val)}
                  >
                    {lbl}
                  </FilterOption>
                ))}
              </FilterPill>

              {/* Region filter */}
              <FilterPill
                id="filter-region"
                icon={<MapPin className="w-3 h-3" />}
                label="Region"
                value={selectedRegion === 'all' ? 'All Regions' : selectedRegion}
                active={selectedRegion !== 'Far North'}
              >
                {Object.entries(regionLabel).map(([val, lbl]) => (
                  <FilterOption
                    key={val}
                    selected={selectedRegion === val}
                    onClick={() => {
                      setSelectedRegion(val)
                      setSelectedDivision('all')
                    }}
                  >
                    {lbl}
                  </FilterOption>
                ))}
              </FilterPill>

              {/* Division filter */}
              <FilterPill
                id="filter-division"
                icon={<MapPin className="w-3 h-3" />}
                label="Division"
                value={selectedDivision === 'all' ? 'All Divisions' : selectedDivision}
                active={selectedDivision !== 'all'}
              >
                <FilterOption selected={selectedDivision === 'all'} onClick={() => setSelectedDivision('all')}>
                  All Divisions
                </FilterOption>
                {availableDivisions.map(div => (
                  <FilterOption
                    key={div}
                    selected={selectedDivision === div}
                    onClick={() => setSelectedDivision(div)}
                  >
                    {div}
                  </FilterOption>
                ))}
              </FilterPill>

              {/* Intensity filter */}
              <FilterPill
                id="filter-intensity"
                icon={<BarChart2 className="w-3 h-3" />}
                label="Intensity"
                value={intensityLabel[selectedIntensity] || 'All Levels'}
                active={selectedIntensity !== 'all'}
              >
                {Object.entries(intensityLabel).map(([val, lbl]) => (
                  <FilterOption
                    key={val}
                    selected={selectedIntensity === val}
                    onClick={() => setSelectedIntensity(val)}
                  >
                    {lbl}
                  </FilterOption>
                ))}
              </FilterPill>

              {/* Clear filters */}
              {hasActiveFilters && (
                <button
                  onClick={handleClearFilters}
                  aria-label="Clear all active filters"
                  className="flex items-center gap-1 text-[11px] text-[#737D89] hover:text-[#E05A64] font-semibold px-2 py-1 rounded transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-rose-500"
                >
                  <X className="w-3 h-3" aria-hidden="true" />
                  <span>Clear filters</span>
                </button>
              )}
            </div>

            {/* Matching count */}
            <div className="text-[11px] text-[#737D89] shrink-0 self-center" aria-live="polite">
              {loadingEvents ? (
                <span>Loading records…</span>
              ) : (
                <>
                  <span className="font-semibold text-[#A7AFB9]">{filteredEvents.length}</span>
                  {' '}events matching
                </>
              )}
            </div>
          </section>

          {/* ── CATALOGUE OVERVIEW STRIP ────────────────────────────────────── */}
          <section
            aria-label="Catalogue overview statistics"
            className="bg-[#14181D] border border-[#252B33] rounded-lg px-5 py-4"
          >
            <div className="flex items-center justify-between mb-3.5">
              <span className="text-[10px] font-bold uppercase tracking-widest text-[#737D89]">
                Catalogue Overview
              </span>
              <span className="text-[11px] text-[#4A5568]">
                Verified Far North flood catalogue
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-0 divide-y sm:divide-y-0 sm:divide-x divide-[#252B33]">
              {/* Primary metric: Verified events */}
              <div className="sm:pr-6 pb-4 sm:pb-0">
                <p className="text-[28px] font-bold text-[#F1F3F5] tracking-tight leading-none" aria-label={`${filteredEvents.length} verified events`}>
                  {loadingEvents ? <span className="inline-block w-12 h-7 bg-[#252B33] rounded animate-pulse" /> : filteredEvents.length}
                </p>
                <p className="text-xs text-[#A7AFB9] mt-1.5 font-medium">Verified events</p>
                <p className="text-[10px] text-[#4A5568] mt-0.5">Primary historical record</p>
              </div>

              {/* Divisions */}
              <div className="sm:px-6 pt-4 sm:pt-0">
                <p className="text-[28px] font-bold text-[#F1F3F5] tracking-tight leading-none" aria-label={`${eventsByDivision.length} divisions`}>
                  {loadingEvents ? <span className="inline-block w-8 h-7 bg-[#252B33] rounded animate-pulse" /> : eventsByDivision.length}
                </p>
                <p className="text-xs text-[#A7AFB9] mt-1.5 font-medium">Divisions</p>
                <p className="text-[10px] text-[#4A5568] mt-0.5">Administrative areas</p>
              </div>

              {/* My Predictions — visually secondary */}
              <div className="sm:px-6 pt-4 sm:pt-0">
                <p className="text-[22px] font-semibold text-[#737D89] tracking-tight leading-none" aria-label={`${predictions.length} personal predictions`}>
                  {loadingPredictions ? <span className="inline-block w-6 h-6 bg-[#252B33] rounded animate-pulse" /> : predictions.length}
                </p>
                <p className="text-xs text-[#737D89] mt-1.5 font-medium">My predictions</p>
                <p className="text-[10px] text-[#4A5568] mt-0.5">Model assessments</p>
              </div>

              {/* My Reports — visually secondary */}
              <div className="sm:pl-6 pt-4 sm:pt-0">
                <p className="text-[22px] font-semibold text-[#737D89] tracking-tight leading-none" aria-label={`${reports.length} submitted reports`}>
                  {loadingReports ? <span className="inline-block w-6 h-6 bg-[#252B33] rounded animate-pulse" /> : reports.length}
                </p>
                <p className="text-xs text-[#737D89] mt-1.5 font-medium">My reports</p>
                <p className="text-[10px] text-[#4A5568] mt-0.5">Submitted by me</p>
              </div>
            </div>
          </section>

          {/* ── GLOBAL ERROR ────────────────────────────────────────────────── */}
          {loadError && (
            <div
              role="alert"
              className="bg-rose-950/20 border border-rose-800/60 rounded-lg p-4 flex items-center justify-between"
            >
              <div className="flex items-center gap-2.5 text-xs text-rose-300">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" aria-hidden="true" />
                <span>{loadError}</span>
              </div>
              <button
                onClick={fetchData}
                className="text-xs font-semibold bg-rose-900/50 hover:bg-rose-800/70 text-white px-3 py-1.5 rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 cursor-pointer"
              >
                Retry
              </button>
            </div>
          )}

          {/* ── ROW 1: TIME-SERIES + SEVERITY ───────────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6" role="region" aria-label="Historical trend and severity charts">

            {/* Chart 1 — Verified Events by Year (≈60%, 7 cols) */}
            <section
              aria-label="Verified events by year"
              className="lg:col-span-7 bg-[#14181D] border border-[#252B33] rounded-lg p-5 flex flex-col"
            >
              <div className="flex items-start justify-between mb-5">
                <div>
                  <h2 className="text-[15px] font-semibold text-[#F1F3F5] leading-tight">
                    Verified Events by Year
                  </h2>
                  <p className="text-xs text-[#737D89] mt-1">
                    How has event frequency changed over time?
                  </p>
                </div>
                <span className="text-[10px] text-[#737D89] font-medium bg-[#0F1216] border border-[#252B33] px-2 py-0.5 rounded shrink-0 ml-3">
                  Far North
                </span>
              </div>

              {loadingEvents ? (
                <ChartSkeleton height={216} />
              ) : eventsByYear.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center py-12 space-y-2">
                  <p className="text-sm font-semibold text-[#A7AFB9]">
                    No event timeline available for this selection.
                  </p>
                  <p className="text-xs text-[#737D89]">
                    Try expanding your date range or selecting all divisions.
                  </p>
                  {hasActiveFilters && (
                    <button
                      onClick={handleClearFilters}
                      className="mt-2 text-xs text-[#2563EB] hover:text-blue-400 font-semibold underline-offset-2 hover:underline transition-colors cursor-pointer"
                    >
                      Clear filters
                    </button>
                  )}
                </div>
              ) : (
                <div className="flex-1" style={{ height: 216 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={eventsByYear}
                      margin={{ top: 8, right: 16, left: -18, bottom: 4 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#1E2530"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="year"
                        tick={{ fontSize: 11, fill: '#737D89', fontFamily: 'inherit' }}
                        axisLine={false}
                        tickLine={false}
                        dy={6}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fontSize: 11, fill: '#737D89', fontFamily: 'inherit' }}
                        axisLine={false}
                        tickLine={false}
                        width={28}
                      />
                      <Tooltip content={<YearTooltip />} cursor={{ stroke: '#252B33', strokeWidth: 1 }} />
                      <ReferenceLine y={0} stroke="#1E2530" />
                      <Line
                        type="monotone"
                        dataKey="events"
                        stroke="#2563EB"
                        strokeWidth={2}
                        dot={{ r: 3, fill: '#2563EB', stroke: '#14181D', strokeWidth: 2 }}
                        activeDot={{ r: 5, fill: '#2563EB', stroke: '#14181D', strokeWidth: 2 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              <div className="pt-3 mt-4 border-t border-[#252B33] flex items-center justify-between text-[10px] text-[#4A5568]">
                <span>Source: Verified historical flood events database</span>
                <span>Confirmed physical occurrences only</span>
              </div>
            </section>

            {/* Chart 2 — Documented Severity (≈40%, 5 cols) */}
            <section
              aria-label="Documented severity distribution"
              className="lg:col-span-5 bg-[#14181D] border border-[#252B33] rounded-lg p-5 flex flex-col"
            >
              <div className="mb-5">
                <h2 className="text-[15px] font-semibold text-[#F1F3F5] leading-tight">
                  Documented Severity
                </h2>
                <p className="text-xs text-[#737D89] mt-1">
                  How severe were the recorded events?
                </p>
              </div>

              {loadingEvents ? (
                <div className="space-y-4">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="space-y-1.5 animate-pulse">
                      <div className="h-3 w-3/4 bg-[#252B33] rounded" />
                      <div className="h-2 w-full bg-[#1A1F28] rounded-full" />
                    </div>
                  ))}
                </div>
              ) : severityDistribution.length === 0 ? (
                <div className="flex-1 flex items-center justify-center py-12">
                  <p className="text-xs text-[#737D89]">No severity data for this selection.</p>
                </div>
              ) : (
                <div className="space-y-3.5 flex-1">
                  {severityDistribution.map(item => (
                    <div key={item.name} role="group" aria-label={`${item.name} severity: ${item.percent}%`}>
                      <div className="flex items-center justify-between text-xs mb-1.5">
                        <span className="font-medium text-[#F1F3F5] flex items-center gap-2">
                          <span
                            className="w-2 h-2 rounded-full shrink-0"
                            style={{ backgroundColor: item.color }}
                            aria-hidden="true"
                          />
                          {item.name}
                        </span>
                        <span className="text-[#A7AFB9] font-mono text-[11px] tabular-nums">
                          {item.percent}%
                          <span className="text-[#4A5568] ml-1 font-sans">({item.count})</span>
                        </span>
                      </div>
                      <div
                        className="h-1.5 w-full bg-[#0F1216] rounded-full overflow-hidden"
                        role="progressbar"
                        aria-valuenow={item.percent}
                        aria-valuemin={0}
                        aria-valuemax={100}
                      >
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${Math.max(2, item.percent)}%`,
                            backgroundColor: item.color,
                          }}
                        />
                      </div>
                    </div>
                  ))}

                  {/* Percentage integrity note */}
                  {severityDistribution.length > 0 && (
                    <p className="text-[10px] text-[#4A5568] pt-1">
                      {percentValid
                        ? `Percentages account for all ${filteredEvents.length} events in the active filter subset.`
                        : `Note: Displayed percentages may not sum to 100% due to rounding.`
                      }
                    </p>
                  )}
                </div>
              )}

              <div className="pt-3 mt-4 border-t border-[#252B33] text-[10px] text-[#4A5568]">
                Severity categories drawn from catalogue records. Colors follow semantic convention.
              </div>
            </section>
          </div>

          {/* ── ROW 2: FLOOD FREQUENCY BY DIVISION ──────────────────────────── */}
          <section
            aria-label="Flood frequency by administrative division"
            className="bg-[#14181D] border border-[#252B33] rounded-lg p-5"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-5">
              <div>
                <h2 className="text-[15px] font-semibold text-[#F1F3F5] leading-tight">
                  Flood Frequency by Division
                </h2>
                <p className="text-xs text-[#737D89] mt-1">
                  Where were events concentrated? Sorted by documented occurrences.
                </p>
              </div>
              {!loadingEvents && eventsByDivision.length > 0 && (
                <span className="text-[11px] text-[#737D89] shrink-0">
                  {eventsByDivision.length} administrative {eventsByDivision.length === 1 ? 'area' : 'areas'}
                </span>
              )}
            </div>

            {loadingEvents ? (
              <ChartSkeleton height={260} />
            ) : eventsByDivision.length === 0 ? (
              <div className="py-12 text-center space-y-2">
                <p className="text-sm font-semibold text-[#A7AFB9]">
                  No division occurrences recorded under active filters.
                </p>
                {hasActiveFilters && (
                  <button
                    onClick={handleClearFilters}
                    className="text-xs text-[#2563EB] hover:text-blue-400 font-semibold cursor-pointer"
                  >
                    Clear filters to view all divisions
                  </button>
                )}
              </div>
            ) : (
              // Dynamic height: at least 200px, 40px per division row
              <div style={{ height: Math.max(200, eventsByDivision.length * 40) }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    layout="vertical"
                    data={eventsByDivision}
                    margin={{ top: 4, right: 48, left: 8, bottom: 4 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#1E2530" horizontal={false} />
                    <XAxis
                      type="number"
                      allowDecimals={false}
                      tick={{ fontSize: 11, fill: '#737D89', fontFamily: 'inherit' }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="division"
                      tick={{ fontSize: 12, fill: '#A7AFB9', fontFamily: 'inherit' }}
                      axisLine={false}
                      tickLine={false}
                      width={145}
                    />
                    <Tooltip content={<DivisionTooltip />} cursor={{ fill: 'rgba(37,43,51,0.5)' }} />
                    <Bar
                      dataKey="count"
                      radius={[0, 4, 4, 0]}
                      barSize={18}
                      label={{
                        position: 'right',
                        fontSize: 11,
                        fill: '#737D89',
                        fontFamily: 'inherit',
                      }}
                    >
                      {eventsByDivision.map((_, index) => (
                        <Cell
                          key={`cell-${index}`}
                          // Top division gets full blue, others get progressively lighter
                          fill={index === 0 ? '#2563EB' : '#3B6FC7'}
                          fillOpacity={1 - index * 0.04 < 0.6 ? 0.6 : 1 - index * 0.04}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>

          {/* ── ROW 3: MY HISTORY TABS ───────────────────────────────────────── */}
          <section
            aria-label="Personal history and verified catalogue records"
            className="bg-[#14181D] border border-[#252B33] rounded-lg overflow-hidden"
          >
            {/* Tab header */}
            <div className="border-b border-[#252B33] px-5 pt-5 pb-0">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className="text-[15px] font-semibold text-[#F1F3F5] leading-tight">
                    My History
                  </h2>
                  <p className="text-xs text-[#737D89] mt-1">
                    Personal records and the verified historical catalogue
                  </p>
                </div>
              </div>

              {/* Tab strip */}
              <div
                className="flex items-center gap-1 -mb-px"
                role="tablist"
                aria-label="History record tabs"
              >
                {/* Historical Events tab */}
                <button
                  role="tab"
                  id="tab-events"
                  aria-controls="tabpanel-events"
                  aria-selected={activeTab === 'events'}
                  onClick={() => setActiveTab('events')}
                  className={`px-3.5 py-2 text-xs font-semibold border-b-2 transition-all cursor-pointer flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB] rounded-t-sm ${
                    activeTab === 'events'
                      ? 'text-[#2563EB] border-[#2563EB]'
                      : 'text-[#737D89] border-transparent hover:text-[#A7AFB9] hover:border-[#353D47]'
                  }`}
                >
                  <BookOpen className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Historical Events</span>
                  {!loadingEvents && (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#0F1216] border border-[#252B33] text-[#737D89]">
                      {filteredEvents.length}
                    </span>
                  )}
                </button>

                {/* My Predictions tab */}
                <button
                  role="tab"
                  id="tab-predictions"
                  aria-controls="tabpanel-predictions"
                  aria-selected={activeTab === 'predictions'}
                  onClick={() => setActiveTab('predictions')}
                  className={`px-3.5 py-2 text-xs font-semibold border-b-2 transition-all cursor-pointer flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB] rounded-t-sm ${
                    activeTab === 'predictions'
                      ? 'text-[#2563EB] border-[#2563EB]'
                      : 'text-[#737D89] border-transparent hover:text-[#A7AFB9] hover:border-[#353D47]'
                  }`}
                >
                  <TrendingUp className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>My Predictions</span>
                  {!loadingPredictions && (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#0F1216] border border-[#252B33] text-[#737D89]">
                      {predictions.length}
                    </span>
                  )}
                </button>

                {/* My Reports tab */}
                <button
                  role="tab"
                  id="tab-reports"
                  aria-controls="tabpanel-reports"
                  aria-selected={activeTab === 'reports'}
                  onClick={() => setActiveTab('reports')}
                  className={`px-3.5 py-2 text-xs font-semibold border-b-2 transition-all cursor-pointer flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB] rounded-t-sm ${
                    activeTab === 'reports'
                      ? 'text-[#2563EB] border-[#2563EB]'
                      : 'text-[#737D89] border-transparent hover:text-[#A7AFB9] hover:border-[#353D47]'
                  }`}
                >
                  <FileText className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>My Reports</span>
                  {!loadingReports && (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#0F1216] border border-[#252B33] text-[#737D89]">
                      {reports.length}
                    </span>
                  )}
                </button>
              </div>
            </div>

            {/* ── TAB PANEL: Historical Events ──────────────────────────────── */}
            {activeTab === 'events' && (
              <div
                id="tabpanel-events"
                role="tabpanel"
                aria-labelledby="tab-events"
                className="p-5"
              >
                {/* Context note */}
                <div className="flex items-start gap-2 mb-4 p-3 bg-[#0F1216] border border-[#252B33] rounded-md">
                  <Info className="w-3.5 h-3.5 text-[#737D89] shrink-0 mt-0.5" aria-hidden="true" />
                  <p className="text-[11px] text-[#737D89] leading-relaxed">
                    <strong className="text-[#A7AFB9] font-semibold">Verified Historical Events</strong>
                    {' '}— Records from the verified Far North flood catalogue. These are confirmed physical occurrences distinct from your personal predictions or submitted reports.
                  </p>
                </div>

                {/* Filter context */}
                <div className="flex items-center justify-between mb-3 text-[11px] text-[#737D89]">
                  <span>
                    Showing{' '}
                    <strong className="text-[#A7AFB9]">{filteredEvents.length}</strong>
                    {' '}verified canonical flood events
                  </span>
                  {hasActiveFilters && (
                    <button
                      onClick={handleClearFilters}
                      className="text-[#2563EB] hover:text-blue-400 font-semibold transition-colors cursor-pointer"
                    >
                      Reset filters
                    </button>
                  )}
                </div>

                {loadingEvents ? (
                  <div className="space-y-3">
                    {[1, 2, 3, 4].map(i => <RowSkeleton key={i} />)}
                  </div>
                ) : filteredEvents.length === 0 ? (
                  <div className="py-14 text-center space-y-3">
                    <p className="text-sm font-semibold text-[#A7AFB9]">
                      No verified events match these filters.
                    </p>
                    <p className="text-xs text-[#737D89]">
                      Try expanding your date range, division, or intensity selection.
                    </p>
                    {hasActiveFilters && (
                      <button
                        onClick={handleClearFilters}
                        className="mt-1 text-xs font-semibold text-[#2563EB] hover:text-blue-400 inline-flex items-center gap-1 cursor-pointer"
                      >
                        <span>Clear filters to view all records</span>
                        <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="max-h-[480px] overflow-y-auto divide-y divide-[#1A1F28]">
                    {filteredEvents.map((ev, idx) => {
                      const sev = normSev(ev.severity)
                      const badgeClass = SEVERITY_BADGE[sev] || SEVERITY_BADGE.unspecified
                      return (
                        <div
                          key={ev.event_id || idx}
                          className="py-3.5 hover:bg-[#0F1216]/60 transition-colors px-1 -mx-1 rounded"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-xs font-semibold text-[#F1F3F5] truncate">
                                {ev.locality || 'Unspecified locality'}
                              </span>
                              <span className="text-[#4A5568] text-[11px] shrink-0">·</span>
                              <span className="text-[11px] text-[#737D89] truncate">
                                {ev.division || ev.region || 'Far North'}
                              </span>
                            </div>
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full border capitalize shrink-0 ${badgeClass}`}
                            >
                              {ev.severity || 'Unspecified'}
                            </span>
                          </div>

                          <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 mt-1.5 text-[11px] text-[#737D89]">
                            <span>
                              Date:{' '}
                              <strong className="text-[#A7AFB9] font-medium">
                                {ev.date || ev.year || '—'}
                              </strong>
                            </span>
                            {ev.source && (
                              <span className="truncate max-w-[200px]">
                                Source: <strong className="text-[#737D89] font-medium">{ev.source}</strong>
                              </span>
                            )}
                          </div>

                          {ev.description && (
                            <p className="text-[11px] text-[#737D89] leading-relaxed mt-1.5 line-clamp-2">
                              {ev.description}
                            </p>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

            {/* ── TAB PANEL: My Predictions ──────────────────────────────────── */}
            {activeTab === 'predictions' && (
              <div
                id="tabpanel-predictions"
                role="tabpanel"
                aria-labelledby="tab-predictions"
                className="p-5"
              >
                {/* Context note */}
                <div className="flex items-start gap-2 mb-4 p-3 bg-[#0F1216] border border-[#252B33] rounded-md">
                  <Info className="w-3.5 h-3.5 text-[#737D89] shrink-0 mt-0.5" aria-hidden="true" />
                  <p className="text-[11px] text-[#737D89] leading-relaxed">
                    <strong className="text-[#A7AFB9] font-semibold">My Predictions</strong>
                    {' '}— Model-generated flood risk assessments you have previously requested. These are not historical records; they represent probabilistic risk estimates at the time of assessment.
                  </p>
                </div>

                {loadingPredictions ? (
                  <div className="space-y-3">
                    {[1, 2].map(i => <RowSkeleton key={i} />)}
                  </div>
                ) : predictions.length === 0 ? (
                  <div className="py-14 text-center space-y-3">
                    <p className="text-sm font-semibold text-[#A7AFB9]">No previous predictions.</p>
                    <p className="text-xs text-[#737D89]">Your completed flood risk assessments will appear here.</p>
                    <button
                      onClick={() => navigate('/assess-flood-risk')}
                      className="mt-2 bg-[#2563EB] hover:bg-[#1D55D4] text-white font-semibold px-4 py-2 rounded-md text-xs transition-colors inline-block cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB] focus-visible:ring-offset-2 focus-visible:ring-offset-[#14181D]"
                    >
                      Assess flood risk
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {predictions.map(p => {
                      const sev = normSev(p.risk_level)
                      const badgeClass = SEVERITY_BADGE[sev] || SEVERITY_BADGE.moderate
                      return (
                        <article
                          key={p.id}
                          className="bg-[#0F1216] border border-[#252B33] rounded-lg p-4 space-y-3 hover:border-[#353D47] transition-colors"
                          aria-label={`Prediction for ${p.locality}`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h3 className="text-xs font-semibold text-[#F1F3F5] truncate">
                                {p.locality}
                              </h3>
                              <p className="text-[10px] text-[#737D89] mt-0.5">Far North Region</p>
                            </div>
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full border capitalize shrink-0 ${badgeClass}`}
                            >
                              {p.risk_level || 'Moderate'}
                            </span>
                          </div>

                          <div className="grid grid-cols-2 gap-2 bg-[#14181D] border border-[#252B33]/60 rounded-md p-2.5">
                            <div>
                              <span className="text-[9px] font-bold uppercase tracking-wider text-[#4A5568] block">
                                Probability
                              </span>
                              <strong className="text-sm text-[#F1F3F5] tabular-nums">
                                {Number(p.estimated_risk_percent ?? 0).toFixed(1)}%
                              </strong>
                            </div>
                            <div>
                              <span className="text-[9px] font-bold uppercase tracking-wider text-[#4A5568] block">
                                Confidence
                              </span>
                              <strong className="text-sm text-[#F1F3F5] tabular-nums">
                                {Number(p.confidence_score ?? 0).toFixed(0)}%
                              </strong>
                            </div>
                          </div>

                          <div className="flex items-center justify-between text-[10px] text-[#737D89]">
                            <span className="flex items-center gap-1">
                              <Clock className="w-3 h-3" aria-hidden="true" />
                              {p.created_at
                                ? new Date(p.created_at).toLocaleDateString([], {
                                    day: '2-digit',
                                    month: 'short',
                                    year: 'numeric',
                                  })
                                : '—'}
                            </span>
                            <button
                              onClick={() => navigate('/prediction')}
                              className="text-[#2563EB] hover:text-blue-400 font-semibold inline-flex items-center gap-1 cursor-pointer transition-colors focus-visible:outline-none"
                            >
                              <span>View prediction</span>
                              <ArrowRight className="w-3 h-3" aria-hidden="true" />
                            </button>
                          </div>
                        </article>
                      )
                    })}
                  </div>
                )}
              </div>
            )}

            {/* ── TAB PANEL: My Reports ──────────────────────────────────────── */}
            {activeTab === 'reports' && (
              <div
                id="tabpanel-reports"
                role="tabpanel"
                aria-labelledby="tab-reports"
                className="p-5"
              >
                {/* Context note */}
                <div className="flex items-start gap-2 mb-4 p-3 bg-[#0F1216] border border-[#252B33] rounded-md">
                  <Info className="w-3.5 h-3.5 text-[#737D89] shrink-0 mt-0.5" aria-hidden="true" />
                  <p className="text-[11px] text-[#737D89] leading-relaxed">
                    <strong className="text-[#A7AFB9] font-semibold">My Reports</strong>
                    {' '}— Flood situation reports you have submitted. These are citizen-contributed observations and are distinct from both model predictions and the verified historical catalogue.
                  </p>
                </div>

                {loadingReports ? (
                  <div className="space-y-3">
                    {[1, 2].map(i => <RowSkeleton key={i} />)}
                  </div>
                ) : reports.length === 0 ? (
                  <div className="py-14 text-center space-y-3">
                    <p className="text-sm font-semibold text-[#A7AFB9]">No reports submitted yet.</p>
                    <p className="text-xs text-[#737D89]">Flood reports you submit will appear here.</p>
                    <button
                      onClick={() => navigate('/reports')}
                      className="mt-2 bg-[#2563EB] hover:bg-[#1D55D4] text-white font-semibold px-4 py-2 rounded-md text-xs transition-colors inline-block cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB] focus-visible:ring-offset-2 focus-visible:ring-offset-[#14181D]"
                    >
                      Submit a flood report
                    </button>
                  </div>
                ) : (
                  <div className="divide-y divide-[#1A1F28]">
                    {reports.map(r => {
                      const sev = normSev(r.risk_level)
                      const badgeClass = SEVERITY_BADGE[sev] || SEVERITY_BADGE.moderate
                      return (
                        <article
                          key={r.id}
                          className="py-3.5 hover:bg-[#0F1216]/60 transition-colors px-1 -mx-1 rounded"
                          aria-label={`Report from ${r.arrondissement || r.department || r.region || 'Far North'}`}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <h3 className="text-xs font-semibold text-[#F1F3F5] truncate">
                              {r.arrondissement || r.department || r.locality || r.region || 'Far North Area'}
                              {r.division && (
                                <span className="text-[#737D89] font-normal ml-1.5">· {r.division}</span>
                              )}
                            </h3>
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border capitalize shrink-0 ${badgeClass}`}>
                              {r.risk_level || 'N/A'}
                            </span>
                          </div>

                          {r.details && (
                            <p className="text-[11px] text-[#737D89] leading-relaxed mt-1.5 line-clamp-2">
                              {r.details}
                            </p>
                          )}

                          <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 mt-1.5 text-[10px] text-[#4A5568]">
                            <span>
                              Status:{' '}
                              <strong className="text-[#737D89] font-medium">{r.status || 'Received'}</strong>
                            </span>
                            {r.reported_at && (
                              <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3" aria-hidden="true" />
                                {new Date(r.reported_at).toLocaleDateString([], {
                                  day: '2-digit',
                                  month: 'short',
                                  year: 'numeric',
                                })}
                              </span>
                            )}
                          </div>
                        </article>
                      )
                    })}
                  </div>
                )}
              </div>
            )}
          </section>

          {/* ── CATALOGUE FOOTNOTE ──────────────────────────────────────────── */}
          <footer className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pt-1 border-t border-[#1A1F28]">
            <p className="text-[11px] text-[#4A5568]">
              Historical catalogue · {selectedRegion === 'all' ? 'All Regions' : `${selectedRegion} Region`} ·{' '}
              {!loadingEvents && (
                <span>{events.length} total records</span>
              )}
            </p>
            <div className="flex items-center gap-3">
              <p className="text-[11px] text-[#4A5568]">
                Counts are based on records in the connected database. Only Far North data is currently supported.
              </p>
              <button
                onClick={() => setMethodologyOpen(true)}
                className="text-[11px] text-[#2563EB] hover:text-blue-400 font-medium whitespace-nowrap flex items-center gap-1 transition-colors cursor-pointer focus-visible:outline-none focus-visible:underline"
              >
                <Info className="w-3 h-3" aria-hidden="true" />
                Methodology
              </button>
            </div>
          </footer>

          {/* ── METHODOLOGY MODAL ───────────────────────────────────────────── */}
          {methodologyOpen && (
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="methodology-title"
              className="fixed inset-0 z-50 flex items-center justify-center p-4"
            >
              {/* Backdrop */}
              <div
                className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                onClick={() => setMethodologyOpen(false)}
                aria-hidden="true"
              />

              {/* Panel */}
              <div className="relative z-10 bg-[#14181D] border border-[#252B33] rounded-lg p-6 max-w-lg w-full shadow-2xl">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h2
                      id="methodology-title"
                      className="text-base font-semibold text-[#F1F3F5] flex items-center gap-2"
                    >
                      <BookOpen className="w-4 h-4 text-[#2563EB]" aria-hidden="true" />
                      About the Historical Catalogue
                    </h2>
                    <p className="text-xs text-[#737D89] mt-1">Data transparency and methodology</p>
                  </div>
                  <button
                    onClick={() => setMethodologyOpen(false)}
                    aria-label="Close methodology information"
                    className="p-1.5 text-[#737D89] hover:text-[#F1F3F5] hover:bg-[#252B33] rounded-md transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <dl className="space-y-4">
                  <div>
                    <dt className="text-xs font-semibold text-[#A7AFB9] uppercase tracking-wide mb-1">Verified Events</dt>
                    <dd className="text-[13px] text-[#737D89] leading-relaxed">
                      Historical flood incidents confirmed through official sources including government
                      agencies, international humanitarian databases (EMDAT, ReliefWeb), and peer-reviewed
                      hydrological records. Events must have a confirmed date, location, and severity assessment
                      to be included in the catalogue.
                    </dd>
                  </div>

                  <div>
                    <dt className="text-xs font-semibold text-[#A7AFB9] uppercase tracking-wide mb-1">Historical Catalogue Scope</dt>
                    <dd className="text-[13px] text-[#737D89] leading-relaxed">
                      The connected catalogue currently documents verified flood events in the
                      <strong className="text-[#A7AFB9] font-medium"> Far North Region</strong> of Cameroon,
                      spanning 2005–2026. Records for other regions will be added as data becomes available.
                    </dd>
                  </div>

                  <div>
                    <dt className="text-xs font-semibold text-[#A7AFB9] uppercase tracking-wide mb-1">Severity Classification</dt>
                    <dd className="text-[13px] text-[#737D89] leading-relaxed">
                      Severity is drawn directly from source records where specified. Categories are:
                      <span className="text-[#22B981] font-medium"> Low</span>,
                      <span className="text-[#D89B3F] font-medium"> Moderate</span>,
                      <span className="text-[#E05A64] font-medium"> High</span>,
                      <span className="text-red-800 font-medium"> Very High</span>,
                      <span className="text-red-950 font-medium"> Critical</span>.
                      Events with no recorded severity appear as Unspecified.
                    </dd>
                  </div>

                  <div>
                    <dt className="text-xs font-semibold text-[#A7AFB9] uppercase tracking-wide mb-1">Division Frequency</dt>
                    <dd className="text-[13px] text-[#737D89] leading-relaxed">
                      Division event counts reflect how many documented flood incidents occurred in or
                      affected each administrative division. Events recorded across multiple divisions are
                      attributed to each named division.
                    </dd>
                  </div>

                  <div className="pt-2 border-t border-[#252B33]">
                    <dt className="text-xs font-semibold text-[#A7AFB9] uppercase tracking-wide mb-1">Data Trust</dt>
                    <dd className="text-[13px] text-[#737D89] leading-relaxed">
                      Statistics displayed are calculated from the connected database in real time.
                      Percentages and counts are mathematically consistent with the filtered record set.
                      No fabricated or synthetic historical values are used.
                    </dd>
                  </div>
                </dl>

                <div className="mt-5 pt-4 border-t border-[#252B33] flex justify-end">
                  <button
                    onClick={() => setMethodologyOpen(false)}
                    className="h-8 bg-[#2563EB] hover:bg-[#1D55D4] text-white text-xs font-semibold px-4 rounded-md transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#14181D] focus-visible:ring-[#2563EB]"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
