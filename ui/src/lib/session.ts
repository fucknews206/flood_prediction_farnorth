/** Single browser-side source of truth for AquaGuard's local auth session.
 *
 * The server remains authoritative for identity/ownership.  This object only
 * retains the signed-in presentation identity needed to attach local-dev
 * request headers and to choose public versus citizen navigation.
 */
export interface AquaGuardSession {
  user_id?: string
  username?: string
  email?: string
  name?: string
  role?: string
}

const SESSION_KEY = 'aquaguard_user'

export function getSession(): AquaGuardSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const session = JSON.parse(raw) as AquaGuardSession
    const identity = session.user_id || session.username || session.email
    return identity ? session : null
  } catch {
    return null
  }
}

export function setSession(session: AquaGuardSession): void {
  const user_id = String(session.user_id || session.username || session.email || '').trim()
  if (!user_id) throw new Error('Cannot store a session without an authenticated identity.')
  window.localStorage.setItem(SESSION_KEY, JSON.stringify({ ...session, user_id }))
  window.dispatchEvent(new Event('aquaguard-session-changed'))
}

export function clearSession(): void {
  const session = getSession()
  window.localStorage.removeItem(SESSION_KEY)
  // Assessment drafts are namespaced by owner. Clear only the departing
  // citizen's transient draft, never another browser user's data.
  const identity = session?.user_id || session?.username || session?.email
  if (identity) window.sessionStorage.removeItem(`aquaguard:assessment-draft:${identity}`)
  window.dispatchEvent(new Event('aquaguard-session-changed'))
}

export function isCitizen(session = getSession()): boolean {
  return Boolean(session && session.role !== 'admin' && session.role !== 'administrator')
}

export function assessmentDraftKey(session = getSession()): string {
  const identity = session?.user_id || session?.username || session?.email || 'visitor'
  return `aquaguard:assessment-draft:${identity}`
}

/**
 * Return the authenticated user's stable identity, or null for visitors.
 * Used for logging, scoping, and ownership checks.
 */
export function getCurrentUserId(): string | null {
  const session = getSession()
  return session?.user_id || session?.username || session?.email || null
}
