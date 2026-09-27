'use client'

import { useState } from 'react'
import {
  Settings,
  Shield,
  Database,
  CheckCircle2,
  HardDrive,
  Cpu,
  User,
  Key,
} from 'lucide-react'

export default function AdminSettingsView() {
  const [copied, setCopied] = useState(false)

  const adminUser = (() => {
    try {
      const u = JSON.parse(localStorage.getItem('aquaguard_user') || '{}')
      return u.username || u.name || 'Administrator'
    } catch {
      return 'Administrator'
    }
  })()

  return (
    <div className="space-y-6">
      {/* HEADER */}
      <div>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#0B172A] text-blue-400 font-bold text-[11px] tracking-wider uppercase mb-2 shadow-xs">
          <Settings className="h-3.5 w-3.5 text-blue-400" />
          <span>SYSTEM & CONFIGURATION</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight leading-tight">
          Admin Settings
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 font-medium mt-1">
          System infrastructure, administrative credentials, and operational scope settings.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Administrator Profile Card */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs space-y-4">
          <div className="flex items-center gap-3 pb-3 border-b border-slate-100">
            <div className="h-12 w-12 rounded-2xl bg-blue-600 text-white flex items-center justify-center font-extrabold text-lg shadow-sm">
              <User className="h-6 w-6" />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-slate-900">
                {adminUser}
              </h3>
              <span className="px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 text-xs font-bold border border-blue-200/60">
                System Administrator
              </span>
            </div>
          </div>

          <div className="space-y-2 text-xs text-slate-600">
            <div className="flex justify-between py-1 border-b border-slate-50">
              <span className="text-slate-400">Username / Identity:</span>
              <span className="font-bold text-slate-900">{adminUser}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-50">
              <span className="text-slate-400">Access Level:</span>
              <span className="font-bold text-slate-900">Full Administrator Privileges</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-50">
              <span className="text-slate-400">Primary Route:</span>
              <span className="font-mono text-blue-600 font-semibold">/admin-dashboard</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Session Mode:</span>
              <span className="font-bold text-emerald-600">Active (Authenticated)</span>
            </div>
          </div>
        </div>

        {/* Infrastructure Health Card */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200/80 shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Database className="h-5 w-5 text-blue-600" />
              <h3 className="text-base font-extrabold text-slate-900">
                System Infrastructure
              </h3>
            </div>
            <span className="px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-xs font-bold border border-emerald-200">
              Online
            </span>
          </div>

          <div className="space-y-2.5 text-xs text-slate-700">
            <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="font-bold">PostgreSQL & PostGIS</span>
              </div>
              <span className="text-slate-500 font-medium">Connected (Port 5432)</span>
            </div>

            <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="font-bold">Redis Cache & Queue</span>
              </div>
              <span className="text-slate-500 font-medium">Active (Port 6379)</span>
            </div>

            <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="font-bold">FastAPI Backend Server</span>
              </div>
              <span className="text-slate-500 font-medium">Active (Port 8000)</span>
            </div>

            <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="font-bold">Operational Scope</span>
              </div>
              <span className="text-blue-700 font-bold">Far North Cameroon</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
