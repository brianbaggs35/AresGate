import { fetchCollectors, type CollectorsReport } from '@/api/collectors'
import { fetchDashboard, type Dashboard, type DashboardWindow } from '@/api/dashboard'

/** The window the dashboard opens on, and so the only one fetched ahead. */
export const FIRST_WINDOW: DashboardWindow = '24h'
/** How long an answer fetched ahead may wait for its page. After that the page asks again, so a
 * page that was never opened can't show what was true a while ago. */
export const KEEP_MS = 10_000

export interface Early {
  window: DashboardWindow
  dashboard: Promise<Dashboard>
  collectors: Promise<CollectorsReport>
}

let early: { at: number; calls: Early } | null = null

/** Starts the dashboard's own requests, so that they travel while the page's code is still being
 * fetched. Called once it is known that someone is signed in, and only for the page they land on. */
export function prefetchDashboard(now = Date.now()): void {
  const calls: Early = {
    window: FIRST_WINDOW,
    dashboard: fetchDashboard(FIRST_WINDOW),
    collectors: fetchCollectors(),
  }
  // Nobody may ever ask for these (the person goes elsewhere first); that is not an error to report.
  // The page that does ask still gets the failure, since these catch a copy of each promise.
  calls.dashboard.catch(() => undefined)
  calls.collectors.catch(() => undefined)
  early = { at: now, calls }
}

/** What was fetched ahead for the window, handed over once, or null if there is none for it or it
 * has waited too long. */
export function takePrefetched(window: DashboardWindow, now = Date.now()): Early | null {
  const found = early
  early = null
  if (!found || found.calls.window !== window || now - found.at > KEEP_MS) return null
  return found.calls
}
