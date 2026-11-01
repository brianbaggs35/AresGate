<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { saveLimits, type UsageLimit } from '@/api/aiUsage'
import { errorMessage } from '@/api/client'
import { dollarsOf, limitColor, limitName, limitPercent, limitWords } from '@/aiUsage'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * What may be spent on AI that is paid for by the token: a limit for the last 24 hours and one for
 * the month. Reaching one stops the requests to such a provider until spending falls below it, so
 * nothing that runs by itself can spend more than was agreed. The meters show how much is gone.
 */
const props = defineProps<{ limits: readonly UsageLimit[] }>()
const emit = defineEmits<{ changed: [limits: UsageLimit[]] }>()

const session = useSessionStore()

const daily = ref('')
const monthly = ref('')
const busy = ref(false)
const failure = ref<string | null>(null)
const saved = ref(false)

const day = computed(() => props.limits.find(({ period }) => period === 'day') as UsageLimit)
const month = computed(() => props.limits.find(({ period }) => period === 'month') as UsageLimit)

// The fields start as the limits are kept, and follow them when the page asks again.
watch(
  () => props.limits,
  () => {
    daily.value = dollarsOf(day.value.limit_micros)
    monthly.value = dollarsOf(month.value.limit_micros)
  },
  { immediate: true },
)

/** What is wrong with an amount typed in, or nothing. An empty field is no limit. */
function problem(text: string): string | true {
  const amount = text.trim()
  if (amount === '') return true
  if (!/^\d{1,7}(\.\d{1,2})?$/.test(amount)) return 'Use dollars and cents, such as 5 or 2.50.'
  return Number(amount) > 0 || 'Use more than nothing, or leave it empty for no limit.'
}

const invalid = computed(() => problem(daily.value) !== true || problem(monthly.value) !== true)

async function save() {
  busy.value = true
  failure.value = null
  saved.value = false
  try {
    const kept = await session.change((token) =>
      saveLimits(
        { daily: daily.value.trim() || null, monthly: monthly.value.trim() || null },
        token,
      ),
    )
    saved.value = true
    emit('changed', kept)
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <SectionCard
    title="Spending limits"
    description="A limit holds whatever uses the AI. When one is used up, AresGate stops asking providers that charge by the token until spending is back under it. A provider on your own computer costs nothing and is never stopped."
    data-test="limits-card"
  >
    <ul class="limits" aria-label="How much of each limit is spent">
      <li
        v-for="limit in limits"
        :key="limit.period"
        class="limits__item"
        :data-test="`limit-${limit.period}`"
      >
        <div class="limits__text">
          <span class="text-label-large">{{ limitName(limit) }}</span>
          <span
            class="text-body-medium text-medium-emphasis"
            :data-test="`limit-${limit.period}-words`"
          >
            {{ limitWords(limit) }}
          </span>
        </div>
        <v-progress-linear
          v-if="limit.limit_micros !== null"
          :model-value="limitPercent(limit)"
          :color="limitColor(limit.state)"
          height="8"
          rounded
          :aria-label="`${limitName(limit)}: ${limitPercent(limit)} percent spent`"
          :data-test="`limit-${limit.period}-meter`"
        />
      </li>
    </ul>

    <form class="limits__form" novalidate @submit.prevent="save">
      <v-text-field
        v-model="daily"
        label="Daily limit"
        prefix="$"
        inputmode="decimal"
        autocomplete="off"
        hint="Spent in the last 24 hours. Empty is no limit."
        :rules="[problem]"
        :disabled="busy"
        data-test="limit-daily-field"
      />
      <v-text-field
        v-model="monthly"
        label="Monthly limit"
        prefix="$"
        inputmode="decimal"
        autocomplete="off"
        hint="Spent in the calendar month, in UTC, as providers bill it. Empty is no limit."
        :rules="[problem]"
        :disabled="busy"
        data-test="limit-monthly-field"
      />
      <v-btn
        type="submit"
        color="primary"
        :loading="busy"
        :disabled="invalid"
        class="limits__save"
        data-test="limits-save"
      >
        Save limits
      </v-btn>
    </form>
    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      class="mt-4"
      role="alert"
      data-test="limits-failure"
    >
      {{ failure }}
    </v-alert>
    <p v-else-if="saved" class="text-body-medium mt-4" role="status" data-test="limits-saved">
      The limits are saved.
    </p>
  </SectionCard>
</template>

<style scoped>
.limits {
  display: grid;
  gap: 1rem;
  margin: 0 0 1.5rem;
  padding: 0;
  list-style: none;
}

.limits__item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.limits__text {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0 1rem;
}

.limits__form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.5rem 1rem;
  align-items: start;
}

.limits__save {
  justify-self: start;
}
</style>
