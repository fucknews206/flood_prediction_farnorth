'use client'

import { useState, useEffect } from 'react'
import {
  FileText,
  Search,
  RefreshCw,
  Eye,
  Filter,
  CheckCircle2,
  AlertTriangle,
  Clock,
  X,
  MapPin,
  Image as ImageIcon,
} from 'lucide-react'
import { adminApi, type CommunityReport } from '@/lib/api'

export default function AdminReportsView() {
  const [reports, setReports] = useState<CommunityReport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'submitted' | 'under review' | 'verified' | 'resolved'>('all')
  const [selectedReport, setSelectedReport] = useState<CommunityReport | null>(null)
  const [updatingId, setUpdatingId] = useState<number | null>(null)
  const [successMsg, setSuccessMsg] = useState('')

  const loadReports = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await adminApi.getReports(200)
      setReports(res.reports || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load community flood reports.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadReports()
  }, [])

  const handleStatusChange = async (reportId: number, newStatus: string) => {
    setUpdatingId(reportId)
    setSuccessMsg('')
    try {
      const res = await adminApi.updateReportStatus(reportId, newStatus)
      if (res.status === 'success' && res.report) {
        setReports(prev => prev.map(r => (r.id === reportId ? res.report : r)))
        if (selectedReport && selectedReport.id === reportId) {
          setSelectedReport(res.report)
        }
        setSuccessMsg(`Report #${reportId} status updated to ${newStatus}`)
        setTimeout(() => setSuccessMsg(''), 4000)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update report status.')
    } finally {
      setUpdatingId(null)
    }
  }

  const filteredReports = reports.filter(r => {
    const matchesSearch =
      (r.locality && r.locality.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (r.reporter_name && r.reporter_name.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (r.user_id && r.user_id.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (r.details && r.details.toLowerCase().includes(searchQuery.toLowerCase()))

    if (statusFilter === 'all') return matchesSearch
    const rStatus = (r.status || 'Submitted').toLowerCase()
    return matchesSearch && rStatus === statusFilter
  })

  const getStatusBadge = (status?: string) => {
    const s = (status || 'Submitted').toLowerCase()
    if (s === 'verified') return 'bg-emerald-100 text-emerald-800 border-emerald-300'
    if (s === 'under review') return 'bg-amber-100 text-amber-800 border-amber-300'
    if (s === 'resolved') return 'bg-blue-100 text-blue-800 border-blue-300'
    if (s === 'rejected') return 'bg-rose-100 text-rose-800 border-rose-300'
    return 'bg-slate-100 text-slate-800 border-slate-300'
  }

  return (
    <div className="space-y-6">
      {/* HEADER */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#0B172A] text-blue-400 font-bold text-[11px] tracking-wider uppercase mb-2 shadow-xs">
            <FileText className="h-3.5 w-3.5 text-blue-400" />
            <span>GROUND INTELLIGENCE</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight leading-tight">
            Community Reports
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 font-medium mt-1">
            Real flood observations and water depth reports submitted by citizens on the ground.
          </p>
        </div>

        <button
          onClick={loadReports}
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white border border-slate-200/80 hover:bg-slate-50 text-slate-700 text-xs font-bold shadow-xs transition-all cursor-pointer self-start sm:self-auto disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Reports</span>
        </button>
      </div>

      {successMsg && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800 text-xs flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-600 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs">
          {error}
        </div>
      )}

      {/* FILTER TABS */}
      <div className="flex flex-wrap items-center gap-2">
        {(['all', 'submitted', 'under review', 'verified', 'resolved'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setStatusFilter(tab)}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-bold capitalize transition-all cursor-pointer ${
              statusFilter === tab
                ? 'bg-[#0B172A] text-white shadow-xs'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            {tab === 'all' ? `All Reports (${reports.length})` : tab}
          </button>
        ))}
      </div>

      {/* SEARCH BAR */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs flex items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search by locality, citizen email, or observations..."
            className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 transition-all"
          />
        </div>
        <span className="text-xs font-semibold text-slate-500">
          Showing {filteredReports.length} of {reports.length} reports
        </span>
      </div>

      {/* REPORTS TABLE */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 font-extrabold uppercase tracking-wider text-[10px] border-b border-slate-200/80">
              <tr>
                <th className="py-3.5 px-4">Report ID</th>
                <th className="py-3.5 px-4">Citizen / Reporter</th>
                <th className="py-3.5 px-4">Locality</th>
                <th className="py-3.5 px-4">Observed Time</th>
                <th className="py-3.5 px-4">Water Depth</th>
                <th className="py-3.5 px-4">Details / Observations</th>
                <th className="py-3.5 px-4">Evidence</th>
                <th className="py-3.5 px-4">Review Status</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-medium text-slate-700">
              {loading ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-slate-400">
                    <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-blue-600" />
                    <span>Loading real citizen reports…</span>
                  </td>
                </tr>
              ) : filteredReports.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-slate-400">
                    No community flood reports found for selected filter.
                  </td>
                </tr>
              ) : (
                filteredReports.map(report => (
                  <tr key={report.id} className="hover:bg-slate-50/80 transition-colors align-top">
                    <td className="py-3 px-4 font-mono font-bold text-slate-900">
                      #{report.id}
                    </td>
                    <td className="py-3 px-4">
                      <div>
                        <span className="font-bold text-slate-900 block leading-tight">
                          {report.reporter_name || report.user_id || 'Authenticated Citizen'}
                        </span>
                        {report.user_id && report.reporter_name && (
                          <span className="text-[10px] text-slate-400 block">{report.user_id}</span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1 font-semibold text-slate-800">
                        <MapPin className="h-3 w-3 text-red-500 flex-shrink-0" />
                        <span>{report.locality || report.arrondissement || 'Far North Area'}</span>
                      </div>
                      <span className="text-[10px] text-slate-400 pl-4 block">
                        {report.division || report.department || 'Far North'}
                      </span>
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap text-slate-500">
                      {report.observation_at ? new Date(report.observation_at).toLocaleString() : '—'}
                    </td>
                    <td className="py-3 px-4">
                      <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-slate-100 text-slate-800 font-bold text-[10px] capitalize">
                        {report.water_depth_category || report.risk_level || 'Reported'}
                      </span>
                    </td>
                    <td className="py-3 px-4 max-w-xs text-slate-700 leading-snug">
                      <p className="line-clamp-2">{report.details || '—'}</p>
                    </td>
                    <td className="py-3 px-4">
                      {report.evidence_name ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-md">
                          <ImageIcon className="h-3 w-3" />
                          <span className="truncate max-w-[90px]">{report.evidence_name}</span>
                        </span>
                      ) : (
                        <span className="text-slate-400 text-[11px]">None</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <select
                        value={report.status || 'Submitted'}
                        onChange={e => handleStatusChange(report.id, e.target.value)}
                        disabled={updatingId === report.id}
                        className={`text-[11px] font-bold rounded-lg px-2.5 py-1 border focus:outline-none focus:ring-1 cursor-pointer transition-all ${getStatusBadge(
                          report.status
                        )}`}
                      >
                        <option value="Submitted">Submitted</option>
                        <option value="Pending">Pending</option>
                        <option value="Under Review">Under Review</option>
                        <option value="Verified">Verified</option>
                        <option value="Resolved">Resolved</option>
                        <option value="Rejected">Rejected</option>
                      </select>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => setSelectedReport(report)}
                        className="inline-flex items-center gap-1 px-3 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-700 rounded-lg text-xs font-semibold transition-all cursor-pointer"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        <span>View</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* REPORT DETAIL MODAL */}
      {selectedReport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <span className="text-[10px] font-bold text-blue-600 uppercase">
                  CITIZEN FLOOD REPORT #{selectedReport.id}
                </span>
                <h3 className="font-extrabold text-slate-900 text-base leading-tight mt-0.5">
                  {selectedReport.locality || 'Far North Zone'}
                </h3>
              </div>
              <button
                onClick={() => setSelectedReport(null)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs text-slate-700">
              <div className="p-3 bg-slate-50 rounded-xl space-y-2">
                <span className="font-bold text-slate-900 block text-xs">Full Citizen Observations:</span>
                <p className="text-slate-800 leading-relaxed italic bg-white p-3 rounded-lg border border-slate-200/60">
                  "{selectedReport.details}"
                </p>
              </div>

              <div className="grid grid-cols-2 gap-2.5">
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <span className="text-[10px] text-slate-400 font-bold block uppercase">Reporter:</span>
                  <span className="font-bold text-slate-900">{selectedReport.reporter_name || selectedReport.user_id || 'Citizen'}</span>
                </div>
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <span className="text-[10px] text-slate-400 font-bold block uppercase">Water Depth:</span>
                  <span className="font-bold text-slate-900 capitalize">{selectedReport.water_depth_category || selectedReport.risk_level || 'N/A'}</span>
                </div>
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <span className="text-[10px] text-slate-400 font-bold block uppercase">Coordinates:</span>
                  <span className="font-bold text-slate-900">
                    {selectedReport.location_lat.toFixed(4)}°N, {selectedReport.location_lng.toFixed(4)}°E
                  </span>
                </div>
                <div className="p-2.5 bg-slate-50 rounded-lg">
                  <span className="text-[10px] text-slate-400 font-bold block uppercase">Submission Date:</span>
                  <span className="font-bold text-slate-900">
                    {selectedReport.reported_at ? new Date(selectedReport.reported_at).toLocaleString() : 'N/A'}
                  </span>
                </div>
              </div>

              {selectedReport.evidence_name && (
                <div className="p-3 bg-blue-50/60 border border-blue-100 rounded-xl flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ImageIcon className="h-4 w-4 text-blue-600" />
                    <span className="font-semibold text-blue-900">Evidence File: {selectedReport.evidence_name}</span>
                  </div>
                </div>
              )}

              <div className="p-3 bg-slate-50 rounded-xl flex items-center justify-between">
                <span className="font-bold text-slate-700">Update Review Status:</span>
                <select
                  value={selectedReport.status || 'Submitted'}
                  onChange={e => handleStatusChange(selectedReport.id, e.target.value)}
                  className={`text-xs font-bold rounded-lg px-3 py-1 border ${getStatusBadge(selectedReport.status)}`}
                >
                  <option value="Submitted">Submitted</option>
                  <option value="Pending">Pending</option>
                  <option value="Under Review">Under Review</option>
                  <option value="Verified">Verified</option>
                  <option value="Resolved">Resolved</option>
                  <option value="Rejected">Rejected</option>
                </select>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedReport(null)}
                className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs rounded-xl cursor-pointer transition-all"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
