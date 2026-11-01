<script setup lang="ts">
import { Eye } from '@lucide/vue'
import { computed, ref, watch } from 'vue'

import { fetchUsageCalls, type UsageCall, type UsageRange } from '@/api/aiUsage'
import { errorMessage } from '@/api/client'
import { formatMoney, formatTokens, purposeLabel } from '@/aiUsage'
import AiCallDialog from '@/components/AiCallDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatCount, formatTimestamp } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * Every request to a provider in the range, newest first, a page at a time. Each opens to show
 * what the provider was sent and what it answered.
 */
const props = defineProps<{ range: UsageRange; refreshed: number }>()

/** How many calls a page holds. */
const PAGE = 25

const session = useSessionStore()
const calls = ref<UsageCall[]>([])
const total = ref(0)
const loading = ref(false)
const failure = ref<string | null>(null)
const shown = ref<number | null>(null)
const showing = ref(false)
/** Which load is the newest, so the answer to an older one (for another range) is dropped. */
let latest = 0

async function load(more = false) {
  const mine = ++latest
  loading.value = true
  failure.value = null
  try {
    const page = await session.call(() =>
      fetchUsageCalls(props.range, PAGE, more ? calls.value.length : 0),
    )
    if (mine !== latest) return
    calls.value = more ? [...calls.value, ...page.items] : page.items
    total.value = page.total
  } catch (error) {
    if (mine === latest) failure.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

function open(call: UsageCall) {
  shown.value = call.id
  showing.value = true
}

const rest = computed(() => total.value - calls.value.length)

watch(
  () => [props.range, props.refreshed],
  () => load(),
  { immediate: true },
)
</script>

<template>
  <SectionCard
    title="Every request"
    description="Each request to a provider, newest first. Open one to see exactly what the provider was sent and what it said."
    data-test="calls-card"
  >
    <LoadError
      v-if="failure && calls.length === 0"
      :message="failure"
      :loading="loading"
      retry-test-id="calls-retry"
      @retry="load()"
    />
    <v-skeleton-loader
      v-else-if="loading && calls.length === 0"
      type="table"
      data-test="calls-loading"
    />
    <EmptyState
      v-else-if="calls.length === 0"
      title="No requests in this range"
      description="Nothing was sent to a provider in this time."
      data-test="calls-empty"
    />
    <template v-else>
      <ul class="calls" aria-label="Requests to providers">
        <li v-for="call in calls" :key="call.id" class="calls__item" data-test="call">
          <div class="calls__main">
            <span class="text-label-large" data-test="call-use">
              {{ purposeLabel(call.purpose)
              }}<template v-if="call.about">, {{ call.about }}</template>
            </span>
            <span class="text-body-medium text-medium-emphasis">
              {{ formatTimestamp(call.occurred_at) }} · {{ call.model_label }}
            </span>
            <span v-if="!call.ok" class="text-body-medium text-error" data-test="call-failed">
              Failed: {{ call.error }}
            </span>
          </div>
          <div class="calls__numbers text-body-medium tabular-nums">
            <span>{{ formatTokens(call.input_tokens + call.output_tokens) }} tokens</span>
            <span>{{ formatMoney(call.cost_micros) }}</span>
          </div>
          <v-btn
            variant="text"
            :prepend-icon="Eye"
            :aria-label="`See what was sent: ${purposeLabel(call.purpose)}, ${formatTimestamp(call.occurred_at)}`"
            data-test="call-open"
            @click="open(call)"
          >
            See
          </v-btn>
        </li>
      </ul>
      <v-alert v-if="failure" type="error" variant="tonal" class="mt-3" role="alert">
        {{ failure }}
      </v-alert>
      <div v-if="rest > 0" class="calls__more">
        <v-btn variant="tonal" :loading="loading" data-test="calls-more" @click="load(true)">
          Show {{ formatCount(Math.min(rest, PAGE)) }} more
        </v-btn>
        <span class="text-body-medium text-medium-emphasis">
          {{ formatCount(calls.length) }} of {{ formatCount(total) }}
        </span>
      </div>
    </template>
    <AiCallDialog v-model="showing" :call-id="shown" />
  </SectionCard>
</template>

<style scoped>
.calls {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
}

.calls__item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 0.5rem 1rem;
  align-items: center;
  padding: 0.75rem 0;
  border-bottom: 1px solid rgb(var(--v-theme-outline-variant), 0.6);
}

.calls__main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.calls__numbers {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.calls__more {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
  margin-top: 1rem;
}

/* On a phone the numbers go under the text, and the button stays in reach. */
@media (max-width: 599.98px) {
  .calls__item {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .calls__numbers {
    grid-column: 1;
    flex-direction: row;
    gap: 1rem;
    align-items: baseline;
  }

  .calls__item > .v-btn {
    grid-column: 2;
    grid-row: 1 / span 2;
  }
}
</style>
