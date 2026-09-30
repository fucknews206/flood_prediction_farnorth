export interface AppConfig {
    oidc_authority: string
    oidc_client_id: string
    oidc_client_secret: string
    oidc_scope: string
    base_url: string
}

let appConfig: AppConfig | null = null

// Use the absolute backend URL in production so the config request reaches
// the Render backend instead of the Vercel domain.
const API_BASE = `${import.meta.env.VITE_API_BASE_URL || ''}/api`

export const fetchConfig = async (): Promise<AppConfig> => {
    try {
        const response = await fetch(`${API_BASE}/config`)

        if (response.ok) {
            appConfig = await response.json()
            if (appConfig) {
                return appConfig
            }
        }
    } catch (error) {
        console.warn('Backend configuration endpoint unavailable, using local development fallback:', error)
    }

    return {
        oidc_authority: '',
        oidc_client_id: '',
        oidc_client_secret: '',
        oidc_scope: '',
        base_url: '',
    }
}

export const initializeApp = async (): Promise<boolean> => {
    try {
        await fetchConfig()
        return true
    } catch (error) {
        console.error('Failed to initialize app:', error)
        return false
    }
}
