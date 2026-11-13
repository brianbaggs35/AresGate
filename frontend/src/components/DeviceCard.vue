<script setup lang="ts">
import { ArrowDownLeft, ArrowUpRight, Fingerprint, Siren } from '@lucide/vue'
import { computed } from 'vue'

import type { Device } from '@/api/devices'
import { connectionsOf, incomingShare, nameOf, SCOPE } from '@/devices'
import { formatAgo, formatCount, formatDateTime } from '@/format'
import { describePort } from '@/ports'
import { JUDGEMENT } from '@/threatIntel'

/**
 * A device in the list: its address and what it is called, whose it is, how many connections were
 * made to it and by it (as a bar that splits them), the ports they used, and, where there are any,
 * the incidents it is in and what threat intelligence kept of it. On a computer the facts sit in
 * columns; on a phone they stack.
 */
const props = defineProps<{ device: Device }>()

const name = computed(() => nameOf(props.device))
const share = computed(() => incomingShare(props.device))
const total = computed(() => connectionsOf(props.device))
</script>

<template>
  <v-card class="device" :class="`device--${device.scope}`" data-test="device-card">
    <div class="device__main">
      <span class="device__icon" aria-hidden="true">
        <v-icon :icon="SCOPE[device.scope].icon" size="24" />
      </span>
      <div class="device__who">
        <h3 class="device__address text-title-large" data-test="device-address">
          <router-link
            class="device__link"
            :to="{ name: 'device', params: { address: device.address } }"
            data-test="device-link"
          >
            {{ device.address }}
          </router-link>
        </h3>
        <p
          v-if="name"
          class="device__name text-body-medium text-medium-emphasis"
          data-test="device-name"
        >
          {{ name }}
        </p>
      </div>
      <div class="device__state">
        <v-chip size="small" variant="tonal" data-test="device-scope">
          <v-icon :icon="SCOPE[device.scope].icon" size="16" start aria-hidden="true" />
          {{ SCOPE[device.scope].label }}
        </v-chip>
        <span class="text-body-medium text-medium-emphasis" data-test="device-when">
          Seen
          <time :datetime="device.last_seen_at" :title="formatDateTime(device.last_seen_at)">{{
            formatAgo(device.last_seen_at)
          }}</time>
        </span>
      </div>
    </div>

    <div v-if="device.incidents || device.standing || device.asset?.identity" class="device__flags">
      <v-chip
        v-if="device.incidents"
        :prepend-icon="Siren"
        color="error"
        variant="tonal"
        size="small"
        data-test="device-incidents"
      >
        In {{ formatCount(device.incidents.count) }}
        {{ device.incidents.count === 1 ? 'incident' : 'incidents' }}
      </v-chip>
      <v-chip
        v-if="device.standing"
        :color="JUDGEMENT[device.standing.judgement].color"
        :prepend-icon="JUDGEMENT[device.standing.judgement].icon"
        variant="tonal"
        size="small"
        data-test="device-standing"
        :data-judgement="device.standing.judgement"
      >
        {{ JUDGEMENT[device.standing.judgement].short }}
      </v-chip>
      <v-chip
        v-if="device.asset?.identity?.state === 'identified'"
        :prepend-icon="Fingerprint"
        variant="tonal"
        size="small"
        data-test="device-identified"
      >
        {{ device.asset.identity.name ?? device.asset.identity.manufacturer }}
      </v-chip>
    </div>

    <div class="device__mix" data-test="device-mix">
      <div class="device__bar" aria-hidden="true">
        <span class="device__in" :style="{ inlineSize: `${share}%` }" />
      </div>
      <p class="device__counts text-body-medium">
        <span data-test="device-incoming">
          <v-icon :icon="ArrowDownLeft" size="16" aria-hidden="true" />
          {{ formatCount(device.incoming) }} in
        </span>
        <span data-test="device-outgoing">
          <v-icon :icon="ArrowUpRight" size="16" aria-hidden="true" />
          {{ formatCount(device.outgoing) }} out
        </span>
        <span v-if="total === 0" class="text-medium-emphasis">No connections this week</span>
      </p>
    </div>

    <dl v-if="device.ports.length || device.protocols.length" class="device__facts">
      <div v-if="device.ports.length" class="device__fact">
        <dt class="text-label-large text-medium-emphasis">Ports</dt>
        <dd class="device__chips" data-test="device-ports">
          <v-chip
            v-for="port in device.ports"
            :key="`${port.protocol}-${port.port}`"
            size="x-small"
            variant="outlined"
          >
            {{ describePort(port.port, port.protocol) }}
          </v-chip>
        </dd>
      </div>
      <div v-if="device.asset" class="device__fact">
        <dt class="text-label-large text-medium-emphasis">Asset</dt>
        <dd data-test="device-asset">
          <router-link :to="{ name: 'asset', params: { key: device.asset.key } }">
            {{ device.asset.name }}
          </router-link>
        </dd>
      </div>
    </dl>
  </v-card>
</template>

<style scoped>
.device {
  container-type: inline-size;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  overflow: hidden;
}

@media (min-width: 600px) {
  .device {
    padding: 1.25rem;
  }
}

/* The bar on the left says whose it is at a glance, and the chip says it in words. */
.device::before {
  content: '';
  position: absolute;
  inset-block: 0;
  inset-inline-start: 0;
  width: 4px;
  background: rgba(var(--v-theme-on-surface), 0.2);
}

.device--yours::before {
  background: rgb(var(--v-theme-primary));
}

.device--outside::before {
  background: rgb(var(--v-theme-info));
}

.device__main {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 0.25rem 0.75rem;
  align-items: start;
}

.device__icon {
  display: grid;
  place-items: center;
  inline-size: 2.5rem;
  block-size: 2.5rem;
  border-radius: 0.75rem;
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.device__who {
  min-inline-size: 0;
}

.device__who h3,
.device__who p,
.device__counts {
  margin: 0;
}

.device__address {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow-wrap: anywhere;
}

.device__link {
  color: inherit;
  text-decoration: none;
}

.device__link:hover,
.device__link:focus-visible {
  text-decoration: underline;
}

.device__state {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}

@container (min-width: 36rem) {
  .device__main {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .device__state {
    grid-column: auto;
    flex-direction: column;
    align-items: flex-end;
  }
}

.device__flags,
.device__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.device__bar {
  inline-size: 100%;
  block-size: 0.5rem;
  border-radius: 999px;
  background: rgba(var(--v-theme-secondary), 0.35);
  overflow: hidden;
}

.device__in {
  display: block;
  block-size: 100%;
  background: rgb(var(--v-theme-primary));
}

.device__counts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
  margin-block-start: 0.5rem;
}

.device__facts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 2rem;
  margin: 0;
}

.device__fact dd {
  margin: 0;
}
</style>
