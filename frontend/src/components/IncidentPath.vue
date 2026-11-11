<script setup lang="ts">
import { Cpu, Globe, Laptop, Radar, ScanEye, Shield } from '@lucide/vue'
import { computed } from 'vue'

import type { Hop, HopKind, TravelPath } from '@/api/incidents'
import { formatClock, formatCount, formatList } from '@/format'

/**
 * How it travelled: the internet, each program that saw it in the order it sits between there and
 * the device, and the device, drawn as a line of stops. It is the shape of a traceroute without a
 * probe being sent: nothing is scanned, and a program that did not report the incident is not on
 * the path. Where a program says what it did about it (turned it away, stopped it, banned the
 * address) that is written under its stop. It runs across on a wide screen and down on a phone.
 */
const props = defineProps<{ path: TravelPath }>()

const ICON: Record<HopKind, typeof Globe> = {
  internet: Globe,
  firewall: Shield,
  detector: ScanEye,
  monitor: Radar,
  agent: Cpu,
  device: Laptop,
}

const WHAT: Record<HopKind, string> = {
  internet: 'The internet',
  firewall: 'Firewall',
  detector: 'Intrusion detection',
  monitor: 'Traffic monitor',
  agent: 'Agent on the device',
  device: 'Your device',
}

const stops = computed(() => props.path.hops.map((hop, index) => ({ hop, index })))
const programs = computed(() =>
  props.path.hops.filter((hop) => hop.source !== null).map((hop) => hop.subject),
)

function seen(hop: Hop): string | null {
  if (hop.source === null) return null
  const alerts = `${formatCount(hop.alerts)} ${hop.alerts === 1 ? 'alert' : 'alerts'}`
  return hop.first_at ? `${alerts}, from ${formatClock(hop.first_at)}` : alerts
}
</script>

<template>
  <div class="route" data-test="path">
    <p class="text-body-large route__lead" data-test="path-lead">
      <template v-if="path.direction === 'inbound'">It came in from the internet</template>
      <template v-else>It went out from the device to the internet</template>
      <template v-if="programs.length"> and {{ formatList(programs) }} saw it on the way.</template>
      <template v-else>.</template>
    </p>
    <ol class="route__stops" aria-label="The path it took, in order">
      <li
        v-for="{ hop, index } in stops"
        :key="index"
        class="stop"
        :class="[`stop--${hop.kind}`, { 'stop--program': hop.source !== null }]"
        data-test="path-hop"
        :data-kind="hop.kind"
      >
        <span class="stop__node" aria-hidden="true">
          <v-icon :icon="ICON[hop.kind]" size="22" />
        </span>
        <div class="stop__body">
          <p class="text-label-large text-medium-emphasis stop__what">{{ WHAT[hop.kind] }}</p>
          <p class="text-title-medium stop__subject" data-test="hop-subject">
            {{ hop.subject }}
          </p>
          <p
            v-if="hop.name"
            class="text-body-medium text-medium-emphasis stop__name"
            data-test="hop-name"
          >
            {{ hop.name }}
          </p>
          <p v-if="seen(hop)" class="text-body-medium stop__seen" data-test="hop-seen">
            {{ seen(hop) }}
          </p>
          <p v-if="hop.note" class="text-body-medium stop__note" data-test="hop-note">
            {{ hop.note }}
          </p>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.route {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-width: 0;
}

.route__lead {
  margin: 0;
}

.route__stops {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

/* On a phone the stops go down a rail on the left. */
.stop {
  position: relative;
  display: flex;
  gap: 0.875rem;
  min-width: 0;
  padding-block-end: 1.25rem;
}

.stop:last-child {
  padding-block-end: 0;
}

.stop::before {
  position: absolute;
  inset-block: 2.75rem 0.25rem;
  inset-inline-start: calc(1.25rem - 1px);
  border-inline-start: 2px solid rgba(var(--v-theme-on-surface), 0.3);
  content: '';
}

.stop:last-child::before {
  display: none;
}

.stop__node {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border: 2px solid currentcolor;
  border-radius: 50%;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface-variant, var(--v-theme-on-surface)));
}

.stop--program .stop__node {
  color: rgb(var(--v-theme-primary));
}

.stop--internet .stop__node {
  color: rgb(var(--v-theme-error));
}

.stop--device .stop__node {
  color: rgb(var(--v-theme-secondary));
}

.stop__body {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
}

.stop__body p {
  margin: 0;
}

.stop__subject,
.stop__name {
  overflow-wrap: anywhere;
}

.stop__note {
  color: rgb(var(--v-theme-primary));
}

/* Wide enough, they go across, and the rail runs between the nodes. */
@media (min-width: 960px) {
  .route__stops {
    flex-direction: row;
    gap: 0;
  }

  .stop {
    flex: 1 1 0;
    flex-direction: column;
    align-items: flex-start;
    padding-block-end: 0;
    padding-inline-end: 0.75rem;
  }

  .stop::before {
    inset-block: 1.25rem auto;
    inset-inline: 2.75rem 0;
    border-block-start: 2px solid rgba(var(--v-theme-on-surface), 0.3);
    border-inline-start: 0;
  }
}
</style>
