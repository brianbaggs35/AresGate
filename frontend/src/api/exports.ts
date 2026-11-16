import { zone } from '@/search'
import type { ViewPage } from '@/api/views'

export type ExportFormat = 'csv' | 'json'

/** Where each list's file is. It is a link, not a call: the browser saves it as it arrives. */
const PATHS: Record<ViewPage, string> = {
  incidents: '/api/incidents/export',
  alerts: '/api/alerts/deliveries/export',
  devices: '/api/devices/export',
  assets: '/api/assets/export',
}

/** Where what a list shows can be downloaded as a file: the filters and the order it was asked
 * with, with the times in this browser's time zone, and not the page or the offset, since the
 * file holds all of it. */
export function exportAddress(
  list: ViewPage,
  format: ExportFormat,
  asked: URLSearchParams,
): string {
  const params = new URLSearchParams(asked)
  for (const name of ['limit', 'offset', 'before']) params.delete(name)
  params.set('format', format)
  const tz = zone()
  if (tz) params.set('tz', tz)
  return `${PATHS[list]}?${params.toString()}`
}
