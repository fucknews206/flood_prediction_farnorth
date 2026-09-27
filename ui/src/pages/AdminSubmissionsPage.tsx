import { useEffect, useState } from 'react'
import { ArrowLeft, RefreshCw, FileText, MessageSquare } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { adminSubmissionsApi, type CommunityReport, type PredictionFeedback } from '@/lib/api'

/** Admin-only view of citizen submissions. Data comes from the protected API. */
export default function AdminSubmissionsPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<'reports' | 'feedback'>('reports')
  const [reports, setReports] = useState<CommunityReport[]>([])
  const [feedback, setFeedback] = useState<PredictionFeedback[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const [reportResponse, feedbackResponse] = await Promise.all([adminSubmissionsApi.reports(), adminSubmissionsApi.feedback()])
      setReports(reportResponse.reports || [])
      setFeedback(feedbackResponse.feedback || [])
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load administrator submissions.') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  return <div className="min-h-screen bg-slate-950 text-white">
    <header className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
      <div className="flex items-center gap-3"><button onClick={() => navigate('/admin-dashboard')} className="inline-flex items-center gap-2 text-sm text-slate-300 hover:text-white"><ArrowLeft className="h-4 w-4" />Admin dashboard</button><span className="text-slate-600">/</span><h1 className="font-bold">Citizen submissions</h1></div>
      <button onClick={load} disabled={loading} className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800 disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />Refresh</button>
    </header>
    <main className="mx-auto max-w-7xl space-y-5 p-6">
      <div className="flex gap-2"><button onClick={() => setTab('reports')} className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-bold ${tab === 'reports' ? 'bg-blue-600' : 'bg-slate-800 text-slate-300'}`}><FileText className="h-4 w-4" />Reports ({reports.length})</button><button onClick={() => setTab('feedback')} className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-bold ${tab === 'feedback' ? 'bg-blue-600' : 'bg-slate-800 text-slate-300'}`}><MessageSquare className="h-4 w-4" />Feedback ({feedback.length})</button></div>
      {error && <div className="rounded-lg border border-red-800 bg-red-950/40 p-4 text-sm text-red-200">{error}</div>}
      {loading ? <div className="rounded-xl border border-slate-800 bg-slate-900 p-10 text-center text-slate-400"><RefreshCw className="mx-auto mb-2 h-5 w-5 animate-spin" />Loading protected submissions…</div> : tab === 'reports' ? <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900"><table className="min-w-full text-left text-sm"><thead className="bg-slate-800/70 text-xs uppercase text-slate-400"><tr><th className="p-4">Reporter / user</th><th className="p-4">Location</th><th className="p-4">Observed</th><th className="p-4">Depth</th><th className="p-4">Observations</th><th className="p-4">Evidence</th><th className="p-4">Status</th><th className="p-4">Submitted</th></tr></thead><tbody className="divide-y divide-slate-800">{reports.map((r) => <tr key={r.id} className="align-top"><td className="p-4"><div>{r.reporter_name || 'Authenticated citizen'}</div><div className="text-xs text-slate-500">{r.user_id || '—'}</div></td><td className="p-4">{r.locality || r.arrondissement || '—'}<div className="text-xs text-slate-500">{r.division || r.department || 'Far North'}</div></td><td className="p-4 whitespace-nowrap">{r.observation_at ? new Date(r.observation_at).toLocaleString() : '—'}</td><td className="p-4 capitalize">{r.water_depth_category || r.risk_level || '—'}</td><td className="max-w-xs p-4 text-slate-300">{r.details || '—'}</td><td className="p-4">{r.evidence_name || 'None'}</td><td className="p-4"><span className="rounded-full bg-blue-950 px-2 py-1 text-xs text-blue-200">{r.status || 'Submitted'}</span></td><td className="p-4 whitespace-nowrap text-slate-400">{r.reported_at ? new Date(r.reported_at).toLocaleString() : '—'}</td></tr>)}</tbody></table>{reports.length === 0 && <p className="p-10 text-center text-slate-400">No citizen reports have been submitted.</p>}</div> : <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900"><table className="min-w-full text-left text-sm"><thead className="bg-slate-800/70 text-xs uppercase text-slate-400"><tr><th className="p-4">Citizen</th><th className="p-4">Prediction</th><th className="p-4">Accuracy</th><th className="p-4">Comments</th><th className="p-4">Submitted</th></tr></thead><tbody className="divide-y divide-slate-800">{feedback.map((f) => <tr key={f.id} className="align-top"><td className="p-4">{f.user_id}</td><td className="p-4">{f.prediction_locality || '—'}<div className="text-xs text-slate-500">{f.prediction_risk_level || '—'}{f.prediction_estimated_risk_percent != null ? ` · ${Number(f.prediction_estimated_risk_percent).toFixed(1)}%` : ''}</div></td><td className="p-4 capitalize">{f.accuracy}</td><td className="max-w-md p-4 text-slate-300">{f.comments || '—'}</td><td className="p-4 whitespace-nowrap text-slate-400">{f.created_at ? new Date(f.created_at).toLocaleString() : '—'}</td></tr>)}</tbody></table>{feedback.length === 0 && <p className="p-10 text-center text-slate-400">No prediction feedback has been submitted.</p>}</div>}
    </main>
  </div>
}
