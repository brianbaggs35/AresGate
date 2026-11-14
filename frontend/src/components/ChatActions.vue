<script setup lang="ts">
import { Check, ExternalLink, Undo2, Zap } from '@lucide/vue'
import { reactive } from 'vue'
import { useRouter, type RouteLocationRaw } from 'vue-router'

import { errorMessage } from '@/api/client'
import type { ChatAction } from '@/api/aiChat'
import { changeIncidents, undoChange, type BulkUndo, type IncidentStatus } from '@/api/incidents'
import type { VerdictKind } from '@/api/verdicts'
import { useSessionStore } from '@/stores/session'

/**
 * What the assistant suggests you do, as buttons. The assistant changes nothing itself: pressing
 * one is what makes the request, the same one the page for it makes, so a change is in the audit
 * log as yours, and one that changes an incident can be taken back with *Undo* at once.
 */
defineProps<{ actions: readonly ChatAction[] }>()
const emit = defineEmits<{ opened: [] }>()

const session = useSessionStore()
const router = useRouter()

type State =
  | { phase: 'working' }
  | { phase: 'done'; undo: BulkUndo | null }
  | { phase: 'undone' }
  | { phase: 'failed'; reason: string }
const states = reactive<Record<number, State | undefined>>({})

/** Where an action that opens a page goes, or null for one that doesn't. */
function whereTo(action: ChatAction): RouteLocationRaw | null {
  switch (action.target_kind) {
    case 'incident':
      return { name: 'incident', params: { id: action.target_key } }
    case 'device':
      return { name: 'asset', params: { key: `device-${action.target_key}` } }
    case 'integration':
      return { name: 'integration', params: { key: action.target_key } }
    case 'logs':
      return { name: 'logs', query: { q: action.value ?? '' } }
    default:
      return null
  }
}

async function run(action: ChatAction, at: number) {
  if (action.kind === 'open') {
    const to = whereTo(action)
    if (to !== null) await router.push(to)
    emit('opened')
    return
  }
  states[at] = { phase: 'working' }
  const ids = [Number(action.target_key)]
  const change =
    action.kind === 'status'
      ? { status: action.value as IncidentStatus }
      : {
          verdict: action.value as VerdictKind,
          ...(action.note ? { note: action.note } : {}),
        }
  try {
    const result = await session.change((token) => changeIncidents({ ids }, change, token))
    states[at] = { phase: 'done', undo: result.undo }
  } catch (error) {
    states[at] = { phase: 'failed', reason: errorMessage(error) }
  }
}

async function undo(at: number) {
  // Only offered once there is something to take back, so that is what it is.
  const back = (states[at] as { phase: 'done'; undo: BulkUndo }).undo
  states[at] = { phase: 'working' }
  try {
    await session.change((token) => undoChange(back, token))
    states[at] = { phase: 'undone' }
  } catch (error) {
    states[at] = { phase: 'failed', reason: errorMessage(error) }
  }
}

const key = (action: ChatAction) =>
  `${action.kind}:${action.target_kind}:${action.target_key}:${action.value ?? ''}`
const reasonOf = (at: number) => (states[at] as { phase: 'failed'; reason: string }).reason
const canUndo = (at: number) => {
  const state = states[at]
  return state?.phase === 'done' && state.undo !== null
}
</script>

<template>
  <ul class="actions" aria-label="What the assistant suggests" data-test="message-actions">
    <li v-for="(action, at) in actions" :key="key(action)" class="actions__item">
      <v-btn
        variant="tonal"
        :prepend-icon="action.kind === 'open' ? ExternalLink : Zap"
        :loading="states[at]?.phase === 'working'"
        :disabled="states[at]?.phase === 'working' || states[at]?.phase === 'done'"
        data-test="action"
        @click="run(action, at)"
      >
        {{ action.label }}
      </v-btn>
      <output
        v-if="states[at]?.phase === 'done'"
        class="actions__note text-body-medium"
        data-test="action-done"
      >
        <v-icon :icon="Check" color="success" size="18" aria-hidden="true" />
        Done.
        <v-btn
          v-if="canUndo(at)"
          variant="text"
          size="small"
          :prepend-icon="Undo2"
          data-test="action-undo"
          @click="undo(at)"
        >
          Undo
        </v-btn>
      </output>
      <output
        v-else-if="states[at]?.phase === 'undone'"
        class="actions__note text-body-medium"
        data-test="action-undone"
      >
        Taken back.
      </output>
      <span
        v-else-if="states[at]?.phase === 'failed'"
        class="actions__note text-body-medium text-error"
        role="alert"
        data-test="action-failed"
      >
        {{ reasonOf(at) }}
      </span>
    </li>
  </ul>
</template>

<style scoped>
.actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
  margin: 0.75rem 0 0;
  padding: 0;
  list-style: none;
}

.actions__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
}

.actions__note {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}
</style>
