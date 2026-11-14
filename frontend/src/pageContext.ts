import type { RouteLocationNormalizedLoaded } from 'vue-router'

import type { PageContext } from '@/api/aiChat'
import { MAX_QUESTION, STARTERS } from '@/chat'

type Where = Pick<RouteLocationNormalizedLoaded, 'name' | 'params' | 'query' | 'meta'>

/** The longest search or title handed to the assistant, as the API takes it. */
const MAX_SEARCH = 200
const MAX_TITLE = 80

function text(value: unknown, most: number): string | undefined {
  return typeof value === 'string' && value.trim() !== '' ? value.trim().slice(0, most) : undefined
}

/** What the page on screen is about, handed to the assistant when you ask from the panel: the
 * incident or the device you are looking at, the search on the logs or the list of incidents, or
 * only which page it is. Null on the assistant's own pages, which are the conversation. */
export function pageOf(route: Where): PageContext | null {
  const name = typeof route.name === 'string' ? route.name : ''
  if (name === 'assistant' || name === 'assistant-chat') return null
  if (name === 'incident') {
    const id = Number(route.params.id)
    return Number.isSafeInteger(id) && id > 0 ? { kind: 'incident', id } : null
  }
  if (name === 'asset') {
    const found = /^device-(\d{1,15})$/.exec(String(route.params.key))
    return found ? { kind: 'device', id: Number(found[1]) } : { kind: 'other', title: 'Assets' }
  }
  if (name === 'device') {
    const address = text(route.params.address, 45)
    return address ? { kind: 'device', address } : { kind: 'other', title: 'Devices' }
  }
  if (name === 'logs' || name === 'incidents') {
    const query = text(route.query.q, MAX_SEARCH)
    return { kind: name, ...(query ? { query } : {}) }
  }
  const title = text(route.meta.title, MAX_TITLE)
  return title ? { kind: 'other', title } : null
}

/** What the panel says it is looking at, in words, or null where there is nothing to say. */
export function looking(page: PageContext | null): string | null {
  if (page === null) return null
  switch (page.kind) {
    case 'incident':
      return `Looking at incident ${(page.id ?? 0).toString()}`
    case 'device':
      return page.id ? `Looking at device ${page.id.toString()}` : 'Looking at this device'
    case 'logs':
      return page.query ? `Looking at the logs: ${page.query}` : 'Looking at the logs'
    case 'incidents':
      return page.query ? `Looking at the incidents: ${page.query}` : 'Looking at the incidents'
    default:
      return page.title ? `On the ${page.title} page` : null
  }
}

/** What to try asking from this page: something about what is on it, then the general ones. */
export function startersFor(page: PageContext | null): string[] {
  const here: Record<PageContext['kind'], string[]> = {
    incident: [
      'What should I know about this incident, and what should I do about it?',
      'Is this a real attack or just noise?',
    ],
    device: [
      'What is this device, and is anything about it worrying?',
      'Has this device been part of any incident?',
    ],
    logs: ['What do these log entries tell me?', 'Is anything in here worth my attention?'],
    incidents: ['Which of these should I look at first, and why?'],
    other: [],
  }
  const own = page ? here[page.kind] : []
  return [...own, ...STARTERS.slice(0, Math.max(1, 4 - own.length))].filter(
    (starter) => starter.length < MAX_QUESTION,
  )
}
