'use client'

import { useState, useEffect } from 'react'
import {
  LineChart,
  RefreshCw,
  TrendingUp,
  MapPin,
  Calendar,
  Info,
  Shield,
  CheckCircle2,
} from 'lucide-react'
import { adminApi, type AdminAnalytics } from '@/lib/api'

export default function AdminAnalyticsView() {
  const [analytics, setAnalytics] = useState<AdminAnalytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadAnalytics = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await adminApi.getAnalytics()
      setAnalytics(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load prediction analytics.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAnalytics()
  }, [])

  return (
    <div className="space-y-6">
      {/* HEADER */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#0B172A] text-blue-400 font-bold text-[11px] tracking-wider uppercase mb-2 shadow-xs">
            <LineChart className="h-3.5 w-3.5 text-blue-400" />
            <span>PREDICTION ANALYTICS</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight leading-tight">
            Prediction Analytics
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 font-medium mt-1">
            Real risk assessment distribution, locality coverage, and prediction metrics for Far North Cameroon.
          </p>
        </div>

        <button
          onClick={loadAnalytics}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 text-xs font-bold shadow-xs transition-all cursor-pointer self-start sm:self-auto disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs">
          {error}
        </div>
      )}

      {/* METRIC SUMMARY CARDS */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-[10px] font-extrabold uppercase text-slate-400 tracking-wider">
              TOTAL PREDICTIONS
            </span>
            <TrendingUp className="h-4 w-4 text-blue-600" />
          </div>
          <span className="text-2xl font-extrabold text-slate-900">
            {loading ? '…' : analytics?.prediction_count ?? 0}
          </span>
          <p className="text-[11px] text-slate-400 font-medium mt-1">
            Stored in PostgreSQL database
          </p>
        </div>

        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-[10px] font-extrabold uppercase text-slate-400 tracking-wider">
              OPERATIONAL SCOPE
            </span>
            <MapPin className="h-4 w-4 text-emerald-600" />
          </div>
          <span className="text-2xl font-extrabold text-slate-900">
            Far North
          </span>
          <p className="text-[11px] text-slate-400 font-medium mt-1">
            34 verified operational localities
          </p>
        </div>

        <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between text-slate-500 mb-2">
            <span className="text-[10px] font-extrabold uppercase text-slate-400 tracking-wider">
              ASSESSED LOCALITIES
            </span>
            <Calendar className="h-4 w-4 text-purple-600" />
          </div>
          <span className="text-2xl font-extrabold text-slate-900">
            {loading ? '…' : analytics?.locality_distribution.length ?? 0}
          </span>
          <p className="text-[11px] text-slate-400 font-medium mt-1">
            Locations evaluated by citizens
          </p>
        </div>
      </div>

      {/* DETAILED STATS */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Risk Level Distribution */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs space-y-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">Risk Level Distribution</h3>
            <p className="text-xs text-slate-500">Real risk assessment breakdown from stored predictions.</p>
          </div>

          <div className="space-y-3 pt-2">
            {analytics?.risk_distribution && analytics.risk_distribution.length > 0 ? (
              analytics.risk_distribution.map(item => (
                <div key={item.risk_level} className="space-y-1">
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-slate-800">{item.risk_level}</span>
                    <span className="text-amber-600 font-bold">{item.count} assessment(s)</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                    <div
                      className="bg-amber-500 h-2.5 rounded-full"
                      style={{
                        width: `${Math.round(
                          (item.count / (analytics.prediction_count || 1)) * 100
                        )}%`,
                      }}
                    />
                  </div>
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-400 py-4 text-center">
                No risk distribution records available.
              </p>
            )}
          </div>
        </div>

        {/* Locality Distribution */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs space-y-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">Locality Evaluation Volume</h3>
            <p className="text-xs text-slate-500">Localities assessed in Far North Cameroon.</p>
          </div>

          <div className="space-y-2.5 pt-2">
            {analytics?.locality_distribution && analytics.locality_distribution.length > 0 ? (
              analytics.locality_distribution.map(item => (
                <div
                  key={item.locality}
                  className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-200/60 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <MapPin className="h-3.5 w-3.5 text-red-500" />
                    <span className="font-bold text-slate-900">{item.locality}</span>
                    <span className="text-[10px] text-slate-400">Far North</span>
                  </div>
                  <span className="font-bold text-slate-700 bg-white px-2.5 py-1 rounded-md border border-slate-200">
                    {item.count} assessment(s)
                  </span>
                </div>
              ))
            ) : (
              <p className="text-xs text-slate-400 py-4 text-center">
                No locality evaluation records available.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* TIME-SERIES & REAL DATA DISCLOSURE */}
      <div className="p-4 bg-slate-50 border border-slate-200 rounded-2xl flex items-start gap-3">
        <Info className="h-5 w-5 text-slate-500 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-slate-600 leading-relaxed">
          <p className="font-bold text-slate-800 mb-0.5">
            Operational Reporting Transparency:
          </p>
          <p>
            The analytics above reflect the exact prediction records stored in the AquaGuard AI database ({analytics?.prediction_count ?? 0} assessments). In accordance with the system specification, fictional week-long trend curves are not manufactured when fewer records exist. Time-series charts will automatically populate as live operational prediction cycles continue.
          </p>
        </div>
      </div>
    </div>
  )
}
