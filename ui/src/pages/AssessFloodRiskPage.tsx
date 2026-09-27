import { Fragment, useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Droplets,
  MapPin,
  Globe,
  Bell,
  ChevronDown,
  Search,
  ArrowRight,
  ArrowLeft,
  Info,
  Layers,
  Plus,
  Minus,
  Compass,
  Mountain,
  Activity,
  ShieldCheck,
  FileCheck,
  CheckCircle2,
  AlertTriangle,
  CloudRain,
  Droplet,
  Waves,
  TreePine,
  Edit2,
  Calendar,
  Clock,
  Send,
  Download,
  Bot,
  Home,
  TrendingUp,
  Gauge,
  LoaderCircle,
  Radar
} from 'lucide-react'
import { MapContainer, TileLayer, Marker, Tooltip, GeoJSON, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { farNorthRiskApi, geoApi, userPredictionsApi, aiApi, type GeoJSONFeatureCollection } from '@/lib/api'
import { assessmentDraftKey, getSession } from '@/lib/session'

// Custom Leaflet Pin Icon
const customIcon = new L.Icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
})

// Custom zoom controller for map
function MapControls() {
  const map = useMap()
  return (
    <div className="absolute bottom-4 right-4 z-[1000] flex flex-col gap-1.5 bg-white rounded-xl shadow-lg border border-slate-200 overflow-hidden p-1">
      <button
        onClick={() => map.zoomIn()}
        className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-700 hover:bg-slate-100 transition-colors"
        title="Zoom In"
      >
        <Plus className="w-4 h-4" />
      </button>
      <button
        onClick={() => map.zoomOut()}
        className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-700 hover:bg-slate-100 transition-colors"
        title="Zoom Out"
      >
        <Minus className="w-4 h-4" />
      </button>
      <div className="w-full h-px bg-slate-200 my-0.5" />
      <button
        onClick={() => map.setZoom(13)}
        className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-700 hover:bg-slate-100 transition-colors"
        title="Reset Layer View"
      >
        <Layers className="w-4 h-4" />
      </button>
    </div>
  )
}

// ─── RainViewer Live Radar Tile Layer ────────────────────────────────────────
// Tiles are served free at:
//   https://tilecache.rainviewer.com/v2/radar/{timestamp}/256/{z}/{x}/{y}/2/1_1.png
// The manifest endpoint returns the latest 5 past frames; we use the last one.
// No API key required. Tiles update every ~2 minutes.
function RainViewerLayer() {
  const [radarBase, setRadarBase] = useState<string | null>(null)
  const setLatestFrame = (manifest: any) => {
    const past = manifest?.radar?.past ?? []
    const frame = past[past.length - 1]
    if (!frame) return
    const host = String(manifest?.host || 'https://tilecache.rainviewer.com').replace(/\/$/, '')
    setRadarBase(`${host}${frame.path || `/v2/radar/${frame.time}`}`)
  }
  useEffect(() => {
    fetch('https://api.rainviewer.com/public/weather-maps.json')
      .then(r => r.json())
      .then(setLatestFrame)
      .catch(() => {/* silently skip */})
    // Refresh every 2 minutes to pick up the latest frame
    const id = setInterval(() => {
      fetch('https://api.rainviewer.com/public/weather-maps.json')
        .then(r => r.json())
        .then(setLatestFrame)
        .catch(() => {})
    }, 120_000)
    return () => clearInterval(id)
  }, [])
  if (!radarBase) return null
  return (
    <TileLayer
      key={`rv-${radarBase}`}
      url={`${radarBase}/256/{z}/{x}/{y}/2/1_1.png`}
      attribution='&copy; <a href="https://rainviewer.com">RainViewer</a> live radar'
      opacity={0.55}
      zIndex={350}
    />
  )
}

// ─── NASA OPERA DSWx-S1 SAR Surface Water Extent Tile Layer ─────────────────
const OPERA_SAR_TILE_URL =
  'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/OPERA_L3_Dynamic_Surface_Water_Extent-Sentinel-1/default/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png'

function OperaDSWxLayer() {
  return (
    <TileLayer
      key="opera-dswx-assess"
      url={OPERA_SAR_TILE_URL}
      attribution='&copy; <a href="https://earthdata.nasa.gov">NASA GIBS</a> OPERA DSWx-S1 SAR'
      opacity={0.65}
      zIndex={360}
    />
  )
}
// ─────────────────────────────────────────────────────────────────────────────

// ─── Far North Real Risk-Zone Map ────────────────────────────────────────────
// Replaces the former hardcoded concentric circles.  Polygons come from the
// server's /api/farnorth/geo/risk-zones endpoint (Arrondissement-level GeoJSON
// computed from terrain susceptibility + verified flood-event density).
const RISK_ZONE_COLORS: Record<string, string> = {
  High: '#ef4444',
  Moderate: '#f59e0b',
  Medium: '#f59e0b',
  Low: '#22c55e',
}
function FarNorthRiskMap({ coordinates, riskLevel }: { coordinates: [number, number]; riskLevel?: string }) {
  const [zones, setZones] = useState<GeoJSONFeatureCollection | null>(null)
  const [err, setErr]     = useState<string | null>(null)
  const [showRadar, setShowRadar] = useState(true)
  const [showSAR, setShowSAR] = useState(false)
  useEffect(() => {
    geoApi.getFarNorthRiskZones()
      .then(setZones)
      .catch(e => setErr(e?.message ?? 'GeoJSON load error'))
  }, [])

  const zoneStyle = (feature: any) => {
    const r = feature?.properties?.risk_level ?? 'Low'
    const col = RISK_ZONE_COLORS[r] ?? '#22c55e'
    return { fillColor: col, fillOpacity: 0.28, color: col, weight: 1.2, opacity: 0.7 }
  }

  const onEachZone = (feature: any, layer: L.Layer) => {
    const p  = feature?.properties || {}
    const r  = p.risk_level ?? '—'
    const col = RISK_ZONE_COLORS[r] ?? '#22c55e'
    layer.bindTooltip(
      `<strong>${p.name || p.name_fr || 'Arrondissement'}</strong><br/>` +
      `Risk: <span style="color:${col};font-weight:700">${r}</span><br/>` +
      `Score: ${p.risk_score ?? '—'}/100<br/>` +
      `Historical events: ${p.historical_events ?? 0}`,
      { direction: 'top', sticky: true }
    )
  }

  const center = coordinates
  return (
    <MapContainer center={center} zoom={11} scrollWheelZoom={false} zoomControl={false} className="w-full h-full z-0">
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {showRadar && <RainViewerLayer />}
      {showSAR && <OperaDSWxLayer />}
      {zones && (
        <GeoJSON
          key="farnorth-risk-zones"
          data={zones as any}
          style={zoneStyle}
          onEachFeature={onEachZone}
        />
      )}
      <Marker position={coordinates} icon={customIcon}>
        {riskLevel && (
          <Tooltip permanent direction="top" offset={[0, -28]}>
            <span className="font-semibold text-xs">{riskLevel} Risk</span>
          </Tooltip>
        )}
      </Marker>
      {err && <div style={{ position: 'absolute', bottom: 8, left: 8, zIndex: 1000, background: '#fef3c7', color: '#92400e', fontSize: 11, padding: '2px 8px', borderRadius: 6 }}>⚠ {err}</div>}
      {/* Radar & SAR toggle buttons */}
      <div style={{ position: 'absolute', top: 8, left: 8, zIndex: 1000, display: 'flex', gap: 6 }}>
        <button
          onClick={() => setShowRadar(v => !v)}
          style={{
            background: showRadar ? 'rgba(37,99,235,0.92)' : 'rgba(255,255,255,0.92)',
            color: showRadar ? '#fff' : '#1e40af',
            border: '1px solid ' + (showRadar ? '#1d4ed8' : '#bfdbfe'),
            borderRadius: 8, padding: '3px 9px', fontSize: 11, fontWeight: 700, cursor: 'pointer',
            backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', gap: 5,
          }}
          title="Toggle RainViewer live radar overlay"
        >
          <span style={{ fontSize: 13 }}>📡</span>
          Radar {showRadar ? 'ON' : 'OFF'}
        </button>
        <button
          onClick={() => setShowSAR(v => !v)}
          style={{
            background: showSAR ? 'rgba(8,145,178,0.92)' : 'rgba(255,255,255,0.92)',
            color: showSAR ? '#fff' : '#0e7490',
            border: '1px solid ' + (showSAR ? '#0891b2' : '#a5f3fc'),
            borderRadius: 8, padding: '3px 9px', fontSize: 11, fontWeight: 700, cursor: 'pointer',
            backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', gap: 5,
          }}
          title="Toggle NASA OPERA Sentinel-1 SAR flood inundation overlay"
        >
          <span style={{ fontSize: 13 }}>🛰️</span>
          SAR {showSAR ? 'ON' : 'OFF'}
        </button>
      </div>
      <MapControls />
    </MapContainer>
  )
}
// ─────────────────────────────────────────────────────────────────────────────


type EnvironmentalContextProps = {
  area: string
  city: string
  region: string
  onEdit: () => void
  onBack: () => void
  onContinue: () => void
  isLoading?: boolean
  loadingError?: string | null
  mode?: 'locality' | 'division'
  divisionResult?: Record<string, any> | null
  risk: Record<string, any> | null
  forecast: Record<string, any> | null
  coverageDisclosure?: string | null
}

function EnvironmentalContextStep({ area, city, region, onEdit, onBack, onContinue, risk, forecast, coverageDisclosure, isLoading = false, loadingError = null, mode = 'locality', divisionResult = null }: EnvironmentalContextProps) {
  const hasPartialRisk = risk?.prediction_status === 'PARTIAL_DATA'
  const scoreLabel = risk?.score_label || 'Flood Risk Estimate'
  const sources = [
    ['Satellite Radar (RainViewer nowcast)', Activity, 'rainviewer'],
    ['SAR Flood Inundation (NASA OPERA DSWx-S1)', Radar, 'nasa_opera'],
    ['Weather Forecast (Open-Meteo)', CloudRain, 'openmeteo'],
    ['River Discharge (GloFAS v4 Flood API)', Waves, 'glofas'],
    ['Surface Runoff (Open-Meteo / ERA5-Land)', Mountain, 'era5_runoff'],
    ['Historical Flood Records', FileCheck, null],
    ['Drainage Network (HydroRIVERS)', TreePine, null],
  ]
  const current = risk?.current_conditions || {}
  const divisionMaximum = divisionResult?.risk
  const radarNowcast = risk?.current_conditions?.radar_nowcast
  const sarInundation = risk?.current_conditions?.sar_inundation
  const liveDischarge = current.river_discharge_m3s ?? forecast?.trajectory?.[0]?.glofas_discharge_m3s
  const liveRainfall = current.rainfall_3d ?? forecast?.trajectory?.[0]?.local_rainfall_3d_mm
  const liveSoil = current.swvl1 ?? forecast?.trajectory?.[0]?.soil_moisture
  const runoffDisplay = current.runoff_mm == null ? 'Unavailable' : Math.abs(Number(current.runoff_mm)) < 0.001 ? Number(current.runoff_mm).toExponential(2) : Number(current.runoff_mm).toFixed(4)
  const providerStatus = risk?.provider_status?.providers || {}
  const sourceStatus = (key: string) => providerStatus[key]?.status || (isLoading ? 'loading' : 'unavailable')
  const sourceStatusLabel = (key: string) => {
    const status = sourceStatus(key)
    if (providerStatus[key]?.quality === 'SPATIAL_VALIDATION_PENDING') return 'Spatial validation pending'
    if (providerStatus[key]?.quality === 'VISUAL_ONLY') return 'Visual layer only'
    if (status === 'available' || status === 'REAL_CURRENT') return 'Current'
    if (status === 'REAL_FORECAST') return 'Forecast'
    if (status === 'historical' || status === 'REAL_HISTORICAL') return 'Historical'
    if (status === 'REAL_RECENT_BUT_NOT_CURRENT') return 'Recent / visual only'
    if (status === 'STALE_DATA') return 'Stale — context only'
    if (status === 'loading') return 'Checking'
    return 'Unavailable'
  }

  const renderMetricValue = (val: any, unit: string) => {
    if (isLoading) {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-blue-600 font-medium animate-pulse">
          <LoaderCircle className="h-3.5 w-3.5 animate-spin text-blue-500" />
          <span>Fetching live...</span>
        </span>
      )
    }
    if (val == null || val === 'Unavailable') {
      return <span className="text-slate-400 font-normal">Unavailable</span>
    }
    return (
      <>
        {String(val)}
        {unit && <span className="ml-1 text-sm font-semibold text-slate-400">{unit}</span>}
      </>
    )
  }

  const metrics = [
    ['Rainfall (3-day forecast)', liveRainfall == null ? 'Unavailable' : Number(liveRainfall).toFixed(1), 'mm', 'Open-Meteo', CloudRain, 'text-blue-600'],
    ['Soil Saturation', liveSoil == null ? 'Unavailable' : `${(Number(liveSoil) * 100).toFixed(1)}`, '%', 'local historical signal', Droplet, 'text-blue-600'],
    ['GloFAS Discharge', liveDischarge == null ? 'Unavailable' : Number(liveDischarge).toFixed(2), 'm³/s', providerStatus.glofas?.quality === 'SPATIAL_VALIDATION_PENDING' ? 'spatial cell validation pending' : 'GloFAS v4 Flood API', Waves, liveDischarge == null ? 'text-slate-500' : 'text-blue-600'],
    ['Radar Density', radarNowcast?.intensity_0_100 == null ? 'Unavailable' : `${radarNowcast.intensity_0_100}`, radarNowcast?.intensity_0_100 == null ? '' : '/100', radarNowcast?.storm_active ? '⚡ Active storm detected' : 'RainViewer live radar', Activity, radarNowcast?.storm_active ? 'text-red-600' : (radarNowcast?.intensity_0_100 != null ? 'text-blue-600' : 'text-slate-500')],
    ['SAR Inundation', sarInundation?.water_percentage == null ? 'Unavailable' : `${sarInundation.water_percentage}`, sarInundation?.water_percentage == null ? '' : '%', sarInundation?.water_detected ? '🌊 Surface water detected' : 'NASA OPERA DSWx-S1', Radar, sarInundation?.water_detected ? 'text-amber-600' : (sarInundation?.water_percentage != null ? 'text-cyan-600' : 'text-slate-500')],
    ['Surface Runoff', runoffDisplay, current.runoff_mm == null ? '' : 'mm', current.runoff_mm == null ? 'unavailable' : current.runoff_status === 'REAL_HISTORICAL' ? `ERA5-Land historical/reference · ${String(current.runoff_latest_date || 'date unavailable').slice(0, 10)}` : 'Open-Meteo live model', Mountain, current.runoff_mm == null ? 'text-slate-500' : current.runoff_status === 'REAL_HISTORICAL' ? 'text-amber-600' : 'text-blue-600'],
    ['Drainage Density', current.drainage_density_km_per_km2 == null ? 'Unavailable' : Number(current.drainage_density_km_per_km2).toFixed(4), current.drainage_density_km_per_km2 == null ? '' : 'km/km²', current.drainage_density_km_per_km2 == null ? 'not available' : 'HydroRIVERS / basin area', Gauge, current.drainage_density_km_per_km2 == null ? 'text-slate-500' : 'text-blue-600'],
  ] as const

  return (
    <main className="max-w-[1440px] mx-auto px-4 sm:px-8 pb-6">
      <div className="grid grid-cols-1 xl:grid-cols-[355px_minmax(0,1fr)] gap-5">
        <aside className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between"><h2 className="text-sm font-extrabold text-[#102552]">Selected Area</h2><button onClick={onEdit} className="flex items-center gap-1 rounded-md bg-blue-50 px-2 py-1 text-[11px] font-bold text-blue-700"><Edit2 className="h-3 w-3" /> Edit</button></div>
          <div className="mt-4 flex gap-3"><div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-blue-50"><MapPin className="h-5 w-5 text-blue-700" /></div><div><p className="text-sm font-extrabold text-[#142650]">{area}, {city}</p><p className="text-xs font-medium text-slate-500">{region} Region, Cameroon</p></div></div>
          {coverageDisclosure && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-[11px] font-semibold leading-relaxed text-amber-800">{coverageDisclosure}</div>}
          <div className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-100 px-3 text-xs">
            {[[Compass, 'Coordinates', mode === 'division' ? 'Division-level' : (risk?.coordinates ? `${Number(risk.coordinates.lat).toFixed(4)}° N, ${Number(risk.coordinates.lon).toFixed(4)}° E` : (isLoading ? 'Locating...' : 'Loaded after assessment'))], [Mountain, 'Elevation', mode === 'division' ? 'Division-level' : risk?.elevation_m == null ? (isLoading ? 'Loading...' : 'Loaded after assessment') : `${Number(risk.elevation_m).toFixed(1)} m`], [Waves, 'Nearest major waterway', mode === 'division' ? 'Division-level' : risk?.river_distance_m == null ? (isLoading ? 'Loading...' : 'Loaded after assessment') : `Approximately ${Number(risk.river_distance_m).toFixed(0)} m`]].map(([Icon, label, value]) => { const I = Icon as typeof Compass; return <div key={label as string} className="flex items-center justify-between py-3"><span className="flex items-center gap-2 text-slate-500"><I className="h-3.5 w-3.5" />{label as string}</span><b className="text-right text-slate-700">{value as string}</b></div> })}
          </div>
          <h3 className="mt-5 text-sm font-extrabold text-[#102552]">Data Sources</h3>
          <div className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-100 px-3">{sources.map(([label, Icon, provider]) => { const I = Icon as typeof Layers; const providerKey = typeof provider === 'string' ? provider : null; const status = providerKey ? sourceStatusLabel(providerKey) : 'Available'; const dot = status === 'Current' || status === 'Available' ? 'bg-emerald-400' : status === 'Forecast' || status === 'Historical' || status === 'Checking' || status === 'Recent / visual only' || status === 'Stale — context only' ? 'bg-amber-400' : 'bg-slate-300'; return <div key={String(label)} className="flex items-center gap-2 py-3 text-xs"><I className="h-4 w-4 text-blue-600" /><span className="flex-1 font-medium text-slate-600">{String(label)}</span><span className={`h-2 w-2 rounded-full ${dot}`} /><span className="text-[10px] text-slate-500">{status}</span><ArrowRight className="h-3 w-3 text-slate-400" /></div> })}</div>
          <div className="mt-5 rounded-lg border border-blue-100 bg-gradient-to-br from-blue-50 to-indigo-50 p-4"><div className="flex gap-2"><Info className="h-5 w-5 shrink-0 text-blue-600" /><div><p className="text-xs font-bold text-blue-900">About the Analysis</p><p className="mt-2 text-[11px] leading-relaxed text-slate-600">Our AI model analyzes multiple environmental factors to estimate flood probability and potential impact.</p></div></div></div>
        </aside>

        <section className="space-y-3">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><h2 className="text-base font-extrabold text-[#102552]">{mode === 'division' ? `Division Analysis: ${city}` : 'Environmental Analysis Summary'}</h2><p className="mt-1 text-xs text-slate-500">{mode === 'division' ? (divisionResult?.coverage_note || 'Maximum risk across covered localities') : 'Analysis based on the latest available data'}</p>{mode === 'division' ? (divisionMaximum ? <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4"><p className="text-xs font-bold text-amber-900">Maximum covered-locality risk</p><p className="mt-1 text-2xl font-black text-[#122653]">{Number(divisionMaximum.estimated_risk_percent).toFixed(1)}%</p><p className="text-xs font-semibold text-amber-800">{divisionMaximum.locality} · {divisionMaximum.risk_level}</p></div> : <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs font-semibold text-amber-800">No model-covered localities are available for this division, so no division risk is displayed.</div>) : <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">{metrics.map(([label, value, unit, severity, Icon, color]) => { const I = Icon as typeof CloudRain; return <div key={String(label)} className="min-h-[118px] rounded-xl border border-slate-100 p-3 shadow-sm bg-white"><div className="flex gap-2"><span className="grid h-8 w-8 place-items-center rounded-full bg-blue-50"><I className="h-4 w-4 text-blue-600" /></span><span className="text-[10px] font-semibold leading-tight text-slate-500">{String(label)}</span></div><p className="mt-3 text-lg font-extrabold text-[#122653]">{renderMetricValue(value, unit)}</p><p className={`mt-2 text-xs font-medium ${color}`}>{String(severity)} <span className="ml-1">↗</span></p></div> })}</div>}</div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1.08fr_.92fr]">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><div><h3 className="text-sm font-extrabold text-[#102552]">Forecast Rainfall</h3><p className="mt-3 text-[10px] text-slate-500">Open-Meteo daily totals (mm)</p></div><span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-600">Real forecast</span></div><div className="mt-2 flex h-40 items-end gap-3 border-b border-slate-200 px-2">{(forecast?.trajectory || []).map((point: any) => { const maxRain = Math.max(1, ...(forecast?.trajectory || []).map((p: any) => Number(p.local_rainfall_1d_mm || 0))); const height = Math.max(4, Number(point.local_rainfall_1d_mm || 0) / maxRain * 120); return <div key={point.date} className="flex h-32 flex-1 flex-col items-center justify-end gap-2"><span className="block w-full rounded-t bg-[#1353c9]" style={{ height: `${height}px` }} /><span className="whitespace-nowrap text-[10px] font-semibold text-slate-500">{String(point.date).slice(5)}</span></div>})}</div></div>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><h3 className="text-sm font-extrabold text-[#102552]">{scoreLabel}</h3><span className="rounded-md bg-blue-50 px-2 py-1 text-[10px] font-semibold text-blue-700">{hasPartialRisk ? 'Validated partial data' : 'Validated-input gate'}</span></div><div className="relative mx-auto mt-4 h-32 max-w-[290px]"><div className="absolute inset-0 grid place-items-center"><div className="text-center"><p className="text-4xl font-black text-blue-700">{risk?.estimated_risk_percent == null ? '—' : `${Number(risk.estimated_risk_percent).toFixed(1)}%`}</p><p className="mt-1 text-xs font-bold text-[#142650]">{risk?.risk_level || 'Unavailable'} risk</p><p className="mt-1 text-[10px] text-slate-500">{hasPartialRisk ? 'Current validated core inputs' : `Confidence: ${risk?.confidence_score == null ? '—' : `${Number(risk.confidence_score).toFixed(1)}%`}`}</p></div></div></div><div className="mt-3 rounded-lg bg-blue-50 px-5 py-3 text-center text-[11px] font-medium text-blue-800">{hasPartialRisk ? 'Current rain, soil, discharge history and terrain support this calibrated score. Radar and SAR remain optional supporting evidence.' : risk?.prediction_status === 'INSUFFICIENT_DATA' ? 'Quantitative prediction withheld until the validated model inputs are available.' : 'Only validated model inputs may produce a quantitative estimate.'}</div></div>
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1.08fr_.92fr]">
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><h3 className="text-sm font-extrabold text-[#102552]">Key Environmental Insights</h3><div className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-100 px-3">{[[`Operational risk level: ${risk?.risk_level || 'unavailable'}.`, ShieldCheck], [`3-day rainfall signal: ${current.rainfall_3d == null ? 'unavailable' : `${Number(current.rainfall_3d).toFixed(1)} mm`}.`, CloudRain], [`Soil moisture: ${current.swvl1 == null ? 'unavailable' : `${(Number(current.swvl1) * 100).toFixed(1)}%`}.`, Droplet], [`Surface runoff: ${current.runoff_mm == null ? 'unavailable' : `${Number(current.runoff_mm).toFixed(2)} mm/day`}.`, Activity], [`Drainage density: ${current.drainage_density_km_per_km2 == null ? 'unavailable' : `${Number(current.drainage_density_km_per_km2).toFixed(4)} km/km²`}.`, Gauge]].map(([text, Icon]) => { const I = Icon as typeof CloudRain; return <div key={String(text)} className="flex gap-3 py-2.5 text-[11px] text-slate-600"><I className="h-4 w-4 shrink-0 text-blue-600" />{String(text)}</div> })}</div><div className="mt-3 flex gap-2 rounded-lg bg-blue-50 p-3 text-[11px] text-blue-700"><Info className="h-4 w-4 shrink-0" />Rules-based Option B remains the primary operational estimate.</div></div>
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex justify-between"><h3 className="text-sm font-extrabold text-[#102552]">Historical Flood Occurrence</h3><span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-600">Last 5 Years</span></div><div className="mt-3 divide-y divide-slate-100 text-xs">{[['Flood events in this area', '7'], ['Most recent flood', '12 Jul 2025'], ['Average return period', '0.8 years'], ['Severity (Average)', 'High']].map(([label, value]) => <div key={label} className="flex justify-between py-2.5 text-slate-500"><span>{label}</span><b className={value === 'High' ? 'text-red-600' : 'text-[#142650]'}>{value}</b></div>)}</div><button className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 py-2 text-[11px] font-bold text-blue-700">View Historical Flood Records <ArrowRight className="h-4 w-4" /></button></div>
          </div>
        </section>
      </div>
      {loadingError && <p role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">{loadingError}</p>}
      <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between"><button onClick={onBack} disabled={isLoading} className="flex w-fit items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-xs font-bold text-[#142650] disabled:cursor-not-allowed disabled:opacity-50"><ArrowLeft className="h-4 w-4" /> Back to Area Details</button><div className="flex gap-3"><button className="rounded-lg border border-slate-200 bg-white px-5 py-2.5 text-xs font-bold text-[#142650]">♧ &nbsp; Save &amp; Continue Later</button><button onClick={onContinue} disabled={isLoading} aria-busy={isLoading} className="flex min-w-[190px] items-center justify-center gap-3 rounded-lg bg-[#102b6a] px-6 py-2.5 text-xs font-bold text-white shadow-md disabled:cursor-wait disabled:opacity-70">{isLoading ? <><LoaderCircle className="h-4 w-4 animate-spin" /> Preparing review...</> : <>Next: Review &amp; Confirm <ArrowRight className="h-4 w-4" /></>}</button></div></div>
      <div className="mt-4 flex items-center justify-center gap-2 rounded-lg bg-blue-50 py-3 text-[10px] text-slate-500"><ShieldCheck className="h-4 w-4 text-blue-600" />Your data is secure and used only for flood risk assessment and safety purposes.</div>
    </main>
  )
}

export default function AssessFloodRiskPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // Authenticated user
  const [user, setUser] = useState<{ user_id?: string; name?: string; username?: string; role?: string } | null>(null)
  useEffect(() => {
    setUser(getSession())
  }, [])
  const displayName = user?.name || user?.username || 'Citizen'
  const userGreetingName = displayName.includes('@') ? displayName.split('@')[0] : displayName
  const userRole = user?.role === 'admin' ? 'Administrator' : 'Citizen Responder'

  // Current Step state (1, 2, or 3)
  const initialStep = parseInt(searchParams.get('step') || '1', 10)
  const [step, setStep] = useState<number>(initialStep)

  useEffect(() => {
    const stepParam = parseInt(searchParams.get('step') || '1', 10)
    if (stepParam !== step) {
      setStep(stepParam)
    }
  }, [searchParams])

  // Form State for Step 1
  const [region, setRegion] = useState('Far North')
  const [predictionMode, setPredictionMode] = useState<'locality' | 'division'>('locality')
  const [division, setDivision] = useState('Logone-et-Chari')
  const [neighborhoodNote, setNeighborhoodNote] = useState('')
  const initialLocality = searchParams.get('locality') || searchParams.get('city') || ''
  const [city, setCity] = useState(initialLocality)
  const [specificArea, setSpecificArea] = useState(initialLocality)
  const [suggestions, setSuggestions] = useState<Array<{ name: string; division?: string; covered: boolean; score: number }>>([])
  const [isSuggestionMenuOpen, setIsSuggestionMenuOpen] = useState(false)
  const [coverageDisclosure, setCoverageDisclosure] = useState<string | null>(null)
  const [risk, setRisk] = useState<Record<string, any> | null>(null)
  const [forecast, setForecast] = useState<Record<string, any> | null>(null)
  const [divisionResult, setDivisionResult] = useState<Record<string, any> | null>(null)
  const [loadingAction, setLoadingAction] = useState<'assessment' | 'review' | 'saving' | null>(null)
  const [loadingError, setLoadingError] = useState<string | null>(null)
  const session = getSession()
  const draftKey = assessmentDraftKey(session)
  const [assessmentDraftId, setAssessmentDraftId] = useState(() => window.crypto?.randomUUID?.() || `draft-${Date.now()}`)

  const resetAssessmentForLocality = (locality: string) => {
    // Changing locality starts a distinct assessment, never a renamed prior
    // result. Authentication is deliberately untouched.
    window.sessionStorage.removeItem(draftKey)
    setAssessmentDraftId(window.crypto?.randomUUID?.() || `draft-${Date.now()}`)
    setCity(locality); setSpecificArea(locality); setRisk(null); setForecast(null)
    setDivisionResult(null); setCoverageDisclosure(null); setLoadingError(null)
  }

  const changeStep = (newStep: number) => {
    setStep(newStep)
    setSearchParams({ step: newStep.toString(), locality: city || specificArea })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  // Restore only the owner-scoped draft on refresh.  A fresh assessment URL
  // explicitly bypasses drafts so an older result cannot contaminate it.
  useEffect(() => {
    if (searchParams.get('new') === '1') {
      window.sessionStorage.removeItem(draftKey)
      return
    }
    try {
      const draft = JSON.parse(window.sessionStorage.getItem(draftKey) || 'null')
      if (draft?.draftId && draft.locality && draft.risk && draft.locality === initialLocality) {
        setAssessmentDraftId(draft.draftId); setCity(draft.locality); setSpecificArea(draft.locality)
        setRisk(draft.risk); setForecast(draft.forecast || null); setDivisionResult(draft.divisionResult || null)
      }
    } catch { window.sessionStorage.removeItem(draftKey) }
  // This is intentionally run once per mounted assessment flow.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!risk) return
    window.sessionStorage.setItem(draftKey, JSON.stringify({
      draftId: assessmentDraftId, locality: city || specificArea, risk, forecast, divisionResult,
      savedAt: new Date().toISOString(),
    }))
  }, [assessmentDraftId, city, specificArea, risk, forecast, divisionResult, draftKey])

  // A direct Step 2/3 URL must retrieve fresh data when no same-owner draft is
  // available; it must never show a previous prediction as this assessment.
  useEffect(() => {
    if (step >= 2 && !risk && loadingAction === null && city.trim()) {
      assessSelectedLocality().catch(() => undefined)
    }
  }, [step, risk, loadingAction])

  useEffect(() => {
    const query = city.trim()
    if (!isSuggestionMenuOpen || !query) { setSuggestions([]); return }
    const timer = window.setTimeout(() => {
      farNorthRiskApi.gazetteerSearch(query, 8).then((result) => {
        setSuggestions(result.suggestions.map(({ name, division, covered, score }) => ({ name, division, covered, score })))
      }).catch(() => setSuggestions([]))
    }, 180)
    return () => window.clearTimeout(timer)
  }, [city, isSuggestionMenuOpen])

  const assessSelectedLocality = async (): Promise<boolean> => {
    try {
      if (predictionMode === 'division') {
        try {
          const result = await farNorthRiskApi.divisionRisk(division)
          setDivisionResult(result)
          setCity(result.division || division)
          setSpecificArea(result.risk?.locality || result.division || division)
          setRisk(result.risk ? { ...result.risk, locality: result.risk.locality } : null)
          setForecast(null)
          setCoverageDisclosure(result.coverage_note || null)
          return true
        } catch (error) {
          setDivisionResult(null)
          setRisk(null)
          setForecast(null)
          setCoverageDisclosure(error instanceof Error ? `Live division assessment unavailable: ${error.message}` : 'Live division assessment is unavailable. No reference values are shown.')
          return false
        }
      }
      const localityName = city || specificArea
      let resolvedName = localityName
      try {
        const resolved = await farNorthRiskApi.resolve(localityName)
        setCoverageDisclosure(resolved.disclosure)
        resolvedName = resolved.resolved_name
        setCity(resolvedName)
        setSpecificArea(resolvedName)
      } catch {
        // Use the locality name directly if resolve fails
        setCoverageDisclosure(null)
        setCity(localityName)
        setSpecificArea(localityName)
      }
      try {
        // Both endpoints use live provider data.  The forecast endpoint carries
        // the full seven-day Open-Meteo/GloFAS trajectory used in Step 3.
        const [riskResult, forecastResult] = await Promise.all([
          farNorthRiskApi.assess(resolvedName),
          farNorthRiskApi.forecast(resolvedName),
        ])
        if (forecastResult.status === 'not_available' || !Array.isArray(forecastResult.trajectory) || !forecastResult.trajectory.length) {
          throw new Error(forecastResult.message || 'The live forecast provider returned no forecast days.')
        }
        setRisk(riskResult); setForecast(forecastResult); setDivisionResult(null)
        return true
      } catch (error) {
        setRisk(null)
        setForecast(null)
        setDivisionResult(null)
        setCoverageDisclosure(error instanceof Error ? `Live environmental assessment unavailable: ${error.message}` : 'Live environmental assessment is unavailable. No reference values are shown.')
        return false
      }
    } catch (error) {
      setRisk(null); setForecast(null)
      setCoverageDisclosure(error instanceof Error ? error.message : 'The selected location could not be resolved.')
      return false
    }
  }

  const withTimeout = <T,>(promise: Promise<T>, timeoutMs = 45000): Promise<T> => Promise.race([
    promise,
    new Promise<T>((_, reject) => window.setTimeout(() => reject(new Error('This is taking longer than expected - please retry.')), timeoutMs))
  ])

  const handleAssessmentContinue = async () => {
    if (loadingAction) return
    if (predictionMode === 'locality' && !city.trim()) { setLoadingError('Select a locality before continuing.'); return }
    setLoadingAction('assessment'); setLoadingError(null)
    try {
      const ok = await withTimeout(assessSelectedLocality())
      if (!ok) throw new Error('The selected location could not be assessed. Please retry.')
      changeStep(2)
    } catch (error) { setLoadingError(error instanceof Error ? error.message : 'Assessment failed. Please retry.') }
    finally { setLoadingAction(null) }
  }

  const handleReviewContinue = async () => {
    if (loadingAction) return
    setLoadingAction('review'); setLoadingError(null)
    try {
      if (!risk || !forecast) {
        const ok = await withTimeout(assessSelectedLocality())
        if (!ok) throw new Error('The prediction response is not available yet. Please retry.')
        changeStep(3)
        return
      }
      changeStep(3)
    } catch (error) { setLoadingError(error instanceof Error ? error.message : 'This is taking longer than expected - please retry.') }
    finally { setLoadingAction(null) }
  }
  
  // AI Assistant Chat state for Step 3
  const [aiMessages, setAiMessages] = useState<Array<{ sender: 'ai' | 'user'; text: string }>>([
    {
      sender: 'ai',
      text: "Hello! I'm AquaGuard AI. I can help you understand this prediction, answer your questions, and provide safety recommendations. What would you like to know?"
    }
  ])
  const [chatInput, setChatInput] = useState('')

  const handleSendChat = async (textToSend?: string) => {
    const query = textToSend || chatInput
    if (!query.trim()) return
    const userRaw = getSession()
    const newMessages = [...aiMessages, { sender: 'user' as const, text: query }]
    setAiMessages(newMessages)
    setChatInput('')

    if (!userRaw) {
      setTimeout(() => {
        setAiMessages((prev) => [
          ...prev,
          {
            sender: 'ai',
            text: "To receive detailed interactive AI interpretations and customized safety advisories, please log in or register a citizen account."
          }
        ])
      }, 300)
      return
    }

    try {
      const res = await aiApi.chat({
        message: query,
        context: {
          locality: specificArea,
          risk_level: risk?.risk_level,
          estimated_risk_percent: risk?.estimated_risk_percent,
          confidence_score: risk?.confidence_score,
          details: risk
        }
      })
      const reply = res?.response && res.response.trim().length > 0
        ? res.response
        : risk?.risk_level
          ? `For ${specificArea}, the current risk level is ${risk.risk_level}.`
          : `A quantitative risk level for ${specificArea} is unavailable until the required validated model inputs are available.`
      setAiMessages((prev) => [...prev, { sender: 'ai', text: reply }])
    } catch {
      setAiMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: `For ${specificArea} in the Far North, the operational rules-based estimate is ${risk?.estimated_risk_percent == null ? 'currently unavailable' : `${Number(risk.estimated_risk_percent).toFixed(1)}%`}. Ask about rainfall, soil moisture, discharge, or safety guidance for details.`
        }
      ])
    }
  }

  // Coordinates for Yaoundé (Nkolbisson)
  const coordinates: [number, number] = risk?.coordinates ? [Number(risk.coordinates.lat), Number(risk.coordinates.lon)] : [12.1364, 15.0557]
  const riskPercent = risk?.estimated_risk_percent == null ? null : Number(risk.estimated_risk_percent)
  const hasQuantitativeRisk = riskPercent != null && Number.isFinite(riskPercent)
  const hasPartialRisk = risk?.prediction_status === 'PARTIAL_DATA'
  const gaugeDashOffset = hasQuantitativeRisk ? Math.max(0, 125.6 * (1 - Math.min(100, Math.max(0, riskPercent)) / 100)) : 125.6
  const summaryCallout = !hasQuantitativeRisk
    ? {
        className: 'border-amber-100 bg-amber-50/80 text-amber-800',
        text: risk?.prediction_status === 'INSUFFICIENT_DATA'
          ? 'Quantitative flood risk is withheld because the validated model input set is incomplete. Environmental evidence is shown separately.'
          : 'A validated quantitative flood-risk estimate is not available for this assessment.',
      }
    : riskPercent >= 67
      ? { className: 'border-red-100 bg-red-50/80 text-red-700', text: 'High flood-risk conditions are indicated for the next 24–72 hours. Follow local safety guidance and monitor official alerts.' }
      : riskPercent >= 34
        ? { className: 'border-amber-100 bg-amber-50/80 text-amber-800', text: 'Moderate flood-risk conditions are indicated for the next 24–72 hours. Monitor rainfall and local water levels.' }
        : { className: 'border-emerald-100 bg-emerald-50/80 text-emerald-800', text: 'Low flood-risk conditions are indicated for the next 24–72 hours. Continue monitoring changing conditions.' }

  const handleConfirmAndViewDashboard = async () => {
    const currentSession = getSession()
    if (!currentSession) {
      window.sessionStorage.removeItem(draftKey)
      navigate('/')
      return
    }
    if (currentSession.role === 'admin' || currentSession.role === 'administrator') {
      navigate('/admin-dashboard')
      return
    }
    setLoadingAction('saving'); setLoadingError(null)
    try {
      const localityToSave = specificArea || city || 'Far North'
      const userId = currentSession.user_id || currentSession.username || currentSession.email || 'unknown'
      console.log(`[Assessment] user=${userId} locality=${localityToSave}`)
      if (!risk || risk.estimated_risk_percent == null || !risk.risk_level) {
        throw new Error('The authoritative prediction is unavailable and cannot be saved.')
      }
      const riskPct = Number(risk.estimated_risk_percent)
      const riskLvl = String(risk.risk_level)
      const saved = await userPredictionsApi.save({
        locality: localityToSave,
        risk_level: riskLvl,
        estimated_risk_percent: riskPct,
        confidence_score: risk.confidence_score == null ? undefined : Number(risk.confidence_score),
        forecast_period: 'Next 24–72 hrs',
        details: {
          risk,
          forecast: forecast ? { trajectory: forecast.trajectory } : null,
          area: specificArea,
          city,
          region,
          assessment_draft_id: assessmentDraftId,
        },
      })
      if (!saved.assessment_id) throw new Error('The server did not confirm an assessment identity.')
      console.log(`[Prediction] assessment=${saved.assessment_id} prediction=${saved.prediction_id} locality=${localityToSave}`)
      window.sessionStorage.removeItem(draftKey)
      navigate(`/citizen-entry?assessment=${encodeURIComponent(String(saved.assessment_id))}`)
    } catch (err) {
      console.error('Failed to save prediction to user profile:', err)
      setLoadingError(err instanceof Error ? `We could not save your assessment. ${err.message}` : 'We could not save your assessment. Please try again.')
    } finally {
      setLoadingAction(null)
    }
  }

  return (
    <div className="min-h-screen bg-[#f8fafc] font-sans text-slate-900 selection:bg-blue-100 selection:text-blue-900 pb-16">
      {/* ─── TOP NAVBAR HEADER ──────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 bg-white border-b border-slate-200/80 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Brand Logo & Title */}
          <div
            className="flex items-center gap-3 cursor-pointer select-none"
            onClick={() => navigate('/')}
          >
            <div className="w-9 h-9 rounded-xl bg-[#0f2460] flex items-center justify-center shadow-md shadow-blue-900/20">
              <Droplets className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="font-extrabold text-slate-900 text-base leading-none tracking-tight">
                AquaGuard AI
              </h1>
              <p className="text-[10px] text-slate-500 font-semibold tracking-wide uppercase mt-0.5">
                Cameroon Flood Intelligence
              </p>
            </div>
          </div>

          {step >= 2 ? (
            /* Center Nav links for Step 2 and Step 3 */
            <nav className="hidden md:flex items-center gap-6 text-xs font-semibold text-slate-600">
              <button onClick={() => navigate('/')} className="hover:text-blue-600 transition-colors">
                Platform Overview
              </button>
              <button onClick={() => navigate('/')} className="hover:text-blue-600 transition-colors">
                Methodology
              </button>
              <div className="flex items-center gap-1 text-slate-600 cursor-pointer">
                <Globe className="w-3.5 h-3.5" />
                <span>English</span>
              </div>
            </nav>
          ) : null}

          {/* Right Controls */}
          <div className="flex items-center gap-3">
            {step === 1 ? (
              <>
                <div className="hidden sm:flex items-center gap-2 bg-slate-50 hover:bg-slate-100 border border-slate-200/90 text-slate-700 font-medium text-xs px-3.5 py-2 rounded-full cursor-pointer transition-all">
                  <MapPin className="w-4 h-4 text-blue-600" />
                  <span>{specificArea}, Far North Region</span>
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400 ml-1" />
                </div>
                <div className="flex items-center gap-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200/90 text-slate-700 font-medium text-xs px-3.5 py-2 rounded-full cursor-pointer transition-all">
                  <Globe className="w-4 h-4 text-slate-500" />
                  <span>English</span>
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                </div>
                <button className="relative p-2 rounded-full hover:bg-slate-100 text-slate-600 transition-colors cursor-pointer ml-1">
                  <Bell className="w-5 h-5" />
                  <span className="absolute top-1 right-1 w-4 h-4 rounded-full bg-red-500 text-white font-bold text-[9px] flex items-center justify-center border-2 border-white shadow-xs">
                    3
                  </span>
                </button>
                <div className="flex items-center gap-2.5 pl-2 border-l border-slate-200 ml-1">
                  {user ? (
                    <>
                      <div className="w-9 h-9 rounded-full bg-slate-200 overflow-hidden border border-slate-300 shadow-xs flex items-center justify-center text-slate-700 font-bold text-xs bg-gradient-to-br from-blue-100 to-indigo-100">
                        <img
                          src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80"
                          alt={displayName || 'User Avatar'}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = 'none'
                          }}
                        />
                      </div>
                      <div className="hidden md:block text-left leading-tight">
                        <p className="text-xs font-bold text-slate-900">{userGreetingName}</p>
                        <p className="text-[10px] font-semibold text-slate-400">{userRole}</p>
                      </div>
                    </>
                  ) : null}
                </div>
              </>
            ) : step === 2 ? (
              <div className="flex items-center gap-3">
                <button
                  onClick={() => navigate('/login')}
                  className="bg-[#0f2460] hover:bg-[#0a1c4e] text-white text-xs font-semibold px-4 py-2 rounded-full shadow-md transition-all cursor-pointer"
                >
                  Access Portal
                </button>
              </div>
            ) : (
              /* Step 3 Navbar Controls */
              <div className="flex items-center gap-3">
                <button className="relative p-2 rounded-full hover:bg-slate-100 text-slate-600 transition-colors cursor-pointer">
                  <Bell className="w-5 h-5" />
                  <span className="absolute top-1 right-1 w-4 h-4 rounded-full bg-red-500 text-white font-bold text-[9px] flex items-center justify-center border-2 border-white shadow-xs">
                    3
                  </span>
                </button>
                {user ? (
                  <div className="flex items-center gap-2.5 pl-2 border-l border-slate-200">
                    <div className="w-9 h-9 rounded-full bg-slate-200 overflow-hidden border border-slate-300 shadow-xs flex items-center justify-center text-slate-700 font-bold text-xs bg-gradient-to-br from-blue-100 to-indigo-100">
                      <img
                        src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80"
                        alt={displayName || 'User Avatar'}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          (e.target as HTMLElement).style.display = 'none'
                        }}
                      />
                    </div>
                    <div className="hidden md:block text-left leading-tight">
                      <p className="text-xs font-bold text-slate-900">{userGreetingName}</p>
                      <p className="text-[10px] font-semibold text-slate-400">{userRole}</p>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => navigate('/login')}
                    className="bg-[#0f2460] hover:bg-[#0a1c4e] text-white text-xs font-semibold px-4 py-2 rounded-full shadow-md transition-all cursor-pointer"
                  >
                    Access Portal
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ─── STEPPER & BREADCRUMB HEADER SECTION ────────────────────────────── */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-6">
        {step === 1 ? (
          <>
            <nav className="flex items-center gap-2 text-xs text-slate-400 font-medium mb-4">
              <span className="hover:text-blue-600 cursor-pointer transition-colors" onClick={() => navigate('/')}>
                Home
              </span>
              <span className="text-slate-300">&gt;</span>
              <span className="text-slate-700 font-semibold">Assess Flood Risk</span>
            </nav>

            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200/70 pb-6">
              <div>
                <div className="inline-flex items-center gap-1.5 bg-blue-50 text-blue-700 text-[11px] font-bold px-2.5 py-1 rounded-md mb-2 border border-blue-100 uppercase tracking-wider">
                  Step 1 of 3
                </div>
                <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                  Tell us about the area you want to assess
                </h1>
                <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl leading-relaxed">
                  Provide some details about the location and context so we can generate an accurate flood risk prediction.
                </p>
              </div>

              <div className="flex items-center gap-2 sm:gap-3 bg-white px-4 py-3 rounded-2xl border border-slate-200/80 shadow-xs self-start md:self-auto">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center shadow-xs">
                    1
                  </div>
                  <span className="text-xs font-bold text-blue-700 whitespace-nowrap">
                    Area Details
                  </span>
                </div>
                <div className="w-6 sm:w-10 h-0.5 bg-slate-200" />
                <div className="flex items-center gap-2 opacity-60 cursor-pointer" onClick={() => changeStep(2)}>
                  <div className="w-7 h-7 rounded-full bg-slate-100 border border-slate-300 text-slate-500 font-bold text-xs flex items-center justify-center">
                    2
                  </div>
                  <span className="text-xs font-medium text-slate-500 whitespace-nowrap hidden sm:inline">
                    Environmental Context
                  </span>
                </div>
                <div className="w-6 sm:w-10 h-0.5 bg-slate-200" />
                <div className="flex items-center gap-2 opacity-60 cursor-pointer" onClick={() => changeStep(3)}>
                  <div className="w-7 h-7 rounded-full bg-slate-100 border border-slate-300 text-slate-500 font-bold text-xs flex items-center justify-center">
                    3
                  </div>
                  <span className="text-xs font-medium text-slate-500 whitespace-nowrap hidden sm:inline">
                    Review &amp; Confirm
                  </span>
                </div>
              </div>
            </div>
          </>
        ) : step === 2 ? (
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200/70 pb-6">
            <div>
              <div className="inline-flex items-center gap-1.5 bg-blue-50 text-blue-700 text-[11px] font-bold px-2.5 py-1 rounded-md mb-2 border border-blue-100 uppercase tracking-wider">
                Step 2 of 3
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                Analyze Environmental Context
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl leading-relaxed">
                We analyze real-time and historical environmental data for your selected area to assess flood probability and potential impact.
              </p>
            </div>

            <div className="flex items-center gap-2 sm:gap-3 bg-white px-4 py-3 rounded-2xl border border-slate-200/80 shadow-xs self-start md:self-auto">
              <div className="flex items-center gap-2 cursor-pointer" onClick={() => changeStep(1)}>
                <div className="w-7 h-7 rounded-full bg-emerald-500 text-white font-bold text-xs flex items-center justify-center shadow-xs">
                  <CheckCircle2 className="w-4 h-4 text-white" />
                </div>
                <span className="text-xs font-semibold text-slate-700 whitespace-nowrap">
                  Area Details
                </span>
              </div>
              <div className="w-6 sm:w-10 h-0.5 bg-blue-600" />
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center shadow-xs">
                  2
                </div>
                <span className="text-xs font-bold text-blue-700 whitespace-nowrap">
                  Environmental Context
                </span>
              </div>
              <div className="w-6 sm:w-10 h-0.5 bg-slate-200" />
              <div className="flex items-center gap-2 opacity-60 cursor-pointer" onClick={() => changeStep(3)}>
                <div className="w-7 h-7 rounded-full bg-slate-100 border border-slate-300 text-slate-500 font-bold text-xs flex items-center justify-center">
                  3
                </div>
                <span className="text-xs font-medium text-slate-500 whitespace-nowrap hidden sm:inline">
                  Review &amp; Confirm
                </span>
              </div>
            </div>
          </div>
        ) : (
          /* Step 3 Header Banner */
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200/70 pb-6">
            <div>
              <div className="inline-flex items-center gap-1.5 bg-blue-50 text-blue-700 text-[11px] font-bold px-2.5 py-1 rounded-md mb-2 border border-blue-100 uppercase tracking-wider">
                Step 3 of 3
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                Review &amp; Confirm Prediction
              </h1>
              <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-2xl leading-relaxed">
                Review the AI-generated flood risk prediction for your area. Explore the results, recommendations and get AI assistance if needed.
              </p>
            </div>

            {/* Step 3 Stepper Progress Indicator */}
            <div className="flex items-center gap-2 sm:gap-3 bg-white px-4 py-3 rounded-2xl border border-slate-200/80 shadow-xs self-start md:self-auto">
              <div className="flex items-center gap-2 cursor-pointer" onClick={() => changeStep(1)}>
                <div className="w-7 h-7 rounded-full bg-emerald-500 text-white font-bold text-xs flex items-center justify-center shadow-xs">
                  <CheckCircle2 className="w-4 h-4 text-white" />
                </div>
                <span className="text-xs font-semibold text-slate-700 whitespace-nowrap">
                  Area Details
                </span>
              </div>
              <div className="w-6 sm:w-10 h-0.5 bg-emerald-500" />
              <div className="flex items-center gap-2 cursor-pointer" onClick={() => changeStep(2)}>
                <div className="w-7 h-7 rounded-full bg-emerald-500 text-white font-bold text-xs flex items-center justify-center shadow-xs">
                  <CheckCircle2 className="w-4 h-4 text-white" />
                </div>
                <span className="text-xs font-semibold text-slate-700 whitespace-nowrap">
                  Environmental Context
                </span>
              </div>
              <div className="w-6 sm:w-10 h-0.5 bg-blue-600" />
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center shadow-xs">
                  3
                </div>
                <span className="text-xs font-bold text-blue-700 whitespace-nowrap">
                  Review &amp; Confirm
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ─── STEP 1 CONTENT ─────────────────────────────────────────────────── */}
      {step === 1 ? (
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            <div className="lg:col-span-6 bg-white rounded-2xl border border-slate-200/90 shadow-sm p-6 space-y-6">
              <div className="space-y-4">
                <h2 className="text-sm font-bold text-slate-900 tracking-tight flex items-center gap-2">
                  Location Information
                </h2>
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">Prediction mode</label>
                    <div className="grid grid-cols-2 gap-2">
                      <button type="button" onClick={() => setPredictionMode('locality')} className={`rounded-xl border px-3 py-2.5 text-xs font-bold ${predictionMode === 'locality' ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-600'}`}>Assess a specific town</button>
                      <button type="button" onClick={() => setPredictionMode('division')} className={`rounded-xl border px-3 py-2.5 text-xs font-bold ${predictionMode === 'division' ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-600'}`}>Assess a whole division</button>
                    </div>
                  </div>
                  <div className="relative">
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                      Region <span className="text-red-500">*</span>
                    </label>
                  <div className="relative">
                      <select
                        value="Far North"
                        onChange={() => setRegion('Far North')}
                        className="w-full bg-slate-50/60 border border-slate-200 rounded-xl px-3.5 py-2.5 text-xs text-slate-800 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white appearance-none cursor-pointer"
                      >
                        <option value="Far North">Far North</option>
                      </select>
                      <ChevronDown className="w-4 h-4 text-slate-400 absolute right-3 top-3 pointer-events-none" />
                    </div>
                  </div>

                  {predictionMode === 'division' ? <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">Division <span className="text-red-500">*</span></label>
                    <select value={division} onChange={(e) => setDivision(e.target.value)} className="w-full bg-slate-50/60 border border-slate-200 rounded-xl px-3.5 py-2.5 text-xs text-slate-800 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500">
                      {['Logone-et-Chari','Mayo-Danay','Diamaré','Mayo-Sava','Mayo-Tsanaga','Mayo-Kani'].map((d) => <option key={d}>{d}</option>)}
                    </select>
                  </div> : <div className="relative">
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                      Locality <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={city}
                      onFocus={() => setIsSuggestionMenuOpen(true)}
                      onChange={(e) => { resetAssessmentForLocality(e.target.value); setIsSuggestionMenuOpen(true) }}
                      onBlur={() => window.setTimeout(() => setIsSuggestionMenuOpen(false), 120)}
                      onKeyDown={(e) => { if (e.key === 'Escape') setIsSuggestionMenuOpen(false) }}
                      placeholder="Search a town or locality, e.g. Kousséri"
                      className="w-full bg-slate-50/60 border border-slate-200 rounded-xl px-3.5 py-2.5 text-xs text-slate-800 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white"
                    />
                    {isSuggestionMenuOpen && suggestions.length > 0 && <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-60 overflow-auto rounded-xl border border-slate-200 bg-white shadow-lg">
                      {suggestions.map((suggestion) => <button key={`${suggestion.name}-${suggestion.division || ''}`} type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => { resetAssessmentForLocality(suggestion.name); setSuggestions([]); setIsSuggestionMenuOpen(false) }} className="flex w-full items-center justify-between px-3.5 py-2.5 text-left text-xs hover:bg-blue-50"><span><b className="text-slate-800">{suggestion.name}</b>{suggestion.division && <span className="ml-2 text-slate-400">{suggestion.division}</span>}</span><span className={`text-[10px] font-bold ${suggestion.covered ? 'text-emerald-600' : 'text-amber-600'}`}>{suggestion.covered ? 'Model covered' : 'Gazetteer place'}</span></button>)}
                    </div>}
                  </div>}

                  {predictionMode === 'locality' && <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                      Additional context <span className="text-slate-400 font-normal">(optional)</span>
                    </label>
                    <div className="relative">
                      <input
                        type="text"
                        value={neighborhoodNote}
                        onChange={(e) => setNeighborhoodNote(e.target.value)}
                        placeholder="A neighborhood note (does not change the prediction)"
                        className="w-full bg-slate-50/60 border border-slate-200 rounded-xl px-3.5 py-2.5 pr-10 text-xs text-slate-800 font-medium focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white"
                      />
                      <Search className="w-4 h-4 text-slate-400 absolute right-3 top-3 pointer-events-none" />
                    </div>
                    <p className="mt-1 text-[10px] text-slate-500">We record this for reference; environmental data covers the whole town, not individual neighborhoods.</p>
                  </div>}
                </div>
              </div>

              <div className="h-px bg-slate-100" />

              <div className="space-y-3">
                <h2 className="text-sm font-bold text-slate-900 tracking-tight">Model-resolved context</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="rounded-xl border border-slate-200 bg-slate-50/60 px-3.5 py-3"><p className="text-[10px] font-semibold text-slate-500">Elevation (read-only)</p><p className="mt-1 text-xs font-bold text-slate-800">{risk?.elevation_m == null ? 'Loaded after assessment' : `${Number(risk.elevation_m).toFixed(1)} m`}</p></div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50/60 px-3.5 py-3"><p className="text-[10px] font-semibold text-slate-500">Nearest major waterway (read-only)</p><p className="mt-1 text-xs font-bold text-slate-800">{risk?.river_distance_m == null ? 'Loaded after assessment' : `Approximately ${Number(risk.river_distance_m).toFixed(0)} m away`}</p></div>
                </div>
              </div>

              <div className="pt-2">
                <button
                  onClick={handleAssessmentContinue}
                  disabled={loadingAction !== null}
                  aria-busy={loadingAction === 'assessment'}
                  className="w-full bg-[#165dfc] hover:bg-[#0f4ed8] text-white font-bold text-xs py-3.5 px-6 rounded-xl shadow-md shadow-blue-600/20 transition-all flex items-center justify-center gap-2 cursor-pointer group disabled:cursor-wait disabled:opacity-70"
                >
                  {loadingAction === 'assessment' ? <><LoaderCircle className="w-4 h-4 animate-spin" /><span>Analyzing environmental data...</span></> : <><span>Next: Environmental Context</span><ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" /></>}
                </button>
                {loadingAction === null && loadingError && <p role="alert" className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700">{loadingError}</p>}
              </div>
            </div>

            <div className="lg:col-span-6 space-y-6">
              <div className="bg-white rounded-2xl border border-slate-200/90 shadow-sm overflow-hidden relative" style={{ height: '340px' }}>
                <MapContainer center={coordinates} zoom={13} scrollWheelZoom={false} zoomControl={false} className="w-full h-full z-0">
                  <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  <RainViewerLayer />
                  <Marker position={coordinates} icon={customIcon} />
                  <MapControls />
                </MapContainer>
                <div style={{ position: 'absolute', top: 8, left: 8, zIndex: 1000, background: 'rgba(37,99,235,0.88)', color: '#fff', borderRadius: 8, padding: '3px 9px', fontSize: 11, fontWeight: 700, backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', gap: 5, pointerEvents: 'none' }}>
                  <span style={{ fontSize: 13 }}>📡</span> Live Radar
                </div>
              </div>

              {/* What happens next? */}
              <section className="bg-white rounded-2xl border border-slate-200/90 shadow-sm p-5 sm:p-6">
                <h2 className="text-sm font-extrabold text-slate-900">What happens next?</h2>
                <p className="mt-1 text-xs text-slate-500">Our AI will analyze environmental, geographic, and historical data to estimate flood risk.</p>

                <div className="mt-6 grid grid-cols-2 gap-y-6 sm:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] sm:items-start sm:gap-x-3">
                  {[
                    { Icon: MapPin, title: 'Area Details', text: 'You provide location information' },
                    { Icon: Activity, title: 'Environmental Analysis', text: 'We analyze weather, terrain, soil & hydrology data' },
                    { Icon: ShieldCheck, title: 'Risk Assessment', text: 'AI calculates flood probability and risk level' },
                    { Icon: FileCheck, title: 'Results & Recommendations', text: 'You receive prediction and safety recommendations' },
                  ].map(({ Icon, title, text }, index) => (
                    <Fragment key={title}>
                      <div className="text-center">
                        <div className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-blue-50 text-blue-600">
                          <Icon className="h-5 w-5" />
                        </div>
                        <p className="mt-3 text-[11px] font-bold text-slate-800">{title}</p>
                        <p className="mx-auto mt-1 max-w-[125px] text-[10px] leading-relaxed text-slate-500">{text}</p>
                      </div>
                      {index < 3 && <ArrowRight className="hidden h-4 w-4 self-start mt-4 text-slate-400 sm:block" />}
                    </Fragment>
                  ))}
                </div>

                <div className="mt-6 flex items-center gap-2 rounded-lg border border-blue-100 bg-blue-50/70 px-3 py-3 text-[11px] font-medium text-blue-700">
                  <Info className="h-4 w-4 shrink-0" />
                  The assessment is free and takes less than 1 minute.
                </div>
              </section>
            </div>
          </div>
        </main>
      ) : step === 2 ? (
        /* ─── STEP 2 CONTENT (ANALYZE ENVIRONMENTAL CONTEXT) ───────────────── */
        <EnvironmentalContextStep
          area={specificArea}
          city={city}
          region={region}
          onEdit={() => changeStep(1)}
          onBack={() => changeStep(1)}
          onContinue={handleReviewContinue}
          isLoading={loadingAction !== null}
          loadingError={loadingAction === null ? loadingError : null}
          risk={risk}
          forecast={forecast}
          coverageDisclosure={coverageDisclosure}
          mode={predictionMode}
          divisionResult={divisionResult}
        />
      ) : (
        /* ─── STEP 3 CONTENT (REVIEW & CONFIRM PREDICTION) ──────────────────── */
        <main className="max-w-[1440px] mx-auto px-4 sm:px-8 space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            {/* ─── LEFT COLUMN: SUMMARY CARDS (4 COLS ~ 28%) ─────────────────── */}
            <div className="lg:col-span-3 space-y-5">
              {/* CARD 1: SELECTED AREA SUMMARY */}
              <div className="bg-white rounded-2xl border border-slate-200/90 shadow-sm p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                    Selected Area Summary
                  </h3>
                  <button
                    onClick={() => changeStep(1)}
                    className="flex items-center gap-1 text-[11px] font-semibold text-blue-600 hover:text-blue-800 bg-blue-50 border border-blue-100 px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
                  >
                    <Edit2 className="w-3 h-3" />
                    <span>Edit</span>
                  </button>
                </div>

                <div className="flex items-start gap-2.5">
                  <MapPin className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                  <div>
                    <h4 className="text-sm font-bold text-slate-900 leading-tight">
                      {specificArea}, {city}
                    </h4>
                    <p className="text-xs text-slate-500 mt-0.5">{region} Region, Cameroon</p>
                  </div>
                </div>
                {coverageDisclosure && <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-[11px] font-semibold leading-relaxed text-amber-800">{coverageDisclosure}</div>}
                {predictionMode === 'locality' && neighborhoodNote && <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-[11px] text-slate-600"><b>Additional context:</b> {neighborhoodNote} <span className="text-slate-400">(recorded for reference; it does not change the town-level prediction)</span></div>}
                {predictionMode === 'division' && divisionResult && <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-[11px] font-semibold leading-relaxed text-blue-800">Whole-division mode uses the maximum risk among covered localities. {divisionResult.coverage_note}</div>}

                <div className="space-y-2.5 pt-2 border-t border-slate-100 text-xs">
                  <div className="flex items-center justify-between text-slate-600">
                    <span className="flex items-center gap-2 text-slate-500">
                      <Compass className="w-3.5 h-3.5 text-slate-400" /> Coordinates
                    </span>
                    <span className="font-mono font-semibold text-slate-800">
                      {coordinates[0]}° N, {coordinates[1]}° E
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-slate-600">
                    <span className="flex items-center gap-2 text-slate-500">
                      <Mountain className="w-3.5 h-3.5 text-slate-400" /> Elevation
                    </span>
                    <span className="font-semibold text-slate-800">{predictionMode === 'division' ? 'Division-level' : risk?.elevation_m == null ? 'Unavailable' : `${Number(risk.elevation_m).toFixed(1)} m`}</span>
                  </div>

                  <div className="flex items-center justify-between text-slate-600">
                    <span className="flex items-center gap-2 text-slate-500">
                      <Waves className="w-3.5 h-3.5 text-slate-400" /> Proximity to Water
                    </span>
                    <span className="font-semibold text-slate-800">{predictionMode === 'division' ? 'Division-level' : risk?.river_distance_m == null ? 'Unavailable' : `Approximately ${Number(risk.river_distance_m).toFixed(0)} m`}</span>
                  </div>

                </div>
              </div>

              {/* CARD 2: PREDICTION SUMMARY GAUGE CARD */}
              <div className="bg-white rounded-2xl border border-slate-200/90 shadow-sm p-5 space-y-4">
                <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                  Prediction Summary
                </h3>

                {/* Semi-Circle Gauge SVG */}
                <div className="flex flex-col items-center justify-center pt-1 pb-1">
                  <div className="relative w-48 h-28 flex items-center justify-center">
                    <svg className="w-full h-full overflow-visible" viewBox="0 0 100 55">
                      <path
                        d="M 10 50 A 40 40 0 0 1 90 50"
                        fill="none"
                        stroke="#e2e8f0"
                        strokeWidth="8"
                        strokeLinecap="round"
                      />
                      <path
                        d="M 10 50 A 40 40 0 0 1 90 50"
                        fill="none"
                        stroke="url(#gaugeGradStep3)"
                        strokeWidth="8"
                        strokeDasharray="125.6"
                        strokeDashoffset={gaugeDashOffset}
                        strokeLinecap="round"
                      />
                      <defs>
                        <linearGradient id="gaugeGradStep3" x1="0%" y1="0%" x2="100%" y2="0%">
                          <stop offset="0%" stopColor="#22c55e" />
                          <stop offset="50%" stopColor="#eab308" />
                          <stop offset="100%" stopColor="#ef4444" />
                        </linearGradient>
                      </defs>
                      {hasQuantitativeRisk && <circle cx="82" cy="26" r="4.5" fill={riskPercent >= 67 ? '#ef4444' : riskPercent >= 34 ? '#f59e0b' : '#22c55e'} stroke="#ffffff" strokeWidth="2" />}
                    </svg>

                    <div className="absolute bottom-1 flex flex-col items-center text-center">
                      <span className="text-3xl font-extrabold text-slate-900 tracking-tight leading-none">
                        {risk?.estimated_risk_percent == null ? '—' : `${Number(risk.estimated_risk_percent).toFixed(1)}%`}
                      </span>
                      <span className="text-xs font-extrabold text-slate-900 mt-1">
                        {risk?.risk_level || 'Unavailable'} Risk
                      </span>
                      <span className="text-[10px] text-slate-400 font-semibold mt-0.5">
                        {hasPartialRisk ? 'Validated partial-data score' : `Confidence: ${risk?.confidence_score == null ? '—' : `${Number(risk.confidence_score).toFixed(1)}%`}`}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Red Callout Box */}
                <div className={`border rounded-xl p-3 text-center text-xs font-semibold ${summaryCallout.className}`}>
                  {summaryCallout.text}
                </div>
              </div>

              {/* CARD 3: FORECAST PERIOD */}
              <div className="bg-white rounded-2xl border border-slate-200/90 shadow-sm p-5 space-y-2">
                <div className="flex items-center gap-2 text-xs font-bold text-slate-900 uppercase tracking-wider">
                  <Calendar className="w-4 h-4 text-blue-600" />
                  <span>Forecast Period</span>
                </div>
                <div>
                  <p className="text-sm font-extrabold text-slate-900 mt-1">
                    Next 5 forecast days
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5 font-medium">
                    {forecast?.forecast_issue_time ? `Issued ${new Date(forecast.forecast_issue_time).toLocaleString()}` : 'Forecast issue time unavailable'}
                  </p>
                  <p className='text-xs text-slate-500 mt-0.5 font-medium'>{forecast?.glofas_forecast_available ? 'GloFAS forecast discharge available' : 'GloFAS forecast discharge unavailable'}</p>
                  {forecast?.basin_rainfall_data_source && <p className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-[10px] leading-relaxed text-amber-800">{forecast.basin_rainfall_data_source}</p>}
                  {(forecast?.trajectory || []).some((p: any) => p.discharge_lag_fallback) && <p className="mt-1 rounded border border-amber-200 bg-amber-50 p-2 text-[10px] leading-relaxed text-amber-800">Early forecast days use the nearest available lead time instead of a true historical discharge lag; treat RF probabilities with extra caution.</p>}
                </div>
              </div>
            </div>

            {/* ─── RIGHT COLUMN: PREDICTION DETAILS, TIMELINE & ASSISTANT (8 COLS) ─ */}
            <div className="lg:col-span-9 space-y-5">
              {/* SECTION 1: AI FLOOD RISK PREDICTION OVERVIEW (6 CARDS ROW) */}
              <div className="bg-white rounded-2xl border border-slate-200/90 shadow-sm p-6 space-y-4">
                <h3 className="text-sm font-bold text-slate-900">
                  AI Flood Risk Prediction Overview
                </h3>

                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                  {/* Card 1: Flood Probability */}
                  <div className="bg-slate-50/70 rounded-xl p-3 border border-slate-100 flex flex-col justify-between space-y-2">
                    <Gauge className="w-4 h-4 text-blue-600" />
                    <div>
                      <p className="text-[10px] text-slate-400 font-semibold">{risk?.score_label || 'Flood Risk Estimate'}</p>
                      <p className="text-lg font-extrabold text-slate-900 mt-0.5">{risk?.estimated_risk_percent == null ? '—' : `${Number(risk.estimated_risk_percent).toFixed(1)}%`}</p>
                    </div>
                    <span className={`inline-flex text-[10px] font-bold px-1.5 py-0.5 rounded-md w-fit ${risk?.risk_level === 'HIGH' || risk?.risk_level === 'VERY_HIGH' ? 'text-red-600 bg-red-50' : risk?.risk_level === 'MODERATE' ? 'text-amber-700 bg-amber-50' : risk?.risk_level === 'LOW' ? 'text-emerald-700 bg-emerald-50' : 'text-slate-500 bg-slate-100'}`}>
                      {risk?.risk_level || 'Unavailable'}
                    </span>
                  </div>

                  {/* Card 2: Prediction Confidence */}
                  <div className="bg-slate-50/70 rounded-xl p-3 border border-slate-100 flex flex-col justify-between space-y-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-600" />
                    <div>
                      <p className="text-[10px] text-slate-400 font-semibold">{hasPartialRisk ? 'Prediction basis' : 'Prediction Confidence'}</p>
                      <p className="text-lg font-extrabold text-slate-900 mt-0.5">{hasPartialRisk ? 'Core inputs' : risk?.confidence_score == null ? '—' : `${Number(risk.confidence_score).toFixed(1)}%`}</p>
                    </div>
                    <span className="inline-flex text-[10px] font-bold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-md w-fit">
                      {hasPartialRisk ? 'Validated' : risk?.confidence_score == null ? 'Unavailable' : 'Reported'}
                    </span>
                  </div>

                  {/* Card 3: Expected Onset */}
                  <div className="bg-slate-50/70 rounded-xl p-3 border border-slate-100 flex flex-col justify-between space-y-2">
                    <Calendar className="w-4 h-4 text-amber-500" />
                    <div>
                      <p className="text-[10px] text-slate-400 font-semibold">Expected Onset</p>
                      <p className="text-xs font-extrabold text-slate-900 mt-1">{forecast?.trajectory?.find((p: any) => p.option_b_threshold_flag)?.date || 'No threshold trigger'}</p>
                    </div>
                    <span className="inline-flex text-[10px] font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-md w-fit">
                      {forecast?.trajectory?.some((p: any) => p.option_b_threshold_flag) ? 'Elevated' : 'Baseline'}
                    </span>
                  </div>

                  {/* Card 4: Expected Duration */}
                  <div className="bg-slate-50/70 rounded-xl p-3 border border-slate-100 flex flex-col justify-between space-y-2">
                    <Clock className="w-4 h-4 text-amber-500" />
                    <div>
                      <p className="text-[10px] text-slate-400 font-semibold">Expected Duration</p>
                      <p className="text-xs font-extrabold text-slate-900 mt-1">{forecast?.trajectory?.length ? `${forecast.trajectory.length} days` : 'Unavailable'}</p>
                    </div>
                    <span className="inline-flex text-[10px] font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-md w-fit">
                      API forecast
                    </span>
                  </div>

                  {/* Card 5: Potential Impact */}
                  <div className="bg-slate-50/70 rounded-xl p-3 border border-slate-100 flex flex-col justify-between space-y-2">
                    <AlertTriangle className="w-4 h-4 text-red-600" />
                    <div>
                      <p className="text-[10px] text-slate-400 font-semibold">Potential Impact</p>
                      <p className="text-sm font-extrabold text-slate-900 mt-1">{risk?.risk_level || 'Unavailable'}</p>
                    </div>
                    <span className="inline-flex text-[10px] font-bold text-red-600 bg-red-50 px-1.5 py-0.5 rounded-md w-fit">
                      {risk?.risk_level ? 'API risk level' : 'Unavailable'}
                    </span>
                  </div>

                  {/* Card 6: Risk Trend */}
                  <div className="bg-slate-50/70 rounded-xl p-3 border border-slate-100 flex flex-col justify-between space-y-2">
                    <TrendingUp className="w-4 h-4 text-red-600" />
                    <div>
                      <p className="text-[10px] text-slate-400 font-semibold">Risk Trend</p>
                      <p className="text-xs font-extrabold text-slate-900 mt-1">{forecast?.trajectory?.length ? (forecast.trajectory[forecast.trajectory.length - 1]?.option_b_threshold_flag ? 'Elevated' : 'Stable') : 'Unavailable'}</p>
                    </div>
                    <span className="inline-flex text-[10px] font-bold text-red-600 bg-red-50 px-1.5 py-0.5 rounded-md w-fit">
                      {forecast?.trajectory?.length ? 'API forecast' : 'Unavailable'}
                    </span>
                  </div>
                </div>
              </div>

              {/* SECTION 2: MIDDLE 2 CARDS GRID (TIMELINE & RISK MAP) */}
              <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
                {/* FLOOD RISK TIMELINE CHART CARD (6 COLS) */}
                <div className="md:col-span-6 bg-white rounded-2xl border border-slate-200/90 shadow-sm p-5 space-y-3">
                  <div>
                    <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                      Flood Risk Timeline
                    </h3>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Option B threshold and exploratory RF over the next 5 forecast days
                    </p>
                  </div>

                  {/* Real API trajectory: Option B threshold and exploratory RF are separate. */}
                  <div className="pt-2 pb-1 space-y-2">
                    {(forecast?.trajectory || []).map((point: any) => (
                      <div key={point.date} className="rounded-lg border border-slate-100 p-2">
                        <div className="flex items-center justify-between text-[10px] font-bold text-slate-600"><span>{point.date}</span>{point.method_disagreement && <span className="text-amber-700">⚠ disagreement</span>}</div>
                        <div className="mt-1 grid grid-cols-2 gap-2 text-[10px]">
                          <span className="text-blue-700">Option B: {point.option_b_risk_level} ({point.option_b_threshold_flag ? 'threshold active' : 'threshold quiet'})</span>
                          <span className="text-purple-700">Exploratory RF: {point.classifier_probability == null ? 'unavailable' : `${(Number(point.classifier_probability) * 100).toFixed(1)}%`}</span>
                        </div>
                      </div>
                    ))}
                    {!forecast && <p className="text-[10px] text-slate-500">Forecast is loaded when Step 1 is submitted.</p>}
                  </div>

                  {/* Chart Legend Scale */}
                  <div className="flex items-center justify-between text-[10px] font-semibold text-slate-600 pt-2 border-t border-slate-100">
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Low (&lt;30%)</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-amber-400" /> Moderate (30–60%)</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-500" /> High (60–80%)</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-600" /> Very High (&gt;80%)</span>
                  </div>
                  <div className="mt-3 grid grid-cols-5 gap-1 text-[9px]">
                    {(forecast?.trajectory || []).map((point: any) => <div key={point.date} className="rounded border border-slate-100 p-1 text-center"><b>{String(point.date).slice(5)}</b><br />{point.local_rainfall_3d_mm == null ? 'unavailable' : `${Number(point.local_rainfall_3d_mm).toFixed(1)}mm`}<br /><span className={point.option_b_threshold_flag ? 'text-red-600 font-bold' : 'text-emerald-600'}>{point.option_b_threshold_flag ? 'elevated' : 'baseline'}</span></div>)}
                  </div>
                  {forecast?.basin_rainfall_data_source && <p className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-[10px] text-amber-800"><b>Basin rainfall disclosure:</b> {forecast.basin_rainfall_data_source}</p>}
                  {(forecast?.trajectory || []).some((p: any) => p.discharge_lag_fallback) && <p className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-[10px] text-amber-800"><b>Discharge-lag disclosure:</b> early forecast days use the nearest available lead time in place of a true historical lag - treat these days' RF probability with extra caution.</p>}
                  {(forecast?.trajectory || []).some((p: any) => p.discharge_lag_historical_unavailable) && <p className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-[10px] text-amber-800"><b>Historical-lag disclosure:</b> a required past GloFAS date is not available locally, so the RF probability is withheld for that day.</p>}
                  {forecast && !forecast.glofas_forecast_available && <p className="mt-2 text-[10px] text-amber-700">GloFAS forecast pending; timeline currently shows Open-Meteo rainfall/soil and the independent Option B threshold only.</p>}
                </div>

                {/* RISK MAP (PREDICTED IMPACT) CARD (6 COLS) */}
                <div className="md:col-span-6 bg-white rounded-2xl border border-slate-200/90 shadow-sm overflow-hidden flex flex-col justify-between relative" style={{ height: '300px' }}>
                  <div className="p-4 bg-white/95 backdrop-blur-sm border-b border-slate-100 z-10 flex items-center justify-between">
                    <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                      Far North Risk Zones (Arrondissement-level)
                    </h3>
                    <span className="text-[10px] text-slate-400 font-medium">Terrain susceptibility + event density · SRTM / ReliefWeb</span>
                  </div>

                  {/* Floating Risk Legend Top Right */}
                  <div className="absolute top-14 right-3 z-[1000] bg-white/95 backdrop-blur-sm border border-slate-200/90 p-2.5 rounded-xl shadow-md text-[10px] space-y-1 font-semibold text-slate-700">
                    <p className="font-extrabold uppercase text-slate-400 text-[9px] mb-1 ">Arrondissement Risk</p>
                    <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-red-500" /> High</div>
                    <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-amber-400" /> Moderate</div>
                    <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" /> Low</div>
                    <div className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-blue-600 border-2 border-white" /> Selected locality</div>
                  </div>

                  {/* Far North Administrative Risk-Zone Map — polygons derived from terrain susceptibility and historical event density */}
                  <FarNorthRiskMap coordinates={coordinates} riskLevel={risk?.risk_level as string | undefined} />
                </div>
              </div>

              {/* SECTION 3: BOTTOM 3-COLUMN GRID (IMPACTS, ACTIONS, AI ASSISTANT) */}
              <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
                {/* BOX 1: POTENTIAL IMPACTS (4 COLS) */}
                <div className="md:col-span-4 bg-white rounded-2xl border border-slate-200/90 shadow-sm p-5 space-y-4">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-900 uppercase tracking-wider">
                    <Waves className="w-4 h-4 text-blue-600" />
                    <span>Potential Impacts</span>
                  </div>

                  <div className="space-y-3 text-xs text-slate-700">
                    <div className="flex items-start gap-2.5">
                      <Waves className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                      <p>Flooding of low-lying areas and streets.</p>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <Home className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                      <p>Possible water entry in ground floor buildings.</p>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <Activity className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                      <p>Disruption of transportation and accessibility.</p>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <Droplet className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                      <p>Risk to life and property if proper precautions are not taken.</p>
                    </div>
                  </div>
                </div>

                {/* BOX 2: RECOMMENDED ACTIONS (4 COLS) */}
                <div className="md:col-span-4 bg-white rounded-2xl border border-slate-200/90 shadow-sm p-5 flex flex-col justify-between space-y-4">
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-xs font-bold text-slate-900 uppercase tracking-wider">
                      <ShieldCheck className="w-4 h-4 text-blue-600" />
                      <span>Recommended Actions</span>
                    </div>

                    <div className="space-y-2.5 text-xs text-slate-700">
                      <div className="flex items-start gap-2">
                        <Bell className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
                        <p>Stay informed and monitor alerts regularly.</p>
                      </div>
                      <div className="flex items-start gap-2">
                        <Compass className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
                        <p>Avoid flood-prone areas and unnecessary travel.</p>
                      </div>
                      <div className="flex items-start gap-2">
                        <Home className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
                        <p>Elevate electrical appliances and important documents.</p>
                      </div>
                      <div className="flex items-start gap-2">
                        <FileCheck className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
                        <p>Prepare an emergency kit and safe evacuation plan.</p>
                      </div>
                      <div className="flex items-start gap-2">
                        <CheckCircle2 className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
                        <p>Follow instructions from local authorities.</p>
                      </div>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-slate-100 text-center">
                    <button className="text-xs font-bold text-blue-600 hover:text-blue-800 inline-flex items-center gap-1 transition-colors cursor-pointer">
                      <span>View All Safety Guidelines</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* BOX 3: EMBEDDED AI ASSISTANT CHATBOT (4 COLS) */}
                <div className="md:col-span-4 bg-white rounded-2xl border border-slate-200/90 shadow-sm p-4 flex flex-col justify-between space-y-3">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                        <Bot className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="text-xs font-bold text-slate-900 leading-none">AI Assistant</h4>
                        <p className="text-[9px] text-slate-400 font-semibold mt-0.5">Powered by AquaGuard AI</p>
                      </div>
                    </div>
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Online
                    </span>
                  </div>

                  {/* Chat Messages Body */}
                  <div className="space-y-2 max-h-40 overflow-y-auto pr-1 text-xs scrollbar-none">
                    {aiMessages.map((msg, idx) => (
                      <div key={idx} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <div
                          className={`max-w-[90%] rounded-xl p-2.5 text-[11px] leading-relaxed ${
                            msg.sender === 'user'
                              ? 'bg-blue-600 text-white font-medium'
                              : 'bg-slate-50 text-slate-700 border border-slate-100 font-normal'
                          }`}
                        >
                          {msg.text}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Suggested Question Chips */}
                  <div className="space-y-1.5 pt-1">
                    {[
                      'What makes the flood risk high in my area?',
                      'How accurate is this prediction?',
                      'What should I do to protect my home?',
                      'Which areas nearby are most at risk?'
                    ].map((chip, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSendChat(chip)}
                        className="w-full text-left text-[10px] font-medium text-blue-700 bg-blue-50/70 hover:bg-blue-100 border border-blue-100 px-2.5 py-1 rounded-lg transition-colors truncate cursor-pointer"
                      >
                        {chip}
                      </button>
                    ))}
                  </div>

                  {/* Chat Input Bar */}
                  <div className="relative pt-1">
                    <input
                      type="text"
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleSendChat()}
                      placeholder="Type your question..."
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 pr-9 text-xs text-slate-800 font-medium placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <button
                      onClick={() => handleSendChat()}
                      className="absolute right-1.5 top-2.5 p-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors cursor-pointer"
                    >
                      <Send className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>

              {/* SECTION 4: BOTTOM ACTION FOOTER BAR */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-slate-200/70 lg:relative lg:-left-[calc(33.333%+6.667px)] lg:w-[calc(133.333%+6.667px)]">
                <button
                  onClick={() => changeStep(2)}
                  className="w-full sm:w-auto shrink-0 whitespace-nowrap bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 font-semibold text-xs py-3 px-5 rounded-xl shadow-xs transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  <ArrowLeft className="w-4 h-4" />
                  <span>Back to Environmental Context</span>
                </button>

                {/* Center Banner */}
                <div className="flex shrink-0 items-center gap-1.5 whitespace-nowrap text-xs text-slate-500 text-center font-medium">
                  <Info className="w-4 h-4 text-blue-600 shrink-0" />
                  <span>This prediction is generated using AI and multiple data sources. Results may change with new data.</span>
                </div>

                <div className="w-full sm:w-auto flex items-center gap-3">
                  <button
                    onClick={() => alert('Downloading prediction report...')}
                    className="flex-1 sm:flex-initial bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 font-semibold text-xs py-3 px-5 rounded-xl shadow-xs transition-all flex items-center justify-center gap-2 cursor-pointer"
                  >
                    <Download className="w-4 h-4 text-slate-500" />
                    <span>Download Prediction Report</span>
                  </button>

                  <button
                    onClick={handleConfirmAndViewDashboard}
                    disabled={loadingAction === 'saving'}
                    className="flex-1 sm:flex-initial bg-[#0f2460] hover:bg-[#0a1c4e] text-white font-bold text-xs py-3 px-6 rounded-xl shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer group disabled:cursor-wait disabled:opacity-70"
                  >
                    {loadingAction === 'saving' ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />}
                    <span>{loadingAction === 'saving' ? 'Saving assessment…' : user ? 'Confirm & Review' : 'Confirm & View Dashboard'}</span>
                  </button>
                </div>
              </div>
              {loadingError && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-center text-xs font-semibold text-red-700">{loadingError}</p>}
            </div>
          </div>
        </main>
      )}
    </div>
  )
}
