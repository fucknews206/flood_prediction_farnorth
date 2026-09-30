import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Mail, Lock, Eye, EyeOff, ShieldCheck, Globe, Cpu, Bell, ChevronRight, Home } from 'lucide-react'
import { setSession } from '@/lib/session'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
const API_BASE = `${API_BASE_URL}/api`

type ActiveTab = 'signin' | 'register'

// ─── Left Panel ───────────────────────────────────────────────────────────────
function LeftPanel() {
    return (
        <div
            className="hidden lg:flex lg:w-[52%] flex-col justify-between p-10 text-white relative overflow-hidden"
            style={{ background: '#0f2460' }}
        >
            {/* Real Cameroon flood risk map as background */}
            <div
                className="absolute inset-0"
                style={{
                    backgroundImage: 'url(/cameroon_flood_map.png)',
                    backgroundSize: 'cover',
                    backgroundPosition: 'center top',
                    backgroundRepeat: 'no-repeat',
                    opacity: 0.55,
                }}
            />
            {/* Dark navy overlay to keep text readable */}
            <div
                className="absolute inset-0"
                style={{
                    background: 'linear-gradient(180deg, rgba(10,25,80,0.72) 0%, rgba(10,25,80,0.55) 40%, rgba(10,25,80,0.80) 100%)',
                }}
            />

            {/* Top: Brand */}
            <div className="relative z-10">
                <div className="flex items-center gap-2 mb-1">
                    <div className="w-8 h-8 rounded-lg bg-white/20 flex items-center justify-center">
                        <svg viewBox="0 0 24 24" className="w-5 h-5 text-white fill-white">
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z" />
                        </svg>
                    </div>
                    <span className="font-bold text-lg tracking-tight">AquaGuard AI</span>
                </div>
                <p className="text-blue-200 text-sm">Predicting floods. Protecting communities.</p>
            </div>

            {/* Middle: Headline + Features */}
            <div className="relative z-10 flex-1 flex flex-col justify-center gap-8 py-8">
                <div>
                    <h1 className="text-4xl font-extrabold leading-tight tracking-tight mb-2">
                        AI Flood Prediction<br />System
                    </h1>
                </div>

                <div className="flex flex-col gap-4">
                    {[
                        {
                            icon: <Cpu className="w-5 h-5 text-blue-300" />,
                            title: 'AI-Powered Predictions',
                            desc: 'Advanced machine learning models forecasting flood risks with unprecedented accuracy.',
                        },
                        {
                            icon: <Globe className="w-5 h-5 text-blue-300" />,
                            title: 'Interactive Risk Maps',
                            desc: 'Real-time geographical visualization of vulnerable zones across Cameroon.',
                        },
                        {
                            icon: <Bell className="w-5 h-5 text-blue-300" />,
                            title: 'Early Warning Alerts',
                            desc: 'Automated, timely notifications for immediate disaster response and mitigation.',
                        },
                    ].map((f) => (
                        <div
                            key={f.title}
                            className="flex items-start gap-3 bg-white/10 rounded-xl p-4 backdrop-blur-sm"
                        >
                            <div className="mt-0.5 shrink-0 w-9 h-9 rounded-lg bg-white/15 flex items-center justify-center">
                                {f.icon}
                            </div>
                            <div>
                                <p className="font-semibold text-sm">{f.title}</p>
                                <p className="text-blue-200 text-xs mt-0.5 leading-relaxed">{f.desc}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Bottom: Stats */}
            <div className="relative z-10 flex gap-8 pt-4 border-t border-white/20">
                {[
                    { val: '—', label: 'LIVE COVERAGE' },
                    { val: '—', label: 'MODEL METRICS' },
                    { val: '—', label: 'REPORT COUNT' },
                ].map((s) => (
                    <div key={s.label}>
                        <p className="text-2xl font-extrabold">{s.val}</p>
                        <p className="text-blue-300 text-[10px] font-medium tracking-widest mt-0.5">{s.label}</p>
                    </div>
                ))}
            </div>
        </div>
    )
}

// ─── Sign In Form ──────────────────────────────────────────────────────────────
function SignInForm() {
    const navigate = useNavigate()
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [showPw, setShowPw] = useState(false)
    const [remember, setRemember] = useState(false)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')
        setLoading(true)
        const identifier = email.trim()
        if (!identifier || !password) { setError('Enter a valid username and password.'); setLoading(false); return }
        try {
            const response = await fetch(`${API_BASE}/auth/local-login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ identifier, password }),
})
            if (response.ok) {
                const payload = await response.json()
                setSession(payload.user)
                setLoading(false)
                navigate(payload.user.role === 'admin' ? '/admin-dashboard' : '/citizen-entry')
                return
            }
            throw new Error('Invalid username/email or password')
        } catch (error) {
            setError(error instanceof Error ? error.message : 'Unable to sign in right now.')
            setLoading(false)
        }
    }

    return (
        <form onSubmit={handleSubmit} className="space-y-5">
            <div>
                <h2 className="text-xl font-bold text-gray-900">Welcome Back</h2>
                <p className="text-gray-500 text-sm mt-1">Enter your credentials to access the dashboard.</p>
            </div>

            {/* Email */}
            <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Email Address</label>
                <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                        type="text"
                        required
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="official@domain.gov or username"
                        className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 bg-white transition-all"
                    />
                </div>
            </div>

            {error && <p className="text-sm text-red-600" role="alert">{error}</p>}

            {/* Password */}
            <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Password</label>
                <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                        type={showPw ? 'text' : 'password'}
                        required
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full pl-10 pr-10 py-2.5 border border-gray-200 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 bg-white transition-all"
                    />
                    <button
                        type="button"
                        onClick={() => setShowPw(!showPw)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    >
                        {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                </div>
            </div>

            {/* Remember + Forgot */}
            <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-600">
                    <input
                        type="checkbox"
                        checked={remember}
                        onChange={(e) => setRemember(e.target.checked)}
                        className="w-4 h-4 rounded border-gray-300 text-blue-900 focus:ring-blue-900/20"
                    />
                    Remember Me
                </label>
                <button
                    type="button"
                    onClick={(e) => { e.preventDefault(); alert('Password reset link sent.') }}
                    className="text-sm font-semibold text-blue-700 hover:text-blue-900 transition-colors"
                >
                    Forgot Password?
                </button>
            </div>

            {/* Submit */}
            <button
                type="submit"
                disabled={loading}
                className="w-full bg-[#0f2460] hover:bg-[#0a1c4e] text-white font-semibold text-sm py-3 rounded-lg shadow transition-all flex items-center justify-center gap-2 disabled:opacity-70 cursor-pointer"
            >
                {loading ? 'Signing in...' : 'Sign In to AquaGuard'}
                {!loading && <ChevronRight className="w-4 h-4" />}
            </button>

            {/* Footer badges */}
            <div className="flex items-center justify-between text-xs text-gray-400 pt-2">
                <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1"><ShieldCheck className="w-3.5 h-3.5" /> Secure Auth</span>
                    <span className="flex items-center gap-1"><Globe className="w-3.5 h-3.5" /> Gov Ready</span>
                </div>
                <span>v2.4.1</span>
            </div>

            <div className="flex justify-center gap-5 text-xs text-gray-400 pt-1">
                <button type="button" className="hover:text-gray-600">Help Center</button>
                <button type="button" className="hover:text-gray-600">Privacy</button>
                <button type="button" className="hover:text-gray-600">Terms</button>
            </div>
        </form>
    )
}

// ─── Register Form ─────────────────────────────────────────────────────────────
function RegisterForm() {
    const navigate = useNavigate()
    const [form, setForm] = useState({
        fullName: '', email: '', phone: '', region: 'Littoral', password: '', confirmPassword: '',
    })
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')

    const regions = ['Littoral', 'Centre', 'Far North', 'North', 'Adamaoua', 'West', 'South West', 'North West', 'East', 'South']

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')
        if (form.password !== form.confirmPassword) { setError('Passwords do not match.'); return }
        setLoading(true)
        try {
            const response = await fetch(`${API_BASE}/auth/local-register`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: form.fullName.trim(), email: form.email.trim(), password: form.password }),
            })
            const payload = await response.json()
            if (!response.ok) throw new Error(payload.detail || 'Unable to create your account.')
            setSession(payload.user)
            setLoading(false)
            navigate('/citizen-entry')
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to create your account.')
            setLoading(false)
        }
    }

    const field = (label: string, key: keyof typeof form, type = 'text', placeholder = '') => (
        <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">{label}</label>
            <input
                type={type}
                required
                value={form[key]}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                placeholder={placeholder}
                className="w-full px-3.5 py-2.5 border border-gray-200 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 bg-white transition-all"
            />
        </div>
    )

    return (
        <form onSubmit={handleSubmit} className="space-y-4">
            <div>
                <h2 className="text-xl font-bold text-gray-900">Create Account</h2>
            <p className="text-gray-500 text-sm mt-1">Register to receive flood alerts and access the portal.</p>
            </div>

            {error && <p className="text-sm text-red-600" role="alert">{error}</p>}

            {field('Full Name', 'fullName', 'text', 'Jean-Paul Nkoumou')}

            <div className="grid grid-cols-2 gap-3">
                {field('Email Address', 'email', 'email', 'user@domain.gov')}
                {field('Phone Number', 'phone', 'tel', '+237 6XX XX XX XX')}
            </div>

            <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Region</label>
                <select
                    value={form.region}
                    onChange={(e) => setForm({ ...form, region: e.target.value })}
                    className="w-full px-3.5 py-2.5 border border-gray-200 rounded-lg text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 bg-white transition-all"
                >
                    {regions.map((r) => <option key={r}>{r}</option>)}
                </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
                {field('Password', 'password', 'password', '••••••••')}
                {field('Confirm Password', 'confirmPassword', 'password', '••••••••')}
            </div>

            <button
                type="submit"
                disabled={loading}
                className="w-full bg-[#0f2460] hover:bg-[#0a1c4e] text-white font-semibold text-sm py-3 rounded-lg shadow transition-all flex items-center justify-center gap-2 disabled:opacity-70 cursor-pointer"
            >
                {loading ? 'Creating Account...' : 'Create Account'}
                {!loading && <ChevronRight className="w-4 h-4" />}
            </button>

            <div className="flex justify-center gap-5 text-xs text-gray-400 pt-1">
                <button type="button" className="hover:text-gray-600">Help Center</button>
                <button type="button" className="hover:text-gray-600">Privacy</button>
                <button type="button" className="hover:text-gray-600">Terms</button>
            </div>
        </form>
    )
}

// ─── Main Page ─────────────────────────────────────────────────────────────────
export default function LoginPage() {
    const navigate = useNavigate()
    const [tab, setTab] = useState<ActiveTab>('signin')

    return (
        <div className="min-h-screen flex bg-gray-50 font-sans">
            {/* Left panel */}
            <LeftPanel />

            {/* Right panel */}
            <div className="flex-1 flex items-center justify-center p-6 sm:p-10">
                <div className="w-full max-w-md">
                    <button
                        type="button"
                        onClick={() => navigate('/')}
                        className="mb-6 inline-flex items-center gap-2 text-sm font-semibold text-blue-800 hover:text-blue-950"
                    >
                        <Home className="h-4 w-4" /> Back to Home
                    </button>
                    {/* Tab switcher */}
                    <div className="flex border-b border-gray-200 mb-8">
                        <button
                            onClick={() => setTab('signin')}
                            className={`flex-1 py-3 text-sm font-semibold transition-all ${
                                tab === 'signin'
                                    ? 'text-blue-900 border-b-2 border-blue-900'
                                    : 'text-gray-400 hover:text-gray-600'
                            }`}
                        >
                            Sign In
                        </button>
                        <button
                            onClick={() => setTab('register')}
                            className={`flex-1 py-3 text-sm font-semibold transition-all ${
                                tab === 'register'
                                    ? 'text-blue-900 border-b-2 border-blue-900'
                                    : 'text-gray-400 hover:text-gray-600'
                            }`}
                        >
                            Register
                        </button>
                    </div>

                    {/* Form container */}
                    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8">
                        {tab === 'signin' ? (
                            <SignInForm />
                        ) : (
                            <RegisterForm />
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}
