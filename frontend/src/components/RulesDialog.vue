<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'

import {
  fetchSample,
  previewRules,
  type Choices,
  type Destination,
  type DiscordMessage,
  type Rules,
  type RulesPreview,
  type SampleReason,
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
import ChoiceToggle from '@/components/ChoiceToggle.vue'
import DiscordPreview from '@/components/DiscordPreview.vue'
import ModeCards, { type Purpose } from '@/components/ModeCards.vue'
import RulesPreviewPanel from '@/components/RulesPreview.vue'
import { useKeyboardReturn } from '@/dialog'
import { useSessionStore } from '@/stores/session'

/**
 * What one destination is told about, and when. First what the channel is for: real attacks only
 * (the incidents on the Threats page), everything serious, or custom, which opens how serious and
 * how sure, which programs and kinds of activity. Then quiet hours, how many messages an hour, and
 * how much a message says, with the message itself drawn as Discord will show it. Beside the
 * choices it shows what they would have sent in the last day, worked out by the server each
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

/** Which of the cards the rules are: the real attacks, the plain "everything serious" that a
 * channel got before there were two kinds of rule, or something of the owner's own. */
function purposeOf(rules: Rules): Purpose {
  if (rules.mode === 'threats') return 'threats'
  const plain =
    rules.min_severity === SERIOUS.min_severity &&
    rules.min_confidence === SERIOUS.min_confidence &&
    rules.sources.length === 0 &&
    rules.activities.length === 0
  return plain ? 'serious' : 'custom'
}

const SERIOUS = { min_severity: 2, min_confidence: 65 }

const draft = ref<Rules>({ ...props.destination.rules })
const purpose = ref<Purpose>(purposeOf(props.destination.rules))
const answer = ref<RulesPreview | null>(null)
const sample = ref<DiscordMessage | null>(null)
const sampleReason = ref<SampleReason>('new')
const sampleFailure = ref<string | null>(null)
const previewFailure = ref<string | null>(null)
const previewing = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
// What the last question was about, so that a change that leaves the rules as they were asks nothing.
let lastAsked = ''
// Each question is numbered, so that a late answer to an earlier one is not taken for the latest.
let asked = 0
let shown = 0

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

const threats = computed(() => purpose.value === 'threats')
const stories = computed(() => [
  { key: 'new' as const, label: 'First message' },
  { key: 'worse' as const, label: threats.value ? 'If it escalates' : 'If it gets worse' },
])

function choose(chosen: Purpose) {
  purpose.value = chosen
  draft.value.mode = chosen === 'threats' ? 'threats' : 'custom'
  if (chosen === 'serious') Object.assign(draft.value, { ...SERIOUS, sources: [], activities: [] })
}

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

/** What a message would look like with these rules, as the server makes it. */
async function show() {
  const mine = ++shown
  try {
    const found = await session.call(() =>
      fetchSample(draft.value.mode, draft.value.detail, sampleReason.value),
    )
    if (mine !== shown) return
    sample.value = found.payload
    sampleFailure.value = null
  } catch (error) {
    if (mine === shown) sampleFailure.value = errorMessage(error)
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
  shown += 1
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
    purpose.value = purposeOf(draft.value)
    answer.value = null
    previewFailure.value = null
    sample.value = null
    sampleReason.value = 'new'
    void ask()
  },
  { immediate: true },
)
watch(draft, later, { deep: true })
// Changing what "everything serious" stands for makes it the owner's own.
watch(
  draft,
  (rules) => {
    if (purpose.value === 'serious' && purposeOf(rules) !== 'serious') purpose.value = 'custom'
  },
  { deep: true },
)
// The sample is made when the sheet opens and again whenever what it shows is changed.
watch(
  () => (open.value ? [draft.value.mode, draft.value.detail, sampleReason.value].join() : null),
  (shows) => {
    if (shows !== null) void show()
  },
  { immediate: true },
)
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
        <ModeCards :model-value="purpose" @update:model-value="choose" />

        <RulesPreviewPanel
          :preview="answer"
          :loading="previewing"
          :failure="previewFailure"
          :per-hour="draft.max_per_hour"
        />

        <section v-if="threats" class="rules-group" data-test="rules-purpose-note">
          <h3 class="text-title-medium">What is worth a message</h3>
          <p class="text-body-medium rules-group__note" data-test="rules-threats-note">
            A message goes out when an incident becomes a threat on the Threats page, and again if
            the attack goes a stage further: from looking around to trying to get in, and from there
            to a sign that it worked. It says why, in the words of the incident's own page. If you,
            or the AI, later decide it was not a threat, the message is changed to say it was stood
            down, so a warning never stays up for nothing.
          </p>
          <p class="text-body-medium text-medium-emphasis rules-group__note">
            What counts as a threat is set under
            <router-link :to="{ name: 'settings-threat-detection' }" data-test="rules-threat-link"
              >Threat detection</router-link
            >. Never sent, whatever else: an incident you called not suspicious or low priority, and
            one you resolved or dismissed.
          </p>
        </section>

        <fieldset v-else class="rules-group" data-test="rules-floors">
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
            :label="threats ? 'Tell me again if it escalates' : 'Tell me again if it gets worse'"
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
          <div class="rules-sample">
            <div class="rules-sample__head">
              <h3 class="text-label-large">What it looks like</h3>
              <ChoiceToggle
                v-model="sampleReason"
                :options="stories"
                label="Which message to show"
                name="rules-story"
              />
            </div>
            <v-alert
              v-if="sampleFailure"
              type="warning"
              variant="tonal"
              density="compact"
              data-test="sample-failure"
            >
              {{ sampleFailure }}
            </v-alert>
            <DiscordPreview v-else-if="sample" :message="sample" />
            <p v-else class="text-body-medium text-medium-emphasis" data-test="sample-wait">
              Making a sample message…
            </p>
            <p class="text-body-small text-medium-emphasis">
              A sample about an incident that is made up, written by the same code that writes the
              real ones. Send one to the channel from its card to see it in Discord.
            </p>
          </div>
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

.rules-sample {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.rules-sample__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
}

.rules-sample p,
.rules-sample h3 {
  margin: 0;
}

.rules-detail {
  display: flex;
  flex-direction: column;
  padding-block: 0.25rem;
}
</style>
