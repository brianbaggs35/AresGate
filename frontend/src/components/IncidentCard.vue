<script setup lang="ts">
import { Layers, Network, Repeat, Users } from '@lucide/vue'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useDisplay } from 'vuetify'

import { errorMessage } from '@/api/client'
import { fetchIncident, type Incident } from '@/api/incidents'
import { VERDICTS, giveVerdict, type VerdictKind } from '@/api/verdicts'
import ConfidenceMeter from '@/components/ConfidenceMeter.vue'
import IncidentStatusChip from '@/components/IncidentStatusChip.vue'
import ResponseChip from '@/components/ResponseChip.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import VerdictChip from '@/components/VerdictChip.vue'
import { formatAgo, formatCount, formatDateTime } from '@/format'
import { ACTIVITY, isAboutRule, otherAddresses, portsTouched, spanOf } from '@/incidents'
import { SEVERITY } from '@/severity'
import { useSessionStore } from '@/stores/session'
import { VERDICT, scopesOf, type Judged, type Scope } from '@/verdicts'

/**
 * An incident in a list: how serious it is, what it is, how sure AresGate is and which programs
 * saw it. Its details lead to the incident, and under them are the three verdicts, so the owner
 * can judge it without opening it: they are about what it is about (its address, or the alert
 * where it names no address), and whoever shows the list says what was done. A box beside it
 * picks it, for a change to many at once.
 */
const props = defineProps<{
  incident: Incident
  /** Whether it can be picked, with others, for a change to be made to all of them. */
  selectable?: boolean
  selected?: boolean
}>()
const emit = defineEmits<{
  judged: [Judged]
  /** It was ticked or taken off: `range` when the shift key was held, for all the others between. */
  select: [range: boolean]
}>()

const session = useSessionStore()
const { xs: phone } = useDisplay()

const accent = computed(() => `rgb(var(--v-theme-${SEVERITY[props.incident.severity].color}))`)
/** The addresses besides the one it is about that are not neighbours grouped into it: the
 * devices that were attacked, and whatever else the signals name. */
const others = computed(() =>
  Math.max(0, otherAddresses(props.incident).length - props.incident.neighbours),
)
const neighbours = computed(() => {
  const count = props.incident.neighbours
  return `${formatCount(count)} neighbouring ${count === 1 ? 'address' : 'addresses'}`
})
const signals = computed(() => {
  const count = props.incident.signal_count
  if (count === 1) return '1 signal'
  return `${formatCount(count)} signals ${spanOf(props.incident)}`
})

const rule = computed(() => isAboutRule(props.incident.subject))
/** What a verdict from the card is about, in words that go on from its name. */
const about = computed(() =>
  rule.value ? 'the alert it is about' : `everything about ${props.incident.subject}`,
)
const giving = ref<VerdictKind | null>(null)
const failure = ref<string | null>(null)

/** What a verdict from the card is about: the address, or else the first alert in the incident,
 * which only its signals can say. */
async function scopeOf(): Promise<Scope | undefined> {
  const { subject, id } = props.incident
  const detail = rule.value ? await session.call(() => fetchIncident(id)) : { subject, signals: [] }
  return scopesOf(detail)[0]
}

async function give(kind: VerdictKind) {
  giving.value = kind
  failure.value = null
  try {
    const scope = await scopeOf()
    if (!scope) {
      failure.value = 'It names no address and its alerts have no signature: nothing to judge by.'
      return
    }
    const kept = await session.change((token) =>
      giveVerdict({ verdict: kind, ...scope.request }, token),
    )
    emit('judged', { kind, scope, rule: kept })
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    giving.value = null
  }
}
</script>

<template>
  <v-card
    hover
    class="incident-card"
    :class="{ 'incident-card--selectable': selectable, 'incident-card--selected': selected }"
    :style="{ '--incident-accent': accent }"
    data-test="incident-card"
  >
    <label v-if="selectable" class="incident-card__pick" data-test="incident-pick">
      <input
        type="checkbox"
        class="incident-card__box"
        :checked="selected"
        :aria-label="`Select: ${incident.title}`"
        data-test="incident-select"
        @click="emit('select', ($event as MouseEvent).shiftKey)"
      />
    </label>
    <RouterLink
      :to="{ name: 'incident', params: { id: incident.id } }"
      class="incident-card__link"
      data-test="incident"
    >
      <div class="incident-card__top">
        <SeverityChip :severity="incident.severity" />
        <IncidentStatusChip v-if="incident.status !== 'open'" :status="incident.status" />
        <VerdictChip v-if="incident.verdict" :verdict="incident.verdict" />
        <v-chip
          v-for="activity in incident.activities"
          :key="activity"
          :prepend-icon="ACTIVITY[activity].icon"
          variant="outlined"
          :data-test="`incident-activity-${activity}`"
        >
          {{ ACTIVITY[activity].label }}
        </v-chip>
        <ResponseChip :response="incident.response" />
        <span class="incident-card__when text-body-medium text-medium-emphasis">
          Last signal
          <time
            :datetime="incident.last_seen_at"
            :title="formatDateTime(incident.last_seen_at)"
            data-test="incident-when"
            >{{ formatAgo(incident.last_seen_at) }}</time
          >
        </span>
      </div>

      <h3 class="incident-card__title text-title-large" data-test="incident-title">
        {{ incident.title }}
      </h3>

      <div class="incident-card__details">
        <ConfidenceMeter
          class="incident-card__confidence"
          :confidence="incident.confidence"
          :level="incident.confidence_level"
        />
        <ul class="incident-card__facts text-body-medium text-medium-emphasis">
          <li class="incident-card__fact" data-test="incident-signals">
            <v-icon :icon="Layers" size="18" aria-hidden="true" />
            {{ signals }}
          </li>
          <li v-if="incident.waves > 1" class="incident-card__fact" data-test="incident-waves">
            <v-icon :icon="Repeat" size="18" aria-hidden="true" />
            {{ incident.waves }} waves
          </li>
          <li v-if="incident.port_count > 1" class="incident-card__fact" data-test="incident-ports">
            <v-icon :icon="Network" size="18" aria-hidden="true" />
            {{ portsTouched(incident) }}
          </li>
          <li
            v-if="incident.neighbours > 0"
            class="incident-card__fact"
            data-test="incident-neighbours"
          >
            <v-icon :icon="Users" size="18" aria-hidden="true" />
            {{ neighbours }}
          </li>
          <li class="incident-card__fact" data-test="incident-programs">
            <span class="text-medium-emphasis">Seen by</span>
            {{ incident.sources.map(({ name }) => name).join(', ') }}
          </li>
          <li class="incident-card__fact" data-test="incident-subject">
            <span class="incident-card__subject">{{
              isAboutRule(incident.subject) ? 'A rule with no address' : incident.subject
            }}</span>
            <template v-if="others > 0">
              and {{ others }} other {{ others === 1 ? 'address' : 'addresses' }}
            </template>
          </li>
        </ul>
      </div>
    </RouterLink>

    <fieldset class="incident-card__say px-4 px-sm-5 pb-3 pb-sm-4" data-test="quick-verdicts">
      <legend class="incident-card__legend">Say what you think of it</legend>
      <v-btn
        v-for="kind in VERDICTS"
        :key="kind"
        variant="tonal"
        density="comfortable"
        :stacked="phone"
        :color="VERDICT[kind].color"
        :prepend-icon="VERDICT[kind].icon"
        :loading="giving === kind"
        :disabled="giving !== null && giving !== kind"
        :aria-label="`${VERDICT[kind].label}: ${about}`"
        :title="`${VERDICT[kind].label}: ${about}`"
        class="incident-card__verdict"
        :data-test="`quick-${kind}`"
        @click="give(kind)"
      >
        {{ VERDICT[kind].label }}
      </v-btn>
    </fieldset>
    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      density="compact"
      class="mx-4 mx-sm-5 mb-4"
      data-test="quick-error"
    >
      {{ failure }}
    </v-alert>
  </v-card>
</template>

<style scoped>
.incident-card {
  position: relative;
  display: block;
  overflow: hidden;
}

.incident-card__link {
  display: block;
  padding: 1rem;
  color: inherit;
  text-decoration: none;
}

@media (min-width: 600px) {
  .incident-card__link {
    padding: 1.25rem;
  }
}

.incident-card__link:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.incident-card__link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

/* A box in the corner picks it. It is as big as a thumb needs, and the card makes room for it. */
.incident-card__pick {
  position: absolute;
  inset-block-start: 0.25rem;
  inset-inline-start: 0.25rem;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  cursor: pointer;
}

.incident-card__box {
  width: 1.25rem;
  height: 1.25rem;
  margin: 0;
  accent-color: rgb(var(--v-theme-primary));
  cursor: pointer;
}

.incident-card__box:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 3px;
}

/* Room for the box in the corner. */
.incident-card--selectable .incident-card__link {
  padding-inline-start: 3.25rem;
}

.incident-card--selected {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
  background: rgba(var(--v-theme-primary), 0.06);
}

/* The bar on the left says how serious it is at a glance, and the chip says it in words. */
.incident-card::before {
  content: '';
  position: absolute;
  inset-block: 0;
  inset-inline-start: 0;
  width: 4px;
  background: var(--incident-accent);
}

.incident-card__top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.incident-card__when {
  margin-inline-start: auto;
}

.incident-card__title {
  margin: 0.75rem 0 0.75rem;
  overflow-wrap: anywhere;
}

.incident-card__details {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.75rem 2rem;
  align-items: center;
}

.incident-card__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.incident-card__fact {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
  overflow-wrap: anywhere;
}

.incident-card__subject {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

/* The three verdicts sit in a row: stacked, with the icon over the name, on a phone, where there
 * is not room for them side by side. */
.incident-card__say {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem;
  min-width: 0;
  margin: 0;
  border: 0;
}

.incident-card__legend {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

/* A name that does not fit across a phone's third of the card goes on to a second line. */
.incident-card__verdict {
  min-width: 0;
  height: auto;
  min-height: 2.75rem;
  padding-block: 0.5rem;
}

.incident-card__verdict :deep(.v-btn__content) {
  white-space: normal;
  line-height: 1.25;
  text-align: center;
}

@media (min-width: 720px) {
  .incident-card__details {
    grid-template-columns: minmax(12rem, 16rem) minmax(0, 1fr);
  }
}

@media (min-width: 600px) {
  .incident-card__say {
    grid-template-columns: repeat(3, max-content);
  }
}
</style>
