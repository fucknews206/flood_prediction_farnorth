import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import type { LatLngTuple } from 'leaflet'

/** Generic Cameroon map with no fabricated fallback watershed data. */
interface MapViewProps {
  watersheds?: Array<{ name?: string; latitude?: number; longitude?: number }>
  alerts?: unknown[]
  loading?: boolean
  refreshData?: () => void
}

const CAMEROON_CENTER: LatLngTuple = [7.37, 12.35]

export default function MapView({ watersheds = [], loading = false }: MapViewProps) {
  const points = watersheds.filter((w) => Number.isFinite(Number(w.latitude)) && Number.isFinite(Number(w.longitude)))
  return (
    <div className="relative h-[600px] w-full overflow-hidden rounded-lg">
      <MapContainer center={CAMEROON_CENTER} zoom={6} scrollWheelZoom style={{ height: '100%', width: '100%' }}>
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {points.map((point, index) => {
          const position: LatLngTuple = [Number(point.latitude), Number(point.longitude)]
          return <CircleMarker key={`${point.name || 'point'}-${index}`} center={position} radius={8} pathOptions={{ color: '#2563eb', fillColor: '#3b82f6', fillOpacity: 0.7 }}><Popup>{point.name || 'Far North locality'}</Popup></CircleMarker>
        })}
      </MapContainer>
      {loading && <div className="absolute left-3 top-3 z-[1000] rounded bg-white/90 px-3 py-2 text-xs text-slate-700">Loading real map data…</div>}
      {!loading && points.length === 0 && <div className="absolute bottom-3 left-3 z-[1000] rounded bg-white/90 px-3 py-2 text-xs text-slate-700">No monitored locality points are available.</div>}
    </div>
  )
}
