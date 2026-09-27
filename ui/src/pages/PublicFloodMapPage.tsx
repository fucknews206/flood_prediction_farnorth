import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
    AlertTriangle,
    RefreshCw,
    Activity,
    Droplets,
    Globe
} from 'lucide-react'
import { dashboardApi, type DashboardData, type Watershed } from '@/lib/api'
import GlobalWatershedMap from '@/components/GlobalWatershedMap'

export default function PublicFloodMapPage() {
    const navigate = useNavigate()
    const [lang, setLang] = useState<'English' | 'Français'>('English')
    const [dashboardData, setDashboardData] = useState<DashboardData | null>(null)
    const [selectedWatershed, setSelectedWatershed] = useState<Watershed | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const fetchData = async () => {
        setIsLoading(true)
        setError(null)
        try {
            const data = await dashboardApi.getDashboardData()
            setDashboardData(data)
        } catch (err) {
            console.error('Failed to load flood map data:', err)
            setError('Unable to load latest watershed data. Using cached/local data.')
        } finally {
            setIsLoading(false)
        }
    }

    useEffect(() => {
        fetchData()
    }, [])

    const summary = dashboardData?.summary
    const watersheds = dashboardData?.watersheds || []

    return (
        <div className="min-h-screen bg-slate-50 font-sans text-slate-900 flex flex-col">
            {/* Public Header matching Landing Page */}
            <header className="sticky top-0 z-50 bg-white border-b border-slate-200 shadow-xs">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
                    {/* Logo */}
                    <div
                        className="flex items-center gap-2.5 cursor-pointer select-none"
                        onClick={() => navigate('/')}
                    >
                        <div className="w-8 h-8 rounded-lg bg-[#0f2460] flex items-center justify-center shadow">
                            <Droplets className="w-4 h-4 text-white" />
                        </div>
                        <div className="leading-tight">
                            <p className="font-bold text-slate-900 text-sm tracking-tight">AquaGuard AI</p>
                            <p className="text-[10px] text-slate-500 -mt-0.5">Cameroon Flood Intel</p>
                        </div>
                    </div>

                    {/* Center nav pills */}
                    <nav className="hidden md:flex items-center gap-1 bg-slate-100 px-1 py-1 rounded-full text-sm font-medium">
                        <button
                            onClick={() => navigate('/')}
                            className="px-4 py-1 rounded-full text-slate-500 hover:text-slate-800 text-xs transition-colors cursor-pointer"
                        >
                            Platform Overview
                        </button>
                        <button
                            onClick={() => navigate('/#methodology')}
                            className="px-4 py-1 rounded-full text-slate-500 hover:text-slate-800 text-xs transition-colors cursor-pointer"
                        >
                            Methodology
                        </button>
                        <button
                            onClick={() => setLang(lang === 'English' ? 'Français' : 'English')}
                            className="flex items-center gap-1 px-3 py-1 rounded-full text-slate-500 hover:text-slate-800 text-xs transition-colors border-l border-slate-300 ml-1 pl-3 cursor-pointer"
                        >
                            <Globe className="w-3 h-3" />
                            {lang}
                        </button>
                    </nav>

                    {/* Right actions */}
                    <div className="flex items-center gap-2">
                        <button
                            onClick={fetchData}
                            disabled={isLoading}
                            className="hidden sm:flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 bg-white border border-slate-200 px-3 py-1.5 rounded-full shadow-xs transition-colors cursor-pointer"
                            title="Refresh map data"
                        >
                            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-blue-600' : ''}`} />
                            <span>Refresh</span>
                        </button>

                        <button
                            onClick={() => navigate('/login')}
                            className="bg-[#0f2460] hover:bg-[#0a1c4e] text-white text-xs font-semibold px-4 py-2 rounded-full shadow transition-all cursor-pointer"
                        >
                            Access Portal
                        </button>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 flex flex-col gap-5">
                {/* Title & Stats Ribbon */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
                    <div>
                        <div className="flex items-center gap-2">
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
                                <Activity className="w-3 h-3" /> Live Hydrological Monitoring
                            </span>
                            {summary?.last_updated && (
                                <span className="text-[11px] text-slate-400">
                                    Updated: {new Date(summary.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                </span>
                            )}
                        </div>
                        <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight mt-1">
                            Cameroon Flood Risk Map
                        </h1>
                        <p className="text-xs text-slate-500 mt-0.5">
                            Real-time hydrological basin monitoring, risk classifications, and satellite telemetry across Cameroon.
                        </p>
                    </div>

                    {/* Summary Badges */}
                    <div className="flex items-center gap-3 flex-wrap">
                        <div className="bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2">
                            <p className="text-[10px] font-bold uppercase text-slate-400">Monitored Basins</p>
                            <p className="text-lg font-black text-slate-800">{summary?.total_watersheds ?? watersheds.length}</p>
                        </div>
                        <div className="bg-red-50 border border-red-200 rounded-xl px-3.5 py-2">
                            <p className="text-[10px] font-bold uppercase text-red-500">High Risk</p>
                            <p className="text-lg font-black text-red-600">{summary?.high_risk_watersheds ?? 0}</p>
                        </div>
                        <div className="bg-amber-50 border border-amber-200 rounded-xl px-3.5 py-2">
                            <p className="text-[10px] font-bold uppercase text-amber-600">Moderate Risk</p>
                            <p className="text-lg font-black text-amber-600">{summary?.moderate_risk_watersheds ?? 0}</p>
                        </div>
                        <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-3.5 py-2">
                            <p className="text-[10px] font-bold uppercase text-emerald-600">Low Risk</p>
                            <p className="text-lg font-black text-emerald-600">{summary?.low_risk_watersheds ?? 0}</p>
                        </div>
                    </div>
                </div>

                {error && (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-center gap-2.5 text-xs text-amber-800">
                        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                        <span>{error}</span>
                    </div>
                )}

                {/* Map Grid */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 flex-1 items-start">
                    {/* Interactive Map (8 or 12 cols depending on selection) */}
                    <div className={`${selectedWatershed ? 'lg:col-span-8' : 'lg:col-span-12'} bg-white rounded-2xl border border-slate-200 p-2 shadow-xs overflow-hidden transition-all duration-300`}>
                        <div className="relative w-full h-[540px] rounded-xl overflow-hidden">
                            {/* Legend Card */}
                            <div className="absolute top-3 left-3 z-[1000] bg-white/95 backdrop-blur-md border border-slate-200 p-3 rounded-xl text-xs space-y-1.5 shadow-sm font-semibold text-slate-700">
                                <p className="text-[10px] font-bold uppercase text-slate-400 tracking-wider">Risk Legend</p>
                                <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-red-500" /> High Risk</div>
                                <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-amber-500" /> Moderate Risk</div>
                                <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-emerald-500" /> Low Risk</div>
                                <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-blue-500" /> Community Report</div>
                            </div>

                            <GlobalWatershedMap
                                watersheds={watersheds}
                                height="100%"
                                onWatershedClick={(ws) => setSelectedWatershed(ws)}
                            />
                        </div>
                    </div>

                    {/* Selected Watershed Details Drawer */}
                    {selectedWatershed && (
                        <div className="lg:col-span-4 bg-white rounded-2xl border border-slate-200 p-5 shadow-xs space-y-4">
                            <div className="flex items-start justify-between">
                                <div>
                                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Selected Basin</span>
                                    <h3 className="text-base font-extrabold text-slate-900 mt-0.5">{selectedWatershed.name}</h3>
                                    <p className="text-xs text-slate-500">{selectedWatershed.region || 'Cameroon'} Region</p>
                                </div>
                                <button
                                    onClick={() => setSelectedWatershed(null)}
                                    className="text-xs text-slate-400 hover:text-slate-600 p-1"
                                >
                                    ✕
                                </button>
                            </div>

                            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-2 text-xs">
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Risk Level</span>
                                    <span className={`font-bold ${
                                        selectedWatershed.current_risk_level === 'High' ? 'text-red-600' :
                                        selectedWatershed.current_risk_level === 'Moderate' ? 'text-amber-600' : 'text-emerald-600'
                                    }`}>
                                        {selectedWatershed.current_risk_level || 'Low'}
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Current Streamflow</span>
                                    <span className="font-bold text-slate-700">
                                        {selectedWatershed.current_streamflow_cms != null ? `${Number(selectedWatershed.current_streamflow_cms).toFixed(1)} m³/s` : 'N/A'}
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Flood Stage</span>
                                    <span className="font-bold text-slate-700">
                                        {selectedWatershed.flood_stage_cms != null ? `${Number(selectedWatershed.flood_stage_cms).toFixed(1)} m³/s` : 'N/A'}
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Basin Area</span>
                                    <span className="font-bold text-slate-700">
                                        {selectedWatershed.basin_size_sqkm != null ? `${Number(selectedWatershed.basin_size_sqkm).toLocaleString()} km²` : 'N/A'}
                                    </span>
                                </div>
                            </div>

                            <div className="pt-2">
                                <button
                                    onClick={() => {
                                        const lat = selectedWatershed.location_lat
                                        const lon = selectedWatershed.location_lng
                                        const query = [
                                            lat != null ? `lat=${lat}` : null,
                                            lon != null ? `lon=${lon}` : null,
                                            selectedWatershed.name ? `locality=${encodeURIComponent(selectedWatershed.name)}` : null,
                                        ].filter(Boolean).join('&')
                                        navigate(query ? `/assess-flood-risk?${query}` : '/assess-flood-risk')
                                    }}
                                    className="w-full bg-[#0f2460] hover:bg-[#0a1c4e] text-white text-xs font-bold py-2.5 px-4 rounded-xl shadow-xs transition-colors flex items-center justify-center gap-2 cursor-pointer"
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
    )
}
