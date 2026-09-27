import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Globe,
  ChevronDown,
  ShieldCheck,
  Map as MapIcon,
  ChevronRight
} from 'lucide-react'

// ─── Top Navbar ─────────────────────────────────────────────────────────────
function Navbar({ onLogin }: { onLogin: () => void }) {
  const [lang, setLang] = useState<'English' | 'Français'>('English')

  return (
    <header className="sticky top-0 z-50 bg-white/95 backdrop-blur-sm border-b border-slate-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Logo */}
        <div
          className="flex items-center gap-2.5 cursor-pointer select-none"
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
        >
          <div className="w-8 h-8 rounded-lg bg-[#0f2460] flex items-center justify-center text-white shadow-sm">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div className="leading-tight">
            <p className="font-bold text-slate-900 text-sm tracking-tight">AquaGuard AI</p>
            <p className="text-[10px] text-slate-500 font-medium">Cameroon Flood Intelligence</p>
          </div>
        </div>

        {/* Center links */}
        <nav className="hidden md:flex items-center gap-8 text-xs font-semibold text-slate-600">
          <a
            href="#overview"
            className="hover:text-slate-900 transition-colors"
          >
            Platform Overview
          </a>
          <a
            href="#methodology"
            className="hover:text-slate-900 transition-colors"
          >
            Methodology
          </a>
        </nav>

        {/* Right actions */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => setLang(lang === 'English' ? 'Français' : 'English')}
            className="hidden sm:flex items-center gap-1 text-slate-600 hover:text-slate-900 text-xs font-medium cursor-pointer transition-colors"
          >
            <Globe className="w-3.5 h-3.5 text-slate-500" />
            <span>{lang}</span>
            <ChevronDown className="w-3 h-3 text-slate-400" />
          </button>

          <button
            onClick={onLogin}
            className="bg-[#0f2460] hover:bg-[#0a1c4e] text-white text-xs font-bold px-4 py-2 rounded-lg shadow-sm transition-all cursor-pointer"
          >
            Access Portal
          </button>
        </div>
      </div>
    </header>
  )
}

// ─── Hero Section ───────────────────────────────────────────────────────────
function HeroSection({ onAssess, onMap }: { onAssess: () => void; onMap: () => void }) {
  // 7 illustrative bars matching Image 2
  const bars = [
    { height: 28, color: 'bg-slate-200/90' },
    { height: 35, color: 'bg-slate-200/90' },
    { height: 60, color: 'bg-amber-500' },
    { height: 80, color: 'bg-amber-500' },
    { height: 95, color: 'bg-rose-500' },
    { height: 75, color: 'bg-amber-500' },
    { height: 32, color: 'bg-slate-200/90' }
  ]

  return (
    <section
      id="overview"
      className="relative overflow-hidden bg-white border-b border-slate-200/60"
      style={{ minHeight: '520px' }}
    >
      {/* Background Topographic Map with subtle opacity */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.06] bg-repeat"
        style={{
          backgroundImage: 'url(/cameroon_hero_map.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'center 20%'
        }}
      />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-16 pb-20">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
          {/* Left Column: Headlines & CTAs */}
          <div className="lg:col-span-7 space-y-6">
            <p className="text-[11px] font-bold uppercase tracking-widest text-slate-500">
              CAMEROON FLOOD INTELLIGENCE
            </p>

            <h1 className="text-4xl sm:text-5xl font-black text-slate-950 tracking-tight leading-[1.12]">
              Predictive analytics <br />
              for <span className="text-[#1D68F7]">climate resilience</span>
            </h1>

            <p className="text-sm sm:text-base text-slate-600 leading-relaxed max-w-xl">
              AquaGuard AI combines satellite imagery, hydrological modeling and
              machine learning to forecast flood events across Cameroon —
              supporting communities, analysts and infrastructure planning.
            </p>

            {/* CTAs */}
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <button
                onClick={onAssess}
                className="flex items-center gap-2 bg-[#1D68F7] hover:bg-blue-600 text-white font-bold text-xs sm:text-sm px-6 py-3 rounded-lg shadow-md shadow-blue-600/20 transition-all cursor-pointer"
              >
                <span>Assess Flood Risk</span>
                <ArrowRight className="w-4 h-4" />
              </button>

              <button
                onClick={onMap}
                className="flex items-center gap-2 bg-white hover:bg-slate-50 text-slate-800 border border-slate-300 font-semibold text-xs sm:text-sm px-5 py-3 rounded-lg shadow-sm transition-all cursor-pointer"
              >
                <MapIcon className="w-4 h-4 text-slate-500" />
                <span>View Flood Map</span>
              </button>
            </div>

            <p className="text-xs text-slate-400 font-medium pt-2">
              Built for analysts, communities and resilience teams working on flood preparedness in Cameroon.
            </p>
          </div>

          {/* Right Column: Hero Basin Card (Image 2 exact match) */}
          <div className="lg:col-span-5">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-xl p-5 space-y-4 max-w-md mx-auto">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-900">
                  Logone–Chari basin
                </span>
                <span className="text-[10px] font-semibold text-slate-500 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded">
                  Example view
                </span>
              </div>

              <div className="flex items-start justify-between pt-1">
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                    Current alert level
                  </p>
                  <p className="text-xl font-extrabold text-slate-900 mt-0.5">
                    Unavailable
                  </p>
                  <p className="text-[11px] text-slate-500 font-medium mt-0.5">
                    No live signal from the connected pipeline.
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                    Model confidence
                  </p>
                  <p className="text-base font-extrabold text-slate-700 mt-1">
                    —
                  </p>
                </div>
              </div>

              {/* 7-day risk trend */}
              <div className="pt-2">
                <p className="text-[10px] font-semibold text-slate-400 mb-2">
                  7-day risk trend (Illustrative)
                </p>
                <div className="h-16 flex items-end justify-between gap-1.5 px-1 pb-1">
                  {bars.map((bar, idx) => (
                    <div
                      key={idx}
                      className="flex-1 flex flex-col justify-end h-full"
                    >
                      <div
                        style={{ height: `${bar.height}%` }}
                        className={`w-full rounded-t-sm ${bar.color}`}
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* Precipitation & Soil Saturation Box */}
              <div className="bg-slate-50 rounded-xl p-3 border border-slate-100 grid grid-cols-2 gap-4">
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase">
                    Precipitation
                  </p>
                  <p className="text-xs font-extrabold text-slate-800 mt-0.5">
                    — <span className="font-normal text-slate-400">mm/h</span>
                  </p>
                </div>
                <div>
                  <p className="text-[10px] font-bold text-slate-400 uppercase">
                    Soil saturation
                  </p>
                  <p className="text-xs font-extrabold text-slate-800 mt-0.5">
                    — <span className="font-normal text-slate-400">%</span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

// ─── What We Provide / System Capabilities ──────────────────────────────────
function CapabilitiesSection() {
  const capabilities = [
    {
      num: '01',
      title: 'Regional coverage',
      badge: 'Far North',
      desc: "Verified locality and division assessments for Cameroon's Far North region. Coverage expands as validated data becomes available."
    },
    {
      num: '02',
      title: 'Live operational signal',
      badge: 'Rules-based',
      desc: 'Current risk signals come from the operational Far North environmental pipeline, not from projected or simulated values.'
    },
    {
      num: '03',
      title: 'Verified reporting',
      badge: 'Database-backed',
      desc: 'Report counts are shown only when the connected database returns them. No totals are estimated or fabricated.'
    }
  ]

  return (
    <section className="py-20 bg-white border-b border-slate-200/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-12">
          <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400 mb-2">
            WHAT WE PROVIDE
          </p>
          <h2 className="text-3xl sm:text-4xl font-black text-slate-900 tracking-tight">
            System capabilities
          </h2>
          <p className="text-sm text-slate-600 mt-2 max-w-2xl leading-relaxed">
            AquaGuard AI is scoped to what the underlying data can support today: defined
            regional coverage, an operational risk signal, and reporting that reflects the
            database of record.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {capabilities.map((c) => (
            <div key={c.num} className="space-y-3 pt-4 border-t border-slate-200">
              <p className="text-xs font-bold text-slate-400 font-mono">{c.num}</p>
              <h3 className="text-lg font-bold text-slate-900 tracking-tight">
                {c.title}
              </h3>
              <p className="text-sm font-bold text-[#1D68F7]">{c.badge}</p>
              <p className="text-xs text-slate-600 leading-relaxed font-normal">
                {c.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

// ─── Dynamic Risk Mapping Section ───────────────────────────────────────────
function RiskMappingSection({ onExplore }: { onExplore: () => void }) {
  return (
    <section id="methodology" className="py-20 bg-white border-b border-slate-200/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
          {/* Left Text */}
          <div className="lg:col-span-6 space-y-6">
            <p className="text-[11px] font-bold uppercase tracking-widest text-slate-400">
              RISK MAPPING
            </p>
            <h2 className="text-3xl sm:text-4xl font-black text-slate-900 tracking-tight">
              Dynamic risk mapping
            </h2>
            <p className="text-sm text-slate-600 leading-relaxed">
              Topological models overlaid with hydrological data, so vulnerable zones
              can be identified before critical thresholds are breached.
            </p>

            <div className="space-y-4 pt-2">
              <div>
                <h4 className="text-sm font-bold text-slate-900">
                  Sub-meter resolution
                </h4>
                <p className="text-xs text-slate-500 mt-0.5">
                  Granular insight for urban infrastructure and drainage planning.
                </p>
              </div>

              <div>
                <h4 className="text-sm font-bold text-slate-900">
                  72-hour forecast horizon
                </h4>
                <p className="text-xs text-slate-500 mt-0.5">
                  Actionable lead time for evacuation and preparedness protocols.
                </p>
              </div>
            </div>

            <button
              onClick={onExplore}
              className="inline-flex items-center gap-1.5 text-xs font-bold text-[#1D68F7] hover:text-blue-700 transition-colors pt-2 cursor-pointer"
            >
              <span>Explore the interactive map</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Right Map Image with Caption */}
          <div className="lg:col-span-6">
            <div className="rounded-2xl overflow-hidden border border-slate-200 shadow-xl bg-slate-950">
              <div className="relative h-72 sm:h-80 w-full overflow-hidden">
                <img
                  src="/cameroon_flood_map.png"
                  alt="Dynamic risk map — Far North Lake Chad basin"
                  className="w-full h-full object-cover object-center"
                />
              </div>

              <div className="bg-white px-5 py-3 border-t border-slate-200 flex items-center justify-between text-xs">
                <span className="font-semibold text-slate-800">
                  Far North — Lake Chad basin
                </span>
                <div className="flex items-center gap-4">
                  <span className="flex items-center gap-1.5 text-slate-600 font-medium text-[11px]">
                    <span className="w-2 h-2 rounded-full bg-amber-400" />
                    Moderate
                  </span>
                  <span className="flex items-center gap-1.5 text-slate-600 font-medium text-[11px]">
                    <span className="w-2 h-2 rounded-full bg-rose-500" />
                    Elevated
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

// ─── Footer (Image 2 clean light footer) ────────────────────────────────────
function Footer({ onNavigate }: { onNavigate: (path: string) => void }) {
  return (
    <footer className="bg-white text-slate-600 pt-16 pb-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-8 pb-12 border-b border-slate-200">
          {/* Brand */}
          <div className="md:col-span-6 space-y-3">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-[#0f2460] flex items-center justify-center text-white shadow-sm">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div className="leading-tight">
                <p className="font-bold text-slate-900 text-sm tracking-tight">
                  AquaGuard AI
                </p>
                <p className="text-[10px] text-slate-500">
                  Cameroon Flood Intelligence
                </p>
              </div>
            </div>
            <p className="text-xs text-slate-500 max-w-sm leading-relaxed">
              Predictive modeling for climate resilience and flood management in Cameroon.
            </p>
          </div>

          {/* Platform Links */}
          <div className="md:col-span-3 space-y-3">
            <h4 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              PLATFORM
            </h4>
            <ul className="space-y-2 text-xs">
              <li>
                <button
                  onClick={() => onNavigate('/dashboard')}
                  className="hover:text-slate-900 transition-colors text-left"
                >
                  Dashboard &amp; analytics
                </button>
              </li>
              <li>
                <button
                  onClick={() => onNavigate('/flood-map')}
                  className="hover:text-slate-900 transition-colors text-left"
                >
                  Interactive map
                </button>
              </li>
              <li>
                <button
                  onClick={() => onNavigate('/reports')}
                  className="hover:text-slate-900 transition-colors text-left"
                >
                  Reporting tools
                </button>
              </li>
              <li>
                <span className="text-slate-400 cursor-not-allowed">
                  API documentation
                </span>
              </li>
            </ul>
          </div>

          {/* Resources Links */}
          <div className="md:col-span-3 space-y-3">
            <h4 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              RESOURCES
            </h4>
            <ul className="space-y-2 text-xs">
              <li>
                <a href="#methodology" className="hover:text-slate-900 transition-colors">
                  Methodology
                </a>
              </li>
              <li>
                <button
                  onClick={() => onNavigate('/history')}
                  className="hover:text-slate-900 transition-colors text-left"
                >
                  Historical data archive
                </button>
              </li>
              <li>
                <button
                  onClick={() => onNavigate('/safety')}
                  className="hover:text-slate-900 transition-colors text-left"
                >
                  Emergency protocols
                </button>
              </li>
              <li>
                <button
                  onClick={() => onNavigate('/feedback')}
                  className="hover:text-slate-900 transition-colors text-left"
                >
                  Support center
                </button>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="pt-8 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-4">
          <p>© 2026 AquaGuard AI Initiative. All rights reserved.</p>
          <div className="flex items-center gap-6">
            <span className="hover:text-slate-800 cursor-pointer transition-colors">
              Privacy Policy
            </span>
            <span className="hover:text-slate-800 cursor-pointer transition-colors">
              Terms of Service
            </span>
            <span className="hover:text-slate-800 cursor-pointer transition-colors">
              Data Ethics
            </span>
          </div>
        </div>
      </div>
    </footer>
  )
}

// ─── Root Page Export ───────────────────────────────────────────────────────
export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-white font-sans text-slate-900 selection:bg-blue-100 selection:text-blue-900">
      <Navbar onLogin={() => navigate('/login')} />
      <HeroSection
        onAssess={() => navigate('/assess-flood-risk')}
        onMap={() => navigate('/flood-map')}
      />
      <CapabilitiesSection />
      <RiskMappingSection onExplore={() => navigate('/flood-map')} />
      <Footer onNavigate={navigate} />
    </div>
  )
}
