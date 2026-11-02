<script setup lang="ts">
import { FlaskConical, Pencil, Trash2 } from '@lucide/vue'
import { computed, useId } from 'vue'

import type { Destination } from '@/api/alerts'
import StatusChip from '@/components/StatusChip.vue'
import { KINDS, lastResult, maskedAddress } from '@/alerts'
import { formatDateTime } from '@/format'

/**
 * One place alerts are sent: its name, what kind it is, whether it works, a masked version of its
 * address (the address itself is a secret that is never shown again) and the buttons to test it,
 * change it, turn it off or remove it. It only asks; what the buttons do is up to the page.
 */
const props = defineProps<{
  destination: Destination
  /** Something is being done to it, so its buttons wait. */
  busy?: boolean
  /** The test message is being sent. */
  testing?: boolean
}>()
const emit = defineEmits<{
  test: []
  edit: []
  remove: []
  toggle: [enabled: boolean]
}>()

const kind = computed(() => KINDS[props.destination.kind])
const titleId = useId()
</script>

<template>
  <li class="destination" :aria-labelledby="titleId" data-test="destination">
    <div class="destination__head">
      <v-icon :icon="kind.icon" size="22" class="destination__icon" aria-hidden="true" />
      <h3 :id="titleId" class="text-title-medium destination__name" data-test="destination-name">
        {{ destination.name }}
      </h3>
      <v-chip size="small" variant="outlined" data-test="destination-kind">{{ kind.label }}</v-chip>
      <v-chip v-if="!destination.enabled" size="small" variant="tonal" data-test="destination-off">
        Turned off
      </v-chip>
      <StatusChip :status="destination.status" class="destination__status" />
    </div>

    <p class="destination__address text-body-medium" data-test="destination-address">
      <span class="sr-only">Webhook address, with the secret part hidden: </span>
      <code>{{ maskedAddress(destination) }}</code>
    </p>

    <v-alert
      v-if="destination.last_error"
      type="error"
      variant="tonal"
      density="compact"
      title="The last message did not get through"
      data-test="destination-error"
    >
      {{ destination.last_error }}
    </v-alert>
    <p class="text-body-medium text-medium-emphasis" data-test="destination-result">
      <time
        v-if="destination.last_attempt_at"
        :datetime="destination.last_attempt_at"
        :title="formatDateTime(destination.last_attempt_at)"
        >{{ lastResult(destination) }}</time
      >
      <template v-else>{{ lastResult(destination) }}</template>
    </p>

    <div class="destination__actions">
      <v-btn
        variant="tonal"
        color="primary"
        :prepend-icon="FlaskConical"
        :loading="testing"
        :disabled="busy || destination.status === 'not_connected'"
        data-test="destination-test"
        @click="emit('test')"
      >
        Send test message
      </v-btn>
      <v-btn
        variant="text"
        :prepend-icon="Pencil"
        :disabled="busy"
        data-test="destination-edit"
        @click="emit('edit')"
      >
        Edit
      </v-btn>
      <v-btn
        variant="text"
        color="error"
        :prepend-icon="Trash2"
        :disabled="busy"
        data-test="destination-remove"
        @click="emit('remove')"
      >
        Remove
      </v-btn>
      <v-switch
        :model-value="destination.enabled"
        :disabled="busy"
        :label="destination.enabled ? 'Sending alerts' : 'Not sending'"
        color="primary"
        hide-details
        density="compact"
        class="destination__switch"
        data-test="destination-enabled"
        @update:model-value="emit('toggle', $event === true)"
      />
    </div>
  </li>
</template>

<style scoped>
.destination {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding-block: 1.25rem;
}

.destination + .destination {
  border-block-start: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.destination__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}

.destination__icon {
  color: rgb(var(--v-theme-primary));
}

.destination__name {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
}

.destination__status {
  margin-inline-start: auto;
}

.destination__address {
  margin: 0;
  overflow-wrap: anywhere;
}

.destination__address code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.875em;
}

.destination p {
  margin: 0;
}

.destination__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.5rem;
}

.destination__switch {
  margin-inline-start: auto;
  flex: none;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
