import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Calendar, Filter, MapPin, Search, RefreshCw } from 'lucide-react'
import { AssistantSidebar } from '@/history/page'
import { historicalEventsApi, type HistoricalFloodEvent } from '@/lib/api'

export default function HistoricalEventsPage() {
  const [events, setEvents] = useState<HistoricalFloodEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [locality, setLocality] = useState('')
  const [division, setDivision] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  useEffect(() => {
    historicalEventsApi.list(500).then((r) => setEvents(r.events || [])).catch(() => setEvents([])).finally(() => setLoading(false))
  }, [])

  const localities = useMemo(() => [...new Set(events.map((e) => e.locality).filter(Boolean) as string[])].sort(), [events])
  const divisions = useMemo(() => [...new Set(events.map((e) => e.division).filter(Boolean) as string[])].sort(), [events])
  const filtered = useMemo(() => events.filter((event) => {
    const haystack = [event.event_id, event.locality, event.division, event.region, event.description, event.source].filter(Boolean).join(' ').toLowerCase()
    const date = String(event.date || event.start_date || event.year || '')
    return (!query || haystack.includes(query.toLowerCase())) &&
      (!locality || event.locality === locality) &&
      (!division || event.division === division) &&
      (!from || date >= from) && (!to || date <= to)
  }), [events, query, locality, division, from, to])

  return (
    <div className="flex h-[100dvh] w-full overflow-hidden bg-[#040914] font-sans text-slate-100">
      <AssistantSidebar />
      <main className="flex-1 min-w-0 overflow-y-auto bg-[#040914]">
        <header className="flex h-16 items-center border-b border-slate-800/80 bg-[#060c18] px-6 shadow-sm">
          <button onClick={() => window.history.back()} className="mr-4 inline-flex items-center gap-2 text-sm font-semibold text-slate-400 hover:text-white"><ArrowLeft className="h-4 w-4" />History</button>
          <h1 className="text-lg font-bold text-white">Historical Flood Events</h1>
        </header>
        <section className="p-6 bg-gradient-to-br from-[#040914] via-[#07101d] to-[#0a1628] min-h-[calc(100dvh-4rem)]">
          <div className="mb-6 rounded-xl border border-slate-800 bg-[#0a111d] p-5 shadow-xl">
            <div className="mb-4 flex items-center gap-2"><Filter className="h-4 w-4 text-blue-300" /><h2 className="font-bold text-white">Filter verified Far North events</h2></div>

            {/* FIX: lg:grid-cols-5 -> lg:grid-cols-6, and the two date inputs are now
                each their own direct grid item (no more shared flex wrapper), with
                min-w-0 added so they can shrink to fit their column instead of
                overflowing the card. */}
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-6">
              <label className="relative md:col-span-2 lg:col-span-2">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search event, locality or description"
                  className="w-full min-w-0 rounded-lg border border-slate-700 bg-slate-900/80 py-2 pl-9 pr-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none"
                />
              </label>

              <select
                value={locality}
                onChange={(e) => setLocality(e.target.value)}
                className="w-full min-w-0 rounded-lg border border-slate-700 bg-slate-900/80 px-3 py-2 text-sm text-slate-200"
              >
                <option value="">All localities</option>
                {localities.map((v) => <option key={v}>{v}</option>)}
              </select>

              <select
                value={division}
                onChange={(e) => setDivision(e.target.value)}
                className="w-full min-w-0 rounded-lg border border-slate-700 bg-slate-900/80 px-3 py-2 text-sm text-slate-200"
              >
                <option value="">All divisions</option>
                {divisions.map((v) => <option key={v}>{v}</option>)}
              </select>

              <label className="w-full min-w-0">
                <span className="sr-only">From date</span>
                <input
                  type="date"
                  value={from}
                  onChange={(e) => setFrom(e.target.value)}
                  className="w-full min-w-0 rounded-lg border border-slate-700 bg-slate-900/80 px-2 py-2 text-sm text-slate-200"
                />
              </label>

              <label className="w-full min-w-0">
                <span className="sr-only">To date</span>
                <input
                  type="date"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  className="w-full min-w-0 rounded-lg border border-slate-700 bg-slate-900/80 px-2 py-2 text-sm text-slate-200"
                />
              </label>
            </div>

            <p className="mt-4 text-xs text-slate-400">
              <Calendar className="mr-1 inline h-3.5 w-3.5" />
              Showing <span className="font-bold text-slate-200">{filtered.length}</span> of {events.length} verified catalogue records.
            </p>
          </div>

          <div className="space-y-3">
            {loading && (
              <div className="rounded-xl border border-slate-800 bg-[#0a111d] p-8 text-center text-sm text-slate-400">
                <RefreshCw className="mr-2 inline h-4 w-4 animate-spin text-blue-400" />
                Loading verified events…
              </div>
            )}
            {!loading && filtered.length === 0 && (
              <div className="rounded-xl border border-slate-800 bg-[#0a111d] p-8 text-center text-sm text-slate-400">
                No verified events match these filters.
              </div>
            )}
            {filtered.map((event, index) => (
              <article key={`${event.event_id}-${event.date}-${index}`} className="rounded-xl border border-slate-800 bg-[#0a111d] p-6 shadow-xl transition-colors hover:border-slate-700">
                <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide text-blue-300">{event.event_id || 'Verified flood event'}</p>
                    <h2 className="mt-1 text-base font-bold text-white">
                      {event.date || event.year || 'Date unavailable'}
                      {event.end_date ? ` – ${event.end_date}` : ''}
                    </h2>
                  </div>
                  <span className="self-start rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1 text-xs font-bold capitalize text-amber-300">
                    {event.severity || 'Documented'}
                  </span>
                </div>

                <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-300">
                  <span><MapPin className="mr-1 inline h-3.5 w-3.5 text-blue-300" />{event.locality || 'Regional footprint'}</span>
                  {event.division && <span>{event.division}</span>}
                  {event.region && <span>{event.region}</span>}
                  {event.evidence_quality && <span className="text-slate-400">Confidence: {event.evidence_quality}</span>}
                </div>

                {(event.description || event.evidence_summary) && (
                  <p className="mt-4 text-sm leading-relaxed text-slate-300">
                    {event.description || event.evidence_summary}
                  </p>
                )}

                {event.source && (
                  <details className="mt-4 rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
                    <summary className="cursor-pointer text-xs font-semibold text-slate-300">Source citation</summary>
                    <p className="mt-2 break-all text-xs leading-relaxed text-slate-500">{event.source}</p>
                  </details>
                )}
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}