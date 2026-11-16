import { apiDelete, apiGet, apiPut } from '@/api/client'

/** How wide a widget is: the whole row, or half of it (a phone always shows it whole). */
export type WidgetSize = 'half' | 'full'

/** One widget of the dashboard as an account has it. */
export interface PlaceOut {
  id: string
  size: WidgetSize
  hidden: boolean
}

/** A layout to start from. */
export interface PresetOut {
  key: string
  title: string
  description: string
  widgets: PlaceOut[]
}

export interface LayoutOut {
  /** The preset it started from, or null for one the account made. */
  preset: string | null
  widgets: PlaceOut[]
  presets: PresetOut[]
}

export interface LayoutIn {
  preset: string | null
  widgets: PlaceOut[]
}

const PATH = '/dashboard/layout'

export const fetchLayout = () => apiGet<LayoutOut>(PATH)

export const saveLayout = (layout: LayoutIn, csrfToken: string) =>
  apiPut<LayoutOut>(PATH, layout, csrfToken)

export const resetLayout = (csrfToken: string) => apiDelete(PATH, csrfToken)

/** Where the dashboard hears that something changed, as server-sent events. */
export const LIVE_PATH = '/api/dashboard/stream'
