'use client'

import { useState, useEffect } from 'react'
import {
  Database,
  RefreshCw,
  Search,
  CheckCircle2,
  HardDrive,
  Layers,
  MapPin,
  ExternalLink,
  Shield,
} from 'lucide-react'
import { adminApi, type AdminDataset } from '@/lib/api'

export default function AdminDatasetsView() {
  const [datasets, setDatasets] = useState<AdminDataset[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  const loadDatasets = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await adminApi.getDatasets()
      setDatasets(res.datasets || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load operational datasets.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDatasets()
  }, [])

  const filteredDatasets = datasets.filter(d =>
    d.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    d.category.toLowerCase().includes(searchQuery.toLowerCase()) ||
    d.coverage.toLowerCase().includes(searchQuery.toLowerCase()) ||
    d.source.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div className="space-y-6">
      {/* HEADER */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#0B172A] text-blue-400 font-bold text-[11px] tracking-wider uppercase mb-2 shadow-xs">
            <Database className="h-3.5 w-3.5 text-blue-400" />
            <span>DATA REGISTRY & INTEGRATIONS</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight leading-tight">
            Registered Datasets
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 font-medium mt-1">
            Active GIS boundary layers, hydrological basins, meteorological feeds, and historical benchmarks.
          </p>
        </div>

        <button
          onClick={loadDatasets}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 text-xs font-bold shadow-xs transition-all cursor-pointer self-start sm:self-auto disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* METRIC SUMMARY CARDS */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-[10px] font-extrabold uppercase text-slate-400 tracking-wider">
              OPERATIONAL DATASETS
            </span>
            <Database className="h-4 w-4 text-blue-600" />
          </div>
          <span className="text-2xl font-extrabold text-slate-900">
            {loading ? '…' : datasets.length}
          </span>
          <p className="text-[11px] text-slate-400 font-medium mt-1">
            Registered in application pipeline
          </p>
        </div>

        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-[10px] font-extrabold uppercase text-slate-400 tracking-wider">
              POSTGIS SPATIAL LAYERS
            </span>
            <Layers className="h-4 w-4 text-emerald-600" />
          </div>
          <span className="text-2xl font-extrabold text-slate-900">
            2
          </span>
          <p className="text-[11px] text-slate-400 font-medium mt-1">
            HydroBASINS & Admin Boundaries
          </p>
        </div>

        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-[10px] font-extrabold uppercase text-slate-400 tracking-wider">
              EXTERNAL WEATHER & HYDRO FEEDS
            </span>
            <HardDrive className="h-4 w-4 text-purple-600" />
          </div>
          <span className="text-2xl font-extrabold text-slate-900">
            2
          </span>
          <p className="text-[11px] text-slate-400 font-medium mt-1">
            Open-Meteo & Copernicus GloFAS
          </p>
        </div>
      </div>

      {/* SEARCH BAR */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search datasets by name, category, or source..."
            className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
          />
        </div>
        <span className="text-xs font-semibold text-slate-500">
          Showing {filteredDatasets.length} of {datasets.length} datasets
        </span>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs">
          {error}
        </div>
      )}

      {/* DATASETS GRID */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {loading ? (
          <div className="col-span-2 py-12 text-center text-slate-400 bg-white rounded-2xl border border-slate-200/80">
            <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-blue-600" />
            <span>Loading registered datasets…</span>
          </div>
        ) : filteredDatasets.length === 0 ? (
          <div className="col-span-2 py-12 text-center text-slate-400 bg-white rounded-2xl border border-slate-200/80">
            No datasets matching search query.
          </div>
        ) : (
          filteredDatasets.map(dataset => (
            <div
              key={dataset.id}
              className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs hover:shadow-md transition-shadow flex flex-col justify-between space-y-4"
            >
              <div>
                <div className="flex items-start justify-between gap-3 mb-2">
                  <span className="px-2.5 py-0.5 rounded-md bg-blue-50 text-blue-700 font-bold text-[10px] uppercase">
                    {dataset.category}
                  </span>
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                    <CheckCircle2 className="h-3 w-3" />
                    {dataset.status}
                  </span>
                </div>
                <h3 className="text-sm font-extrabold text-slate-900 leading-tight">
                  {dataset.name}
                </h3>
                <p className="text-xs text-slate-600 leading-relaxed mt-2">
                  {dataset.description}
                </p>
              </div>

              <div className="pt-3 border-t border-slate-100 space-y-1.5 text-xs text-slate-600">
                <div className="flex justify-between">
                  <span className="text-slate-400">Geographic Coverage:</span>
                  <span className="font-semibold text-slate-900">{dataset.coverage}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Primary Source:</span>
                  <span className="font-semibold text-slate-900">{dataset.source}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Storage / Format:</span>
                  <span className="font-semibold text-slate-900">{dataset.format}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Active Records:</span>
                  <span className="font-mono font-bold text-slate-900">{dataset.records}</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
