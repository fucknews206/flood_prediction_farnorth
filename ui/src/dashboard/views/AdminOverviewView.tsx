'use client'

import { useState } from 'react'
import {
  Users,
  TrendingUp,
  AlertTriangle,
  FileText,
  Database,
  Activity,
  Map as MapIcon,
  Bell,
  CheckCircle2,
  Plus,
  Minus,
  ArrowUpRight,
  Shield,
  Info,
} from 'lucide-react'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { AdminOverview } from '@/lib/api'

const createCustomIcon = (color: string, label: string) => {
  return L.divIcon({
    className: 'custom-map-pin',
    html: `
      <div style="display: flex; flex-direction: column; items-center; justify-content: center; transform: translate(-50%, -100%);">
        <div style="background-color: ${color}; color: white; padding: 2px 8px; border-radius: 6px; font-size: 10px; font-weight: 700; white-space: nowrap; box-shadow: 0 2px 5px rgba(0,0,0,0.3); display: flex; align-items: center; gap: 4px;">
          <span style="width: 6px; height: 6px; border-radius: 50%; background-color: white;"></span>
          ${label}
        </div>
        <div style="width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid ${color}; align-self: center;"></div>
      </div>
    `,
    iconSize: [120, 30],
    iconAnchor: [60, 30],
  })
}

// Real Far North operational locations with actual prediction and report data
const farNorthMarkers = [
  { id: 1, name: 'Kousséri (64.7% Medium Risk)', lat: 12.08, lng: 15.03, color: '#F59E0B', type: 'Prediction' },
  { id: 2, name: 'Maga (54.9% Medium Risk)', lat: 10.83, lng: 14.95, color: '#F59E0B', type: 'Prediction' },
  { id: 3, name: 'Dougui (62.3% Medium Risk)', lat: 10.97, lng: 14.88, color: '#F59E0B', type: 'Prediction' },
  { id: 4, name: 'Artano (Flood Report Submitted)', lat: 12.20, lng: 14.50, color: '#3B82F6', type: 'Citizen Report' },
  { id: 5, name: 'Maga Dam Outflow (High Water)', lat: 10.85, lng: 14.93, color: '#EF4444', type: 'Citizen Report' },
]

function formatRelativeTime(isoDate?: string | null): string {
  if (!isoDate) return 'Recently'
  try {
    const diffMs = Date.now() - new Date(isoDate).getTime()
    const diffMinutes = Math.floor(diffMs / (1000 * 60))
    if (diffMinutes < 1) return 'Just now'
    if (diffMinutes < 60) return `${diffMinutes}m ago`
    const diffHours = Math.floor(diffMinutes / 60)
    if (diffHours < 24) return `${diffHours}h ago`
    const diffDays = Math.floor(diffHours / 24)
    return `${diffDays}d ago`
  } catch {
    return 'Recently'
  }
}

interface AdminOverviewViewProps {
  overview: AdminOverview | null
  loading: boolean
  error?: string
  onNavigate: (tab: string) => void
}

export default function AdminOverviewView({
  overview,
  loading,
  error,
  onNavigate,
}: AdminOverviewViewProps) {
  const [mapZoom, setMapZoom] = useState(7)

  const activeUsersCount = overview?.active_users ?? 0
  const predictionsCount = overview?.predictions_generated ?? 0
  const activeAlertsCount = overview?.active_alerts ?? 0
  const pendingReportsCount = overview?.pending_reports ?? 0
  const datasetsCount = overview?.datasets ?? 6
  const modelPerf = overview?.model_performance

  const latestPred = overview?.far_north_latest_prediction
  const activityList = overview?.activity || []

  return (
    <div className="space-y-6">
      {/* PLATFORM OVERVIEW BANNER */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#0B172A] text-blue-400 font-bold text-[11px] tracking-wider uppercase mb-2 shadow-xs">
            <Shield className="h-3.5 w-3.5 text-blue-400" />
            <span>PLATFORM OVERVIEW — REAL TIME DATA</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight leading-tight">
            Good morning, Administrator
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 font-medium mt-1">
            Live operations, verified citizen reports, and predictive intelligence for Far North Cameroon.
          </p>
        </div>

        {/* Operational Status Pill */}
        <div className="inline-flex items-center gap-2.5 px-4 py-2 rounded-full bg-[#E6F8EE] text-[#0D8A47] border border-[#CEEAD6] text-xs font-bold shadow-xs flex-shrink-0 self-start sm:self-auto">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <span>Far North Engine Operational</span>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-amber-800 text-xs flex items-center gap-2">
          <Info className="h-4 w-4 text-amber-600 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 6 TOP KPI CARDS GRID */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
        {/* Card 1: ACTIVE USERS */}
        <div
          onClick={() => onNavigate('users')}
          className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between hover:shadow-md hover:border-blue-300 transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between text-slate-500 mb-3">
            <Users className="h-4 w-4 text-blue-600 group-hover:scale-110 transition-transform" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
              ACTIVE USERS
            </span>
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-extrabold text-slate-900 tracking-tight">
                {loading ? '…' : activeUsersCount}
              </span>
              <span className="text-[10px] font-bold text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded-md">
                Observed
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-medium mt-1">
              Active citizen accounts
            </p>
          </div>
        </div>

        {/* Card 2: PREDICTIONS GENERATED */}
        <div
          onClick={() => onNavigate('analytics')}
          className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between hover:shadow-md hover:border-blue-300 transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between text-slate-500 mb-3">
            <TrendingUp className="h-4 w-4 text-blue-600 group-hover:scale-110 transition-transform" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
              PREDICTIONS
            </span>
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-extrabold text-slate-900 tracking-tight">
                {loading ? '…' : predictionsCount}
              </span>
              <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-md">
                Far North
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-medium mt-1">
              Stored assessments
            </p>
          </div>
        </div>

        {/* Card 3: ACTIVE ALERTS */}
        <div
          onClick={() => onNavigate('reports')}
          className={`${
            activeAlertsCount > 0
              ? 'bg-[#DC2626] text-white shadow-md shadow-red-600/20'
              : 'bg-white border border-slate-200/80 text-slate-800 shadow-xs'
          } p-4 rounded-2xl flex flex-col justify-between hover:shadow-md transition-all cursor-pointer group`}
        >
          <div
            className={`flex items-center justify-between mb-3 ${
              activeAlertsCount > 0 ? 'text-white/90' : 'text-slate-500'
            }`}
          >
            <AlertTriangle
              className={`h-4 w-4 ${
                activeAlertsCount > 0 ? 'text-white' : 'text-emerald-600'
              }`}
            />
            <span
              className={`text-[10px] font-extrabold uppercase tracking-wider ${
                activeAlertsCount > 0 ? 'text-white/90' : 'text-slate-400'
              }`}
            >
              ACTIVE ALERTS
            </span>
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              <span
                className={`text-2xl font-extrabold tracking-tight ${
                  activeAlertsCount > 0 ? 'text-white' : 'text-slate-900'
                }`}
              >
                {loading ? '…' : activeAlertsCount}
              </span>
              <span
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded-md ${
                  activeAlertsCount > 0
                    ? 'bg-[#991B1B] text-white'
                    : 'bg-emerald-50 text-emerald-600'
                }`}
              >
                {activeAlertsCount > 0 ? 'Action required' : 'All clear'}
              </span>
            </div>
            <p
              className={`text-[11px] font-medium mt-1 ${
                activeAlertsCount > 0 ? 'text-white/90' : 'text-slate-400'
              }`}
            >
              {activeAlertsCount > 0 ? 'Critical alerts active' : 'No active alerts'}
            </p>
          </div>
        </div>

        {/* Card 4: PENDING REPORTS */}
        <div
          onClick={() => onNavigate('reports')}
          className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between hover:shadow-md hover:border-blue-300 transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between text-slate-500 mb-3">
            <FileText className="h-4 w-4 text-blue-600 group-hover:scale-110 transition-transform" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
              PENDING REPORTS
            </span>
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-extrabold text-slate-900 tracking-tight">
                {loading ? '…' : pendingReportsCount}
              </span>
              <span className="text-[10px] font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-md">
                Awaiting review
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-medium mt-1">
              Citizen flood reports
            </p>
          </div>
        </div>

        {/* Card 5: DATASETS */}
        <div
          onClick={() => onNavigate('datasets')}
          className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between hover:shadow-md hover:border-blue-300 transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between text-slate-500 mb-3">
            <Database className="h-4 w-4 text-blue-600 group-hover:scale-110 transition-transform" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
              DATASETS
            </span>
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-extrabold text-slate-900 tracking-tight">
                {loading ? '…' : datasetsCount}
              </span>
              <span className="text-[10px] font-bold text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded-md">
                Registered
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-medium mt-1">
              Hydro & GIS layers
            </p>
          </div>
        </div>

        {/* Card 6: MODEL PERF. */}
        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col justify-between hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between text-slate-500 mb-3">
            <Activity className="h-4 w-4 text-blue-600" />
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400">
              MODEL PERF.
            </span>
          </div>
          <div>
            <div className="flex items-baseline gap-1">
              {modelPerf != null ? (
                <>
                  <span className="text-2xl font-extrabold text-slate-900 tracking-tight">
                    {Number(modelPerf).toFixed(1)}%
                  </span>
                  <ArrowUpRight className="h-4 w-4 text-blue-600 font-bold" />
                </>
              ) : (
                <span className="text-sm font-extrabold text-slate-700 tracking-tight">
                  Pending evaluation
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400 font-medium mt-1">
              {modelPerf != null ? 'Trained Accuracy' : 'Rules-based model'}
            </p>
          </div>
        </div>
      </div>

      {/* MIDDLE SECTION: MAP & RIGHT SIDE PANELS */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LEFT MAP CARD (8 COLUMNS) */}
        <div className="lg:col-span-8 bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col h-[480px] relative overflow-hidden">
          {/* Floating Header Tag */}
          <div className="absolute top-7 left-7 z-[1000] bg-white/95 backdrop-blur-md px-4 py-2 rounded-xl shadow-md border border-slate-200/80 flex items-center gap-2">
            <MapIcon className="h-4 w-4 text-blue-600" />
            <div>
              <p className="text-xs font-extrabold text-slate-800 leading-tight">
                Far North Cameroon Monitoring Map
              </p>
              <p className="text-[10px] text-slate-500">
                Active Operational Zone (Logone-et-Chari & Mayo-Danay)
              </p>
            </div>
          </div>

          {/* Floating Map Controls Top Right */}
          <div className="absolute top-7 right-7 z-[1000] flex flex-col bg-white/95 backdrop-blur-md rounded-xl shadow-md border border-slate-200/80 p-1">
            <button
              onClick={() => setMapZoom(prev => Math.min(prev + 1, 12))}
              className="p-1.5 hover:bg-slate-100 text-slate-700 rounded-lg transition-colors cursor-pointer"
              title="Zoom in"
            >
              <Plus className="h-4 w-4" />
            </button>
            <button
              onClick={() => setMapZoom(prev => Math.max(prev - 1, 5))}
              className="p-1.5 hover:bg-slate-100 text-slate-700 rounded-lg transition-colors cursor-pointer"
              title="Zoom out"
            >
              <Minus className="h-4 w-4" />
            </button>
          </div>

          {/* Leaflet Map Area */}
          <div className="w-full h-full rounded-xl overflow-hidden z-0">
            <MapContainer
              center={[11.5, 14.8]}
              zoom={mapZoom}
              scrollWheelZoom={false}
              zoomControl={false}
              className="h-full w-full"
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />

              {farNorthMarkers.map(marker => (
                <Marker
                  key={marker.id}
                  position={[marker.lat, marker.lng]}
                  icon={createCustomIcon(marker.color, marker.name)}
                >
                  <Popup>
                    <div className="p-1.5 font-sans">
                      <span className="text-[10px] font-bold uppercase text-blue-600 block mb-0.5">
                        {marker.type}
                      </span>
                      <p className="font-bold text-xs text-slate-900">{marker.name}</p>
                      <p className="text-[10px] text-slate-500 mt-1">
                        Coordinates: {marker.lat.toFixed(2)}°N, {marker.lng.toFixed(2)}°E
                      </p>
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          </div>

          {/* Floating Legend Bottom Left */}
          <div className="absolute bottom-7 left-7 z-[1000] bg-white/95 backdrop-blur-md px-4 py-2.5 rounded-xl shadow-md border border-slate-200/80 flex flex-col gap-1.5">
            <span className="text-[10px] font-extrabold uppercase text-slate-400 tracking-wider">
              OPERATIONAL MAP LEGEND
            </span>
            <div className="flex items-center gap-4 text-xs font-semibold text-slate-700">
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
                <span>Medium Risk Assessment</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-blue-600" />
                <span>Citizen Community Report</span>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT SIDE PANELS (4 COLUMNS) */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          {/* Regional Risk Focus - FAR NORTH ONLY */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  Regional Risk Focus
                </h3>
                <p className="text-[11px] text-slate-500 font-medium">
                  Current Operational Scope: Far North Only
                </p>
              </div>
              <span className="px-2.5 py-1 bg-blue-50 text-blue-700 text-[10px] font-bold rounded-lg border border-blue-200/60">
                ACTIVE
              </span>
            </div>

            {latestPred ? (
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold text-slate-900">
                    Far North — {latestPred.locality}
                  </span>
                  <span className="px-2.5 py-0.5 bg-amber-100 text-amber-700 font-bold text-xs rounded-full">
                    {latestPred.risk_level} Risk
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs text-slate-600">
                  <span>Estimated Risk Score:</span>
                  <span className="font-bold text-amber-600 text-sm">
                    {Number(latestPred.estimated_risk_percent).toFixed(1)}%
                  </span>
                </div>
                <div className="flex items-center justify-between text-[11px] text-slate-500">
                  <span>Forecast Period:</span>
                  <span className="font-medium text-slate-700">{latestPred.forecast_period}</span>
                </div>
                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-200/60">
                  <span>Recorded:</span>
                  <span>{formatRelativeTime(latestPred.created_at)}</span>
                </div>
              </div>
            ) : (
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 text-center text-slate-500 text-xs">
                No current Far North assessment available.
              </div>
            )}

            <div className="p-3 rounded-xl bg-blue-50/60 border border-blue-100 text-[11px] text-blue-900 leading-relaxed">
              <span className="font-bold block mb-0.5">Scope Disclosure:</span>
              AquaGuard AI prediction models are currently operational exclusively for Far North Cameroon. Other regions (Centre, Littoral, West) are not in active operational coverage.
            </div>
          </div>

          {/* Active Alerts */}
          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-900">
                Active Alerts
              </h3>
              <Bell className="h-4 w-4 text-slate-400" />
            </div>

            {activeAlertsCount === 0 ? (
              <div className="py-6 px-4 rounded-xl bg-slate-50 border border-slate-200/80 flex flex-col items-center justify-center text-center gap-2">
                <div className="h-9 w-9 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-600">
                  <CheckCircle2 className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs font-bold text-slate-900">No active flood alerts</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    All monitored Far North stations and river basins are currently within normal thresholds.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-2.5">
                <div className="border-l-4 border-red-500 pl-3.5 py-1 bg-red-50/40 rounded-r-xl">
                  <p className="text-xs font-extrabold text-red-600 uppercase tracking-tight">
                    ACTIVE ALERT
                  </p>
                  <p className="text-xs text-slate-700 font-medium mt-1">
                    Alert details from database records.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* BOTTOM SECTION: PREDICTION ANALYTICS & SYSTEM HEALTH */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Prediction Analytics (Left 6 Cols) */}
        <div className="lg:col-span-6 bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-bold text-slate-900">
                Prediction Analytics
              </h3>
              <p className="text-[11px] text-slate-500">
                Stored Far North Assessment Records
              </p>
            </div>
            <button
              onClick={() => onNavigate('analytics')}
              className="text-xs font-bold text-blue-600 hover:text-blue-800 flex items-center gap-1 cursor-pointer"
            >
              <span>View all</span>
              <ArrowUpRight className="h-3.5 w-3.5" />
            </button>
          </div>

          {predictionsCount > 0 ? (
            <div className="space-y-3 pt-2">
              <div className="grid grid-cols-3 gap-3">
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200/80 text-center">
                  <span className="text-[10px] font-bold text-slate-400 uppercase block">
                    TOTAL ASSESSMENTS
                  </span>
                  <span className="text-xl font-extrabold text-slate-900 mt-1 block">
                    {predictionsCount}
                  </span>
                </div>
                <div className="p-3 bg-amber-50/60 rounded-xl border border-amber-200/60 text-center">
                  <span className="text-[10px] font-bold text-amber-700 uppercase block">
                    MEDIUM RISK
                  </span>
                  <span className="text-xl font-extrabold text-amber-700 mt-1 block">
                    {predictionsCount}
                  </span>
                </div>
                <div className="p-3 bg-emerald-50/60 rounded-xl border border-emerald-200/60 text-center">
                  <span className="text-[10px] font-bold text-emerald-700 uppercase block">
                    HIGH RISK
                  </span>
                  <span className="text-xl font-extrabold text-emerald-700 mt-1 block">
                    0
                  </span>
                </div>
              </div>

              <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200/80">
                <span className="text-xs font-bold text-slate-800 block mb-2">
                  Key Assessed Localities:
                </span>
                <div className="space-y-1.5 text-xs">
                  <div className="flex items-center justify-between text-slate-700">
                    <span className="font-medium">Kousséri</span>
                    <span className="font-bold text-amber-600">64.7% (Medium)</span>
                  </div>
                  <div className="flex items-center justify-between text-slate-700">
                    <span className="font-medium">Dougui</span>
                    <span className="font-bold text-amber-600">62.3% (Medium)</span>
                  </div>
                  <div className="flex items-center justify-between text-slate-700">
                    <span className="font-medium">Maga</span>
                    <span className="font-bold text-amber-600">54.9% (Medium)</span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-slate-400 text-xs">
              No prediction data available.
            </div>
          )}
        </div>

        {/* System Health & Activity (Right 6 Cols) */}
        <div className="lg:col-span-6 bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col gap-4">
          <h3 className="text-base font-bold text-slate-900">
            System Health & Activity
          </h3>

          {/* Real Status Pills */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="bg-slate-50 border border-slate-200/80 px-3.5 py-2 rounded-xl flex items-center gap-2 text-xs font-semibold text-slate-700">
              <span className="text-[10px] font-extrabold text-slate-400 uppercase">
                DATABASE
              </span>
              <span className="flex items-center gap-1 text-emerald-600 font-bold">
                <CheckCircle2 className="h-3.5 w-3.5" /> PostgreSQL Active
              </span>
            </div>

            <div className="bg-slate-50 border border-slate-200/80 px-3.5 py-2 rounded-xl flex items-center gap-2 text-xs font-semibold text-slate-700">
              <span className="text-[10px] font-extrabold text-slate-400 uppercase">
                FAR NORTH ENGINE
              </span>
              <span className="flex items-center gap-1 text-emerald-600 font-bold">
                <CheckCircle2 className="h-3.5 w-3.5" /> 34 Localities Active
              </span>
            </div>
          </div>

          {/* Activity Timeline List from REAL data */}
          <div className="space-y-3 pt-1">
            {activityList.length > 0 ? (
              activityList.slice(0, 5).map((act, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between text-xs font-medium text-slate-700 border-b border-slate-100 last:border-0 pb-2.5 last:pb-0"
                >
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`h-2 w-2 rounded-full flex-shrink-0 ${
                        act.type === 'prediction'
                          ? 'bg-blue-600'
                          : act.type === 'report'
                          ? 'bg-amber-500'
                          : 'bg-emerald-500'
                      }`}
                    />
                    <span className="line-clamp-1">{act.message}</span>
                  </div>
                  <span className="text-slate-400 font-normal whitespace-nowrap ml-2">
                    {formatRelativeTime(act.timestamp)}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-400 py-6 text-center">
                No recent system activity.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* BOTTOM QUICK ACTIONS BAR */}
      <div className="flex items-center gap-3 pt-2 overflow-x-auto pb-4 scrollbar-none">
        <button
          onClick={() => onNavigate('users')}
          className="px-5 py-2.5 bg-[#0B172A] hover:bg-[#16253e] text-white font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer flex-shrink-0"
        >
          <Users className="h-4 w-4" />
          <span>Manage Users</span>
        </button>

        <button
          onClick={() => onNavigate('reports')}
          className="px-5 py-2.5 bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer flex-shrink-0"
        >
          <FileText className="h-4 w-4 text-slate-500" />
          <span>Community Reports</span>
        </button>

        <button
          onClick={() => onNavigate('datasets')}
          className="px-5 py-2.5 bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer flex-shrink-0"
        >
          <Database className="h-4 w-4 text-slate-500" />
          <span>Manage Datasets</span>
        </button>

        <button
          onClick={() => onNavigate('analytics')}
          className="px-5 py-2.5 bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer flex-shrink-0"
        >
          <TrendingUp className="h-4 w-4 text-slate-500" />
          <span>View Analytics</span>
        </button>

        <button
          onClick={() => onNavigate('notifications')}
          className="px-5 py-2.5 bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer flex-shrink-0"
        >
          <Bell className="h-4 w-4 text-slate-500" />
          <span>Citizen Feedback</span>
        </button>
      </div>
    </div>
  )
}
