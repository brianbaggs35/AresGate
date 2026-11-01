<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDisplay } from 'vuetify'

import { fetchUsageCall, type UsageCallDetail } from '@/api/aiUsage'
import { errorMessage } from '@/api/client'
import { formatMoney, purposeLabel } from '@/aiUsage'
import LoadError from '@/components/LoadError.vue'
import { formatTimestamp } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * One call to a provider as the provider saw it: what it was sent and what it answered. Addresses
 * and names are the stand-ins the provider was given (HOST_3, NAME_1), not the real ones, so this
 * is also the proof of what left this computer.
 */
const props = defineProps<{ callId: number | null }>()
const open = defineModel<boolean>({ required: true })

const session = useSessionStore()
// On a phone it fills the screen: what was sent is long, and a card that stops short of the
// bottom bar leaves its Close button half under it.
const { smAndDown } = useDisplay()
const call = ref<UsageCallDetail | null>(null)
const failure = ref<string | null>(null)
const loading = ref(false)

/** Which load is the newest, so the answer to an older one (for another call) is dropped. */
let latest = 0

async function load() {
  const id = props.callId
  if (id === null) return
  const mine = ++latest
  loading.value = true
  failure.value = null
  call.value = null
  try {
    const found = await session.call(() => fetchUsageCall(id))
    if (mine === latest) call.value = found
  } catch (error) {
    if (mine === latest) failure.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

watch(
  () => [open.value, props.callId] as const,
  ([isOpen]) => {
    if (isOpen) void load()
  },
  { immediate: true },
)
</script>

<template>
  <v-dialog v-model="open" max-width="760" scrollable :fullscreen="smAndDown">
    <v-card data-test="call-dialog">
      <v-card-title class="text-title-large">What was sent</v-card-title>
      <v-card-text>
        <LoadError
          v-if="failure"
          :message="failure"
          :loading="loading"
          retry-test-id="call-retry"
          @retry="load"
        />
        <v-skeleton-loader v-else-if="!call" type="article" data-test="call-loading" />
        <template v-else>
          <p class="text-body-medium text-medium-emphasis" data-test="call-summary">
            {{ purposeLabel(call.purpose)
            }}<template v-if="call.about"> about {{ call.about }}</template
            >, {{ formatTimestamp(call.occurred_at) }}, to {{ call.model_label }} ({{
              call.provider_label
            }}). Costs {{ formatMoney(call.cost_micros) }} (an estimate).
          </p>
          <p class="text-body-medium text-medium-emphasis">
            This is exactly what the provider read and said, with stand-ins such as HOST_1 in place
            of the addresses and names it was not shown.
          </p>
          <h3 class="text-title-medium mt-4">Sent</h3>
          <pre class="call__text" tabindex="0" data-test="call-prompt">{{ call.prompt }}</pre>
          <h3 class="text-title-medium mt-4">Answered</h3>
          <pre v-if="call.answer" class="call__text" tabindex="0" data-test="call-answer">{{
            call.answer
          }}</pre>
          <v-alert v-else type="warning" variant="tonal" data-test="call-error">
            {{ call.error ?? 'There was no answer.' }}
          </v-alert>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" data-test="call-close" @click="open = false">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.call__text {
  max-height: 18rem;
  margin: 0.5rem 0 0;
  padding: 0.75rem 1rem;
  overflow: auto;
  border-radius: 8px;
  background: rgb(var(--v-theme-surface-variant), 0.4);
  font-size: 0.8125rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
