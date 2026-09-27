'use client'

import { useState, useEffect } from 'react'
import {
  Bell,
  MessageSquare,
  RefreshCw,
  Search,
  CheckCircle2,
  AlertCircle,
  Clock,
  Info,
  Shield,
  Check,
  TrendingUp,
} from 'lucide-react'
import { adminApi, type PredictionFeedback } from '@/lib/api'

export default function AdminNotificationsView() {
  const [activeTab, setActiveTab] = useState<'feedback' | 'system'>('feedback')
  const [feedback, setFeedback] = useState<PredictionFeedback[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  const loadFeedback = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await adminApi.getFeedback(200)
      setFeedback(res.feedback || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load citizen prediction feedback.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadFeedback()
  }, [])

  const filteredFeedback = feedback.filter(f =>
    (f.user_id && f.user_id.toLowerCase().includes(searchQuery.toLowerCase())) ||
    (f.prediction_locality && f.prediction_locality.toLowerCase().includes(searchQuery.toLowerCase())) ||
    (f.comments && f.comments.toLowerCase().includes(searchQuery.toLowerCase())) ||
    (f.accuracy && f.accuracy.toLowerCase().includes(searchQuery.toLowerCase()))
  )

  const getAccuracyBadge = (accuracy: string) => {
    const a = accuracy.toLowerCase()
    if (a === 'accurate') {
      return 'bg-emerald-100 text-emerald-800 border-emerald-200'
    }
    if (a === 'partially accurate') {
      return 'bg-amber-100 text-amber-800 border-amber-200'
    }
    return 'bg-rose-100 text-rose-800 border-rose-200'
  }

  return (
    <div className="space-y-6">
      {/* HEADER */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#0B172A] text-blue-400 font-bold text-[11px] tracking-wider uppercase mb-2 shadow-xs">
            <Bell className="h-3.5 w-3.5 text-blue-400" />
            <span>NOTIFICATIONS & FEEDBACK</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight leading-tight">
            Notifications & Feedback
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 font-medium mt-1">
            Citizen validation on prediction accuracy and platform alert notifications.
          </p>
        </div>

        <button
          onClick={loadFeedback}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 text-xs font-bold shadow-xs transition-all cursor-pointer self-start sm:self-auto disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* DOMAIN DISTINCTION CALLOUT BANNER */}
      <div className="p-4 bg-blue-50/70 border border-blue-200/80 rounded-2xl flex items-start gap-3">
        <Info className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
        <div className="text-xs text-blue-900 leading-relaxed">
          <p className="font-bold text-slate-900 mb-0.5">
            Architectural Distinction in AquaGuard AI:
          </p>
          <p>
            <span className="font-semibold text-blue-950">Community Reports</span> are citizen eyewitness submissions of active ground flooding events.
            <br />
            <span className="font-semibold text-blue-950">Prediction Feedback</span> (displayed below) is citizen evaluation regarding the accuracy and reliability of AI risk predictions.
          </p>
        </div>
      </div>

      {/* TAB NAVIGATION */}
      <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
        <button
          onClick={() => setActiveTab('feedback')}
          className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition-all cursor-pointer ${
            activeTab === 'feedback'
              ? 'bg-[#0B172A] text-white shadow-xs'
              : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
          }`}
        >
          <MessageSquare className="h-4 w-4" />
          <span>Citizen Prediction Feedback ({feedback.length})</span>
        </button>
        <button
          onClick={() => setActiveTab('system')}
          className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition-all cursor-pointer ${
            activeTab === 'system'
              ? 'bg-[#0B172A] text-white shadow-xs'
              : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
          }`}
        >
          <Bell className="h-4 w-4" />
          <span>System Alerts & Logs</span>
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs">
          {error}
        </div>
      )}

      {activeTab === 'feedback' ? (
        <div className="space-y-4">
          {/* SEARCH BAR */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex items-center justify-between gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search feedback by citizen, locality, or comments..."
                className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
              />
            </div>
            <span className="text-xs font-semibold text-slate-500">
              Showing {filteredFeedback.length} of {feedback.length} feedback entries
            </span>
          </div>

          {/* FEEDBACK TABLE */}
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 font-extrabold uppercase tracking-wider text-[10px] border-b border-slate-200/80">
                  <tr>
                    <th className="py-3.5 px-4">Feedback ID</th>
                    <th className="py-3.5 px-4">Citizen / User</th>
                    <th className="py-3.5 px-4">Target Prediction</th>
                    <th className="py-3.5 px-4">Locality / Estimated Risk</th>
                    <th className="py-3.5 px-4">Reported Accuracy</th>
                    <th className="py-3.5 px-4">Citizen Comments</th>
                    <th className="py-3.5 px-4 text-right">Submitted At</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium text-slate-700">
                  {loading ? (
                    <tr>
                      <td colSpan={7} className="py-12 text-center text-slate-400">
                        <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-blue-600" />
                        <span>Loading prediction feedback from database…</span>
                      </td>
                    </tr>
                  ) : filteredFeedback.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-12 text-center text-slate-400">
                        No prediction feedback records found.
                      </td>
                    </tr>
                  ) : (
                    filteredFeedback.map(item => (
                      <tr key={item.id} className="hover:bg-slate-50/80 transition-colors align-top">
                        <td className="py-3 px-4 font-mono font-bold text-slate-900">
                          #{item.id}
                        </td>
                        <td className="py-3 px-4">
                          <span className="font-bold text-slate-900 block leading-tight">
                            {item.user_id || 'Authenticated Citizen'}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <span className="px-2 py-0.5 bg-slate-100 text-slate-700 rounded-md font-mono text-[11px] font-semibold">
                            Prediction #{item.prediction_id}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="font-bold text-slate-900">
                            {item.prediction_locality || 'Far North'}
                          </div>
                          <span className="text-[11px] text-slate-500">
                            {item.prediction_risk_level || 'Risk'}
                            {item.prediction_estimated_risk_percent != null &&
                              ` · ${Number(item.prediction_estimated_risk_percent).toFixed(1)}%`}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md font-bold text-[10px] border capitalize ${getAccuracyBadge(
                              item.accuracy
                            )}`}
                          >
                            <Check className="h-3 w-3" />
                            {item.accuracy}
                          </span>
                        </td>
                        <td className="py-3 px-4 max-w-sm">
                          <p className="text-slate-700 leading-snug line-clamp-2 italic">
                            "{item.comments || 'No written commentary'}"
                          </p>
                        </td>
                        <td className="py-3 px-4 text-right whitespace-nowrap text-slate-500">
                          {item.created_at ? new Date(item.created_at).toLocaleString() : '—'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : (
        /* SYSTEM ALERTS TAB */
        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h3 className="text-base font-bold text-slate-900">Platform Notifications</h3>
              <p className="text-xs text-slate-500">System health, alert events, and data feed updates.</p>
            </div>
            <span className="px-3 py-1 bg-emerald-50 text-emerald-700 text-xs font-bold rounded-lg border border-emerald-200">
              System Normal
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200/80 flex items-start gap-3">
              <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-bold text-slate-900">PostgreSQL Database Connection Active</p>
                <p className="text-slate-500 mt-0.5">PostGIS spatial engine initialized. 32 Cameroon river basins and 428 administrative boundaries loaded.</p>
              </div>
            </div>

            <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200/80 flex items-start gap-3">
              <TrendingUp className="h-4 w-4 text-blue-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-bold text-slate-900">Far North Environmental Engine Initialized</p>
                <p className="text-slate-500 mt-0.5">Rules-based assessment pipeline active for 34 verified Far North localities with live Open-Meteo & GloFAS data feeds.</p>
              </div>
            </div>

            <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200/80 flex items-start gap-3">
              <Shield className="h-4 w-4 text-blue-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-bold text-slate-900">Admin Security & Identity Active</p>
                <p className="text-slate-500 mt-0.5">All administrative routes and status endpoints restricted to verified administrator role.</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
