'use client'

import { useEffect, useState, useRef } from 'react'
import { MapContainer, TileLayer, GeoJSON, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Watershed, GeoJSONFeatureCollection, CommunityReport } from '@/lib/api'
import { geoApi, communityReportsApi } from '@/lib/api'

// ─── RainViewer live radar tile (same pattern as AssessFloodRiskPage) ────────────
function RainViewerGWLayer() {
  const [radarBase, setRadarBase] = useState<string | null>(null)
  useEffect(() => {
    const refresh = () =>
      fetch('https://api.rainviewer.com/public/weather-maps.json')
        .then(r => r.json())
        .then(m => { const past = m?.radar?.past ?? []; const frame = past[past.length - 1]; if (frame) { const host = String(m?.host || 'https://tilecache.rainviewer.com').replace(/\/$/, ''); setRadarBase(`${host}${frame.path || `/v2/radar/${frame.time}`}`) } })
        .catch(() => {})
    refresh()
    const id = setInterval(refresh, 120_000)
    return () => clearInterval(id)
  }, [])
  if (!radarBase) return null
  return (
    <TileLayer
      key={`rv-gw-${radarBase}`}
      url={`${radarBase}/256/{z}/{x}/{y}/2/1_1.png`}
      attribution='&copy; <a href="https://rainviewer.com">RainViewer</a>'
      opacity={0.55}
      zIndex={350}
    />
  )
}

// ─── NASA OPERA DSWx-S1 SAR surface water extent tile layer ─────────────────
const OPERA_SAR_TILE_URL =
  'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/OPERA_L3_Dynamic_Surface_Water_Extent-Sentinel-1/default/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png'

function OperaDSWxGWLayer() {
  return (
    <TileLayer
      key="opera-dswx-gw"
      url={OPERA_SAR_TILE_URL}
      attribution='&copy; <a href="https://earthdata.nasa.gov">NASA GIBS</a> OPERA DSWx-S1 SAR'
      opacity={0.65}
      zIndex={360}
    />
  )
}
// ─────────────────────────────────────────────────────────────────────────────

// Fix for default markers in React-Leaflet
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
    iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
    iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
})

// Cameroon default coordinates
const CAMEROON_CENTER: [number, number] = [7.37, 12.35]
const CAMEROON_ZOOM = 6

// Custom risk-based basin fill colours
const BASIN_RISK_COLORS: Record<string, string> = {
    'High':     '#ef4444',
    'Moderate': '#f59e0b',
    'Low':      '#22c55e',
    'Unknown':  '#6b7280',
}

const createReportIcon = () =>
    L.divIcon({
        html: `<div style="
            background-color: #3b82f6;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 2px solid white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.4);
        "></div>`,
        className: 'custom-div-icon',
        iconSize: [14, 14],
        iconAnchor: [7, 7],
    })

// Component to fly to Cameroon once on mount
const MapController = ({ center, zoom }: { center: [number, number]; zoom: number }) => {
    const map = useMap()
    useEffect(() => {
        map.setView(center, zoom)
    }, [center, zoom, map])
    return null
}

interface GlobalWatershedMapProps {
    watersheds?: Watershed[]
    height?: string
    center?: [number, number]
    zoom?: number
    onWatershedClick?: (watershed: Watershed) => void
}

export default function GlobalWatershedMap({
    watersheds = [],
    height = '400px',
    center = CAMEROON_CENTER,
    zoom = CAMEROON_ZOOM,
    onWatershedClick,
}: GlobalWatershedMapProps) {
    const [mounted, setMounted]           = useState(false)
    const [regionsGeo, setRegionsGeo]     = useState<GeoJSONFeatureCollection | null>(null)
    const [basinsGeo, setBasinsGeo]       = useState<GeoJSONFeatureCollection | null>(null)
    const [farNorthGeo, setFarNorthGeo]   = useState<GeoJSONFeatureCollection | null>(null)
    const [showFarNorth, setShowFarNorth] = useState(true)
    const [showRadar, setShowRadar]       = useState(true)
    const [showSAR, setShowSAR]           = useState(false)
    const [reports, setReports]           = useState<CommunityReport[]>([])
    const [geoError, setGeoError]         = useState<string | null>(null)
    const regionsLayerRef                 = useRef<L.GeoJSON | null>(null)
    const basinsLayerRef                  = useRef<L.GeoJSON | null>(null)
    const farNorthLayerRef                = useRef<L.GeoJSON | null>(null)

    useEffect(() => { setMounted(true) }, [])

    useEffect(() => {
        if (!mounted) return
        // Fetch region boundaries
        geoApi.getRegions()
            .then(setRegionsGeo)
            .catch(err => setGeoError(`Regions: ${err.message}`))

        // Fetch basin polygons
        geoApi.getBasins()
            .then(setBasinsGeo)
            .catch(err => setGeoError(`Basins: ${err.message}`))

        // Fetch Far North arrondissement risk zones
        geoApi.getFarNorthRiskZones()
            .then(setFarNorthGeo)
            .catch(err => console.warn('Far North risk zones load:', err))

        // Fetch recent community reports
        communityReportsApi.getRecent()
            .then(setReports)
            .catch(() => { /* silent — community reports are optional */ })
    }, [mounted])

    if (!mounted) {
        return (
            <div className="bg-gray-100 dark:bg-gray-800 rounded-lg flex items-center justify-center" style={{ height }}>
                <div className="text-gray-500 dark:text-gray-400">Loading Cameroon map…</div>
            </div>
        )
    }

    // Basin polygon style
    const basinStyle = (feature: any) => {
        const risk  = feature?.properties?.current_risk_level || 'Unknown'
        const color = BASIN_RISK_COLORS[risk] || BASIN_RISK_COLORS.Unknown
        return {
            fillColor:   color,
            fillOpacity: 0.35,
            color:       color,
            weight:      1.5,
            opacity:     0.8,
        }
    }

    // Region boundary style — thin grey outline only
    const regionStyle = () => ({
        fillColor:   'transparent',
        fillOpacity: 0,
        color:       '#9ca3af',
        weight:      1,
        opacity:     0.7,
    })

    // Popup for each basin feature
    const onEachBasin = (feature: any, layer: L.Layer) => {
        const p = feature.properties || {}
        const isPartial   = p.data_completeness === 'partial'
        const noDischarge = p.discharge_status !== 'available'
        const scoreLabel  = isPartial ? `${p.risk_score} / 10 (partial)` : `${p.risk_score} / 10`
        const dischargeBadge = noDischarge
            ? `<span style="background:#fef3c7;color:#92400e;padding:1px 5px;border-radius:4px;font-size:11px;">⚠ Discharge data unavailable</span>`
            : ''
        const flowLabel = p.current_streamflow_cms != null
            ? `${Number(p.current_streamflow_cms).toFixed(2)} m³/s`
            : '—'

        const html = `
            <div style="min-width:200px;padding:4px">
                <strong style="font-size:13px">${p.name || 'Unknown Basin'}</strong>
                ${dischargeBadge ? `<div style="margin:4px 0">${dischargeBadge}</div>` : ''}
                <table style="width:100%;font-size:12px;margin-top:4px;border-collapse:collapse">
                    <tr><td style="color:#6b7280">Risk Score</td><td style="font-weight:600;text-align:right">${scoreLabel}</td></tr>
                    <tr><td style="color:#6b7280">Risk Level</td><td style="font-weight:600;text-align:right">${p.current_risk_level || '—'}</td></tr>
                    <tr><td style="color:#6b7280">Streamflow</td><td style="text-align:right">${flowLabel}</td></tr>
                    <tr><td style="color:#6b7280">Basin area</td><td style="text-align:right">${p.basin_size_sqkm ? Number(p.basin_size_sqkm).toLocaleString() + ' km²' : '—'}</td></tr>
                </table>
            </div>`

        layer.bindPopup(html)

        layer.on('mouseover', () => (layer as L.Path).setStyle({ fillOpacity: 0.6 }))
        layer.on('mouseout',  () => (layer as L.Path).setStyle({ fillOpacity: 0.35 }))
    }

    // Popup for each region
    const onEachRegion = (feature: any, layer: L.Layer) => {
        const p = feature.properties || {}
        layer.bindTooltip(p.name || p.name_fr || '', { permanent: false, direction: 'center' })
    }

    // Far North Arrondissement risk zone style
    const farNorthStyle = (feature: any) => {
        const risk  = feature?.properties?.risk_level || 'Low'
        const color = BASIN_RISK_COLORS[risk] || BASIN_RISK_COLORS.Low
        return {
            fillColor:   color,
            fillOpacity: 0.42,
            color:       color,
            weight:      1.5,
            opacity:     0.85,
        }
    }

    // Popup for Far North Arrondissement feature
    const onEachFarNorth = (feature: any, layer: L.Layer) => {
        const p = feature.properties || {}
        const r = p.risk_level || 'Low'
        const col = BASIN_RISK_COLORS[r] || BASIN_RISK_COLORS.Low
        const locality = p.name || p.name_fr || 'Far North Zone'
        const lat = p.center_lat ?? p.latitude
        const lon = p.center_lon ?? p.longitude
        const queryParams = new URLSearchParams()
        if (lat != null && lon != null) {
            queryParams.set('lat', String(lat))
            queryParams.set('lon', String(lon))
        }
        queryParams.set('locality', locality)
        const assessUrl = `/assess-flood-risk?${queryParams.toString()}`

        const html = `
            <div style="min-width:210px;padding:4px;font-family:sans-serif">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
                    <strong style="font-size:13px;color:#1e293b">${locality}</strong>
                    <span style="background:${col}22;color:${col};border:1px solid ${col}66;padding:1px 6px;border-radius:9999px;font-size:11px;font-weight:700">
                        ${r}
                    </span>
                </div>
                <div style="font-size:11px;color:#64748b;margin-bottom:6px">Far North Arrondissement (Admin-3)</div>
                <table style="width:100%;font-size:12px;margin-bottom:8px;border-collapse:collapse">
                    <tr><td style="color:#64748b;padding:2px 0">Risk Score</td><td style="font-weight:600;text-align:right;color:#0f172a">${p.risk_score ?? '—'}/100</td></tr>
                    <tr><td style="color:#64748b;padding:2px 0">Historical Events</td><td style="font-weight:600;text-align:right;color:#0f172a">${p.historical_events ?? 0}</td></tr>
                    ${p.terrain_susceptibility != null ? `<tr><td style="color:#64748b;padding:2px 0">Terrain Suscept.</td><td style="font-weight:600;text-align:right;color:#0f172a">${p.terrain_susceptibility}</td></tr>` : ''}
                </table>
                <a href="${assessUrl}" style="display:block;text-align:center;background:#2563eb;color:#ffffff;text-decoration:none;padding:6px 10px;border-radius:6px;font-size:11px;font-weight:600">
                    Assess Locality Risk &rarr;
                </a>
            </div>`

        layer.bindPopup(html)
        layer.on('mouseover', () => (layer as L.Path).setStyle({ fillOpacity: 0.65 }))
        layer.on('mouseout',  () => (layer as L.Path).setStyle({ fillOpacity: 0.42 }))
    }

    return (
        <div style={{ height }} className="rounded-lg overflow-hidden relative">
            {geoError && (
                <div className="absolute top-2 left-2 z-[1000] bg-red-100 text-red-800 text-xs px-2 py-1 rounded shadow">
                    ⚠ {geoError}
                </div>
            )}

            {/* Layer Toggle Controls */}
            <div className="absolute top-3 right-3 z-[1000] flex items-center gap-2 bg-white/95 backdrop-blur-md border border-slate-200 p-1.5 rounded-xl shadow-xs">
                <button
                    type="button"
                    onClick={() => setShowRadar(!showRadar)}
                    className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1.5 ${
                        showRadar
                            ? 'bg-indigo-600 text-white shadow-xs'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                    title="Toggle RainViewer live satellite radar"
                >
                    <span className="text-sm">📡</span>
                    Radar {showRadar ? '(ON)' : '(OFF)'}
                </button>
                <button
                    type="button"
                    onClick={() => setShowSAR(!showSAR)}
                    className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1.5 ${
                        showSAR
                            ? 'bg-cyan-600 text-white shadow-xs'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                    title="Toggle NASA OPERA Sentinel-1 SAR flood inundation overlay"
                >
                    <span className="text-sm">🛰️</span>
                    SAR Floods {showSAR ? '(ON)' : '(OFF)'}
                </button>
                <button
                    type="button"
                    onClick={() => setShowFarNorth(!showFarNorth)}
                    className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-all flex items-center gap-1.5 ${
                        showFarNorth
                            ? 'bg-blue-600 text-white shadow-xs'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                    title="Toggle Far North Arrondissement Risk Zones"
                >
                    <span className={`w-2 h-2 rounded-full ${showFarNorth ? 'bg-white' : 'bg-slate-400'}`} />
                    Far North Zones {showFarNorth ? '(ON)' : '(OFF)'}
                </button>
            </div>

            <MapContainer
                center={center}
                zoom={zoom}
                style={{ height: '100%', width: '100%' }}
                className="rounded-lg"
            >
                <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />

                {/* RainViewer live radar overlay */}
                {showRadar && <RainViewerGWLayer />}

                {/* NASA OPERA Sentinel-1 SAR flood inundation overlay */}
                {showSAR && <OperaDSWxGWLayer />}

                <MapController center={center} zoom={zoom} />

                {/* Region boundary layer */}
                {regionsGeo && (
                    <GeoJSON
                        key="regions"
                        data={regionsGeo as any}
                        style={regionStyle}
                        onEachFeature={onEachRegion}
                        ref={regionsLayerRef}
                    />
                )}

                {/* Basin polygon layer (coloured by risk) */}
                {basinsGeo && (
                    <GeoJSON
                        key="basins"
                        data={basinsGeo as any}
                        style={basinStyle}
                        onEachFeature={onEachBasin}
                        ref={basinsLayerRef}
                    />
                )}

                {/* Far North Arrondissement Risk Zone layer */}
                {showFarNorth && farNorthGeo && (
                    <GeoJSON
                        key="farnorth-risk-zones"
                        data={farNorthGeo as any}
                        style={farNorthStyle}
                        onEachFeature={onEachFarNorth}
                        ref={farNorthLayerRef}
                    />
                )}

                {/* Community report point markers */}
                {reports.map(r => (
                    <Marker
                        key={`report-${r.id}`}
                        position={[r.location_lat, r.location_lng]}
                        icon={createReportIcon()}
                    >
                        <Popup>
                            <div style={{ minWidth: 160, fontSize: 12 }}>
                                <strong>Community Report #{r.id}</strong>
                                <p style={{ margin: '4px 0' }}>{r.details}</p>
                                {r.region && <div><span style={{ color: '#6b7280' }}>Region: </span>{r.region}</div>}
                                {r.department && <div><span style={{ color: '#6b7280' }}>Dept: </span>{r.department}</div>}
                                {r.risk_level && (
                                    <div><span style={{ color: '#6b7280' }}>Risk: </span>
                                        <span style={{
                                            background: r.risk_level === 'High' ? '#fee2e2' : r.risk_level === 'Moderate' ? '#fef3c7' : '#dcfce7',
                                            color:      r.risk_level === 'High' ? '#991b1b' : r.risk_level === 'Moderate' ? '#92400e' : '#166534',
                                            padding: '1px 5px', borderRadius: 4
                                        }}>{r.risk_level}</span>
                                    </div>
                                )}
                            </div>
                        </Popup>
                    </Marker>
                ))}

                {/* Watershed point markers (if provided) */}
                {watersheds.filter(w => w.location_lat && w.location_lng).map(w => (
                    <Marker
                        key={`ws-${w.id}`}
                        position={[w.location_lat!, w.location_lng!]}
                        icon={L.divIcon({
                            html: `<div style="background:${BASIN_RISK_COLORS[w.current_risk_level]||'#6b7280'};width:12px;height:12px;border-radius:50%;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,.35)"></div>`,
                            className: 'custom-div-icon',
                            iconSize: [12, 12],
                            iconAnchor: [6, 6],
                        })}
                        eventHandlers={{ click: () => onWatershedClick?.(w) }}
                    >
                        <Popup>
                            <div style={{ minWidth: 180, fontSize: 12 }}>
                                <strong>{w.name}</strong>
                                {w.discharge_status && w.discharge_status !== 'available' && (
                                    <div style={{ background: '#fef3c7', color: '#92400e', padding: '2px 5px', borderRadius: 4, marginTop: 4, fontSize: 11 }}>
                                        ⚠ Discharge data unavailable
                                    </div>
                                )}
                                <table style={{ width: '100%', marginTop: 4, borderCollapse: 'collapse' }}>
                                    <tbody>
                                        <tr>
                                            <td style={{ color: '#6b7280' }}>Risk Score</td>
                                            <td style={{ textAlign: 'right', fontWeight: 600 }}>
                                                {w.risk_score}/10{w.data_completeness === 'partial' ? ' (partial)' : ''}
                                            </td>
                                        </tr>
                                        <tr>
                                            <td style={{ color: '#6b7280' }}>Streamflow</td>
                                            <td style={{ textAlign: 'right' }}>{w.current_streamflow_cms.toFixed(2)} m³/s</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </Popup>
                    </Marker>
                ))}
            </MapContainer>
        </div>
    )
}
