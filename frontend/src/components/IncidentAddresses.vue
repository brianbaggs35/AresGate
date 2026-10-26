<script setup lang="ts">
import { Laptop } from '@lucide/vue'
import { computed } from 'vue'

import type { IncidentDevice } from '@/api/incidents'
import { isAboutRule } from '@/incidents'

/**
 * The addresses an incident names, the one it is about first, and which of them are devices on
 * your network, with what is known of each. An address that no device has is somewhere else.
 */
const props = defineProps<{
  subject: string
  addresses: readonly string[]
  devices: readonly IncidentDevice[]
}>()

/** The rule an incident is about, for one that named no address. */
const rule = computed(() =>
  isAboutRule(props.subject) ? props.subject.split(':').slice(2).join(':') : null,
)

const rows = computed(() =>
  props.addresses.map((address) => ({
    address,
    subject: address === props.subject,
    device: props.devices.find((device) => device.address === address) ?? null,
  })),
)
</script>

<template>
  <div data-test="addresses">
    <p v-if="rule" class="text-body-large" data-test="addresses-rule">
      This incident is about a rule, <span class="addresses__mono">{{ rule }}</span
      >, whose signals named no address.
    </p>
    <ul v-if="rows.length" class="addresses__list">
      <li v-for="row in rows" :key="row.address" class="addresses__item" data-test="address">
        <div class="addresses__head">
          <span class="addresses__mono text-title-medium" data-test="address-value">{{
            row.address
          }}</span>
          <v-chip
            v-if="row.subject"
            size="small"
            color="primary"
            variant="tonal"
            data-test="address-subject"
          >
            What it is about
          </v-chip>
        </div>
        <div v-if="row.device" class="addresses__device" data-test="address-device">
          <p class="addresses__name text-body-large">
            <v-icon :icon="Laptop" size="20" aria-hidden="true" />
            {{ row.device.hostname ?? 'A device with no name' }}
            <v-chip size="small" variant="outlined">On your network</v-chip>
          </p>
          <p class="text-body-medium text-medium-emphasis">
            <template v-if="row.device.vendor">{{ row.device.vendor }} · </template>
            <span class="addresses__mono">{{ row.device.mac }}</span>
          </p>
        </div>
        <p v-else class="text-body-medium text-medium-emphasis" data-test="address-elsewhere">
          Not a device AresGate knows.
        </p>
      </li>
    </ul>
    <p v-else-if="!rule" class="text-body-medium text-medium-emphasis">No addresses were named.</p>
  </div>
</template>

<style scoped>
.addresses__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.addresses__item {
  padding: 0.75rem 0;
}

.addresses__item + .addresses__item {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.addresses__item:first-child {
  padding-top: 0;
}

.addresses__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
}

.addresses__item p {
  margin: 0.25rem 0 0;
}

.addresses__name {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.5rem;
}

.addresses__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
}
</style>
