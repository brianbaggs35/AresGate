import {
  Activity,
  BrickWallFire,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  Clock,
  Plug,
  ScanSearch,
  ShieldBan,
  Unplug,
} from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { Problem } from '@/api/client'
import type { CollectorState } from '@/api/collectors'
import type {
  Connection,
  ConnectionDefinition,
  ConnectionSettings,
  Field,
  Integration,
  LookupEntry,
  ModuleState,
  Status,
  TlsMode,
} from '@/api/integrations'

type Icon = NonNullable<IconProps['icon']>

/** The picture for each kind of integration the API names. */
const KINDS: Readonly<Record<string, Icon>> = {
  firewall: BrickWallFire,
  traffic: Activity,
  alerts: ScanSearch,
  threats: ShieldBan,
}

/** The picture for a kind of integration. One that this version of the app doesn't know gets a
 * plug, so a newer API doesn't leave a hole. */
export function integrationIcon(kind: string): Icon {
  return KINDS[kind] ?? Plug
}

export interface Appearance {
  label: string
  /** A theme colour, or none for the neutral one. */
  color: string | undefined
  icon: Icon
}

/** How each status looks, always with words and a shape as well as a colour. */
export const STATUS: Readonly<Record<Status, Appearance>> = {
  not_connected: { label: 'Not connected', color: undefined, icon: Unplug },
  untested: { label: 'Not tested yet', color: 'warning', icon: CircleDashed },
  connected: { label: 'Connected', color: 'success', icon: CircleCheck },
  problem: { label: 'Problem', color: 'error', icon: CircleAlert },
}

/** How each state of a collector looks. */
export const COLLECTOR_STATE: Readonly<Record<CollectorState, Appearance>> = {
  waiting: { label: 'Waiting', color: undefined, icon: CircleDashed },
  ok: { label: 'Working', color: 'success', icon: CircleCheck },
  problem: { label: 'Problem', color: 'error', icon: CircleAlert },
  late: { label: 'Late', color: 'warning', icon: Clock },
}

/** How each state of a service looks. */
export const MODULE_STATE: Readonly<Record<ModuleState, Omit<Appearance, 'icon'>>> = {
  running: { label: 'Running', color: 'success' },
  stopped: { label: 'Stopped', color: 'warning' },
  installed: { label: 'Installed', color: 'info' },
  not_installed: { label: 'Not installed', color: undefined },
  no_access: { label: 'No access', color: 'warning' },
  unknown: { label: 'Unknown', color: undefined },
}

/** What is being filled in for a connection, as the form holds it. */
export interface ConnectionDraft {
  /** Whether it is part of the integration. An optional connection can be left out. */
  enabled: boolean
  url: string
  tlsMode: TlsMode
  tlsCaPem: string
  tlsFingerprint: string
  /** Every option, as text, and secrets that were typed. A secret left blank is kept as it is. */
  options: Record<string, string>
  secrets: Record<string, string>
  /** The services AresGate has been told not to read. */
  disabledModules: string[]
}

/** The form for a connection, starting from how it is saved. */
export function draftFrom(connection: Connection): ConnectionDraft {
  const options: Record<string, string> = {}
  for (const field of connection.definition.fields) {
    if (field.kind === 'secret') continue
    options[field.key] = String(connection.options[field.key] ?? field.default ?? '')
  }
  return {
    enabled: !connection.definition.optional || connection.url !== null,
    url: connection.url ?? '',
    tlsMode: connection.tls_mode,
    tlsCaPem: connection.tls_ca_pem ?? '',
    tlsFingerprint: connection.tls_fingerprint ?? '',
    options,
    secrets: {},
    disabledModules: connection.modules.filter((module) => !module.enabled).map(({ key }) => key),
  }
}

/** The fields that apply given what has been chosen: one that depends on another is left out
 * unless that one has the value it needs. */
export function activeFields(
  definition: ConnectionDefinition,
  options: Readonly<Record<string, string>>,
): Field[] {
  return definition.fields.filter(
    (field) => field.only_if === null || options[field.only_if.field] === field.only_if.value,
  )
}

/** Whether the address is a plain http one, which anyone on the network can read. */
export const isPlainHttp = (url: string) => /^\s*http:\/\//i.test(url)

/** Whether there is a certificate to decide about. */
export const usesTls = (url: string) => !isPlainHttp(url)

/** What to send for a connection: only the fields that apply, and only the secrets that were
 * typed, since the others are kept as they are. */
export function settingsFrom(
  definition: ConnectionDefinition,
  draft: ConnectionDraft,
): ConnectionSettings {
  const options: Record<string, string> = {}
  const secrets: Record<string, string> = {}
  for (const field of activeFields(definition, draft.options)) {
    if (field.kind === 'secret') {
      const typed = draft.secrets[field.key]
      if (typed !== undefined && typed.trim() !== '') secrets[field.key] = typed
    } else {
      options[field.key] = draft.options[field.key] ?? ''
    }
  }
  return {
    url: draft.url.trim(),
    tls_mode: draft.tlsMode,
    tls_ca_pem: draft.tlsMode === 'ca' ? draft.tlsCaPem : null,
    tls_fingerprint: draft.tlsMode === 'pinned' ? draft.tlsFingerprint.trim() : null,
    options,
    disabled_modules: draft.disabledModules,
    secrets,
  }
}

/** The id of a field's input, which is what a problem with it moves the keyboard to. */
export const fieldId = (connection: string, field: string) => `${connection}-${field}`

/** What was wrong, by connection and then field. A problem with a connection as a whole (it
 * has to be filled in) is under the field name `connection`. */
export type FieldProblems = Record<string, Record<string, string>>

export const WHOLE = 'connection'

/** Sorts the problems of a save by the connection and field they are about. The first problem
 * for a field is the one kept. Problems about anything else are returned apart. */
export function sortProblems(problems: readonly Problem[]): {
  fields: FieldProblems
  other: string[]
} {
  const fields: FieldProblems = {}
  const other: string[] = []
  for (const { path, message } of problems) {
    const [section, connection, field] = path
    if (section !== 'connections' || connection === undefined) {
      other.push(message)
      continue
    }
    const byField = (fields[connection] ??= {})
    byField[field ?? WHOLE] ??= message
  }
  return { fields, other }
}

/** Whether two fingerprints are the same one, however they are written: with or without colons,
 * spaces or capital letters. */
export function sameFingerprint(a: string, b: string): boolean {
  const plain = (fingerprint: string) => fingerprint.replace(/[^0-9a-f]/gi, '').toLowerCase()
  return plain(a) !== '' && plain(a) === plain(b)
}

/** The name of each of an integration's connections, by key. */
export function connectionLabels(integration: Integration): Record<string, string> {
  return Object.fromEntries(
    integration.connections.map(({ definition }) => [definition.key, definition.label]),
  )
}

/** One choice of a list a system gave, as a select shows it. */
export interface LookupItem {
  value: string
  title: string
  props: { subtitle: string }
}

/** The choices a system listed, each with its identifier and what else is known of it. What is
 * chosen now is among them even when the system doesn't list it (it was saved earlier, or the
 * list hasn't been asked for), so the select never shows an empty box, and says why it is there. */
export function lookupItems(entries: readonly LookupEntry[], chosen: string): LookupItem[] {
  const items = entries.map((entry) => ({
    value: entry.value,
    title: entry.label,
    props: { subtitle: [`ID ${entry.value}`, entry.detail].filter(Boolean).join(' · ') },
  }))
  if (chosen !== '' && !items.some((item) => item.value === chosen)) {
    const subtitle =
      entries.length > 0 ? 'Saved, but not in the list it gave now' : 'Not looked up yet'
    items.unshift({ value: chosen, title: `ID ${chosen}`, props: { subtitle } })
  }
  return items
}
