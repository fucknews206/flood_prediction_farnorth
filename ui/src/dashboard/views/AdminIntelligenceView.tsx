'use client'

import { useState, useEffect } from 'react'
import {
  Bot,
  Map as MapIcon,
  AlertTriangle,
  MapPin,
  TrendingUp,
  RefreshCw,
  ExternalLink,
  Shield,
  CheckCircle2,
} from 'lucide-react'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { adminApi, type AdminAnalytics } from '@/lib/api'

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

const farNorthLocalities = [
  { name: 'Kousséri', division: 'Logone-et-Chari', lat: 12.08, lng: 15.03, risk: 'Medium (64.7%)', status: 'Active' },
  { name: 'Maga', division: 'Mayo-Danay', lat: 10.83, lng: 14.95, risk: 'Medium (54.9%)', status: 'Active' },
  { name: 'Dougui', division: 'Logone-et-Chari', lat: 10.97, lng: 14.88, risk: 'Medium (62.3%)', status: 'Active' },
  { name: 'Artano', division: 'Logone-et-Chari', lat: 12.20, lng: 14.50, risk: 'Report Submitted', status: 'Monitored' },
  { name: 'Yagoua', division: 'Mayo-Danay', lat: 10.34, lng: 15.23, risk: 'Baseline / Low', status: 'Monitored' },
  { name: 'Maroua', division: 'Diamaré', lat: 10.59, lng: 14.33, risk: 'Baseline / Low', status: 'Monitored' },
  { name: 'Mokolo', division: 'Mayo-Tsanaga', lat: 10.74, lng: 13.80, risk: 'Baseline / Low', status: 'Monitored' },
  { name: 'Mora', division: 'Mayo-Sava', lat: 11.04, lng: 14.14, risk: 'Baseline / Low', status: 'Monitored' },
]

interface AdminIntelligenceViewProps {
  type: 'predictions' | 'map' | 'zones'
}

export default function AdminIntelligenceView({ type }: AdminIntelligenceViewProps) {
  const [analytics, setAnalytics] = useState<AdminAnalytics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    adminApi.getAnalytics()
      .then(setAnalytics)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      {/* HEADER */}
      <div>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#0B172A] text-blue-400 font-bold text-[11px] tracking-wider uppercase mb-2 shadow-xs">
          {type === 'predictions' && <Bot className="h-3.5 w-3.5 text-blue-400" />}
          {type === 'map' && <MapIcon className="h-3.5 w-3.5 text-blue-400" />}
          {type === 'zones' && <AlertTriangle className="h-3.5 w-3.5 text-blue-400" />}
          <span>
            {type === 'predictions'
              ? 'FAR NORTH PREDICTIONS'
              : type === 'map'
              ? 'FAR NORTH FLOOD RISK MAP'
              : 'FLOOD-PRONE ZONES'}
          </span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight leading-tight">
          {type === 'predictions'
            ? 'Far North Predictions'
            : type === 'map'
            ? 'Far North Flood Risk Map'
            : 'Flood-Prone Zones'}
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 font-medium mt-1">
          Operational hydrological intelligence and risk assessments for Far North Cameroon.
        </p>
      </div>

      {type === 'map' ? (
        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs h-[560px] relative overflow-hidden">
          <MapContainer
            center={[11.5, 14.8]}
            zoom={7}
            scrollWheelZoom={true}
            className="h-full w-full rounded-xl"
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {farNorthLocalities.map((loc, idx) => (
              <Marker
                key={idx}
                position={[loc.lat, loc.lng]}
                icon={createCustomIcon(
                  loc.risk.includes('Medium') ? '#F59E0B' : loc.risk.includes('Report') ? '#3B82F6' : '#10B981',
                  loc.name
                )}
              >
                <Popup>
                  <div className="p-1 font-sans text-xs">
                    <p className="font-bold text-slate-900">{loc.name}</p>
                    <p className="text-slate-500">Division: {loc.division}</p>
                    <p className="font-semibold text-amber-600 mt-1">{loc.risk}</p>
                  </div>
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        </div>
      ) : type === 'zones' ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
          <div className="p-4 border-b border-slate-100 flex items-center justify-between">
            <h3 className="font-bold text-slate-900 text-sm">Monitored Far North Localities & Basins</h3>
            <span className="text-xs text-slate-500 font-medium">34 Operational Entities</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-extrabold uppercase text-[10px] tracking-wider border-b border-slate-200/80">
                <tr>
                  <th className="p-4">Locality Name</th>
                  <th className="p-4">Division</th>
                  <th className="p-4">Coordinates</th>
                  <th className="p-4">Current Risk Status</th>
                  <th className="p-4 text-right">Engine State</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium text-slate-700">
                {farNorthLocalities.map((loc, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/80 transition-colors">
                    <td className="p-4 font-bold text-slate-900">{loc.name}</td>
                    <td className="p-4 text-slate-600">{loc.division}</td>
                    <td className="p-4 font-mono text-slate-500">{loc.lat.toFixed(2)}°N, {loc.lng.toFixed(2)}°E</td>
                    <td className="p-4">
                      <span className="px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 font-bold text-[10px] border border-amber-200">
                        {loc.risk}
                      </span>
                    </td>
                    <td className="p-4 text-right">
                      <span className="inline-flex items-center gap-1 text-emerald-600 font-bold text-xs">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        {loc.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* PREDICTIONS TAB */
        <div className="space-y-4">
          <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs">
            <h3 className="font-bold text-slate-900 text-sm mb-3">Stored Prediction Records</h3>
            {analytics?.recent_predictions && analytics.recent_predictions.length > 0 ? (
              <div className="space-y-3">
                {analytics.recent_predictions.map(pred => (
                  <div key={pred.id} className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80 flex items-center justify-between text-xs">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-900">{pred.locality}</span>
                        <span className="px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 font-bold text-[10px]">
                          {pred.risk_level} ({Number(pred.estimated_risk_percent).toFixed(1)}%)
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500 mt-1">
                        Citizen User: {pred.user_id} · Recorded: {new Date(pred.created_at).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-400 text-xs py-6 text-center">Loading stored prediction records…</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
