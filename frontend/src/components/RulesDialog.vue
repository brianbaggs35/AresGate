<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'

import {
  previewRules,
  type Choices,
  type Destination,
  type Rules,
  type RulesPreview,
} from '@/api/alerts'
import { errorMessage } from '@/api/client'
import {
  CONFIDENCES,
  DETAILS,
  PER_HOUR,
  SEVERITIES,
  browserZone,
  perHour,
  toMinutes,
  toTime,
  withCurrent,
} from '@/alertRules'
import RulesPreviewPanel from '@/components/RulesPreview.vue'
import { useKeyboardReturn } from '@/dialog'
import { useSessionStore } from '@/stores/session'

/**
 * What one destination is told about, and when: how serious and how sure, which programs and
 * kinds of activity, quiet hours, how many messages an hour, and how much a message says. Beside
 * the choices it shows what they would have sent in the last day, worked out by the server each
 * time they change, so the rules can be tuned before they are used. It is a sheet from the side
 * on a desktop and the screen above the bottom bar on a phone. It only asks; saving the answer is
 * up to the page, which hands back what was wrong with each field.
 */
const props = withDefaults(
  defineProps<{
    destination: Destination
    /** What the rules can name. */
    choices: Choices
    /** The answer is being saved. */
    busy?: boolean
    /** What was wrong with each field the last time it was saved, by the field's name. */
    problems?: Record<string, string>
    /** Something that went wrong that is not about a field. */
    failure?: string | null
    /** How long after the last change the preview is asked for, in milliseconds, so that typing is
     * not a request per key. */
    previewDelay?: number
  }>(),
  { problems: () => ({}), failure: null, previewDelay: 400 },
)
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ save: [rules: Rules] }>()

const session = useSessionStore()
const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)

const draft = ref<Rules>({ ...props.destination.rules })
const answer = ref<RulesPreview | null>(null)
const previewFailure = ref<string | null>(null)
const previewing = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
// What the last question was about, so that a change that leaves the rules as they were asks nothing.
let lastAsked = ''
// Each question is numbered, so that a late answer to an earlier one is not taken for the latest.
let asked = 0

const severities = SEVERITIES.map((item) => ({ title: item.label, value: item.value }))
const confidences = computed(() =>
  withCurrent(
    CONFIDENCES,
    draft.value.min_confidence,
    (value) => `${value.toString()}% or more`,
  ).map((item) => ({ title: item.label, value: item.value })),
)
const rates = computed(() =>
  [...new Set([...PER_HOUR, draft.value.max_per_hour])]
    .sort((a, b) => a - b)
    .map((value) => ({ title: perHour(value), value })),
)
const sources = computed(() =>
  props.choices.sources.map((item) => ({ title: item.name, value: item.key })),
)
const activities = computed(() =>
  props.choices.activities.map((item) => ({ title: item.name, value: item.key })),
)
const zones = computed(() => [
  ...new Set([...Intl.supportedValuesOf('timeZone'), 'UTC', draft.value.time_zone]),
])

const from = computed({
  get: () => toTime(draft.value.quiet_from),
  set: (time: string) => {
    draft.value.quiet_from = toMinutes(time) ?? draft.value.quiet_from
  },
})
const until = computed({
  get: () => toTime(draft.value.quiet_until),
  set: (time: string) => {
    draft.value.quiet_until = toMinutes(time) ?? draft.value.quiet_until
  },
})

const changed = computed(
  () => JSON.stringify(draft.value) !== JSON.stringify(props.destination.rules),
)
const ready = computed(
  () =>
    changed.value &&
    !props.busy &&
    (!draft.value.quiet_hours || draft.value.quiet_from !== draft.value.quiet_until),
)

async function ask() {
  lastAsked = JSON.stringify(draft.value)
  const mine = ++asked
  previewing.value = true
  try {
    const found = await session.change((token) =>
      previewRules(props.destination.id, draft.value, token),
    )
    if (mine !== asked) return
    answer.value = found
    previewFailure.value = null
  } catch (error) {
    if (mine === asked) previewFailure.value = errorMessage(error)
  } finally {
    if (mine === asked) previewing.value = false
  }
}

function later() {
  clearTimeout(timer)
  if (JSON.stringify(draft.value) !== lastAsked) {
    timer = setTimeout(() => void ask(), props.previewDelay)
  }
}

function stop() {
  clearTimeout(timer)
  // Whatever is still on its way is not wanted.
  asked += 1
}

// Each time it opens it shows what is kept now, not what an earlier visit left. A page that
// makes the sheet and opens it in one go shows it open from the start, so this looks at once.
watch(
  open,
  (opening) => {
    if (!opening) {
      stop()
      return
    }
    draft.value = {
      ...props.destination.rules,
      sources: [...props.destination.rules.sources],
      activities: [...props.destination.rules.activities],
    }
    // Quiet hours that are off start in the time zone of this computer.
    if (!draft.value.quiet_hours) draft.value.time_zone = browserZone()
    answer.value = null
    previewFailure.value = null
    void ask()
  },
  { immediate: true },
)
watch(draft, later, { deep: true })
onBeforeUnmount(stop)

function save() {
  if (ready.value) emit('save', { ...draft.value })
}
</script>

<template>
  <v-dialog
    v-model="open"
    scrollable
    transition="slide-x-reverse-transition"
    :persistent="busy"
    :aria-labelledby="titleId"
    class="rules-sheet"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card class="rules-sheet__card" :rounded="0" data-test="rules-dialog">
      <header class="rules-sheet__head">
        <h2 :id="titleId" class="text-title-large rules-sheet__title" data-test="rules-title">
          What {{ destination.name }} is told
        </h2>
        <v-btn
          icon
          variant="text"
          size="small"
          aria-label="Close"
          :disabled="busy"
          data-test="rules-close"
          @click="open = false"
        >
          <v-icon :icon="X" />
        </v-btn>
      </header>

      <form class="rules-sheet__body" @submit.prevent="save">
        <RulesPreviewPanel
          :preview="answer"
          :loading="previewing"
          :failure="previewFailure"
          :per-hour="draft.max_per_hour"
        />

        <fieldset class="rules-group">
          <legend class="text-title-medium">What is worth a message</legend>
          <v-select
            v-model="draft.min_severity"
            :items="severities"
            label="How serious"
            hint="The most serious thing in the incident."
            persistent-hint
            :error-messages="problems?.min_severity"
            data-test="rules-severity"
          />
          <v-select
            v-model="draft.min_confidence"
            :items="confidences"
            label="How sure AresGate is"
            hint="Low is under 35%, medium from 35% and high from 65%. Raise it to hear only of what is almost certainly real."
            persistent-hint
            :error-messages="problems?.min_confidence"
            data-test="rules-confidence"
          />
          <v-select
            v-model="draft.sources"
            :items="sources"
            label="Reported by"
            placeholder="Any program"
            hint="Only incidents that one of these programs saw part of. Leave empty for any."
            persistent-hint
            multiple
            chips
            closable-chips
            :error-messages="problems?.sources"
            data-test="rules-sources"
          />
          <v-select
            v-model="draft.activities"
            :items="activities"
            label="Kind of activity"
            placeholder="Any kind"
            hint="Leave empty for any, including incidents that are no kind in particular."
            persistent-hint
            multiple
            chips
            closable-chips
            :error-messages="problems?.activities"
            data-test="rules-activities"
          />
          <p
            class="text-body-medium text-medium-emphasis rules-group__note"
            data-test="rules-never"
          >
            Never sent, whatever is chosen here: an incident you called not suspicious or low
            priority, and one you resolved or dismissed. One you called a real threat is sent
            whatever its severity and confidence, if it is from the programs and of the kinds
            chosen.
          </p>
        </fieldset>

        <fieldset class="rules-group">
          <legend class="text-title-medium">When</legend>
          <v-switch
            v-model="draft.quiet_hours"
            label="Quiet hours"
            color="primary"
            hide-details
            data-test="rules-quiet"
          />
          <template v-if="draft.quiet_hours">
            <p class="text-body-medium text-medium-emphasis">
              Nothing is sent in these hours. What came in is sent when they end.
            </p>
            <div class="rules-group__times">
              <v-text-field
                v-model="from"
                type="time"
                label="From"
                :error-messages="problems?.quiet_from"
                data-test="rules-from"
              />
              <v-text-field
                v-model="until"
                type="time"
                label="Until"
                :error-messages="problems?.quiet_until"
                data-test="rules-until"
              />
            </div>
            <v-autocomplete
              v-model="draft.time_zone"
              :items="zones"
              label="Time zone"
              :error-messages="problems?.time_zone"
              data-test="rules-zone"
            />
            <v-switch
              v-model="draft.quiet_critical"
              label="Still send critical threats"
              color="primary"
              hide-details
              data-test="rules-critical"
            />
          </template>
          <v-select
            v-model="draft.max_per_hour"
            :items="rates"
            label="Limit"
            hint="When more would come in, the rest are said in one message."
            persistent-hint
            :error-messages="problems?.max_per_hour"
            data-test="rules-rate"
          />
          <v-switch
            v-model="draft.again_when_worse"
            label="Tell me again if it gets worse"
            color="primary"
            hide-details
            data-test="rules-again"
          />
        </fieldset>

        <fieldset class="rules-group">
          <legend class="text-title-medium">What a message says</legend>
          <v-radio-group
            v-model="draft.detail"
            hide-details
            :error-messages="problems?.detail"
            data-test="rules-detail"
          >
            <v-radio v-for="item in DETAILS" :key="item.value" :value="item.value">
              <template #label>
                <span class="rules-detail">
                  <span class="text-body-large">{{ item.label }}</span>
                  <span class="text-body-medium text-medium-emphasis">{{ item.text }}</span>
                </span>
              </template>
            </v-radio>
          </v-radio-group>
        </fieldset>

        <v-alert
          v-if="failure"
          type="error"
          variant="tonal"
          density="compact"
          data-test="rules-failure"
        >
          {{ failure }}
        </v-alert>
      </form>

      <footer class="rules-sheet__foot">
        <span class="rules-sheet__spacer" />
        <v-btn variant="text" :disabled="busy" data-test="rules-cancel" @click="open = false">
          Cancel
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :disabled="!ready"
          :loading="busy"
          data-test="rules-save"
          @click="save"
        >
          Save rules
        </v-btn>
      </footer>
    </v-card>
  </v-dialog>
</template>

<style scoped>
/* A sheet from the side, as tall as the screen; on a phone as wide as it too, and above the bar
   along the bottom, which stays where it is under the dimmed page. */
.rules-sheet {
  justify-content: flex-end;
}

.rules-sheet > :deep(.v-overlay__content) {
  width: min(36rem, 100%);
  max-width: none;
  height: 100%;
  max-height: 100%;
  margin: 0;
}

@media (max-width: 599.98px) {
  .rules-sheet > :deep(.v-overlay__content) {
    align-self: flex-start;
    height: calc(100% - var(--bottom-bar-height));
    max-height: calc(100% - var(--bottom-bar-height));
  }
}

.rules-sheet__card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding-bottom: env(safe-area-inset-bottom);
}

.rules-sheet__head,
.rules-sheet__foot {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.rules-sheet__head {
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 0.75rem 0.75rem 1.5rem;
  border-bottom: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.rules-sheet__title {
  margin: 0;
  overflow-wrap: anywhere;
}

.rules-sheet__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.5rem;
  overflow-y: auto;
}

.rules-sheet__foot {
  padding: 0.75rem 1rem;
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.rules-sheet__spacer {
  flex: 1;
}

.rules-group {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-width: 0;
  padding: 0;
  border: 0;
}

.rules-group legend {
  margin-bottom: 0.75rem;
  padding: 0;
}

.rules-group__note {
  margin: 0;
}

.rules-group__times {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.rules-detail {
  display: flex;
  flex-direction: column;
  padding-block: 0.25rem;
}
</style>
