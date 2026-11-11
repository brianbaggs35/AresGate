<script setup lang="ts">
import { Coins, DatabaseZap, MessagesSquare, Zap } from '@lucide/vue'
import { computed } from 'vue'

import type { Usage, UsageDay } from '@/api/agents'
import { formatMoney, formatTokens } from '@/aiUsage'
import { cachedShare, costWords, dailyCost, tokensOf } from '@/agents'
import BarChart from '@/charts/BarChart.vue'
import StatTile from '@/components/StatTile.vue'
import { formatCount } from '@/format'

/**
 * What an agent has used of the AI over the last 30 days: what it cost, how many requests and
 * tokens that was, how much of what it sent the provider already had cached (which is what makes
 * asking in the same words each time cheap), and each day's cost. The prices are the provider's
 * own, read from its pricing page, and a model whose price isn't known is counted but not priced.
 */
const props = defineProps<{ usage: Usage; days: readonly UsageDay[] }>()

const bars = computed(() => dailyCost(props.days))
const share = computed(() => cachedShare(props.usage))
const perRun = computed(() =>
  props.usage.runs > 0 && props.usage.unpriced_calls === 0
    ? `${formatMoney(Math.round(props.usage.cost_micros / props.usage.runs))} a run`
    : 'Over its last 30 days',
)
</script>

<template>
  <div class="usage" data-test="agent-usage">
    <div class="usage__tiles">
      <StatTile
        label="Cost"
        :icon="Coins"
        :value="costWords(usage)"
        :hint="perRun"
        data-test="usage-cost"
      />
      <StatTile
        label="Requests"
        :icon="MessagesSquare"
        :value="formatCount(usage.calls)"
        :hint="`In ${formatCount(usage.runs)} ${usage.runs === 1 ? 'run' : 'runs'}`"
        data-test="usage-calls"
      />
      <StatTile
        label="Tokens"
        :icon="Zap"
        :value="formatTokens(tokensOf(usage))"
        :hint="`${formatTokens(usage.input_tokens)} sent, ${formatTokens(usage.output_tokens)} back`"
        data-test="usage-tokens"
      />
      <StatTile
        label="Cached"
        :icon="DatabaseZap"
        :value="usage.input_tokens ? `${share}%` : '–'"
        hint="Of what it sent was already cached"
        :tone="share >= 50 ? 'good' : 'neutral'"
        data-test="usage-cached"
      />
    </div>

    <BarChart
      title="Cost by day"
      caption="What this agent's requests cost on each of the last 30 days (UTC)."
      category-label="Day"
      orientation="vertical"
      :height="180"
      :categories="bars.categories"
      :series="bars.series"
      :format="(value) => formatMoney(Math.round(value * 1_000_000))"
      empty-title="No cost yet"
      empty-description="It has not asked the AI anything, or it is on your own computer."
      data-test="usage-chart"
    />

    <p
      v-if="usage.unpriced_calls"
      class="text-body-medium text-medium-emphasis usage__note"
      data-test="usage-unpriced"
    >
      {{ formatCount(usage.unpriced_calls) }}
      {{ usage.unpriced_calls === 1 ? 'request was' : 'requests were' }} to a model whose price
      AresGate doesn't know, so what is shown is at least what it cost.
    </p>
    <p class="text-body-medium text-medium-emphasis usage__note">
      Every request is recorded as the provider saw it on the
      <RouterLink :to="{ name: 'ai-usage' }" data-test="usage-link">AI usage</RouterLink> page.
      Which AI the agents ask, and what they may spend, is under
      <RouterLink :to="{ name: 'settings-agents' }" data-test="usage-settings-link"
        >Settings &gt; Agents</RouterLink
      >.
    </p>
  </div>
</template>

<style scoped>
.usage {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.usage__tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 0.75rem;
}

.usage__note {
  margin: 0;
}
</style>
