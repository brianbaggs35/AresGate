<script setup lang="ts">
import { Fingerprint } from '@lucide/vue'
import { computed } from 'vue'

import type { AssetIdentity } from '@/api/assets'
import { formatAgo, formatDateTime } from '@/format'
import { identityConfidence, identitySteps } from '@/inventory'

/**
 * What a device-fingerprinting service (Fingerbank) says a device is: the most specific thing it
 * is, the steps from the widest kind to it, its maker and operating system, and how sure the
 * service is. It is a guess from the hardware address, so the confidence is shown with a bar and
 * in words, and a device the service had no match for says so rather than showing nothing.
 */
const props = defineProps<{ identity: AssetIdentity }>()

const steps = computed(() => identitySteps(props.identity))
const known = computed(() => props.identity.state === 'identified')
const reason = computed(() =>
  props.identity.reason === 'incident'
    ? 'Asked about because it is in an incident or threat.'
    : 'Asked about because it is one of your devices.',
)
</script>

<template>
  <v-card class="identity pa-5" variant="outlined" data-test="asset-identity">
    <div class="identity__head">
      <span class="identity__icon" aria-hidden="true"><Fingerprint :size="22" /></span>
      <div class="identity__title">
        <p v-if="known" class="text-title-large" data-test="identity-name">
          {{ identity.name ?? steps[steps.length - 1] }}
        </p>
        <p v-else class="text-title-large" data-test="identity-none">No match</p>
        <p class="text-body-medium text-medium-emphasis" data-test="identity-source">
          {{ known ? 'Said by' : 'Asked of' }} {{ identity.source_name }}, checked
          <time :datetime="identity.checked_at" :title="formatDateTime(identity.checked_at)">{{
            formatAgo(identity.checked_at)
          }}</time>
        </p>
      </div>
    </div>

    <p v-if="!known" class="text-body-medium text-medium-emphasis" data-test="identity-unknown">
      {{ identity.source_name }} has nothing on this hardware address. It is asked again after a
      week, since its database grows.
    </p>

    <template v-else>
      <ol
        v-if="steps.length > 1"
        class="identity__steps"
        aria-label="What kind of device"
        data-test="identity-steps"
      >
        <li v-for="step in steps" :key="step">
          <v-chip size="small" variant="tonal" label>{{ step }}</v-chip>
        </li>
      </ol>

      <dl class="identity__facts">
        <div v-if="identity.manufacturer" class="identity__fact">
          <dt class="text-label-large text-medium-emphasis">Maker</dt>
          <dd data-test="identity-maker">{{ identity.manufacturer }}</dd>
        </div>
        <div v-if="identity.operating_system" class="identity__fact">
          <dt class="text-label-large text-medium-emphasis">Operating system</dt>
          <dd data-test="identity-os">{{ identity.operating_system }}</dd>
        </div>
        <div v-if="identity.score !== null" class="identity__fact">
          <dt class="text-label-large text-medium-emphasis">How sure</dt>
          <dd data-test="identity-score">
            <span class="text-label-large">{{ identityConfidence(identity.score) }}</span>
            <span class="text-medium-emphasis tabular-nums"> · {{ identity.score }} of 100</span>
            <v-progress-linear
              :model-value="identity.score"
              color="primary"
              height="6"
              rounded
              aria-hidden="true"
            />
          </dd>
        </div>
      </dl>
    </template>

    <p class="text-body-medium text-medium-emphasis" data-test="identity-reason">{{ reason }}</p>
  </v-card>
</template>

<style scoped>
.identity {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.identity p {
  margin: 0;
}

.identity__head {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.identity__icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 12px;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.identity__title {
  min-width: 0;
  overflow-wrap: anywhere;
}

.identity__steps {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.identity__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(12rem, 100%), 1fr));
  gap: 0.75rem 1.5rem;
  margin: 0;
}

.identity__fact dd {
  margin: 0.125rem 0 0;
  overflow-wrap: anywhere;
}
</style>
