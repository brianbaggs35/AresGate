<script setup lang="ts">
import { computed } from 'vue'

import type { Usage } from '@/api/agents'
import type { UsageLimit } from '@/api/aiUsage'
import { formatTokens, limitColor, limitName, limitPercent, limitWords } from '@/aiUsage'
import { cachedShare, costWords, tokensOf } from '@/agents'
import { formatCount } from '@/format'

/**
 * What all the agents together used of the AI over the last 30 days, in one line, and how much of
 * their own spending limits is gone, if they have any. Nothing is shown until an agent has asked
 * the AI something.
 */
const props = defineProps<{ usage: Usage; limits: readonly UsageLimit[] }>()

const set = computed(() => props.limits.filter((limit) => limit.limit_micros !== null))
const share = computed(() => cachedShare(props.usage))
</script>

<template>
  <section
    v-if="usage.calls > 0 || set.length"
    class="spend"
    aria-labelledby="spend-title"
    data-test="agents-spend"
  >
    <div class="spend__head">
      <h2 id="spend-title" class="text-title-medium">What the agents cost</h2>
      <RouterLink
        :to="{ name: 'settings-agents' }"
        class="text-label-large"
        data-test="spend-settings"
      >
        Agent settings
      </RouterLink>
    </div>
    <p class="text-body-large spend__line" data-test="spend-line">
      <strong data-test="spend-cost">{{ costWords(usage) }}</strong>
      over 30 days · {{ formatCount(usage.calls) }}
      {{ usage.calls === 1 ? 'request' : 'requests' }} · {{ formatTokens(tokensOf(usage)) }} tokens
      <template v-if="usage.input_tokens"> · {{ share }}% cached</template>
    </p>
    <ul v-if="set.length" class="spend__limits" aria-label="How much of each limit is spent">
      <li v-for="limit in set" :key="limit.period" :data-test="`spend-limit-${limit.period}`">
        <span class="text-body-medium">{{ limitName(limit) }}: {{ limitWords(limit) }}</span>
        <v-progress-linear
          :model-value="limitPercent(limit)"
          :color="limitColor(limit.state)"
          height="6"
          rounded
          :aria-label="`${limitName(limit)}: ${limitPercent(limit)} percent spent`"
        />
      </li>
    </ul>
  </section>
</template>

<style scoped>
.spend {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem 1.25rem;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 1rem;
}

.spend__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.25rem 1rem;
}

.spend h2,
.spend p {
  margin: 0;
}

.spend__limits {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 0.75rem 1.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.spend__limits li {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
</style>
