<script setup lang="ts">
import {
  CircleHelp,
  ExternalLink,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
  X,
  type LucideIcon,
} from '@lucide/vue'
import { computed, ref, useId } from 'vue'
import { useDisplay } from 'vuetify'

import type { Judgement, Lookup, SubjectKind } from '@/api/threatIntel'
import { useKeyboardReturn } from '@/dialog'
import { formatDateTime } from '@/format'

/**
 * What VirusTotal reported of one search, in a window over the page: the judgement first, then
 * the counts of its engines, the community's score, the categories it was given and what else
 * VirusTotal says. The counts are shown beside the judgement, because one engine's flag can be a
 * false positive. The whole screen on a phone.
 */
const props = defineProps<{ lookup: Lookup }>()
const open = defineModel<boolean>({ required: true })

const { xs: phone } = useDisplay()
const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)
const title = ref<HTMLElement | null>(null)

/** Moves the keyboard to the title, so a screen reader starts at the top of what opened. */
function takeTheKeyboard() {
  title.value?.focus({ preventScroll: true })
}

const KIND: Record<SubjectKind, string> = {
  ip: 'IP address',
  domain: 'Domain',
  url: 'Web address',
}

const JUDGEMENT: Record<Judgement, { label: string; color: string | undefined; icon: LucideIcon }> =
  {
    malicious: { label: 'Reported as malicious', color: 'error', icon: ShieldAlert },
    suspicious: { label: 'Reported as suspicious', color: 'warning', icon: TriangleAlert },
    clean: { label: 'No engine flagged it', color: 'success', icon: ShieldCheck },
    unknown: { label: 'No report yet', color: undefined, icon: CircleHelp },
  }

const appearance = computed(() => JUDGEMENT[props.lookup.judgement])
const engines = computed(
  () =>
    props.lookup.malicious +
    props.lookup.suspicious +
    props.lookup.harmless +
    props.lookup.undetected,
)

/** What the counts say, in a sentence. */
const summary = computed(() => {
  const { lookup } = props
  switch (lookup.judgement) {
    case 'malicious':
      return `${lookup.malicious} of ${engines.value} engines flagged it as malicious.`
    case 'suspicious':
      return `${lookup.suspicious} of ${engines.value} engines flagged it as suspicious.`
    case 'clean':
      return `None of the ${engines.value} engines flagged it.`
    case 'unknown':
      return 'VirusTotal has no report on it yet.'
  }
})

/** Each kind of engine verdict as a share of the bar, in the order the bar reads. */
const segments = computed(() => {
  const { lookup } = props
  const total = engines.value
  const parts = [
    {
      key: 'malicious',
      label: 'Malicious',
      count: lookup.malicious,
      color: 'var(--chart-severity-critical)',
    },
    {
      key: 'suspicious',
      label: 'Suspicious',
      count: lookup.suspicious,
      color: 'var(--chart-severity-medium)',
    },
    {
      key: 'harmless',
      label: 'Harmless',
      count: lookup.harmless,
      color: 'var(--chart-severity-low)',
    },
    {
      key: 'undetected',
      label: 'Undetected',
      count: lookup.undetected,
      color: 'var(--chart-other)',
    },
  ]
  return parts.map((part) => ({ ...part, share: total ? (part.count / total) * 100 : 0 }))
})

const barLabel = computed(() =>
  segments.value.map((part) => `${part.count} ${part.label.toLowerCase()}`).join(', '),
)

/** The community's score, with its sign, or that there is none yet. */
const reputation = computed(() => {
  const score = props.lookup.reputation
  if (score === null) return 'No score yet'
  return score > 0 ? `+${score}` : `${score}`
})

const analysed = computed(() =>
  props.lookup.analysed_at ? formatDateTime(props.lookup.analysed_at) : 'Never',
)
</script>

<template>
  <v-dialog
    v-model="open"
    :fullscreen="phone"
    scrollable
    max-width="680"
    :aria-labelledby="titleId"
    @after-enter="takeTheKeyboard"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card
      class="report"
      :class="{ 'report--screen': phone }"
      :rounded="phone ? 0 : undefined"
      :border="!phone"
      data-test="threat-report"
    >
      <header class="report__head">
        <div class="report__heading">
          <p class="text-label-large text-medium-emphasis report__kind" data-test="report-kind">
            VirusTotal · {{ KIND[lookup.kind] }}
          </p>
          <h2
            :id="titleId"
            ref="title"
            tabindex="-1"
            class="report__title text-title-large"
            data-test="report-subject"
          >
            {{ lookup.subject }}
          </h2>
        </div>
        <v-btn
          icon
          variant="text"
          aria-label="Close"
          data-test="report-close"
          @click="open = false"
        >
          <X :size="20" aria-hidden="true" />
        </v-btn>
      </header>

      <v-card-text class="report__body">
        <div class="report__verdict">
          <v-chip
            :color="appearance.color"
            variant="tonal"
            size="large"
            :prepend-icon="appearance.icon"
            data-test="report-judgement"
            :data-judgement="lookup.judgement"
          >
            {{ appearance.label }}
          </v-chip>
          <p class="text-body-large report__summary" data-test="report-summary">
            {{ summary }}
          </p>
        </div>

        <div
          v-if="lookup.judgement !== 'unknown'"
          class="verdict-bar"
          role="img"
          :aria-label="`Engine verdicts: ${barLabel}`"
          data-test="report-bar"
        >
          <span
            v-for="part in segments"
            :key="part.key"
            class="verdict-bar__part"
            :style="{ width: `${part.share}%`, background: part.color }"
            :data-part="part.key"
          />
        </div>
        <ul v-if="lookup.judgement !== 'unknown'" class="verdict-legend" data-test="report-counts">
          <li v-for="part in segments" :key="part.key">
            <span
              class="verdict-legend__dot"
              :style="{ background: part.color }"
              aria-hidden="true"
            />
            {{ part.label }} <strong>{{ part.count }}</strong>
          </li>
        </ul>

        <section class="report__section" aria-label="Details">
          <dl class="report__facts">
            <div>
              <dt>Community score</dt>
              <dd data-test="report-reputation">{{ reputation }}</dd>
            </div>
            <div>
              <dt>Last analysed</dt>
              <dd data-test="report-analysed">{{ analysed }}</dd>
            </div>
            <div v-for="detail in lookup.details" :key="detail.label">
              <dt>{{ detail.label }}</dt>
              <dd>{{ detail.value }}</dd>
            </div>
          </dl>
        </section>

        <section v-if="lookup.categories.length" class="report__section">
          <h3 class="text-title-small">Categories</h3>
          <div class="report__categories" data-test="report-categories">
            <v-chip
              v-for="category in lookup.categories"
              :key="category"
              size="small"
              variant="outlined"
            >
              {{ category }}
            </v-chip>
          </div>
        </section>

        <p class="text-body-small text-medium-emphasis report__note">
          What you search for is added to VirusTotal's shared data, so keep private names out of
          searches. Checked {{ formatDateTime(lookup.checked_at) }}.
        </p>
      </v-card-text>

      <footer class="report__actions">
        <v-btn
          :href="lookup.link"
          target="_blank"
          rel="noopener noreferrer"
          variant="text"
          :append-icon="ExternalLink"
          data-test="report-open"
        >
          Open in VirusTotal
        </v-btn>
        <v-spacer />
        <v-btn variant="tonal" data-test="report-done" @click="open = false">Done</v-btn>
      </footer>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.report {
  display: flex;
  flex-direction: column;
  max-height: 100%;
}

.report--screen {
  height: 100%;
}

.report__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.25rem 1.25rem 0.5rem 1.5rem;
}

.report__heading {
  min-width: 0;
}

.report__kind {
  margin: 0;
}

.report__title {
  margin: 0.125rem 0 0;
  overflow-wrap: anywhere;
  outline: none;
}

.report__body {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding-top: 0.5rem;
}

.report__verdict {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
}

.report__summary {
  margin: 0;
}

.verdict-bar {
  display: flex;
  height: 0.75rem;
  overflow: hidden;
  border-radius: 999px;
  background: var(--chart-empty);
}

.verdict-bar__part {
  display: block;
  height: 100%;
  min-width: 0;
  transition: width 240ms ease;
}

.verdict-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.verdict-legend li {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.verdict-legend__dot {
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 999px;
}

.report__section h3 {
  margin: 0 0 0.5rem;
}

.report__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.75rem 1.5rem;
  margin: 0;
}

.report__facts dt {
  font-size: 0.8125rem;
  opacity: 0.75;
}

.report__facts dd {
  margin: 0.125rem 0 0;
  overflow-wrap: anywhere;
}

.report__categories {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.report__note {
  margin: 0;
}

.report__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
}
</style>
