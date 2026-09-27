'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  LayoutDashboard,
  Bot,
  Map as MapIcon,
  AlertTriangle,
  Database,
  MessageSquare,
  Users,
  LineChart,
  Bell,
  Settings,
  LogOut,
  Search,
  CheckCircle2,
  TrendingUp,
  FileText,
  Plus,
  Minus,
  Layers,
  Shield,
  Activity,
  ArrowUpRight,
  RefreshCw,
  Eye,
  ChevronDown,
  Info,
  Clock,
  User,
  BarChart2,
  Package,
} from 'lucide-react'

import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

import {
  adminApi,
  type AdminOverview,
  type AdminUser,
  type AdminDataset,
  type AdminAnalytics,
  type AdminPrediction,
  type Alert,
  type CommunityReport,
  type PredictionFeedback,
} from '@/lib/api'

// ─── Map helpers ─────────────────────────────────────────────────────────────
const createCustomIcon = (color: string, label: string) =>
  L.divIcon({
    className: 'custom-map-pin',
    html: `<div style="display:flex;flex-direction:column;align-items:center;transform:translate(-50%,-100%);"><div style="background-color:${color};color:white;padding:2px 8px;border-radius:6px;font-size:10px;font-weight:700;white-space:nowrap;box-shadow:0 2px 5px rgba(0,0,0,0.3);display:flex;align-items:center;gap:4px;"><span style="width:6px;height:6px;border-radius:50%;background-color:white;"></span>${label}</div><div style="width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid ${color};align-self:center;"></div></div>`,
    iconSize: [120, 30],
    iconAnchor: [60, 30],
  })

// ─── Utilities ────────────────────────────────────────────────────────────────
function timeAgo(ts: string | null | undefined): string {
  if (!ts) return '—'
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function riskColor(level: string | undefined): string {
  const l = (level || '').toLowerCase()
  if (l === 'high' || l === 'very high') return 'text-red-600'
  if (l === 'medium' || l === 'moderate') return 'text-amber-600'
  return 'text-emerald-600'
}

function riskBadge(level: string | undefined): string {
  const l = (level || '').toLowerCase()
  if (l === 'high' || l === 'very high') return 'bg-red-100 text-red-700'
  if (l === 'medium' || l === 'moderate') return 'bg-amber-100 text-amber-700'
  return 'bg-emerald-100 text-emerald-700'
}

const STATUS_OPTIONS = ['Submitted', 'Pending', 'Under Review', 'Verified', 'Linked to existing event', 'Rejected', 'Resolved']

// ─── Sidebar button ───────────────────────────────────────────────────────────
function SidebarBtn({
  icon: Icon, label, tabKey, activeTab, onClick,
}: {
  icon: React.ElementType; label: string; tabKey: string; activeTab: string; onClick: () => void
}) {
  const active = activeTab === tabKey
  return (
    <button onClick={onClick} className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl font-semibold text-sm transition-all ${active ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'}`}>
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </button>
  )
}

// ─── Dashboard view ───────────────────────────────────────────────────────────
function DashboardView({ overview, loading, mapZoom, setMapZoom, isClient }: {
  overview: AdminOverview | null; loading: boolean; mapZoom: number; setMapZoom: React.Dispatch<React.SetStateAction<number>>; isClient: boolean
}) {
  const fn = overview?.far_north_latest_prediction ?? null
  const activity = overview?.activity ?? []

  return (
    <>
      <div className="flex items-start justify-between">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#0B172A] text-blue-400 font-bold text-[11px] tracking-wider uppercase mb-2 shadow-xs">
            <Shield className="h-3.5 w-3.5 text-blue-400" /><span>PLATFORM OVERVIEW</span>
          </div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight leading-tight">Good morning, Administrator</h1>
          <p className="text-sm text-slate-500 font-medium mt-1">Monitor flood intelligence, predictive models, and platform activity across Far North Cameroon.</p>
        </div>
        <div className={`inline-flex items-center gap-2.5 px-4 py-2 rounded-full border text-xs font-bold shadow-xs ${loading ? 'bg-slate-50 text-slate-500 border-slate-200' : 'bg-[#E6F8EE] text-[#0D8A47] border-[#CEEAD6]'}`}>
          <span className={`h-2.5 w-2.5 rounded-full ${loading ? 'bg-slate-400' : 'bg-emerald-500 animate-pulse'}`} /><span>{loading ? 'Loading system status' : 'Backend connected'}</span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        {/* Active Users */}
        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between text-slate-500 mb-3">
            <Users className="h-4 w-4 text-blue-600" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">ACTIVE USERS</span>
          </div>
          <div>
            <span className="text-2xl font-extrabold text-slate-900 tracking-tight">{loading ? '—' : (overview?.known_user_id_count ?? 0)}</span>
            <p className="text-[11px] text-slate-400 font-medium mt-1">Observed citizens</p>
          </div>
        </div>

        {/* Predictions */}
        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between text-slate-500 mb-3">
            <TrendingUp className="h-4 w-4 text-blue-600" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">PREDICTIONS</span>
          </div>
          <div>
            <span className="text-2xl font-extrabold text-slate-900 tracking-tight">{loading ? '—' : (overview?.predictions_generated ?? 0)}</span>
            <p className="text-[11px] text-slate-400 font-medium mt-1">Total generated</p>
          </div>
        </div>

        {/* Active Alerts */}
        <div className={`p-4 rounded-2xl flex flex-col justify-between relative overflow-hidden ${!loading && (overview?.active_alerts ?? 0) > 0 ? 'bg-[#DC2626] text-white shadow-md shadow-red-600/20' : 'bg-white border border-slate-200/80 shadow-xs hover:shadow-md transition-shadow'}`}>
          <div className={`flex items-center justify-between mb-3 ${!loading && (overview?.active_alerts ?? 0) > 0 ? 'text-white/90' : 'text-slate-500'}`}>
            <AlertTriangle className={`h-4 w-4 ${!loading && (overview?.active_alerts ?? 0) > 0 ? 'text-white' : 'text-blue-600'}`} />
            <span className={`text-[10px] font-extrabold uppercase tracking-wider ${!loading && (overview?.active_alerts ?? 0) > 0 ? 'text-white/90' : 'text-slate-400'}`}>ACTIVE ALERTS</span>
          </div>
          <div>
            <span className={`text-2xl font-extrabold tracking-tight ${!loading && (overview?.active_alerts ?? 0) > 0 ? 'text-white' : 'text-slate-900'}`}>{loading ? '—' : (overview?.active_alerts ?? 0)}</span>
            <p className={`text-[11px] font-medium mt-1 ${!loading && (overview?.active_alerts ?? 0) > 0 ? 'text-white/90' : 'text-slate-400'}`}>{!loading && (overview?.active_alerts ?? 0) === 0 ? 'No active alerts' : 'Require attention'}</p>
          </div>
        </div>

        {/* Pending Reports */}
        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between text-slate-500 mb-3">
            <FileText className="h-4 w-4 text-blue-600" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">PENDING REPORTS</span>
          </div>
          <div>
            <span className="text-2xl font-extrabold text-slate-900 tracking-tight">{loading ? '—' : (overview?.pending_reports ?? 0)}</span>
            <p className="text-[11px] text-slate-400 font-medium mt-1">Awaiting review</p>
          </div>
        </div>

        {/* Datasets */}
        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between text-slate-500 mb-3">
            <Database className="h-4 w-4 text-blue-600" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">DATASETS</span>
          </div>
          <div>
            <span className="text-2xl font-extrabold text-slate-900 tracking-tight">{loading ? '—' : (overview?.datasets ?? 0)}</span>
            <p className="text-[11px] text-slate-400 font-medium mt-1">verified data</p>
          </div>
        </div>

        {/* Model Perf */}
        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between text-slate-500 mb-3">
            <Activity className="h-4 w-4 text-blue-600" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">MODEL PERF.</span>
          </div>
          <div>
            {loading ? <span className="text-2xl font-extrabold text-slate-900 tracking-tight">—</span>
              : overview?.model_performance != null ? (
                <div className="flex items-baseline gap-1">
                  <span className="text-2xl font-extrabold text-slate-900 tracking-tight">{overview.model_performance}%</span>
                  <ArrowUpRight className="h-4 w-4 text-blue-600" />
                </div>
              ) : <span className="text-sm font-bold text-slate-500">No evaluation data</span>}
            <p className="text-[11px] text-slate-400 font-medium mt-1">{overview?.model_performance_metric ?? 'No persisted evaluation records'}</p>
          </div>
        </div>
      </div>

      {/* Map + Right panels */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col h-[460px] relative overflow-hidden">
          <div className="absolute top-7 left-7 z-[1000] bg-white/95 backdrop-blur-md px-4 py-2 rounded-xl shadow-md border border-slate-200/80 flex items-center gap-2">
            <MapIcon className="h-4 w-4 text-blue-600" /><span className="text-xs font-extrabold text-slate-800">Far North — Flood Risk Map</span>
          </div>
          <div className="absolute top-7 right-7 z-[1000] flex flex-col bg-white/95 backdrop-blur-md rounded-xl shadow-md border border-slate-200/80 p-1">
            <button onClick={() => setMapZoom(p => Math.min(p + 1, 13))} className="p-1.5 hover:bg-slate-100 text-slate-700 rounded-lg transition-colors cursor-pointer"><Plus className="h-4 w-4" /></button>
            <button onClick={() => setMapZoom(p => Math.max(p - 1, 4))} className="p-1.5 hover:bg-slate-100 text-slate-700 rounded-lg transition-colors cursor-pointer"><Minus className="h-4 w-4" /></button>
            <div className="h-[1px] bg-slate-200 my-0.5" />
            <button className="p-1.5 hover:bg-slate-100 text-slate-700 rounded-lg transition-colors cursor-pointer"><Layers className="h-4 w-4" /></button>
          </div>
          <div className="w-full h-full rounded-xl overflow-hidden z-0">
            {isClient && (
              <MapContainer center={[11.5, 14.8]} zoom={mapZoom} scrollWheelZoom={false} zoomControl={false} className="h-full w-full">
                <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                {(() => {
                  const coordinates = fn?.details?.risk?.coordinates
                  if (!coordinates || typeof coordinates.lat !== 'number' || typeof coordinates.lon !== 'number') return null
                  return <Marker position={[coordinates.lat, coordinates.lon]} icon={createCustomIcon('#2563EB', fn.locality)}>
                    <Popup>
                      <div className="p-1 font-sans">
                        <p className="font-bold text-xs">{fn.locality}</p>
                        <p className="text-[10px] text-slate-500">Far North Region</p>
                        <p className="text-[10px] font-bold text-blue-600 mt-1">Risk: {fn.risk_level} ({fn.estimated_risk_percent}%)</p>
                      </div>
                    </Popup>
                  </Marker>
                })()}
              </MapContainer>
            )}
          </div>
          <div className="absolute bottom-7 left-7 z-[1000] bg-white/95 backdrop-blur-md px-4 py-2.5 rounded-xl shadow-md border border-slate-200/80 flex flex-col gap-1.5">
            <span className="text-[10px] font-extrabold uppercase text-slate-400 tracking-wider">RISK LEGEND</span>
            <div className="flex items-center gap-4 text-xs font-semibold text-slate-700">
              <div className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-red-600" /><span>High</span></div>
              <div className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-amber-500" /><span>Medium</span></div>
              <div className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-emerald-500" /><span>Low</span></div>
            </div>
          </div>
        </div>

        <div className="lg:col-span-4 flex flex-col gap-6">
          {/* Regional Risk - Far North ONLY */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col gap-4">
            <h3 className="text-base font-bold text-slate-900">Regional Risk Focus</h3>
            {loading ? (
              <div className="flex items-center gap-2 text-slate-400 text-sm"><RefreshCw className="h-4 w-4 animate-spin" /><span>Loading...</span></div>
            ) : fn ? (
              <div className="flex items-center justify-between p-2.5 rounded-xl bg-amber-50/40 border border-amber-100">
                <div>
                  <p className="text-sm font-bold text-slate-900">Far North</p>
                  <p className={`text-xs font-bold ${riskColor(fn.risk_level)}`}>{fn.risk_level} ({fn.estimated_risk_percent}%) — {fn.locality}</p>
                  <p className="text-[10px] text-slate-400 mt-0.5">{fn.forecast_period}</p>
                </div>
                <span className={`px-3 py-1 font-bold text-xs rounded-full ${riskBadge(fn.risk_level)}`}>{fn.risk_level}</span>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-slate-400 text-sm py-2">
                <Info className="h-4 w-4 flex-shrink-0" /><span>No current Far North assessment available.</span>
              </div>
            )}
            <p className="text-[10px] text-slate-400 font-medium">Operational scope: Far North Region only.</p>
          </div>

          {/* Active Alerts */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col gap-4">
            <div className="flex items-center justify-between"><h3 className="text-base font-bold text-slate-900">Active Alerts</h3><Bell className="h-4 w-4 text-slate-400" /></div>
            {loading ? (
              <div className="flex items-center gap-2 text-slate-400 text-sm"><RefreshCw className="h-4 w-4 animate-spin" /><span>Loading...</span></div>
            ) : (overview?.active_alerts ?? 0) === 0 ? (
              <div className="flex flex-col items-center justify-center py-4 text-center">
                <CheckCircle2 className="h-8 w-8 text-emerald-500 mb-2" />
                <p className="text-sm font-bold text-slate-700">No active flood alerts</p>
                <p className="text-xs text-slate-400 mt-1">No alert records are currently active in the backend.</p>
              </div>
            ) : (
              <div className="border-l-4 border-red-500 pl-3.5 py-1 bg-red-50/40 rounded-r-xl">
                <p className="text-xs font-extrabold text-red-600 uppercase tracking-tight">{overview!.active_alerts} ACTIVE ALERT{overview!.active_alerts > 1 ? 'S' : ''}</p>
                <p className="text-xs text-slate-700 font-medium mt-1">Require immediate administrative attention.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom analytics + activity */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-6 bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col gap-4">
          <h3 className="text-base font-bold text-slate-900">Prediction Analytics</h3>
          {loading ? (
            <div className="flex items-center gap-2 text-slate-400 text-sm"><RefreshCw className="h-4 w-4 animate-spin" /><span>Loading...</span></div>
          ) : fn ? (
            <div className="flex items-center justify-between gap-6 pt-2">
              <div className="flex-1 space-y-3">
                {[['Locality', fn.locality], ['Risk Level', fn.risk_level], ['Estimated Risk', `${fn.estimated_risk_percent}%`], ['Confidence', `${fn.confidence_score}%`], ['Forecast Period', fn.forecast_period]].map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-slate-600">{k}</span>
                    <span className={`font-bold ${k === 'Risk Level' ? riskColor(v) : 'text-slate-900'}`}>{v}</span>
                  </div>
                ))}
              </div>
              <div className="flex flex-col items-center justify-center p-4">
                <div className="relative h-28 w-28 flex items-center justify-center">
                  <svg className="h-full w-full -rotate-90" viewBox="0 0 36 36">
                    <path className="text-slate-100" strokeWidth="4" stroke="currentColor" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                    <path className={fn.estimated_risk_percent > 65 ? 'text-red-500' : fn.estimated_risk_percent > 35 ? 'text-amber-500' : 'text-emerald-500'} strokeDasharray={`${fn.estimated_risk_percent}, 100`} strokeWidth="4.5" strokeLinecap="round" stroke="currentColor" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                  </svg>
                  <div className="absolute flex flex-col items-center justify-center text-center">
                    <span className="text-2xl font-extrabold text-slate-900">{fn.estimated_risk_percent}%</span>
                  </div>
                </div>
                <span className={`text-xs font-bold mt-2 ${riskColor(fn.risk_level)}`}>{fn.risk_level} Risk</span>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-slate-400 text-sm py-4"><Info className="h-4 w-4 flex-shrink-0" /><span>No prediction data available.</span></div>
          )}
        </div>

        <div className="lg:col-span-6 bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col gap-4">
          <h3 className="text-base font-bold text-slate-900">System Health &amp; Activity</h3>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="bg-slate-50 border border-slate-200/80 px-3.5 py-2 rounded-xl flex items-center gap-2 text-xs font-semibold text-slate-700">
              <span className="text-[10px] font-extrabold text-slate-400 uppercase">WEATHER DATA</span>
              <span className="flex items-center gap-1 text-slate-500 font-bold"><Info className="h-3.5 w-3.5" /> No health telemetry</span>
            </div>
            <div className="bg-slate-50 border border-slate-200/80 px-3.5 py-2 rounded-xl flex items-center gap-2 text-xs font-semibold text-slate-700">
              <span className="text-[10px] font-extrabold text-slate-400 uppercase">HISTORICAL DATA</span>
              <span className="flex items-center gap-1 text-slate-500 font-bold"><Info className="h-3.5 w-3.5" /> No health telemetry</span>
            </div>
          </div>
          <div className="space-y-3 pt-2">
            {loading ? (
              <div className="flex items-center gap-2 text-slate-400 text-sm"><RefreshCw className="h-4 w-4 animate-spin" /><span>Loading activity...</span></div>
            ) : activity.length === 0 ? (
              <p className="text-xs text-slate-400">No recent platform activity recorded.</p>
            ) : activity.slice(0, 6).map((item, idx) => (
              <div key={idx} className="flex items-center justify-between text-xs font-medium text-slate-700">
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full flex-shrink-0 ${item.type === 'prediction' ? 'bg-blue-600' : item.type === 'report' ? 'bg-amber-500' : 'bg-emerald-500'}`} />
                  <span className="truncate max-w-xs">{item.message}</span>
                </div>
                <span className="text-slate-400 font-normal ml-3 flex-shrink-0">{timeAgo(item.timestamp)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Quick actions */}
      <div className="flex items-center gap-3 pt-2 overflow-x-auto pb-4 scrollbar-none">
        <button onClick={() => window.dispatchEvent(new CustomEvent('admin-tab', { detail: 'users' }))} className="px-5 py-2.5 bg-[#0B172A] hover:bg-[#16253e] text-white font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer flex-shrink-0">
          <Users className="h-4 w-4" /><span>Manage Users</span>
        </button>
        <button onClick={() => window.dispatchEvent(new CustomEvent('admin-tab', { detail: 'reports' }))} className="px-5 py-2.5 bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer flex-shrink-0">
          <MessageSquare className="h-4 w-4 text-slate-500" /><span>Community Reports</span>
        </button>
        <button onClick={() => window.dispatchEvent(new CustomEvent('admin-tab', { detail: 'datasets' }))} className="px-5 py-2.5 bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer flex-shrink-0">
          <Database className="h-4 w-4 text-slate-500" /><span>Manage Datasets</span>
        </button>
        <button onClick={() => window.dispatchEvent(new CustomEvent('admin-tab', { detail: 'analytics' }))} className="px-5 py-2.5 bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer flex-shrink-0">
          <LineChart className="h-4 w-4 text-slate-500" /><span>View Analytics</span>
        </button>
        <button onClick={() => window.dispatchEvent(new CustomEvent('admin-tab', { detail: 'notifications' }))} className="px-5 py-2.5 bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer flex-shrink-0">
          <Bell className="h-4 w-4 text-slate-500" /><span>Notifications &amp; Feedback</span>
        </button>
      </div>
    </>
  )
}

// ─── Users view ───────────────────────────────────────────────────────────────
function UsersView() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<AdminUser | null>(null)
  const [editName, setEditName] = useState('')
  const [editUsername, setEditUsername] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editPassword, setEditPassword] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    adminApi.getUsers().then(r => { setUsers(r.users); setCount(r.count) }).catch(console.error).finally(() => setLoading(false))
  }, [])

  const filtered = users.filter(u => u.user_id.toLowerCase().includes(search.toLowerCase()) || u.role.toLowerCase().includes(search.toLowerCase()))

  const saveUser = async () => {
    if (!selected || saving) return
    setSaving(true)
    try { const payload: { display_name?: string; username?: string; email?: string; password?: string } = { display_name: editName, username: editUsername, email: editEmail }; if (editPassword.trim()) payload.password = editPassword; const r = await adminApi.updateUser(selected.user_id, payload); setUsers(prev => prev.map(u => u.user_id === selected.user_id ? { ...u, ...r.user } : u)); setSelected({ ...selected, ...r.user }); setEditPassword('') }
    catch (e) { console.error(e) } finally { setSaving(false) }
  }
  const deactivate = async () => {
    if (!selected || saving || !window.confirm(`Are you sure you want to deactivate ${selected.user_id}?`)) return
    setSaving(true)
    try { const r = await adminApi.deactivateUser(selected.user_id); setUsers(prev => prev.map(u => u.user_id === selected.user_id ? { ...u, ...r.user } : u)); setSelected({ ...selected, ...r.user }) }
    catch (e) { console.error(e) } finally { setSaving(false) }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-extrabold text-slate-900">Manage Users</h2>
          <p className="text-sm text-slate-500 mt-0.5">{count} observed citizen account{count !== 1 ? 's' : ''} in the platform</p>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input type="text" placeholder="Search by user ID or role..." value={search} onChange={e => setSearch(e.target.value)} className="pl-10 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all w-64" />
        </div>
      </div>
      {loading ? (
        <div className="flex items-center gap-3 text-slate-400 py-8"><RefreshCw className="h-5 w-5 animate-spin" /><span>Loading users...</span></div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-12 text-center">
          <User className="h-10 w-10 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 font-medium">No user accounts found.</p>
          <p className="text-xs text-slate-400 mt-1">Citizen accounts are created automatically when they use the platform.</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200/80">
                {['User ID', 'Role', 'Source', 'Predictions', 'Reports', 'Feedback', 'Last Active', ''].map(h => (
                  <th key={h} className="text-left px-5 py-3 text-xs font-extrabold uppercase tracking-wider text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map(u => (
                <tr key={u.user_id} className="hover:bg-slate-50/60 transition-colors">
                  <td className="px-5 py-3.5 font-mono text-xs text-slate-700 max-w-[180px] truncate">{u.display_name || u.username || u.email || u.user_id}</td>
                  <td className="px-5 py-3.5"><span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${u.role === 'admin' || u.role === 'administrator' ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600'}`}>{u.role}</span></td>
                  <td className="px-5 py-3.5 text-xs text-slate-500">{u.is_active === false ? 'Deactivated' : u.source}</td>
                  <td className="px-5 py-3.5 text-xs font-bold text-slate-900 text-center">{u.prediction_count}</td>
                  <td className="px-5 py-3.5 text-xs font-bold text-slate-900 text-center">{u.report_count}</td>
                  <td className="px-5 py-3.5 text-xs font-bold text-slate-900 text-center">{u.feedback_count}</td>
                  <td className="px-5 py-3.5 text-xs text-slate-400">{timeAgo(u.last_seen)}</td>
                  <td className="px-5 py-3.5"><button onClick={() => { setSelected(u); setEditName(u.display_name || ''); setEditUsername(u.username || ''); setEditEmail(u.email || ''); setEditPassword('') }} className="p-1.5 hover:bg-blue-50 rounded-lg text-blue-600 transition-colors cursor-pointer"><Eye className="h-3.5 w-3.5" /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={() => setSelected(null)}>
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-xl max-h-[calc(100vh-2rem)] mx-4 flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between gap-4 px-6 py-5 border-b border-slate-100 flex-shrink-0">
              <div className="flex items-center gap-3">
              <div className="h-12 w-12 rounded-xl bg-blue-100 flex items-center justify-center"><User className="h-6 w-6 text-blue-600" /></div>
              <div><h3 className="font-extrabold text-slate-900">User Details</h3><p className="text-xs text-slate-400 font-mono mt-0.5 break-all">{selected.user_id}</p></div>
              </div>
              <button type="button" onClick={() => setSelected(null)} className="h-9 w-9 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 text-xl leading-none" aria-label="Close user details">×</button>
            </div>
            <div className="overflow-y-auto px-6 py-5 space-y-5">
              <div className="rounded-xl border border-blue-100 bg-blue-50/60 px-4 py-3 text-xs text-blue-800">Edit the account fields below, then select <b>Save changes</b>. Leave the password blank to keep the current password.</div>
              <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-xs font-bold text-slate-500">Display name<input value={editName} onChange={e => setEditName(e.target.value)} className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Optional display name" /></label>
              <label className="block text-xs font-bold text-slate-500">Username<input value={editUsername} onChange={e => setEditUsername(e.target.value)} className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Username" /></label>
              <label className="block text-xs font-bold text-slate-500">Email<input type="email" value={editEmail} onChange={e => setEditEmail(e.target.value)} className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Email address" /></label>
              <label className="block text-xs font-bold text-slate-500">New password<input type="password" value={editPassword} onChange={e => setEditPassword(e.target.value)} className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Leave blank to keep current" /></label>
              </div>
              <div>
                <h4 className="text-xs font-extrabold uppercase tracking-wider text-slate-400 mb-2">Account information</h4>
                <div className="rounded-xl border border-slate-200 divide-y divide-slate-100">
              {[['Role', selected.role], ['Source', selected.source], ['Predictions', String(selected.prediction_count)], ['Community Reports', String(selected.report_count)], ['Feedback Submitted', String(selected.feedback_count)], ['Last Active', timeAgo(selected.last_seen)]].map(([label, val]) => (
                <div key={label} className="flex items-center justify-between gap-4 px-4 py-2.5 text-sm">
                  <span className="text-slate-500 font-medium">{label}</span>
                  <span className="font-bold text-slate-900 text-right truncate">{val}</span>
                </div>
              ))}
                </div>
              </div>
            </div>
            <div className="flex flex-col-reverse sm:flex-row gap-2 px-6 py-4 border-t border-slate-100 bg-slate-50 flex-shrink-0"><button type="button" onClick={() => setSelected(null)} className="flex-1 py-2.5 bg-white border border-slate-200 text-slate-700 font-bold text-sm rounded-xl hover:bg-slate-100">Cancel</button><button type="button" disabled={saving} onClick={saveUser} className="flex-1 py-2.5 bg-blue-600 text-white font-bold text-sm rounded-xl disabled:opacity-50">{saving ? 'Saving…' : 'Save changes'}</button><button type="button" disabled={saving || selected.is_active === false} onClick={deactivate} className="flex-1 py-2.5 bg-red-50 text-red-700 font-bold text-sm rounded-xl disabled:opacity-50">Deactivate</button></div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Community Reports view ───────────────────────────────────────────────────
function ReportsView() {
  const [reports, setReports] = useState<CommunityReport[]>([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<CommunityReport | null>(null)
  const [verificationNotes, setVerificationNotes] = useState('')
  const [alertMessage, setAlertMessage] = useState('')
  const [actionBusy, setActionBusy] = useState(false)
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    adminApi.getReports().then(r => { setReports(r.reports); setCount(r.count) }).catch(console.error).finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    let objectUrl: string | null = null
    setEvidenceUrl(null)
    if (selected?.evidence_url) {
      adminApi.getEvidenceObjectUrl(selected.id).then(url => { objectUrl = url; setEvidenceUrl(url) }).catch(() => setEvidenceUrl(null))
    }
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [selected])

  const handleStatusChange = async (id: number, status: string) => {
    setUpdating(id)
    try {
      await adminApi.updateReportStatus(id, status)
      setReports(prev => prev.map(r => r.id === id ? { ...r, status } : r))
      setSelected(prev => prev && prev.id === id ? { ...prev, status } : prev)
    } catch (e) { console.error(e) } finally { setUpdating(null) }
  }

  const filtered = reports.filter(r =>
    (r.locality ?? '').toLowerCase().includes(search.toLowerCase()) ||
    (r.division ?? '').toLowerCase().includes(search.toLowerCase()) ||
    (r.reporter_name ?? r.user_id ?? '').toLowerCase().includes(search.toLowerCase()) ||
    String(r.id).includes(search)
  )

  const verify = async (verified: boolean) => {
    if (!selected || actionBusy) return
    setActionBusy(true)
    try {
      const result = await adminApi.verifyReport(selected.id, verified, verificationNotes || undefined)
      setReports(prev => prev.map(r => r.id === selected.id ? result.report : r))
      setSelected(result.report)
    } catch (e) { console.error(e) } finally { setActionBusy(false) }
  }

  const sendAlert = async () => {
    if (!selected || !alertMessage.trim() || actionBusy) return
    if (!window.confirm(`Create an internal platform alert for report #${selected.id}?`)) return
    setActionBusy(true)
    try { await adminApi.createReportAlert(selected.id, { message: alertMessage.trim(), severity: selected.risk_level || 'Moderate' }); setAlertMessage(''); window.alert('Internal alert record created.') }
    catch (e) { console.error(e) } finally { setActionBusy(false) }
  }

  const permanentlyDeleteReport = async (report: CommunityReport) => {
    if (report.status !== 'Rejected' || actionBusy) return
    if (!window.confirm(`Permanently delete report #${report.id}? This cannot be undone.`)) return
    setActionBusy(true)
    try {
      await adminApi.deleteReport(report.id)
      setReports(prev => prev.filter(r => r.id !== report.id))
      setCount(prev => Math.max(0, prev - 1))
      setSelected(prev => prev?.id === report.id ? null : prev)
    } catch (e) { console.error(e) } finally { setActionBusy(false) }
  }

  const deleteSelectedReport = () => { if (selected) permanentlyDeleteReport(selected) }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-extrabold text-slate-900">Community Reports</h2>
          <p className="text-sm text-slate-500 mt-0.5">{count} flood report{count !== 1 ? 's' : ''} submitted by citizens</p>
          <p className="text-xs text-slate-400 mt-1">Review status is persisted to the report record. Verification does not automatically publish a new training dataset.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input type="text" placeholder="Search by locality, reporter..." value={search} onChange={e => setSearch(e.target.value)} className="pl-10 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all w-72" />
          </div>
          <button onClick={load} className="p-2 bg-white border border-slate-200 hover:bg-slate-50 rounded-xl text-slate-500 transition-all cursor-pointer"><RefreshCw className="h-4 w-4" /></button>
        </div>
      </div>
      {loading ? (
        <div className="flex items-center gap-3 text-slate-400 py-8"><RefreshCw className="h-5 w-5 animate-spin" /><span>Loading reports...</span></div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-12 text-center">
          <FileText className="h-10 w-10 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 font-medium">No community reports found.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(r => (
            <div key={r.id} className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <span className="text-xs font-extrabold text-slate-400 uppercase">Report #{r.id}</span>
                    {r.locality && <span className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs font-bold rounded-full">{r.locality}</span>}
                    {r.division && <span className="px-2 py-0.5 bg-slate-100 text-slate-600 text-xs font-semibold rounded-full">{r.division}</span>}
                    {r.water_depth_category && <span className="px-2 py-0.5 bg-amber-50 text-amber-700 text-xs font-semibold rounded-full">Water: {r.water_depth_category}</span>}
                  </div>
                  <p className="text-sm text-slate-700 font-medium mb-2">{r.details}</p>
                  <div className="flex items-center gap-4 text-xs text-slate-400 flex-wrap">
                    <span className="flex items-center gap-1"><User className="h-3 w-3" />{r.reporter_name ?? r.user_id ?? 'Unknown citizen'}</span>
                    {(r.observation_at ?? r.reported_at) && <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{new Date(r.observation_at ?? r.reported_at!).toLocaleDateString()}</span>}
                    {r.evidence_name && <span className="flex items-center gap-1 text-blue-500"><FileText className="h-3 w-3" />{r.evidence_name}</span>}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2 flex-shrink-0">
                  <div className="relative">
                    <select value={r.status ?? 'Submitted'} onChange={e => handleStatusChange(r.id, e.target.value)} disabled={updating === r.id} className="pl-3 pr-7 py-1.5 text-xs font-bold border border-slate-200 rounded-xl bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500/30 cursor-pointer appearance-none disabled:opacity-50">
                      {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-400 pointer-events-none" />
                  </div>
                  {updating === r.id && <RefreshCw className="h-3.5 w-3.5 animate-spin text-blue-500" />}
                  <div className="flex items-center gap-2">
                    <button onClick={() => { setSelected(r); setVerificationNotes(r.verification_notes || '') }} className="px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 text-xs font-bold hover:bg-blue-100">View details / verify</button>
                    {r.status === 'Rejected' && <button onClick={() => permanentlyDeleteReport(r)} disabled={actionBusy} className="px-3 py-1.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs font-bold hover:bg-red-100 disabled:opacity-50">Delete permanently</button>}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {selected && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setSelected(null)}><div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}><div className="flex justify-between items-start"><div><h3 className="text-xl font-extrabold text-slate-900">Report #{selected.id}</h3><p className="text-sm text-slate-500 mt-1">{selected.locality || 'Location not named'} · {selected.division || 'Division not recorded'} · {selected.region || 'Region not recorded'}</p></div><span className="px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-xs font-bold">{selected.status || 'Submitted'}</span></div><div className="grid grid-cols-2 gap-3 mt-5 text-sm"><div><span className="text-slate-400">Reporter</span><p className="font-semibold text-slate-800">{selected.reporter_name || selected.user_id || 'Not provided'}</p></div><div><span className="text-slate-400">Observed</span><p className="font-semibold text-slate-800">{selected.observation_at ? new Date(selected.observation_at).toLocaleString() : 'Not provided'}</p></div><div><span className="text-slate-400">Coordinates</span><p className="font-semibold text-slate-800">{selected.location_lat}, {selected.location_lng}</p></div><div><span className="text-slate-400">Evidence</span><p className="font-semibold text-slate-800">{selected.evidence_name || 'No file attached'}</p></div></div>{selected.evidence_url && evidenceUrl && (selected.evidence_media_type?.startsWith('video/') ? <video controls className="mt-4 w-full max-h-80 rounded-xl bg-black" src={evidenceUrl} /> : <img className="mt-4 max-h-80 w-full rounded-xl object-contain bg-slate-100" src={evidenceUrl} alt={selected.evidence_name || 'Citizen evidence'} />)}{selected.evidence_name && !selected.evidence_url && <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800"><b>Filename recorded only:</b> “{selected.evidence_name}” was submitted before media upload storage was enabled, so the original image/video is not present on this server. New uploads will display here.</div>}<div className="mt-4 p-4 rounded-xl bg-slate-50 text-sm text-slate-700 whitespace-pre-wrap">{selected.details}</div><label className="block text-xs font-bold text-slate-500 mt-5 mb-1">Verification notes</label><textarea value={verificationNotes} onChange={e => setVerificationNotes(e.target.value)} className="w-full border border-slate-200 rounded-xl p-3 text-sm min-h-20" placeholder="Record evidence checks or rejection reason" /><div className="flex flex-wrap gap-2 mt-4"><button disabled={actionBusy} onClick={() => verify(true)} className="px-4 py-2 rounded-xl bg-emerald-600 text-white text-sm font-bold disabled:opacity-50">Confirm / Verify</button><button disabled={actionBusy} onClick={() => verify(false)} className="px-4 py-2 rounded-xl bg-red-600 text-white text-sm font-bold disabled:opacity-50">Reject</button>{selected.status === 'Rejected' && <button disabled={actionBusy} onClick={deleteSelectedReport} className="px-4 py-2 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm font-bold disabled:opacity-50">Delete permanently</button>}</div>{selected.status === 'Rejected' && <p className="mt-2 text-xs text-red-600">Rejected reports can be permanently deleted. This action cannot be undone.</p>}{(selected.status === 'Verified' || selected.status === 'Linked to existing event') && <div className="mt-5 pt-4 border-t border-slate-200"><p className="text-sm font-bold text-slate-800">Create internal alert from this verified event</p><p className="text-xs text-slate-500 mt-1">This stores a platform alert; it does not claim SMS or push delivery.</p><textarea value={alertMessage} onChange={e => setAlertMessage(e.target.value)} className="w-full border border-slate-200 rounded-xl p-3 text-sm mt-2" placeholder="Alert message" /><button disabled={actionBusy || !alertMessage.trim()} onClick={sendAlert} className="mt-2 px-4 py-2 rounded-xl bg-amber-500 text-white text-sm font-bold disabled:opacity-50">Send Alert</button></div>}<button onClick={() => setSelected(null)} className="mt-5 w-full py-2.5 rounded-xl border border-slate-200 text-slate-600 font-bold text-sm">Close</button></div></div>}
    </div>
  )
}

// ─── Notifications / Feedback view ───────────────────────────────────────────
function NotificationsView() {
  const [feedback, setFeedback] = useState<PredictionFeedback[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([adminApi.getFeedback(), adminApi.getAlerts()]).then(([f, a]) => { setFeedback(f.feedback); setCount(f.count); setAlerts(a.alerts) }).catch(console.error).finally(() => setLoading(false))
  }, [])

  const accuracyColor = (a: string) => {
    const l = a.toLowerCase()
    if (l === 'accurate' || l === 'highly accurate') return 'bg-emerald-100 text-emerald-700'
    if (l === 'somewhat accurate') return 'bg-blue-100 text-blue-700'
    return 'bg-red-100 text-red-700'
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-extrabold text-slate-900">Notifications &amp; Prediction Feedback</h2>
        <p className="text-sm text-slate-500 mt-0.5">{count} feedback record{count !== 1 ? 's' : ''} from citizens on their predictions</p>
      </div>
      {loading ? (
        <div className="flex items-center gap-3 text-slate-400 py-8"><RefreshCw className="h-5 w-5 animate-spin" /><span>Loading feedback...</span></div>
      ) : feedback.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-12 text-center">
          <Bell className="h-10 w-10 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 font-medium">No prediction feedback submitted yet.</p>
          <p className="text-xs text-slate-400 mt-1">Citizens can submit feedback on flood prediction accuracy from their workspace.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {feedback.map(f => (
            <div key={f.id} className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5">
              <div className="flex items-center gap-2 flex-wrap mb-2">
                <span className="text-xs font-extrabold text-slate-400 uppercase">Feedback #{f.id}</span>
                <span className={`px-2 py-0.5 text-xs font-bold rounded-full ${accuracyColor(f.accuracy)}`}>{f.accuracy}</span>
                {f.prediction_locality && <span className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs font-bold rounded-full">{f.prediction_locality}</span>}
                {f.prediction_risk_level && <span className={`px-2 py-0.5 text-xs font-bold rounded-full ${riskBadge(f.prediction_risk_level)}`}>{f.prediction_risk_level} ({f.prediction_estimated_risk_percent}%)</span>}
              </div>
              {f.comments && <p className="text-sm text-slate-700 font-medium mb-2">"{f.comments}"</p>}
              <div className="flex items-center gap-4 text-xs text-slate-400">
                <span className="flex items-center gap-1"><User className="h-3 w-3" />{f.user_id ?? 'Anonymous'}</span>
                <span className="flex items-center gap-1"><Bot className="h-3 w-3" />Prediction #{f.prediction_id}</span>
                {f.created_at && <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{timeAgo(f.created_at)}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-5">
        <h3 className="text-base font-bold text-slate-900 mb-3">Active system alerts</h3>
        {alerts.length === 0 ? <p className="text-xs text-slate-400">No active alerts are persisted for Far North Cameroon.</p> : <div className="space-y-2">{alerts.map(a => <div key={a.alert_id} className="p-3 rounded-xl bg-red-50 border border-red-100 text-sm"><span className="font-bold text-red-700">{a.watershed}</span><span className="text-slate-600"> — {a.message}</span></div>)}</div>}
      </div>
    </div>
  )
}

// ─── Datasets view ────────────────────────────────────────────────────────────
function DatasetsView() {
  const [datasets, setDatasets] = useState<AdminDataset[]>([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    adminApi.getDatasets().then(r => { setDatasets(r.datasets); setCount(r.count) }).catch(console.error).finally(() => setLoading(false))
  }, [])

  const statusColor = (s: string) => {
    const l = s.toLowerCase()
    if (l === 'active' || l === 'operational') return 'bg-emerald-100 text-emerald-700'
    if (l === 'pending') return 'bg-amber-100 text-amber-700'
    return 'bg-slate-100 text-slate-600'
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-extrabold text-slate-900">Operational Datasets</h2>
        <p className="text-sm text-slate-500 mt-0.5">{count} registered dataset{count !== 1 ? 's' : ''} powering the AquaGuard AI prediction model</p>
      </div>
      {loading ? (
        <div className="flex items-center gap-3 text-slate-400 py-8"><RefreshCw className="h-5 w-5 animate-spin" /><span>Loading datasets...</span></div>
      ) : datasets.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-12 text-center"><Database className="h-10 w-10 text-slate-300 mx-auto mb-3" /><p className="text-slate-500 font-medium">No datasets registered.</p></div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {datasets.map(d => (
            <div key={d.id} className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5 flex flex-col gap-3">
              <div className="flex items-start justify-between gap-3">
                <div className="h-10 w-10 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0"><Package className="h-5 w-5 text-blue-600" /></div>
                <div className="flex-1 min-w-0">
                  <h4 className="font-bold text-slate-900 text-sm leading-tight">{d.name}</h4>
                  <p className="text-xs text-slate-400 mt-0.5">{d.category}</p>
                </div>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold flex-shrink-0 ${statusColor(d.status)}`}>{d.status}</span>
              </div>
              <p className="text-xs text-slate-600 leading-relaxed">{d.description}</p>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-slate-50 rounded-xl p-2.5"><p className="text-slate-400 font-semibold mb-0.5">Coverage</p><p className="font-bold text-slate-700">{d.coverage}</p></div>
                <div className="bg-slate-50 rounded-xl p-2.5"><p className="text-slate-400 font-semibold mb-0.5">Format</p><p className="font-bold text-slate-700">{d.format}</p></div>
                <div className="bg-slate-50 rounded-xl p-2.5 col-span-2"><p className="text-slate-400 font-semibold mb-0.5">Source</p><p className="font-bold text-slate-700">{d.source}</p></div>
              </div>
              {d.records !== undefined && d.records !== '' && <p className="text-[10px] text-slate-400 font-semibold">Records: {d.records}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Analytics view ───────────────────────────────────────────────────────────
function AnalyticsView() {
  const [analytics, setAnalytics] = useState<AdminAnalytics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    adminApi.getAnalytics().then(setAnalytics).catch(console.error).finally(() => setLoading(false))
  }, [])

  const maxRisk = analytics ? Math.max(...analytics.risk_distribution.map(r => r.count), 1) : 1
  const maxLocality = analytics ? Math.max(...analytics.locality_distribution.map(l => l.count), 1) : 1

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-2xl font-extrabold text-slate-900">Prediction Analytics</h2>
        <p className="text-sm text-slate-500 mt-0.5">Deep-dive into flood prediction records and risk distributions</p>
      </div>
      {loading ? (
        <div className="flex items-center gap-3 text-slate-400 py-8"><RefreshCw className="h-5 w-5 animate-spin" /><span>Loading analytics...</span></div>
      ) : !analytics ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-12 text-center"><BarChart2 className="h-10 w-10 text-slate-300 mx-auto mb-3" /><p className="text-slate-500 font-medium">Analytics data not available.</p></div>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: 'Total Predictions', value: analytics.prediction_count, icon: TrendingUp, color: 'text-blue-600', bg: 'bg-blue-50' },
              { label: 'Risk Categories', value: analytics.risk_distribution.length, icon: AlertTriangle, color: 'text-amber-600', bg: 'bg-amber-50' },
              { label: 'Localities Covered', value: analytics.locality_distribution.length, icon: MapIcon, color: 'text-emerald-600', bg: 'bg-emerald-50' },
              { label: 'Recent Predictions', value: analytics.recent_predictions?.length ?? 0, icon: Clock, color: 'text-indigo-600', bg: 'bg-indigo-50' },
            ].map(({ label, value, icon: Icon, color, bg }) => (
              <div key={label} className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5">
                <div className={`h-10 w-10 rounded-xl ${bg} flex items-center justify-center mb-3`}><Icon className={`h-5 w-5 ${color}`} /></div>
                <div className="text-2xl font-extrabold text-slate-900">{value}</div>
                <p className="text-xs text-slate-400 font-medium mt-1">{label}</p>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5">
              <h3 className="text-base font-bold text-slate-900 mb-4">Risk Level Distribution</h3>
              {analytics.risk_distribution.length === 0 ? <p className="text-xs text-slate-400">No risk distribution data.</p> : (
                <div className="space-y-3">
                  {analytics.risk_distribution.map(r => (
                    <div key={r.risk_level}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className={`font-bold ${riskColor(r.risk_level)}`}>{r.risk_level}</span>
                        <span className="font-bold text-slate-900">{r.count} prediction{r.count !== 1 ? 's' : ''}</span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-2">
                        <div className={`h-2 rounded-full transition-all ${r.risk_level.toLowerCase().includes('high') ? 'bg-red-500' : r.risk_level.toLowerCase().includes('medium') || r.risk_level.toLowerCase().includes('moderate') ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${(r.count / maxRisk) * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs p-5">
              <h3 className="text-base font-bold text-slate-900 mb-4">Locality Distribution</h3>
              {analytics.locality_distribution.length === 0 ? <p className="text-xs text-slate-400">No locality data.</p> : (
                <div className="space-y-3">
                  {analytics.locality_distribution.map(l => (
                    <div key={l.locality}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="font-bold text-slate-700">{l.locality}</span>
                        <span className="font-bold text-slate-900">{l.count}</span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-2">
                        <div className="h-2 rounded-full bg-blue-500 transition-all" style={{ width: `${(l.count / maxLocality) * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          {analytics.recent_predictions && analytics.recent_predictions.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-100"><h3 className="text-base font-bold text-slate-900">Recent Predictions</h3></div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200/80">
                    {['ID', 'Locality', 'Risk Level', 'Risk %', 'Confidence', 'Created'].map(h => (
                      <th key={h} className="text-left px-5 py-3 text-xs font-extrabold uppercase tracking-wider text-slate-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {analytics.recent_predictions.map(p => (
                    <tr key={p.id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="px-5 py-3 text-xs text-slate-400 font-mono">#{p.id}</td>
                      <td className="px-5 py-3 text-xs font-bold text-slate-900">{p.locality}</td>
                      <td className="px-5 py-3"><span className={`px-2 py-0.5 rounded-full text-xs font-bold ${riskBadge(p.risk_level)}`}>{p.risk_level}</span></td>
                      <td className="px-5 py-3 text-xs font-bold text-slate-900">{p.estimated_risk_percent}%</td>
                      <td className="px-5 py-3 text-xs font-bold text-slate-900">{p.confidence_score}%</td>
                      <td className="px-5 py-3 text-xs text-slate-400">{timeAgo(p.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ─── Persisted prediction records ───────────────────────────────────────────
function PredictionsView() {
  const [rows, setRows] = useState<AdminPrediction[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  useEffect(() => { adminApi.getPredictions().then(r => setRows(r.predictions)).catch(console.error).finally(() => setLoading(false)) }, [])
  const filtered = rows.filter(r => `${r.locality} ${r.risk_level} ${r.user_id}`.toLowerCase().includes(query.toLowerCase()))
  return <div className="space-y-5">
    <div className="flex items-center justify-between"><div><h2 className="text-2xl font-extrabold text-slate-900">Prediction Records</h2><p className="text-sm text-slate-500 mt-0.5">Persisted Far North citizen prediction requests</p></div><div className="relative"><Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search locality or risk..." className="pl-10 pr-4 py-2 bg-white border border-slate-200 rounded-xl text-xs text-slate-700 w-64 focus:outline-none focus:ring-2 focus:ring-blue-500/30" /></div></div>
    {loading ? <div className="flex items-center gap-2 text-slate-400 py-8"><RefreshCw className="h-5 w-5 animate-spin" />Loading predictions...</div> : filtered.length === 0 ? <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center"><Bot className="h-10 w-10 text-slate-300 mx-auto mb-3" /><p className="text-slate-500 font-medium">No persisted prediction records found.</p></div> : <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden"><table className="w-full text-sm"><thead className="bg-slate-50 border-b border-slate-200"><tr>{['ID','Locality','Risk','Estimated risk','Confidence','User','Created'].map(h => <th key={h} className="text-left px-5 py-3 text-xs font-extrabold uppercase tracking-wider text-slate-500">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">{filtered.map(r => <tr key={r.id} className="hover:bg-slate-50"><td className="px-5 py-3 text-xs text-slate-400">#{r.id}</td><td className="px-5 py-3 font-bold text-slate-900">{r.locality}</td><td className="px-5 py-3"><span className={`px-2 py-0.5 rounded-full text-xs font-bold ${riskBadge(r.risk_level)}`}>{r.risk_level}</span></td><td className="px-5 py-3 font-bold text-slate-900">{r.estimated_risk_percent}%</td><td className="px-5 py-3">{r.confidence_score}%</td><td className="px-5 py-3 text-xs text-slate-500 max-w-[160px] truncate">{r.user_id}</td><td className="px-5 py-3 text-xs text-slate-400">{timeAgo(r.created_at)}</td></tr>)}</tbody></table></div>}
  </div>
}

// ─── Risk map and zones use persisted backend records only ───────────────────
function RiskMapView({ isClient }: { isClient: boolean }) {
  const [predictions, setPredictions] = useState<AdminPrediction[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => { adminApi.getPredictions().then(r => setPredictions(r.predictions)).catch(console.error).finally(() => setLoading(false)) }, [])
  const mapped = predictions.filter(p => typeof p.details?.risk?.coordinates?.lat === 'number' && typeof p.details?.risk?.coordinates?.lon === 'number')
  return <div className="space-y-5"><div><h2 className="text-2xl font-extrabold text-slate-900">Far North Flood Risk Map</h2><p className="text-sm text-slate-500 mt-0.5">Only coordinates persisted with real prediction records are shown.</p></div><div className="bg-white rounded-2xl border border-slate-200 p-4 h-[560px]">{loading ? <div className="h-full flex items-center justify-center text-slate-400"><RefreshCw className="h-5 w-5 animate-spin mr-2" />Loading map records...</div> : isClient ? <MapContainer center={[11.5, 14.8]} zoom={7} scrollWheelZoom className="h-full w-full rounded-xl"><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />{mapped.map(p => { const c = p.details?.risk?.coordinates; return <Marker key={p.id} position={[c.lat, c.lon]} icon={createCustomIcon('#2563EB', p.locality)}><Popup><strong>{p.locality}</strong><br />{p.risk_level} risk ({p.estimated_risk_percent}%)<br /><small>Persisted prediction #{p.id}</small></Popup></Marker> })}<div className="absolute z-[1000] bottom-5 left-5 bg-white/95 border border-slate-200 rounded-xl px-3 py-2 text-xs text-slate-600">{mapped.length ? `${mapped.length} persisted prediction coordinate${mapped.length === 1 ? '' : 's'}` : 'No persisted prediction coordinates available.'}</div></MapContainer> : null}</div></div>
}

function ZonesView() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => { adminApi.getAlerts().then(r => setAlerts(r.alerts)).catch(console.error).finally(() => setLoading(false)) }, [])
  return <div className="space-y-5"><div><h2 className="text-2xl font-extrabold text-slate-900">Flood-Prone Zones</h2><p className="text-sm text-slate-500 mt-0.5">Active zones are shown only when an alert is persisted by the backend.</p></div>{loading ? <div className="text-slate-400 py-8"><RefreshCw className="h-5 w-5 animate-spin inline mr-2" />Loading zones...</div> : alerts.length === 0 ? <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center"><AlertTriangle className="h-10 w-10 text-slate-300 mx-auto mb-3" /><p className="text-slate-500 font-medium">No active flood-prone zone alerts.</p><p className="text-xs text-slate-400 mt-1">The system has no current persisted alerts for Far North Cameroon.</p></div> : <div className="grid gap-4">{alerts.map(a => <div key={a.alert_id} className="bg-white rounded-2xl border border-red-200 p-5"><div className="flex items-center justify-between"><h3 className="font-bold text-slate-900">{a.watershed}</h3><span className="px-2 py-1 rounded-full bg-red-100 text-red-700 text-xs font-bold">{a.severity}</span></div><p className="text-sm text-slate-700 mt-2">{a.message}</p><p className="text-xs text-slate-400 mt-2">Issued {a.issued_time ? new Date(a.issued_time).toLocaleString() : '—'} · Source: {a.data_source || 'recorded alert'}</p></div>)}</div>}</div>
}

// ─── Settings view ────────────────────────────────────────────────────────────
function SettingsView() {
  return (
    <div className="space-y-5">
      <div><h2 className="text-2xl font-extrabold text-slate-900">System Settings</h2><p className="text-sm text-slate-500 mt-0.5">Administrator configuration and system preferences</p></div>
      <div className="bg-white rounded-2xl border border-slate-200/80 p-8 text-center">
        <Settings className="h-10 w-10 text-slate-300 mx-auto mb-3" />
        <p className="text-slate-500 font-medium">Settings management coming soon.</p>
        <p className="text-xs text-slate-400 mt-1">System configuration options will be available in a future release.</p>
      </div>
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function AdminDashboardPage() {
  const navigate = useNavigate()
  const { tab } = useParams<{ tab?: string }>()
  const normalizeTab = (value?: string) => value === 'flood-risk-map' ? 'map' : value === 'flood-prone-zones' ? 'zones' : (value ?? 'dashboard')
  const [activeTab, setActiveTab] = useState(normalizeTab(tab))
  const [mapZoom, setMapZoom] = useState(7)
  const [isClient, setIsClient] = useState(false)
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [overviewLoading, setOverviewLoading] = useState(true)
  const previousOverview = useRef<AdminOverview | null>(null)
  const [adminNotice, setAdminNotice] = useState<{ kind: 'report' | 'feedback'; count: number } | null>(null)
  const [showNotifications, setShowNotifications] = useState(false)

  useEffect(() => { const next = normalizeTab(tab); if (next !== activeTab) setActiveTab(next) }, [tab, activeTab])

  useEffect(() => {
    const handler = (e: CustomEvent<string>) => switchTab(e.detail)
    window.addEventListener('admin-tab', handler as EventListener)
    return () => window.removeEventListener('admin-tab', handler as EventListener)
  }, [])

  const refreshOverview = useCallback((showLoading = false) => {
    if (showLoading) setOverviewLoading(true)
    adminApi.getOverview().then(next => {
      const previous = previousOverview.current
      if (previous) {
        const newReports = Math.max(0, (next.reports_submitted ?? 0) - (previous.reports_submitted ?? 0))
        const newFeedback = Math.max(0, (next.feedback_submissions ?? 0) - (previous.feedback_submissions ?? 0))
        if (newReports > 0) setAdminNotice({ kind: 'report', count: newReports })
        else if (newFeedback > 0) setAdminNotice({ kind: 'feedback', count: newFeedback })
      }
      previousOverview.current = next
      setOverview(next)
    }).catch(console.error).finally(() => { if (showLoading) setOverviewLoading(false) })
  }, [])

  useEffect(() => {
    refreshOverview(true)
    const poll = window.setInterval(() => refreshOverview(), 15000)
    return () => window.clearInterval(poll)
  }, [refreshOverview])

  useEffect(() => {
    if (!adminNotice) return
    const dismiss = window.setTimeout(() => setAdminNotice(null), 7000)
    return () => window.clearTimeout(dismiss)
  }, [adminNotice])

  useEffect(() => { setIsClient(true) }, [])

  const switchTab = useCallback((t: string) => {
    setActiveTab(t)
    if (t === 'dashboard') navigate('/admin-dashboard', { replace: true })
    else navigate(`/admin-dashboard/${t === 'map' ? 'flood-risk-map' : t === 'zones' ? 'flood-prone-zones' : t}`, { replace: true })
  }, [navigate])

  let adminName = 'Administrator'
  try {
    const u = JSON.parse(localStorage.getItem('aquaguard_user') || 'null')
    if (u?.email) adminName = u.email.split('@')[0]
    else if (u?.name) adminName = u.name
    else if (u?.username) adminName = u.username
  } catch { /* ignore */ }

  const tabTitle: Record<string, string> = {
    dashboard: 'Administrator Dashboard',
    users: 'Manage Users',
    reports: 'Community Reports',
    notifications: 'Notifications & Feedback',
    datasets: 'Operational Datasets',
    analytics: 'Prediction Analytics',
    predictions: 'Prediction Records',
    map: 'Far North Flood Risk Map',
    zones: 'Flood-Prone Zones',
    settings: 'System Settings',
  }

  return (
    <div className="flex h-screen w-full bg-[#F4F6F9] overflow-hidden font-sans text-slate-800">
      {adminNotice && (
        <div role="status" aria-live="polite" className="fixed right-6 top-20 z-[100] w-[min(370px,calc(100vw-2rem))] rounded-2xl border border-blue-200 bg-white p-4 shadow-2xl shadow-blue-900/15">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-full bg-blue-100 p-2 text-blue-700"><Bell className="h-4 w-4" /></div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-extrabold text-slate-900">New citizen {adminNotice.kind} received</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">{adminNotice.count} new {adminNotice.kind}{adminNotice.count === 1 ? '' : 's'} {adminNotice.kind === 'report' ? 'awaiting review.' : 'submitted on a prediction.'}</p>
              <button type="button" onClick={() => switchTab(adminNotice.kind === 'report' ? 'reports' : 'notifications')} className="mt-2 text-xs font-bold text-blue-700 hover:text-blue-900">Open {adminNotice.kind === 'report' ? 'community reports' : 'feedback'} →</button>
            </div>
            <button type="button" aria-label="Dismiss notification" onClick={() => setAdminNotice(null)} className="text-lg leading-none text-slate-400 hover:text-slate-700">×</button>
          </div>
        </div>
      )}
      {/* SIDEBAR */}
      <aside className="w-64 bg-white flex flex-col h-full border-r border-slate-200 shadow-sm select-none z-20 flex-shrink-0">
        <div className="px-5 py-5 flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-blue-500/20"><Shield className="h-5 w-5" /></div>
          <div>
            <h1 className="text-slate-900 font-extrabold text-base tracking-tight leading-none">AquaGuard AI</h1>
            <p className="text-[10px] font-bold text-slate-500 tracking-wider uppercase mt-1">Cameroon Flood Intelligence</p>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-5 scrollbar-none">
          <div>
            <div className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Overview</div>
            <SidebarBtn icon={LayoutDashboard} label="Dashboard" tabKey="dashboard" activeTab={activeTab} onClick={() => switchTab('dashboard')} />
          </div>
          <div>
            <div className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Flood Intelligence</div>
            <div className="space-y-1">
              <SidebarBtn icon={Bot} label="Predictions" tabKey="predictions" activeTab={activeTab} onClick={() => switchTab('predictions')} />
              <SidebarBtn icon={MapIcon} label="Flood Risk Map" tabKey="map" activeTab={activeTab} onClick={() => switchTab('map')} />
              <SidebarBtn icon={AlertTriangle} label="Flood-Prone Zones" tabKey="zones" activeTab={activeTab} onClick={() => switchTab('zones')} />
            </div>
          </div>
          <div>
            <div className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Data &amp; Reports</div>
            <div className="space-y-1">
              <SidebarBtn icon={Database} label="Datasets" tabKey="datasets" activeTab={activeTab} onClick={() => switchTab('datasets')} />
              <SidebarBtn icon={MessageSquare} label="Community Reports" tabKey="reports" activeTab={activeTab} onClick={() => switchTab('reports')} />
            </div>
          </div>
          <div>
            <div className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Management</div>
            <div className="space-y-1">
              <SidebarBtn icon={Users} label="Users" tabKey="users" activeTab={activeTab} onClick={() => switchTab('users')} />
              <SidebarBtn icon={LineChart} label="Analytics" tabKey="analytics" activeTab={activeTab} onClick={() => switchTab('analytics')} />
            </div>
          </div>
          <div>
            <div className="px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">System</div>
            <div className="space-y-1">
              <SidebarBtn icon={Bell} label="Notifications" tabKey="notifications" activeTab={activeTab} onClick={() => switchTab('notifications')} />
              <SidebarBtn icon={Settings} label="Settings" tabKey="settings" activeTab={activeTab} onClick={() => switchTab('settings')} />
            </div>
          </div>
        </div>

        <div className="p-3 mt-auto">
          <div className="bg-slate-50 border border-slate-200 rounded-2xl p-3.5 flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="h-10 w-10 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-extrabold text-sm shadow">{adminName.charAt(0).toUpperCase()}</div>
                <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-emerald-500 ring-2 ring-slate-50" />
              </div>
              <div className="flex flex-col overflow-hidden">
                <span className="text-sm font-bold text-slate-900 leading-tight truncate">{adminName}</span>
                <span className="text-xs text-slate-500 truncate">Administrator</span>
              </div>
            </div>
            <button onClick={() => { localStorage.removeItem('aquaguard_user'); navigate('/login') }} className="w-full py-2 bg-white border border-slate-200 hover:bg-slate-100 text-slate-600 hover:text-slate-900 text-xs font-semibold rounded-xl flex items-center justify-center gap-2 transition-all cursor-pointer">
              <LogOut className="h-3.5 w-3.5" /><span>Log out</span>
            </button>
          </div>
        </div>
      </aside>

      {/* MAIN */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        <header className="bg-white border-b border-slate-200/80 px-8 py-3.5 flex items-center justify-between flex-shrink-0 shadow-xs z-10">
          <div>
            <h2 className="text-lg font-bold text-slate-900 leading-tight">{tabTitle[activeTab] ?? 'Administrator Dashboard'}</h2>
            <p className="text-xs text-slate-500 font-medium">Cameroon Flood Intelligence Platform — Far North Region</p>
          </div>
          <div className="flex items-center gap-5">
            <div className="relative w-80">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <input type="text" placeholder="Search reports, users, datasets..." className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-full text-xs font-medium text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all" />
            </div>
            <div className="relative">
              <button type="button" aria-label="Open notifications" onClick={() => setShowNotifications(prev => !prev)} className="relative p-2 rounded-full hover:bg-slate-100 text-slate-600 transition-all cursor-pointer">
                <Bell className="h-5 w-5" />
                {!overviewLoading && ((overview?.pending_reports ?? 0) + (overview?.feedback_submissions ?? 0)) > 0 && (
                  <span className="absolute top-1 right-1 h-4 w-4 bg-red-500 text-white text-[10px] font-extrabold rounded-full flex items-center justify-center shadow-xs">{(overview?.pending_reports ?? 0) + (overview?.feedback_submissions ?? 0)}</span>
                )}
              </button>
              {showNotifications && (
                <div className="absolute right-0 top-11 z-[90] w-80 rounded-2xl border border-slate-200 bg-white p-4 shadow-2xl">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                    <h3 className="text-sm font-extrabold text-slate-900">Notifications</h3>
                    <span className="text-[10px] font-semibold text-slate-400">Live updates</span>
                  </div>
                  <div className="max-h-72 overflow-y-auto py-2">
                    {(overview?.activity ?? []).filter(item => item.type === 'report' || item.type === 'feedback').slice(0, 8).map((item, index) => (
                      <button type="button" key={`${item.type}-${item.timestamp ?? index}`} onClick={() => { setShowNotifications(false); switchTab(item.type === 'report' ? 'reports' : 'notifications') }} className="flex w-full items-start gap-3 rounded-xl px-2 py-3 text-left hover:bg-slate-50">
                        <span className={`mt-1 h-2 w-2 flex-shrink-0 rounded-full ${item.type === 'report' ? 'bg-blue-600' : 'bg-amber-500'}`} />
                        <span className="min-w-0"><span className="block text-xs font-semibold leading-relaxed text-slate-700">{item.message}</span><span className="mt-1 block text-[10px] text-slate-400">{item.timestamp ? timeAgo(item.timestamp) : 'Recently'}</span></span>
                      </button>
                    ))}
                    {(overview?.activity ?? []).filter(item => item.type === 'report' || item.type === 'feedback').length === 0 && <p className="px-2 py-5 text-center text-xs text-slate-400">No report or feedback notifications yet.</p>}
                  </div>
                  <div className="border-t border-slate-100 pt-2 text-[10px] text-slate-400">New submissions are checked automatically every 15 seconds.</div>
                </div>
              )}
            </div>
            <div className="flex items-center gap-3 pl-3 border-l border-slate-200">
              <div className="text-right">
                <p className="text-xs font-bold text-slate-900 leading-tight">{adminName}</p>
                <p className="text-[10px] text-slate-500 font-medium">Administrator</p>
              </div>
              <div className="h-9 w-9 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-extrabold text-sm shadow">{adminName.charAt(0).toUpperCase()}</div>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin scrollbar-thumb-slate-300">
          {activeTab === 'dashboard' && <DashboardView overview={overview} loading={overviewLoading} mapZoom={mapZoom} setMapZoom={setMapZoom} isClient={isClient} />}
          {activeTab === 'users' && <UsersView />}
          {activeTab === 'reports' && <ReportsView />}
          {activeTab === 'notifications' && <NotificationsView />}
          {activeTab === 'datasets' && <DatasetsView />}
          {activeTab === 'predictions' && <PredictionsView />}
          {activeTab === 'map' && <RiskMapView isClient={isClient} />}
          {activeTab === 'zones' && <ZonesView />}
          {activeTab === 'analytics' && <AnalyticsView />}
          {activeTab === 'settings' && <SettingsView />}
        </main>
      </div>
    </div>
  )
}
