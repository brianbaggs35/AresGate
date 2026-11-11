<script setup lang="ts">
import { ArrowRight, Copy, Globe } from '@lucide/vue'
import { computed } from 'vue'

import type { ChainDetail, ChainStep } from '@/api/threats'
import SeverityChip from '@/components/SeverityChip.vue'
import { DEVICE_ICON, LINK, ROLE, certainty, deviceTitle } from '@/chains'
import { agreedBy } from '@/evidence'
import { formatAgo, formatClock, formatCount } from '@/format'
import { STAGE } from '@/threats'

/**
 * The steps of an attack across two devices, drawn in the order they happened: who got in from the
 * internet, the device it got into, and where the device then called. A step that was seen is
 * drawn solid and says "Seen"; one that is only inferred from the device and the timing is
 * dashed and says "Inferred", so the two are never mistaken for each other. Under each step is
 * the evidence behind it, where an alert that two programs reported is one alert that says which
 * programs saw it.
 */
const props = defineProps<{ chain: ChainDetail }>()

const MOST = 6

/** Where the device sits: before the first step that is the device calling out. */
const pivot = computed(() => props.chain.path.findIndex(({ role }) => role === 'callout'))

function shown(step: ChainStep) {
  return step.evidence.slice(0, MOST)
}
</script>

<template>
  <ol class="path" data-test="chain-path" aria-label="The steps of the attack, in order">
    <template v-for="(step, index) in chain.path" :key="step.incident_id">
      <li v-if="index === pivot" class="path__device" data-test="path-device">
        <span class="path__node path__node--device" aria-hidden="true">
          <v-icon :icon="DEVICE_ICON" size="22" />
        </span>
        <div>
          <p class="text-title-medium path__device-name">{{ deviceTitle(chain) }}</p>
          <p class="text-body-medium text-medium-emphasis">{{ certainty(chain) }}</p>
        </div>
      </li>
      <li
        class="path__step"
        :class="`path__step--${step.link}`"
        data-test="path-step"
        :data-link="step.link"
      >
        <span class="path__node" :class="`path__node--${step.link}`" aria-hidden="true">
          <v-icon :icon="ROLE[step.role].icon" size="20" />
        </span>
        <div class="path__body">
          <div class="path__top">
            <h3 class="text-title-medium path__title" data-test="step-role">
              {{ ROLE[step.role].title }}
            </h3>
            <v-chip
              size="small"
              variant="outlined"
              :color="LINK[step.link].color"
              :prepend-icon="LINK[step.link].icon"
              data-test="step-link"
            >
              {{ LINK[step.link].label }}
            </v-chip>
            <SeverityChip :severity="step.severity" />
          </div>
          <p class="text-body-medium text-medium-emphasis path__when">
            <v-icon :icon="Globe" size="16" aria-hidden="true" />
            <span class="path__subject" data-test="step-subject">{{ step.subject }}</span>
            <span v-if="step.subject_name" data-test="step-subject-name">
              ({{ step.subject_name }})
            </span>
            at <time :datetime="step.first_seen_at">{{ formatClock(step.first_seen_at) }}</time
            >,
            {{ formatAgo(step.first_seen_at) }}
          </p>
          <p class="text-body-large path__reason" data-test="step-reason">{{ step.reason }}</p>
          <ul v-if="step.stages.length" class="path__stages" aria-label="How far it got">
            <li v-for="stage in step.stages" :key="stage">
              <v-chip size="small" variant="tonal" :prepend-icon="STAGE[stage].icon">
                {{ STAGE[stage].label }}
              </v-chip>
            </li>
          </ul>
          <p class="text-body-medium text-medium-emphasis" data-test="step-sources">
            Reported by
            <b v-for="(source, at) in step.sources" :key="source.key"
              >{{ at > 0 ? ', ' : '' }}{{ source.name }}</b
            >.
            <span v-if="step.duplicates > 0" data-test="step-duplicates">
              <v-icon :icon="Copy" size="16" aria-hidden="true" />
              {{ formatCount(step.duplicates) }}
              {{ step.duplicates === 1 ? 'alert was' : 'alerts were' }} also reported by another
              program, counted once.
            </span>
          </p>
          <ul v-if="step.evidence.length" class="path__evidence" data-test="step-evidence">
            <li v-for="(item, at) in shown(step)" :key="at" class="path__item" data-test="evidence">
              <p class="text-body-large path__item-summary">{{ item.signal.summary }}</p>
              <p class="text-body-medium text-medium-emphasis">
                {{ item.signal.src_address }}
                <v-icon :icon="ArrowRight" size="14" aria-hidden="true" />
                {{ item.signal.dst_address
                }}<template v-if="item.signal.dst_port !== null"
                  >:{{ item.signal.dst_port }}</template
                >
                <template v-if="item.count > 1">, {{ formatCount(item.count) }} times</template>.
                <span v-if="item.duplicates > 0" data-test="evidence-agreed">
                  Also reported by {{ agreedBy(item) }}, counted once.
                </span>
              </p>
            </li>
          </ul>
          <v-btn
            variant="text"
            size="small"
            :append-icon="ArrowRight"
            :to="{ name: 'incident', params: { id: step.incident_id } }"
            data-test="step-open"
          >
            Open the incident
          </v-btn>
        </div>
      </li>
    </template>
  </ol>
</template>

<style scoped>
.path {
  --rail: 2.75rem;

  position: relative;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* The rail that joins the steps: solid where a link was seen, dashed where it is inferred. */
.path__step,
.path__device {
  position: relative;
  display: flex;
  gap: 0.875rem;
}

.path__step::before,
.path__device::before {
  position: absolute;
  inset-block: calc(2.5rem + 0.25rem) calc(-1.25rem - 0.25rem);
  inset-inline-start: calc(1.25rem - 1px);
  border-inline-start: 2px solid rgb(var(--v-theme-error));
  content: '';
}

.path__step--inferred::before {
  border-inline-start-style: dashed;
  border-color: rgb(var(--v-theme-warning));
}

.path__step:last-child::before {
  display: none;
}

.path__node {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border: 2px solid currentcolor;
  border-radius: 50%;
  background: rgb(var(--v-theme-surface));
}

.path__node--confirmed {
  color: rgb(var(--v-theme-error));
}

.path__node--inferred {
  color: rgb(var(--v-theme-warning));
}

.path__node--device {
  color: rgb(var(--v-theme-primary));
}

.path__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
  min-width: 0;
  padding-block-end: 0.5rem;
}

.path__top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.path__title,
.path__device-name,
.path__reason,
.path__when {
  margin: 0;
}

.path__when {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
}

.path__subject {
  font-family: ui-monospace, monospace;
  overflow-wrap: anywhere;
}

.path__stages,
.path__evidence {
  display: flex;
  margin: 0;
  padding: 0;
  list-style: none;
}

.path__stages {
  flex-wrap: wrap;
  gap: 0.375rem;
}

.path__evidence {
  flex-direction: column;
  align-self: stretch;
  gap: 0.5rem;
  padding: 0.75rem;
  border: 1px solid rgba(var(--v-theme-on-surface), var(--v-border-opacity));
  border-radius: 12px;
}

.path__item-summary {
  margin: 0;
  overflow-wrap: anywhere;
}

.path__item p {
  margin: 0;
}
</style>
