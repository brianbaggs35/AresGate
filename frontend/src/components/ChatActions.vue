<script setup lang="ts">
import { Check, ExternalLink, MessageSquareReply, StepForward, Undo2, X, Zap } from '@lucide/vue'
import { computed, reactive } from 'vue'
import { useRouter, type RouteLocationRaw } from 'vue-router'

import { errorMessage } from '@/api/client'
import { NEXT_BATCH } from '@/chat'
import type { ChatAction } from '@/api/aiChat'
import {
  changeIncidents,
  undoChange,
  type BulkChange,
  type BulkResult,
  type BulkSelection,
  type BulkUndo,
  type IncidentStatus,
} from '@/api/incidents'
import { denyProposal } from '@/api/aiDenials'
import type { VerdictKind } from '@/api/verdicts'
import { formatCount } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * What the assistant suggests you do. A page to open is a button. A change (a status, or a verdict
 * on what an incident is about, for one incident or several the assistant names) is a proposal
 * that waits for you to *Approve* or *Deny* it: the assistant changes nothing itself, and approving
 * is what makes the request, the same one the page for it makes, so it is in the audit log as
 * yours and can be taken back with *Undo* at once. A status can also be given to the earlier
 * incidents about the same address, and the proposal says how many that is before it is approved.
 * A denial is remembered, so the same change is not proposed again for a while. Instead of either,
 * *Suggest something else* puts the proposal in the box, to say what to do about it instead.
 * When the answer is a batch of a walk-through (`walkthrough`) and every proposal in it has been
 * settled, *Next batch* asks for the next one.
 */
const props = defineProps<{ actions: readonly ChatAction[]; walkthrough?: boolean }>()
const emit = defineEmits<{ opened: []; suggest: [text: string]; ask: [text: string] }>()

const session = useSessionStore()
const router = useRouter()

type State =
  | { phase: 'working' }
  | { phase: 'done'; undo: BulkUndo | null; said: string }
  | { phase: 'undone' }
  | { phase: 'denied' }
  | { phase: 'failed'; reason: string }
const states = reactive<Record<number, State | undefined>>({})
/** Whether a proposal is also for the earlier incidents about its address, and what that comes to. */
const earlier = reactive<Record<number, boolean | undefined>>({})
const looked = reactive<Record<number, string | undefined>>({})

/** Every status, since the earlier incidents are the ones the list leaves out as well. */
const EVERY_STATUS: readonly IncidentStatus[] = ['open', 'investigating', 'resolved', 'dismissed']

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

async function open(action: ChatAction) {
  const to = whereTo(action)
  if (to !== null) await router.push(to)
  emit('opened')
}

const changeOf = (action: ChatAction): BulkChange =>
  action.kind === 'status'
    ? { status: action.value as IncidentStatus }
    : {
        verdict: action.value as VerdictKind,
        ...(action.note ? { note: action.note } : {}),
      }

/** The incidents a proposal is about: the ones it names, or with the box ticked, everything about
 * the address, whatever has become of it. */
function selectionOf(action: ChatAction, at: number): BulkSelection {
  if (earlier[at]) {
    return { matching: { statuses: EVERY_STATUS, address: action.address as string } }
  }
  return { ids: [action.target_key, ...action.also].map(Number) }
}

const incidentsOf = (count: number) =>
  `${formatCount(count)} ${count === 1 ? 'incident' : 'incidents'}`

function saidOf(action: ChatAction, result: BulkResult): string {
  if (action.kind === 'verdict') {
    const verdicts = `${formatCount(result.verdicts)} ${result.verdicts === 1 ? 'verdict' : 'verdicts'}`
    return `Remembered ${verdicts}, covering ${incidentsOf(result.incidents)}.`
  }
  return result.changed === 0
    ? 'Nothing to change: they already are so.'
    : `${incidentsOf(result.changed)} changed.`
}

async function approve(action: ChatAction, at: number) {
  states[at] = { phase: 'working' }
  try {
    const result = await session.change((token) =>
      changeIncidents(selectionOf(action, at), changeOf(action), token),
    )
    states[at] = { phase: 'done', undo: result.undo, said: saidOf(action, result) }
  } catch (error) {
    states[at] = { phase: 'failed', reason: errorMessage(error) }
  }
}

async function deny(action: ChatAction, at: number) {
  states[at] = { phase: 'working' }
  try {
    await session.change((token) =>
      denyProposal(
        {
          kind: action.kind as 'status' | 'verdict',
          value: action.value as string,
          incident_ids: [action.target_key, ...action.also].map(Number),
        },
        token,
      ),
    )
    states[at] = { phase: 'denied' }
  } catch (error) {
    states[at] = { phase: 'failed', reason: errorMessage(error) }
  }
}

/** Where a proposal stands: what has been done with it here, or that it was denied before. */
function phaseOf(action: ChatAction, at: number): State['phase'] | undefined {
  return states[at]?.phase ?? (action.denied ? 'denied' : undefined)
}

/** Ticking the box asks what it would come to, so that it is known before anything is approved. */
async function widen(action: ChatAction, at: number, on: boolean) {
  earlier[at] = on
  looked[at] = undefined
  if (!on) return
  try {
    const result = await session.change((token) =>
      changeIncidents(selectionOf(action, at), changeOf(action), token, true),
    )
    looked[at] = `${incidentsOf(result.incidents)} in all, and ${
      result.changed === 0 ? 'none' : formatCount(result.changed)
    } would change.`
  } catch (error) {
    earlier[at] = false
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

/** Whether every proposal has been answered here (approved, denied or taken back), and so that
 * there is none to answer when there are none. */
const settled = computed(() =>
  props.actions.every(
    (action, at) =>
      action.kind === 'open' || ['done', 'denied', 'undone'].includes(phaseOf(action, at) ?? ''),
  ),
)

/** What is said in the box to suggest something else for a proposal. */
const instead = (action: ChatAction) => `Instead of "${action.label}", `

const key = (action: ChatAction) =>
  `${action.kind}:${action.target_kind}:${action.target_key}:${action.also.join(',')}:${action.value ?? ''}`
const reasonOf = (at: number) => (states[at] as { phase: 'failed'; reason: string }).reason
const canUndo = (at: number) => {
  const state = states[at]
  return state?.phase === 'done' && state.undo !== null
}
const saidAt = (at: number) => (states[at] as { phase: 'done'; said: string }).said
/** Waiting for an answer: not decided yet, or it failed and may be tried again. */
const waiting = (action: ChatAction, at: number) => {
  const phase = phaseOf(action, at)
  return phase === undefined || phase === 'failed'
}

/** What approving a proposal does, in words. */
function effectOf(action: ChatAction, at: number): string {
  const count = action.also.length + 1
  if (action.kind === 'verdict') {
    const several = count > 1 ? 'what each of them is about' : 'every alert like it'
    const about = action.address ? `everything about ${action.address}` : several
    return `Remembered for ${about}: the incidents about it that are not over are judged by it now, and so is what comes next.`
  }
  if (earlier[at]) return `Changes every incident about ${action.address}, earlier ones too.`
  return count > 1
    ? `Changes these ${formatCount(count)} incidents.`
    : 'Changes this incident only.'
}
</script>

<template>
  <ul class="actions" aria-label="What the assistant suggests" data-test="message-actions">
    <li
      v-for="(action, at) in actions"
      :key="key(action)"
      class="actions__item"
      :class="{ 'actions__item--proposal': action.kind !== 'open' }"
    >
      <v-btn
        v-if="action.kind === 'open'"
        variant="tonal"
        :prepend-icon="ExternalLink"
        data-test="action"
        @click="open(action)"
      >
        {{ action.label }}
      </v-btn>

      <section
        v-else
        class="proposal"
        :aria-label="`Proposal: ${action.label}`"
        data-test="proposal"
      >
        <p class="proposal__label text-title-small" data-test="proposal-label">
          <v-icon :icon="Zap" size="18" aria-hidden="true" />
          {{ action.label }}
        </p>
        <p
          v-if="action.note"
          class="text-body-medium text-medium-emphasis"
          data-test="proposal-why"
        >
          Why: {{ action.note }}
        </p>
        <p class="text-body-medium text-medium-emphasis" data-test="proposal-effect">
          {{ effectOf(action, at) }}
        </p>

        <template v-if="waiting(action, at) || phaseOf(action, at) === 'working'">
          <v-checkbox
            v-if="action.kind === 'status' && action.address"
            :model-value="earlier[at] ?? false"
            :label="`Also the earlier incidents about ${action.address}`"
            :disabled="phaseOf(action, at) === 'working'"
            density="compact"
            hide-details
            data-test="proposal-earlier"
            @update:model-value="(on) => widen(action, at, on === true)"
          />
          <output
            v-if="looked[at]"
            class="text-body-medium proposal__look"
            data-test="proposal-look"
          >
            {{ looked[at] }}
          </output>
          <div class="proposal__buttons">
            <v-btn
              color="primary"
              variant="flat"
              :prepend-icon="Check"
              :loading="phaseOf(action, at) === 'working'"
              :disabled="phaseOf(action, at) === 'working'"
              data-test="proposal-approve"
              @click="approve(action, at)"
            >
              Approve
            </v-btn>
            <v-btn
              variant="text"
              :prepend-icon="X"
              :disabled="phaseOf(action, at) === 'working'"
              data-test="proposal-deny"
              @click="deny(action, at)"
            >
              Deny
            </v-btn>
            <v-btn
              variant="text"
              :prepend-icon="MessageSquareReply"
              :disabled="phaseOf(action, at) === 'working'"
              data-test="proposal-suggest"
              @click="emit('suggest', instead(action))"
            >
              Suggest something else
            </v-btn>
          </div>
        </template>

        <output
          v-if="phaseOf(action, at) === 'done'"
          class="actions__note text-body-medium"
          data-test="action-done"
        >
          <v-icon :icon="Check" color="success" size="18" aria-hidden="true" />
          Approved. {{ saidAt(at) }}
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
          v-else-if="phaseOf(action, at) === 'undone'"
          class="actions__note text-body-medium"
          data-test="action-undone"
        >
          Taken back.
        </output>
        <output
          v-else-if="phaseOf(action, at) === 'denied'"
          class="actions__note text-body-medium"
          data-test="action-denied"
        >
          Denied. Nothing was changed, and it won't be suggested again unless the incident changes.
        </output>
        <span
          v-else-if="phaseOf(action, at) === 'failed'"
          class="actions__note text-body-medium text-error"
          role="alert"
          data-test="action-failed"
        >
          {{ reasonOf(at) }}
        </span>
      </section>
    </li>
    <li v-if="walkthrough && settled" class="actions__item">
      <v-btn
        color="primary"
        variant="tonal"
        :prepend-icon="StepForward"
        data-test="next-batch"
        @click="emit('ask', NEXT_BATCH)"
      >
        Next batch
      </v-btn>
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

.actions__item--proposal {
  align-self: stretch;
}

.proposal {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
  padding: 0.75rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 0.75rem;
}

.proposal p {
  margin: 0;
  overflow-wrap: anywhere;
}

.proposal__label {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.proposal__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-block-start: 0.25rem;
}

.actions__note {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
}
</style>
