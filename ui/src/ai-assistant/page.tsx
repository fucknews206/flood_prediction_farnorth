'use client'

import { useState, useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import {
    Send,
    Bot,
    RefreshCw,
    Sparkles,
    TrendingUp,
    Loader,
    Settings,
    Zap,
    Brain,
    Database,
    Menu
} from 'lucide-react'
import CitizenSidebar from '@/components/CitizenSidebar'
import { dashboardApi, aiApi, farNorthRiskApi, userPredictionsApi, type Watershed, type UserPredictionRecord } from '@/lib/api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'

interface Message {
    id: number
    role: 'user' | 'assistant'
    content: string
    timestamp: Date
    confidence?: number
    recommendations?: string[]
    isError?: boolean
    isStreaming?: boolean
    evaluation?: {
        id: string
        overall_score: number
        confidence: number
        safety_score: number
        helpfulness: number
        accuracy: number
        reasoning: string
    }
}

const ASSISTANT_SESSION_KEY = 'aquaguard_ai_assistant_session_v1'
const LLM_UNAVAILABLE_MESSAGE = "I'm having trouble processing that request right now. Try asking about a specific Far North locality or division by name."

// Forecast questions are answered from the deterministic Far North forecast
// endpoint.  Keeping this intent separate prevents the general LLM from
// inventing probabilities or dates that are not present in the API response.
function isForecastQuestion(text: string): boolean {
    return /\b(will\s+it\s+flood|flood(?:ing)?\s+forecast|forecast(?:ed|ing)?|in\s+\d+\s+days?|tomorrow|this\s+week|next\s+(?:few|\d+)\s+days?|probability\s+of\s+flood(?:ing)?\s+(?:in\s+the\s+)?(?:the\s+)?(?:next|coming)|risk\s+highest)\b/i.test(text)
}

function isRiskRankingQuestion(text: string): boolean {
    const quantityRequest = /\b(?:give\s+me|show\s+me|list|name|just)\b.*\b(?:localit(?:y|ies)|areas?|places?)\b/i.test(text)
        || /^\s*(?:just\s+)?(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*$/i.test(text)
    const rankedRequest = /\b(?:highest|top\s*\d*|most\s+(?:at\s+)?risk|where\s+should\s+i\s+worry|which\s+(?:area|region|locality))\b/i.test(text)
    return quantityRequest || (rankedRequest && /\b(risk|flood|danger|worry|area|region|localit)/i.test(text))
}

const RANKING_NUMBER_WORDS: Record<string, number> = {
    one: 1, two: 2, three: 3, four: 4, five: 5,
    six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
}
function requestedRankingCount(text: string): number {
    const numeric = text.match(/\b(?:top|give\s+me|show\s+me|list|name|just)\s+(?:just\s+)?(\d{1,2})\b/i)
    if (numeric) return Math.max(1, Math.min(20, Number(numeric[1])))
    const word = text.match(/\b(?:give\s+me|show\s+me|list|name|just)\s+(?:just\s+)?(one|two|three|four|five|six|seven|eight|nine|ten)\b/i)
    if (word) return RANKING_NUMBER_WORDS[word[1].toLowerCase()]
    const bare = text.match(/^\s*(?:just\s+)?(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*$/i)
    if (bare) return Number(bare[1]) || RANKING_NUMBER_WORDS[bare[1].toLowerCase()]
    return 5
}

const FAR_NORTH_DIVISIONS = ['Logone-et-Chari', 'Mayo-Danay', 'Diamaré', 'Mayo-Sava', 'Mayo-Tsanaga', 'Mayo-Kani']
function canonicalMention(text: string, choices: string[]): string | null {
    const fold = (value: string) => value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
    const haystack = fold(text)
    // Match complete names only. Prefix/substring matches can turn words such
    // as "Primary" or "Compare" into fake locality queries.
    return choices.filter((choice) => {
        const tokens = fold(choice).match(/[a-z0-9]+/g) || []
        if (!tokens.length) return false
        return new RegExp(`(?<![a-z0-9])${tokens.join('[^a-z0-9]+')}(?![a-z0-9])`, 'i').test(haystack)
    }).sort((a, b) => b.length - a.length)[0] || null
}
function isDivisionQuestion(text: string): boolean {
    return /\bdivision\b/i.test(text) || Boolean(canonicalMention(text, FAR_NORTH_DIVISIONS))
}
function isLocalityRiskQuestion(text: string): boolean {
    return /\b(probability|risk|conditions?|flood(?:ing)?|danger|safe)\b/i.test(text)
}
function formatLocalityRisk(locality: string, payload: Record<string, any>): string {
    const percent = typeof payload.estimated_risk_percent === 'number' ? `${Number(payload.estimated_risk_percent).toFixed(1)}%` : 'unavailable'
    return `**${locality} — Far North operational assessment**\n\n- Risk level: **${payload.risk_level || 'Unavailable'}**\n- Estimated risk signal: **${percent}**\n- Data confidence: **${payload.confidence_score == null ? 'unavailable' : `${Number(payload.confidence_score).toFixed(1)}%`}**\n\nThis is the rules-based locality result returned by the backend, not a generated probability. Current environmental signals and safety guidance should be checked before acting.`
}
function formatDivisionRisk(payload: Record<string, any>): string {
    if (!payload.risk) return `**${payload.division || 'Selected division'}**\n\n${payload.coverage_note || 'No model-covered localities are mapped to this division.'}`
    const rows = (payload.localities || []).map((r: any) => `- **${r.locality}**: ${r.estimated_risk_percent == null ? 'unavailable' : `${Number(r.estimated_risk_percent).toFixed(1)}%`} (${r.risk_level || 'Unavailable'})`).join('\n')
    return `**${payload.division} division — maximum covered-locality risk**\n\n- Maximum: **${payload.risk.locality}**, **${Number(payload.risk.estimated_risk_percent).toFixed(1)}%** (${payload.risk.risk_level})\n- Coverage: ${payload.coverage_note}\n\nPer-locality breakdown:\n${rows}\n\nThe division result uses the maximum covered locality, not an average.`
}

function generalFloodAnswer(text: string): string | null {
    const q = text.toLowerCase()
    if (/\bmayos?\b/.test(q) && /\bmaroua\b/.test(q)) {
        return 'I do not have specific backend data identifying named waterways (mayos) in Maroua. I can provide the available locality risk and forecast signals for Maroua, but I will not substitute a generic definition for that location-specific question.'
    }
    if (/medium\s+(?:risk\s+)?score|score\s+of\s+65|65%/.test(q) && /medium|score|prediction/.test(q)) {
        return '**What a medium score of 65% means:** this is an elevated rules-based risk signal for the selected area, not a measured 65% probability that flooding will occur. It reflects the model\'s combined environmental and historical indicators. Check current alerts, rainfall and river conditions, and follow local safety guidance.'
    }
    if (/\btravel\b/.test(q) && /moderate|high|flood/.test(q)) {
        return '**Travel safety during moderate flood conditions:** avoid unnecessary travel through areas under flood warnings. Never drive or walk through moving or unknown-depth water, and do not cross a submerged bridge or road. Check official local alerts and use a known high-ground route. If water is rising, conditions are high risk even if the current label says moderate—delay travel and follow evacuation instructions.'
    }
    if (/cause|causes|why.*flood|types? of flood|rainfall.driven|river.driven/.test(q)) {
        return '**What causes flooding:** rainfall-driven (pluvial or flash) flooding happens when intense rain overwhelms drainage or saturates the ground. River-driven (fluvial) flooding happens when upstream runoff raises a river until it overtops its channel or defenses. They can combine: the Blangoua investigation in this project showed how a Chari overflow can produce flooding even when rainfall at the downstream locality is low.'
    }
    if (/\b(?:explain|what are|difference between)\b.*\bflood stages?\b|\bflood stages?\b/.test(q)) {
        return '**Flood stages:** a river reaches flood stage when water rises high enough to affect its banks. Impacts are commonly described as minor, moderate, or major, but the threshold is specific to each gauge and locality. Use the responsible local authority\'s gauge and warning definitions rather than treating these labels as universal water levels.'
    }
    if (/risk level|risk levels|moderate risk|high risk|low risk|what does.*risk/.test(q)) {
        return '**Risk levels:** LOW means the available rules-based signals are below their local thresholds; MODERATE means conditions or susceptibility warrant increased caution and monitoring; HIGH means the threshold signal is elevated and users should avoid exposure to floodwater, prepare to move, and follow official warnings. These labels are operational categories, not guaranteed probabilities.'
    }
    if (/estimated risk|risk score|data confidence|confidence number|confidence score/.test(q)) {
        return '**Estimated Risk and Data Confidence:** Estimated Risk is the rules-based system’s weighted signal from terrain susceptibility, current threshold conditions, and documented event history. It is not a probability unless the response explicitly labels a separate model probability. Data Confidence describes input completeness and match quality (such as grid, terrain, and historical-data coverage); it does not mean a flood is that percentage likely.'
    }
    if (/evacuat|prepare|preparedness|safety|what should i do|during.*flood|floodwater/.test(q)) {
        return '**General flood safety:** keep alerts enabled, prepare water, medication, documents, lighting, and a charged phone, and identify higher ground before conditions worsen. During flooding, move away from rivers and low crossings, never enter moving water, avoid downed electrical lines, and evacuate when instructed. Return only after authorities confirm it is safe.'
    }
    return null
}

type AssistantIntent = 'educational' | 'ranking' | 'forecast' | 'locality' | 'general'
function classifyAssistantIntent(text: string): AssistantIntent {
    // Classify before entity extraction. Educational questions must never be
    // sent through the locality matcher.
    if (generalFloodAnswer(text) !== null) return 'educational'
    if (isRiskRankingQuestion(text)) return 'ranking'
    if (isForecastQuestion(text)) return 'forecast'
    if (isLocalityRiskQuestion(text)) return 'locality'
    return 'general'
}

function formatRiskRanking(payload: { basis: string; results: Array<any> }): string {
    const rows = payload.results || []
    if (!rows.length) return 'No static Far North susceptibility ranking is available right now.'
    return `**Highest static susceptibility areas in the Far North**\n\n${rows.map((row, index) => `${index + 1}. **${row.name}** — susceptibility score **${Number(row.susceptibility_score).toFixed(2)}**, documented event count **${row.historical_verified_event_count}**${row.caveat ? `\n   _${row.caveat}_` : ''}`).join('\n')}\n\nThis is based on the **static susceptibility layer** (terrain and documented historical patterns), not live current conditions or a day-specific forecast.`
}

function requestedForecastIndex(text: string): number | null {
    if (/\btomorrow\b/i.test(text)) return 1
    const match = text.match(/\bin\s+(\d+)\s+days?\b/i)
    return match ? Math.max(0, Number(match[1])) : null
}

function formatForecastResponse(locality: string, payload: Record<string, any>, question: string): string {
    const rows = Array.isArray(payload.trajectory) ? payload.trajectory : []
    if (!rows.length) return `I could not find a forecast trajectory for ${locality} in the live forecast response.`

    const rowText = (row: Record<string, any>) => {
        const optionB = row.option_b_risk_level || (row.option_b_threshold_flag ? 'ELEVATED' : 'BASELINE')
        const probability = typeof row.classifier_probability === 'number'
            ? `${(row.classifier_probability * 100).toFixed(1)}%`
            : 'unavailable in the live response (required discharge lag is unavailable)'
        const disagreement = row.method_disagreement && row.method_disagreement !== 'NOT_AVAILABLE_UNTIL_GLOFAS_FORECAST'
            ? `; ${row.method_disagreement}`
            : ''
        return `- **${row.date}**: rules-based status **${optionB}**; exploratory RF probability **${probability}**${disagreement}.`
    }

    const exactIndex = requestedForecastIndex(question)
    const confidenceFollowUp = /confiden|certain|limitation|reliable|why/i.test(question)
    let selectedRows = rows
    let heading = `${locality} forecast for the next ${rows.length} days`
    if (exactIndex !== null) {
        const exact = rows[exactIndex]
        if (!exact) return `The live forecast contains ${rows.length} days, so day ${exactIndex} is outside the returned range.`
        selectedRows = [exact]
        heading = `${locality} forecast for ${exact.date}`
    } else if (/\bwhen\b|\bhighest\b|\brisk\s+highest\b/i.test(question)) {
        const flagged = rows.filter((r: any) => Number(r.option_b_threshold_flag) === 1)
        const candidates = flagged.length ? flagged : rows.filter((r: any) => typeof r.classifier_probability === 'number')
        if (candidates.length) {
            const highest = candidates.reduce((a: any, b: any) => {
                const av = typeof a.classifier_probability === 'number' ? a.classifier_probability : Number(a.option_b_threshold_flag || 0)
                const bv = typeof b.classifier_probability === 'number' ? b.classifier_probability : Number(b.option_b_threshold_flag || 0)
                return bv > av ? b : a
            })
            const highestValue = typeof highest.classifier_probability === 'number'
                ? highest.classifier_probability
                : Number(highest.option_b_threshold_flag || 0)
            selectedRows = candidates.filter((r: any) => {
                const value = typeof r.classifier_probability === 'number'
                    ? r.classifier_probability
                    : Number(r.option_b_threshold_flag || 0)
                return value === highestValue
            })
            heading = `${locality}: highest flagged day(s) in the returned forecast`
        } else {
            heading = `${locality}: no elevated day was flagged in the returned forecast`
        }
    }

    let answer = `Using the live Far North forecast for **${locality}** (not a generated estimate):\n\n**${heading}**\n${selectedRows.map(rowText).join('\n')}`
    if (exactIndex !== null && selectedRows[0]?.method_disagreement === 'NOT_AVAILABLE_UNTIL_GLOFAS_FORECAST') {
        answer += '\n\nThe two methods cannot be compared for this day because the RF probability is not available in the API response.'
    }
    if (confidenceFollowUp) {
        if (payload.basin_rainfall_data_source) answer += `\n\n**Basin-rainfall limitation:** ${payload.basin_rainfall_data_source}`
        const lagged = selectedRows.filter((r: any) => r.discharge_lag_fallback || r.discharge_lag_historical_unavailable)
        if (lagged.length) answer += '\n**Discharge-lag limitation:** at least one selected day uses unavailable/forecast-lead lag data; treat any RF probability with extra caution.'
    }
    return answer
}

// These legacy presentation helpers are retained for compatibility with old
// saved sessions, but the backend router now owns all intent and response
// formatting.  Mark the compatibility symbols as intentionally unused so the
// TypeScript build does not mistake them for an active client-side route.
void isForecastQuestion
void isRiskRankingQuestion
void requestedRankingCount
void isDivisionQuestion
void isLocalityRiskQuestion
void formatLocalityRisk
void formatDivisionRisk
void generalFloodAnswer
void classifyAssistantIntent
void formatRiskRanking
void formatForecastResponse


export default function Page() {
    const [messages, setMessages] = useState<Message[]>([
        {
            id: 1,
            role: 'assistant',
            content: `Hello! I'm AquaGuard AI, the Cameroon Far North flood assistant. I can help with locality or division-level flood risk, five-day forecasts, verified historical flood events, environmental signals, and practical safety guidance.

You can ask about a named town such as Zina, Yagoua, or Maga, a Far North division, forecast days, historical events, or what to do during flooding.

I use the project's Cameroon data and clearly distinguish operational rules-based results from exploratory forecasts.`,
            timestamp: new Date()
        }
    ])

    const location = useLocation()
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
    const [trajectoryContext, setTrajectoryContext] = useState<any>(location.state?.trajectoryContext || null)
    const [inputMessage, setInputMessage] = useState('')
    const [isLoading, setIsLoading] = useState(false)
    const [selectedWatershed, setSelectedWatershed] = useState('')
    // The deterministic forecast flow is scoped to a Far North locality.  The
    // Assess Flood Risk flow can later set this value; Kousséri is the default
    // locality already used by the Far North forecast demonstrations.
    const [selectedFarNorthLocality, setSelectedFarNorthLocality] = useState('')
    const [latestPrediction, setLatestPrediction] = useState<UserPredictionRecord | null>(null)
    const [, setFarNorthLocalities] = useState<string[]>(['Kousséri', 'Zina', 'Yagoua', 'Maga'])
    const [watersheds, setWatersheds] = useState<Watershed[]>([])
    const [loadingWatersheds, setLoadingWatersheds] = useState(true)
    const [hasUserSentMessage, setHasUserSentMessage] = useState(false)
    const [useAgents, setUseAgents] = useState(false)
    
    // NAT Agent Chat States
    const [chatMode, setChatMode] = useState<'normal' | 'nat'>('normal')
    const [natAgentType, setNatAgentType] = useState<string>('risk_analyzer')
    const [natLocation, setNatLocation] = useState<string>('Cameroon')
    const [natForecastHours, setNatForecastHours] = useState<number>(24)
    const [natScenario, setNatScenario] = useState<string>('routine_check')
    const [availableNATAgents, setAvailableNATAgents] = useState<any>({})
    const [loadingNATAgents, setLoadingNATAgents] = useState(true)
    
    // New NVIDIA provider states
    const [selectedProvider, setSelectedProvider] = useState<string>('auto')
    const [availableProviders, setAvailableProviders] = useState<any>({})
    const [selectedModel, setSelectedModel] = useState<string>('')
    const [availableModels, setAvailableModels] = useState<string[]>([])
    const [showSettings, setShowSettings] = useState(false)
    const [temperature, setTemperature] = useState<number>(0.7)
    const [maxTokens, setMaxTokens] = useState<number>(4096)
    const [loadingProviders, setLoadingProviders] = useState(true)

    const messagesEndRef = useRef<HTMLDivElement>(null)
    const inputRef = useRef<HTMLTextAreaElement>(null)
    const sessionHydrated = useRef(false)

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }

    useEffect(() => {
        if (location.state?.trajectoryContext) {
            const ctx = location.state.trajectoryContext
            setTrajectoryContext(ctx)
            if (ctx.location) {
                const locClean = ctx.location.split('·')[0].trim()
                setSelectedFarNorthLocality(locClean)
            }
            const contextMsg: Message = {
                id: Date.now(),
                role: 'assistant',
                content: `**7-Day Trajectory Chart Context Loaded**\n\n- **Location**: ${ctx.location}\n- **Selected Date**: ${ctx.selectedDate}\n- **Risk Condition**: ${ctx.selectedRiskValue}\n- **Model Probability**: ${ctx.probability}\n- **Overall Prediction**: ${ctx.prediction}\n- **Forecast Period**: ${ctx.forecastPeriod}\n\nI have the complete forecast details for this date and locality ready. How can I help explain this assessment?`,
                timestamp: new Date()
            }
            setMessages(prev => [contextMsg, ...prev])
        }
    }, [location.state])

    useEffect(() => {
        // Load the authenticated citizen's latest authoritative prediction so
        // explanations start from the same result shown on Prediction.  The
        // assistant never manufactures a second risk assessment.
        userPredictionsApi.getLatest().then((result) => {
            const prediction = result.prediction || null
            setLatestPrediction(prediction)
            if (prediction?.locality) setSelectedFarNorthLocality(prediction.locality)
        }).catch(() => setLatestPrediction(null))
    }, [])

    useEffect(() => {
        scrollToBottom()
    }, [messages])

    // Restore the conversation and Far North locality after a page reload.
    // This is deliberately client-side: it keeps the assistant responsive and
    // avoids sending personal conversation content to a separate session DB.
    useEffect(() => {
        try {
            const raw = window.localStorage.getItem(ASSISTANT_SESSION_KEY)
            if (raw) {
                const saved = JSON.parse(raw)
                if (Array.isArray(saved.messages) && saved.messages.length) {
                    setMessages(saved.messages.map((message: any) => ({
                        ...message,
                        timestamp: new Date(message.timestamp),
                        isStreaming: false
                    })))
                    setHasUserSentMessage(Boolean(saved.hasUserSentMessage))
                }
                if (typeof saved.selectedFarNorthLocality === 'string' && saved.selectedFarNorthLocality) {
                    setSelectedFarNorthLocality(saved.selectedFarNorthLocality)
                }
                if (typeof saved.selectedWatershed === 'string') setSelectedWatershed(saved.selectedWatershed)
                if (typeof saved.natLocation === 'string' && saved.natLocation) setNatLocation(saved.natLocation)
            }
        } catch (error) {
            console.warn('Could not restore assistant session:', error)
        } finally {
            sessionHydrated.current = true
        }
    }, [])

    useEffect(() => {
        if (!sessionHydrated.current) return
        try {
            const persisted = messages.filter(message => !message.isStreaming)
            window.localStorage.setItem(ASSISTANT_SESSION_KEY, JSON.stringify({
                messages: persisted,
                selectedFarNorthLocality,
                selectedWatershed,
                natLocation,
                hasUserSentMessage
            }))
        } catch (error) {
            console.warn('Could not persist assistant session:', error)
        }
    }, [messages, selectedFarNorthLocality, selectedWatershed, natLocation, hasUserSentMessage])

    // Fetch watersheds data
    useEffect(() => {
        const fetchWatersheds = async () => {
            try {
                setLoadingWatersheds(true)
                const data = await dashboardApi.getWatersheds()
                setWatersheds(data)
            } catch (error) {
                console.error('Failed to fetch watersheds:', error)
            } finally {
                setLoadingWatersheds(false)
            }
        }

        fetchWatersheds()
    }, [])

    useEffect(() => {
        // Keep the assistant's locality index available for entity validation.
        // Do not silently select an example locality when the citizen has not
        // selected one or made a prediction.
        farNorthRiskApi.localities().then((data) => {
            if (data.localities?.length) {
                setFarNorthLocalities(data.localities)
            }
        }).catch(() => undefined)
    }, [])

    // Fetch AI providers and models
    useEffect(() => {
        const fetchProviders = async () => {
            try {
                setLoadingProviders(true)
                const providersData = await aiApi.getProviders()
                setAvailableProviders(providersData)
                
                // Set default provider
                const defaultProvider = providersData.current_default || 'h2ogpte'
                setSelectedProvider(defaultProvider)
                
                // Fetch models for default provider
                if (providersData.providers[defaultProvider]?.available) {
                    const modelsData = await aiApi.getProviderModels(defaultProvider)
                    setAvailableModels(modelsData.models)
                    setSelectedModel(modelsData.default_model)
                }
            } catch (error) {
                console.error('Failed to fetch AI providers:', error)
            } finally {
                setLoadingProviders(false)
            }
        }

        fetchProviders()
    }, [])

    // Fetch NAT agents
    useEffect(() => {
        const fetchNATAgents = async () => {
            try {
                setLoadingNATAgents(true)
                const natData = await aiApi.getNATAgents()
                setAvailableNATAgents(natData)
            } catch (error) {
                console.error('Failed to fetch NAT agents:', error)
                setAvailableNATAgents({ nat_available: false, available_agents: {} })
            } finally {
                setLoadingNATAgents(false)
            }
        }

        fetchNATAgents()
    }, [])

    // Fetch models when provider changes
    useEffect(() => {
        if (selectedProvider && selectedProvider !== 'auto') {
            const fetchModels = async () => {
                try {
                    const modelsData = await aiApi.getProviderModels(selectedProvider)
                    setAvailableModels(modelsData.models)
                    setSelectedModel(modelsData.default_model)
                } catch (error) {
                    console.error('Failed to fetch models:', error)
                    setAvailableModels([])
                    setSelectedModel('')
                }
            }

            fetchModels()
        }
    }, [selectedProvider])


    const handleSendMessage = async () => {
        if (!inputMessage.trim() || isLoading) return

        const userMessage: Message = {
            id: Date.now(),
            role: 'user',
            content: inputMessage,
            timestamp: new Date()
        }

        const currentInput = inputMessage
        setMessages(prev => [...prev, userMessage])
        setHasUserSentMessage(true)
        setIsLoading(true)

        // Create a placeholder assistant message with loading indicator
        const assistantMessageId = Date.now() + 1
        const assistantMessage: Message = {
            id: assistantMessageId,
            role: 'assistant',
            content: '',
            timestamp: new Date(),
            isStreaming: true
        }

        setMessages(prev => [...prev, assistantMessage])

        // Clear input only after messages are added
        setInputMessage('')

        try {
            if (chatMode === 'normal') {
                // Normal chat mode - existing logic
                // Get watershed data for context
                const selectedWatershedData = selectedWatershed && watersheds.length > 0
                    ? watersheds.find(w => w.name === selectedWatershed)
                    : null

                // Prepare enhanced API request with provider selection
                const enhancedRequest = {
                    message: currentInput,
                    watershed_id: selectedWatershedData?.id,
                    provider: selectedProvider === 'auto' ? undefined : selectedProvider,
                    model: selectedModel || undefined,
                    use_agent: useAgents,
                    temperature: temperature,
                    max_tokens: maxTokens,
                    context: (selectedWatershedData || selectedFarNorthLocality) ? {
                        // Keep a selected Far-North locality as explicit
                        // context for a follow-up, while the backend remains
                        // the authority for resolving and querying it.
                        location: selectedFarNorthLocality || selectedWatershedData?.name,
                        name: selectedFarNorthLocality || selectedWatershedData?.name,
                        risk_level: selectedWatershedData?.current_risk_level,
                        risk_score: selectedWatershedData?.risk_score,
                        current_flow: selectedWatershedData?.current_streamflow_cms,
                        flood_stage: selectedWatershedData?.flood_stage_cms,
                        prediction_id: latestPrediction?.id,
                        prediction_date: latestPrediction?.created_at,
                        prediction_locality: latestPrediction?.locality,
                        prediction_risk_level: latestPrediction?.risk_level,
                        prediction_estimated_risk_percent: latestPrediction?.estimated_risk_percent,
                        prediction_confidence_score: latestPrediction?.confidence_score,
                        prediction_forecast_period: latestPrediction?.forecast_period,
                        prediction_details: latestPrediction?.details
                    } : undefined
                }

                // Stream AI response using enhanced API
                let fullContent = ''
                let evaluationData = null
                
                const backendStarted = performance.now()
                const llmStarted = performance.now()
                for await (const chunk of aiApi.enhancedStreamChat(enhancedRequest)) {
                    console.log('Received chunk:', chunk, typeof chunk); // Debug logging
                    
                    if (typeof chunk === 'object' && chunk !== null) {
                        if ((chunk as any).type === 'evaluation') {
                            // Handle evaluation data
                            evaluationData = (chunk as any).data
                        } else if ((chunk as any).type === 'provider_info') {
                            // Handle provider information (metadata only, not stored)
                            console.log('Provider info:', (chunk as any).data)
                        } else if ((chunk as any).type === 'error') {
                            fullContent = LLM_UNAVAILABLE_MESSAGE
                            setMessages(prev => prev.map(msg => msg.id === assistantMessageId
                                ? { ...msg, content: fullContent, isStreaming: false, isError: true }
                                : msg))
                            break
                        } else if ((chunk as any).type === 'stream_complete') {
                            // Stream completed with metadata
                            break
                        }
                    } else if (typeof chunk === 'string' && chunk.trim()) {
                        // Handle text content - accumulate it
                        fullContent = chunk

                        setMessages(prev => prev.map(msg =>
                            msg.id === assistantMessageId
                                ? { ...msg, content: fullContent, isStreaming: true }
                                : msg
                        ))
                    }
                }
                console.info('[assistant.timing] llm_response_generation_ms', (performance.now() - llmStarted).toFixed(1))
                console.info('[assistant.timing] backend_function_call_ms', (performance.now() - backendStarted).toFixed(1))

                // Mark streaming as complete and add evaluation data
                setMessages(prev => prev.map(msg =>
                    msg.id === assistantMessageId
                        ? { ...msg, isStreaming: false, evaluation: evaluationData }
                        : msg
                ))
            } else {
                // NAT agent chat mode
                const natRequest = {
                    message: currentInput,
                    agent_type: natAgentType,
                    location: natLocation,
                    forecast_hours: natForecastHours,
                    scenario: natScenario,
                    context: latestPrediction ? {
                        locality: latestPrediction.locality,
                        risk_level: latestPrediction.risk_level,
                        estimated_risk_percent: latestPrediction.estimated_risk_percent,
                        confidence_score: latestPrediction.confidence_score,
                        forecast_period: latestPrediction.forecast_period,
                        details: latestPrediction.details,
                    } : undefined,
                }

                let fullContent = ''
                let agentLogs: any[] = []
                
                for await (const chunk of aiApi.natStreamChat(natRequest)) {
                    console.log('Received NAT chunk:', chunk, typeof chunk);
                    
                    if (typeof chunk === 'object' && chunk !== null) {
                        if (chunk.type === 'start') {
                            // Handle start metadata
                            console.log('NAT agent started:', chunk.data)
                        } else if (chunk.type === 'log') {
                            // Handle agent logs
                            agentLogs.push(chunk.data)
                            
                            // Update message with current logs for real-time display
                            setMessages(prev => prev.map(msg =>
                                msg.id === assistantMessageId
                                    ? { 
                                        ...msg, 
                                        content: `**Agent ${natAgentType} is processing...**\n\n**Logs:**\n${agentLogs.map(log => `[${log.level}] ${log.message}`).join('\n')}`,
                                        isStreaming: true 
                                    }
                                    : msg
                            ))
                        } else if (chunk.type === 'result') {
                            // Handle final result
                            fullContent = chunk.data.output || 'Agent processing completed.'
                            
                            setMessages(prev => prev.map(msg =>
                                msg.id === assistantMessageId
                                    ? { 
                                        ...msg, 
                                        content: `**Agent: ${natAgentType}** | **Location: ${natLocation}**\n\n${fullContent}`,
                                        isStreaming: false 
                                    }
                                    : msg
                            ))
                        } else if (chunk.type === 'error') {
                            fullContent = LLM_UNAVAILABLE_MESSAGE
                            setMessages(prev => prev.map(msg => msg.id === assistantMessageId
                                ? { ...msg, content: fullContent, isStreaming: false, isError: true }
                                : msg))
                            break
                        } else if (chunk.type === 'done') {
                            break
                        }
                    }
                }

                // If we didn't get a result, use accumulated content
                if (!fullContent && agentLogs.length > 0) {
                    setMessages(prev => prev.map(msg =>
                        msg.id === assistantMessageId
                            ? { 
                                ...msg, 
                            content: `**Agent: ${natAgentType}** | **Location: ${natLocation}**\n\nAgent processing completed.`,
                                isStreaming: false 
                            }
                            : msg
                    ))
                }
            }

        } catch (error) {
            console.error('Error sending message to AI:', error)

            const errorMessage: Message = {
                id: Date.now() + 1,
                role: 'assistant',
            content: LLM_UNAVAILABLE_MESSAGE,
                timestamp: new Date(),
                isError: true,
                isStreaming: false
            }

            // Replace the placeholder message with error
            setMessages(prev => prev.map(msg =>
                msg.id === assistantMessageId
                    ? errorMessage
                    : msg
            ))
        } finally {
            setIsLoading(false)
        }
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSendMessage()
        }
    }

    const normalQuickQuestions = [
        "Is it safe to travel during moderate flood conditions?",
        "How should I prepare for potential flooding?",
        "What does a risk score of 6.5 mean?",
        "Explain the difference between flood stages"
    ]

    const natQuickQuestions = [
        "What is the flood risk in Yaoundé?",
        "Analyze current flood conditions in Cameroon",
        "Generate a 24-hour flood forecast for Douala",
        "Emergency response status check"
    ]

    const quickQuestions = chatMode === 'normal' ? normalQuickQuestions : natQuickQuestions

    const handleQuickQuestion = (question: string) => {
        setInputMessage(question)
        inputRef.current?.focus()
    }

    const clearChat = () => {
        setMessages([messages[0]]) // Keep only the initial welcome message
        setHasUserSentMessage(false)
    }

    return (
        <div className="flex h-screen w-full bg-[#060B13] font-sans text-slate-100 selection:bg-blue-600 selection:text-white overflow-hidden">
            {/* 1) Standard Citizen Dashboard Sidebar */}
            <CitizenSidebar
                isOpen={mobileMenuOpen}
                onClose={() => setMobileMenuOpen(false)}
            />

            {/* 2) Main Content Column */}
            <div className="flex-1 min-w-0 flex flex-col h-full overflow-hidden bg-[#060B13]">
                {/* Header with Controls */}
                <header className="shrink-0 flex flex-wrap justify-between items-center gap-4 px-4 sm:px-6 py-3.5 bg-[#060B13] border-b border-slate-800/80 z-20">
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => setMobileMenuOpen(true)}
                            className="lg:hidden p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors cursor-pointer"
                            aria-label="Open sidebar navigation"
                        >
                            <Menu className="w-5 h-5" />
                        </button>
                        <h1 className="text-xl font-semibold text-white flex items-center gap-2">
                            <Bot className="h-5 w-5 text-blue-400" />
                            AI Flood Assistant
                        </h1>
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                            {/* Chat Mode Selector */}
                            <div className="flex items-center bg-slate-800 rounded-lg p-1">
                                <button
                                    onClick={() => setChatMode('normal')}
                                    className={`px-3 py-1 text-sm rounded-md transition-colors ${
                                        chatMode === 'normal'
                                            ? 'bg-[#1D68F7] text-white shadow-sm'
                                            : 'text-slate-400 hover:text-white'
                                    }`}
                                >
                                    Normal Chat
                                </button>
                                <button
                                    onClick={() => setChatMode('nat')}
                                    disabled={!availableNATAgents.nat_available}
                                    className={`px-3 py-1 text-sm rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                                        chatMode === 'nat'
                                            ? 'bg-[#1D68F7] text-white shadow-sm'
                                            : 'text-slate-400 hover:text-white'
                                    }`}
                                >
                                    NAT Agents {!availableNATAgents.nat_available && '(Unavailable)'}
                                </button>
                            </div>

                            {/* Normal Chat Controls */}
                            {chatMode === 'normal' && (
                                <>
                                    {/* Provider Selection */}
                                    <select
                                        value={selectedProvider}
                                        onChange={(e) => setSelectedProvider(e.target.value)}
                                        disabled={loadingProviders}
                                        className="text-sm border border-border/20 rounded-lg px-3 py-1.5 bg-card text-card-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                                        title="AI Provider"
                                    >
                                        <option value="auto">Auto</option>
                                        {Object.entries(availableProviders.providers || {}).map(([name, info]: [string, any]) => (
                                            <option key={name} value={name} disabled={!info.available}>
                                                {name === 'h2ogpte' ? 'H2OGPTE' : name === 'nvidia' ? 'NVIDIA' : name}
                                                {!info.available && ' (Unavailable)'}
                                            </option>
                                        ))}
                                    </select>
                                </>
                            )}

                            {/* NAT Agent Controls */}
                            {chatMode === 'nat' && availableNATAgents.nat_available && (
                                <>
                                    {/* Agent Type Selection */}
                                    <select
                                        value={natAgentType}
                                        onChange={(e) => setNatAgentType(e.target.value)}
                                        disabled={loadingNATAgents}
                                        className="text-sm border border-border/20 rounded-lg px-3 py-1.5 bg-card text-card-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                                        title="NAT Agent Type"
                                    >
                                        {Object.entries(availableNATAgents.available_agents || {}).map(([key, _name]: [string, any]) => (
                                            <option key={key} value={key}>
                                                {key.replace('_', ' ').split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
                                            </option>
                                        ))}
                                        <option value="all">All Agents (Comprehensive)</option>
                                    </select>

                                    {/* Location for Risk Analyzer and Predictor */}
                                    {(natAgentType === 'risk_analyzer' || natAgentType === 'predictor') && (
                                        <input
                                            type="text"
                                            value={natLocation}
                                            onChange={(e) => setNatLocation(e.target.value)}
                                            placeholder="Location (e.g., Douala)"
                                            className="text-sm border border-border/20 rounded-lg px-3 py-1.5 bg-card text-card-foreground focus:outline-none focus:ring-2 focus:ring-ring max-w-32"
                                            title="Location"
                                        />
                                    )}

                                    {/* Forecast Hours for Predictor */}
                                    {natAgentType === 'predictor' && (
                                        <input
                                            type="number"
                                            value={natForecastHours}
                                            onChange={(e) => setNatForecastHours(parseInt(e.target.value) || 24)}
                                            min="1"
                                            max="168"
                                            className="text-sm border border-border/20 rounded-lg px-3 py-1.5 bg-card text-card-foreground focus:outline-none focus:ring-2 focus:ring-ring w-20"
                                            title="Forecast Hours"
                                        />
                                    )}

                                    {/* Scenario for Emergency Responder */}
                                    {natAgentType === 'emergency_responder' && (
                                        <select
                                            value={natScenario}
                                            onChange={(e) => setNatScenario(e.target.value)}
                                            className="text-sm border border-border/20 rounded-lg px-3 py-1.5 bg-card text-card-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                                            title="Emergency Scenario"
                                        >
                                            <option value="routine_check">Routine Check</option>
                                            <option value="flash_flood_alert">Flash Flood Alert</option>
                                        </select>
                                    )}
                                </>
                            )}

                            {/* Model Selection (when specific provider is selected) */}
                            {selectedProvider !== 'auto' && availableModels.length > 0 && (
                                <select
                                    value={selectedModel}
                                    onChange={(e) => setSelectedModel(e.target.value)}
                                    className="text-sm border border-border/20 rounded-lg px-3 py-1.5 bg-card text-card-foreground focus:outline-none focus:ring-2 focus:ring-ring max-w-48"
                                    title="AI Model"
                                >
                                    {availableModels.map((model) => (
                                        <option key={model} value={model}>
                                            {model.split('/').pop() || model}
                                        </option>
                                    ))}
                                </select>
                            )}

                            {/* Watershed Selection */}
                            <select
                                value={selectedWatershed}
                                onChange={(e) => setSelectedWatershed(e.target.value)}
                                disabled={loadingWatersheds}
                                className="text-sm border border-border/20 rounded-lg px-3 py-1.5 bg-card text-card-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                            >
                                <option value="">All Watersheds</option>
                                {watersheds.map((watershed) => (
                                    <option key={watershed.id} value={watershed.name}>
                                        {watershed.name}
                                    </option>
                                ))}
                            </select>

                            {/* Settings Button */}
                            <button
                                onClick={() => setShowSettings(!showSettings)}
                                className="inline-flex items-center px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-lg transition-colors text-sm"
                            >
                                <Settings className="h-4 w-4 mr-1.5" />
                                Settings
                            </button>

                            {/* Clear Button */}
                            <button
                                onClick={clearChat}
                                className="inline-flex items-center px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-lg transition-colors text-sm"
                            >
                                <RefreshCw className="h-4 w-4 mr-1.5" />
                                Clear
                            </button>
                        </div>
                    </header>

                    {/* Advanced Settings Panel */}
                    {showSettings && (
                        <div className="shrink-0 border-b border-slate-800/80 bg-[#0a1120] px-6 py-4">
                            <div className="max-w-4xl mx-auto">
                                <div className="flex items-center justify-between mb-4">
                                    <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                                        <Brain className="h-4 w-4 text-primary" />
                                        AI Configuration
                                    </h3>
                                    <div className="flex items-center space-x-4 text-xs text-muted-foreground">
                                        {selectedProvider !== 'auto' && availableProviders.providers?.[selectedProvider] && (
                                            <div className="flex items-center space-x-2">
                                                <div className={`w-2 h-2 rounded-full ${availableProviders.providers[selectedProvider].available ? 'bg-green-500' : 'bg-red-500'}`} />
                                                <span>{selectedProvider === 'nvidia' ? 'NVIDIA NIM' : selectedProvider === 'h2ogpte' ? 'H2OGPTE' : selectedProvider}</span>
                                                {availableProviders.providers[selectedProvider].info?.supports_agents && (
                                                    <div title="Supports Agents">
                                                        <Zap className="h-3 w-3 text-primary" />
                                                    </div>
                                                )}
                                                {availableProviders.providers[selectedProvider].info?.supports_embeddings && (
                                                    <div title="Supports Embeddings">
                                                        <Database className="h-3 w-3 text-blue-500" />
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                                    <div>
                                        <label className="block text-xs font-medium text-muted-foreground mb-1">Temperature</label>
                                        <div className="flex items-center space-x-2">
                                            <input
                                                type="range"
                                                min="0"
                                                max="2"
                                                step="0.1"
                                                value={temperature}
                                                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                                                className="flex-1"
                                            />
                                            <span className="text-xs w-8 text-center">{temperature.toFixed(1)}</span>
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-1">Controls randomness (0.0-2.0)</p>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-muted-foreground mb-1">Max Tokens</label>
                                        <div className="flex items-center space-x-2">
                                            <input
                                                type="range"
                                                min="512"
                                                max="8192"
                                                step="256"
                                                value={maxTokens}
                                                onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                                                className="flex-1"
                                            />
                                            <span className="text-xs w-12 text-center">{maxTokens}</span>
                                        </div>
                                        <p className="text-xs text-muted-foreground mt-1">Maximum response length</p>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-muted-foreground mb-1">Provider Features</label>
                                        <div className="space-y-1">
                                            {availableProviders.nvidia_features && (
                                                <div className="text-xs text-muted-foreground">
                                                    <div className="flex items-center space-x-2">
                                                        <span className={`w-2 h-2 rounded-full ${availableProviders.nvidia_features.agents_enabled ? 'bg-green-500' : 'bg-gray-400'}`} />
                                                        <span>NVIDIA Agents: {availableProviders.nvidia_features.agents_enabled ? 'Enabled' : 'Disabled'}</span>
                                                    </div>
                                                    <div className="flex items-center space-x-2">
                                                        <span className={`w-2 h-2 rounded-full ${availableProviders.nvidia_features.rag_enabled ? 'bg-green-500' : 'bg-gray-400'}`} />
                                                        <span>NVIDIA RAG: {availableProviders.nvidia_features.rag_enabled ? 'Enabled' : 'Disabled'}</span>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Main Content Area */}
                    <div className="flex-1 min-h-0 flex flex-col relative bg-[#060B13]">
                        {/* Messages and Quick Questions Container */}
                        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-6">
                            <div className="w-full max-w-4xl mx-auto flex flex-col h-full">

                                {/* Active 7-Day Trajectory Chart Context Banner */}
                                {trajectoryContext && (
                                    <div className="mb-4 p-4 rounded-xl bg-blue-950/40 border border-blue-800/80 shadow-md">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <Sparkles className="w-4 h-4 text-blue-400" />
                                                <span className="text-xs font-bold text-white">Active 7-Day Trajectory Context</span>
                                                <span className="text-[10px] font-semibold bg-blue-900/60 text-blue-200 px-2 py-0.5 rounded-full border border-blue-700/60">
                                                    {trajectoryContext.selectedDate}
                                                </span>
                                            </div>
                                            <button
                                                onClick={() => setTrajectoryContext(null)}
                                                className="text-[11px] text-slate-400 hover:text-white cursor-pointer"
                                            >
                                                Dismiss
                                            </button>
                                        </div>
                                        <p className="mt-1.5 text-xs text-slate-300">
                                            <strong>{trajectoryContext.location}</strong> · Status: <span className={trajectoryContext.risk.includes('Elevated') ? 'text-rose-400 font-semibold' : 'text-emerald-400 font-semibold'}>{trajectoryContext.selectedRiskValue}</span> · Signal: <strong className="text-blue-300">{trajectoryContext.probability}</strong> (Confidence: {trajectoryContext.confidence})
                                        </p>
                                    </div>
                                )}

                                {/* Chat Messages */}
                                <div className="space-y-6 pb-6">
                                    {messages.map((message) => (
                                        <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                                            <div className={`max-w-[85%] rounded-2xl px-6 py-4 ${message.role === 'assistant'
                                                ? message.isError
                                                    ? 'bg-rose-950/40 text-rose-300 border border-rose-800/60'
                                                    : 'bg-[#0f172a] text-slate-100 border border-slate-800/80 shadow-md'
                                                : 'bg-[#1D68F7] text-white shadow-md shadow-blue-600/30'
                                                }`}>
                                                <div className="text-sm leading-relaxed">
                                                    {message.role === 'assistant' ? (
                                                        message.isStreaming && !message.content ? (
                                                            // Show loading indicator when starting to stream
                                                            <div className="flex items-center space-x-2">
                                                                <Loader className="h-4 w-4 animate-spin text-primary" />
                                                                <span className="text-muted-foreground">AI is thinking...</span>
                                                            </div>
                                                        ) : (
                                                            <div>
                                                                <ReactMarkdown
                                                                    remarkPlugins={[remarkGfm]}
                                                                    rehypePlugins={[rehypeSanitize]}
                                                                    components={{
                                                                        h1: ({ ...props }) => <h1 className="text-lg font-bold mb-3 text-current" {...props} />,
                                                                        h2: ({ ...props }) => <h2 className="text-base font-semibold mb-2 text-current flex items-center gap-2" {...props} />,
                                                                        h3: ({ ...props }) => <h3 className="text-sm font-semibold mb-2 text-current" {...props} />,
                                                                        p: ({ ...props }) => <p className="mb-2 text-current" {...props} />,
                                                                        ul: ({ ...props }) => <ul className="list-disc ml-4 mb-3 space-y-1" {...props} />,
                                                                        ol: ({ ...props }) => <ol className="list-decimal ml-4 mb-3 space-y-1" {...props} />,
                                                                        li: ({ ...props }) => <li className="text-current" {...props} />,
                                                                        blockquote: ({ ...props }) => (
                                                                            <blockquote className="border-l-4 border-orange-400 bg-orange-50/10 p-3 rounded-r mb-3 text-current" {...props} />
                                                                        ),
                                                                        code: ({ className, children, ...props }) => (
                                                                            <code
                                                                                className="bg-muted/80 text-current px-1.5 py-0.5 rounded text-xs font-mono"
                                                                                {...props}
                                                                            >
                                                                                {children}
                                                                            </code>
                                                                        ),
                                                                        pre: ({ ...props }) => (
                                                                            <pre className="bg-muted/80 p-3 rounded text-xs font-mono overflow-x-auto mb-3 text-current" {...props} />
                                                                        ),
                                                                        strong: ({ ...props }) => <strong className="font-bold text-current" {...props} />,
                                                                        em: ({ ...props }) => <em className="italic text-current" {...props} />,
                                                                        hr: ({ ...props }) => <hr className="border-border/20 my-4" {...props} />,
                                                                        a: ({ ...props }) => <a className="text-blue-400 hover:text-blue-300 underline" {...props} />
                                                                    }}
                                                                >
                                                                    {message.content}
                                                                </ReactMarkdown>
                                                            </div>
                                                        )
                                                    ) : (
                                                        <div className="whitespace-pre-wrap">
                                                            {message.content}
                                                        </div>
                                                    )}
                                                </div>

                                                {message.recommendations && message.recommendations.length > 0 && (
                                                    <div className="mt-4 pt-3 border-t border-border/10">
                                                        <p className="text-xs font-medium mb-2 flex items-center gap-1 opacity-80">
                                                            <Sparkles className="h-3 w-3" />
                                                            Recommendations:
                                                        </p>
                                                        <ul className="text-xs space-y-1 opacity-90">
                                                            {message.recommendations.slice(0, 3).map((rec, index) => (
                                                                <li key={index} className="flex items-start">
                                                                    <span className="mr-2">•</span>
                                                                    <span>{rec}</span>
                                                                </li>
                                                            ))}
                                                        </ul>
                                                    </div>
                                                )}

                                                <div className="flex items-center justify-between mt-3 text-xs opacity-60">
                                                    <span>
                                                        {message.timestamp.toLocaleTimeString()}
                                                    </span>
                                                    {message.confidence && (
                                                        <span className="flex items-center gap-1">
                                                            <TrendingUp className="h-3 w-3" />
                                                            {(message.confidence * 100).toFixed(0)}%
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    ))}

                                    <div ref={messagesEndRef} />
                                </div>

                                {/* Context Information - Above quick questions */}
                                {selectedWatershed && watersheds.length > 0 && (() => {
                                    const watershed = watersheds.find(w => w.name === selectedWatershed)
                                    if (!watershed) return null

                                    return (
                                        <div className="text-center pb-6">
                                            <div className="inline-flex items-center px-4 py-2 bg-muted/50 rounded-full text-sm text-muted-foreground">
                                                <span className="font-medium text-foreground">{selectedWatershed}</span>
                                                <span className="mx-2">•</span>
                                                <span>Risk: {watershed.current_risk_level}</span>
                                                <span className="mx-2">•</span>
                                                <span>Score: {watershed.risk_score}/10</span>
                                            </div>
                                        </div>
                                    )
                                })()}

                                {/* Quick Questions Pills - Only show if user hasn't sent a message */}
                                {!hasUserSentMessage && (
                                    <div className="flex flex-wrap gap-2 justify-center pb-6">
                                        {quickQuestions.map((question, index) => (
                                            <button
                                                key={index}
                                                onClick={() => handleQuickQuestion(question)}
                                                disabled={isLoading}
                                                className="px-4 py-2 bg-slate-800/80 hover:bg-slate-700 text-slate-200 rounded-full text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed border border-slate-700/60 shadow-sm cursor-pointer"
                                            >
                                                {question}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Fixed Input Area at Bottom */}
                        <div className="shrink-0 bg-[#060B13] border-t border-slate-800/80 p-4 sm:p-6">
                            <div className="w-full max-w-4xl mx-auto">
                                <div className="flex items-end space-x-3 bg-[#0a1120] border border-slate-800/80 rounded-2xl p-4 shadow-xl">
                                    <div className="flex-1">
                                        <textarea
                                            ref={inputRef}
                                            value={inputMessage}
                                            onChange={(e) => setInputMessage(e.target.value)}
                                            onKeyDown={handleKeyDown}
                                            placeholder={chatMode === 'normal' 
                                                ? "Ask about flood conditions, safety, or data interpretation..." 
                                                : `Ask ${natAgentType.replace('_', ' ')} agent about flood analysis...`}
                                            className="w-full bg-transparent text-card-foreground placeholder-muted-foreground focus:outline-none resize-none text-sm"
                                            rows={2}
                                            disabled={isLoading}
                                        />
                                    </div>
                                    {/* Agent toggle only for normal chat mode */}
                                    {chatMode === 'normal' && (
                                        <button
                                            onClick={() => setUseAgents(!useAgents)}
                                            className={`flex items-center space-x-2 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${useAgents
                                                    ? 'bg-primary/10 text-primary border border-primary/20 shadow-sm hover:bg-primary/15 dark:bg-primary/20 dark:text-primary dark:border-primary/30'
                                                    : 'bg-muted hover:bg-muted/80 text-muted-foreground border border-border hover:border-border/60 dark:bg-card dark:hover:bg-card/80 dark:border-sidebar-border'
                                                }`}
                                            title={useAgents ? "AI Agents enabled" : "Enable AI Agents"}
                                        >
                                            <Bot className="h-4 w-4" />
                                            <span>Agent</span>
                                        </button>
                                    )}
                                    
                                    {/* NAT Agent status indicator */}
                                    {chatMode === 'nat' && (
                                        <div className="flex items-center space-x-2 px-3 py-2 bg-primary/10 text-primary border border-primary/20 rounded-lg text-sm">
                                            <Bot className="h-4 w-4" />
                                            <span>NAT Agent</span>
                                        </div>
                                    )}
                                    <button
                                        onClick={handleSendMessage}
                                        disabled={!inputMessage.trim() || isLoading}
                                        className="flex-shrink-0 p-2 bg-primary hover:bg-primary/90 disabled:bg-muted text-primary-foreground rounded-lg transition-colors disabled:cursor-not-allowed"
                                    >
                                        <Send className="h-4 w-4" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
        </div>
    )
}
