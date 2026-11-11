<script setup lang="ts">
import { Bot, Sparkles } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'

import { fetchAi, type Ai, type AiProvider } from '@/api/ai'
import {
  fetchAgentSettings,
  saveAgentSettings,
  type AgentSettings,
  type AiSource,
} from '@/api/agents'
import { dollarsOf, limitColor, limitName, limitPercent, limitWords } from '@/aiUsage'
import { errorMessage } from '@/api/client'
import { foundItems, isReady, modelItems } from '@/ai'
import AiProviderForm from '@/components/AiProviderForm.vue'
import AiProviderPicker from '@/components/AiProviderPicker.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * Settings > Agents: which AI the agents ask and what they may spend. An agent may run every hour,
 * so it gets a choice of its own: what Settings > AI chose, a provider of its own (set up here,
 * with a model of its own, which can be a cheaper one), or none, so that it only looks. Their
 * spending has limits apart from the ones for everything else. What a provider is shown is the
 * same for every use of AI and is set under Settings > AI.
 */
const session = useSessionStore()

const settings = ref<AgentSettings | null>(null)
const ai = ref<Ai | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)
const busy = ref<'ai' | 'limits' | null>(null)
const failure = ref<{ ai?: string; limits?: string }>({})
const saved = ref<'ai' | 'limits' | null>(null)

const source = ref<AiSource>('shared')
/** The provider whose settings are shown, and the model the agents ask of it (null for the one it
 * was set up with). */
const chosen = ref<string | null>(null)
const model = ref<string | null>(null)
const daily = ref('')
const monthly = ref('')

const SOURCES: readonly { value: AiSource; title: string; hint: string }[] = [
  {
    value: 'shared',
    title: 'The same as Settings > AI',
    hint: 'They ask whichever provider you chose there, while AI is turned on there.',
  },
  {
    value: 'own',
    title: 'A provider of their own',
    hint: 'Choose and set one up here, and a model for them, such as a cheaper one than you ask questions of.',
  },
  {
    value: 'off',
    title: 'None',
    hint: 'They still look at your network and keep what they saw, but no AI reads it.',
  },
]

const current = computed<AiProvider | undefined>(() =>
  ai.value?.providers.find((item) => item.key === chosen.value),
)
const modelChoices = computed(() => {
  const provider = current.value
  if (!provider) return []
  const same = {
    value: null,
    title: provider.model ? `As set up (${provider.model})` : 'As set up',
  }
  const items = provider.models.length
    ? modelItems(provider)
    : foundItems(provider, provider.plan, model.value ?? '')
  return [same, ...items]
})
const ready = computed(() => (current.value ? isReady(current.value) : false))
const asking = computed(() => settings.value?.asking ?? null)

function adopt(next: AgentSettings) {
  settings.value = next
  source.value = next.ai_source
  chosen.value = next.provider ?? chosen.value
  model.value = next.model
  daily.value = dollarsOf(next.limits.find(({ period }) => period === 'day')?.limit_micros ?? null)
  monthly.value = dollarsOf(
    next.limits.find(({ period }) => period === 'month')?.limit_micros ?? null,
  )
}

async function load() {
  loading.value = true
  loadError.value = null
  try {
    const [next, providers] = await Promise.all([
      session.call(fetchAgentSettings),
      session.call(fetchAi),
    ])
    ai.value = providers
    adopt(next)
    chosen.value ??=
      providers.provider ?? providers.providers.find((item) => item.configured)?.key ?? null
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

// A model belongs to a provider: choosing another provider starts from its own.
watch(chosen, (now, before) => {
  if (before !== null && now !== before) model.value = null
})

/** What is wrong with an amount typed in, or nothing. An empty field is no limit. */
function problem(text: string): string | true {
  const amount = text.trim()
  if (amount === '') return true
  if (!/^\d{1,7}(\.\d{1,2})?$/.test(amount)) return 'Use dollars and cents, such as 5 or 2.50.'
  return Number(amount) > 0 || 'Use more than nothing, or leave it empty for no limit.'
}
const invalidLimits = computed(
  () => problem(daily.value) !== true || problem(monthly.value) !== true,
)

/** Keeps what was changed in one card, with what is kept of the other: the two are saved apart. */
async function save(part: 'ai' | 'limits') {
  const kept = settings.value as AgentSettings
  const limitOf = (period: 'day' | 'month') =>
    dollarsOf(kept.limits.find((limit) => limit.period === period)?.limit_micros ?? null) || null
  busy.value = part
  failure.value = {}
  saved.value = null
  try {
    const next = await session.change((token) =>
      saveAgentSettings(
        part === 'ai'
          ? {
              ai_source: source.value,
              provider: source.value === 'own' ? chosen.value : null,
              model: source.value === 'own' ? model.value : null,
              daily: limitOf('day'),
              monthly: limitOf('month'),
            }
          : {
              ai_source: kept.ai_source,
              provider: kept.provider,
              model: kept.model,
              daily: daily.value.trim() || null,
              monthly: monthly.value.trim() || null,
            },
        token,
      ),
    )
    adopt(next)
    saved.value = part
  } catch (error) {
    failure.value = { [part]: errorMessage(error) }
  } finally {
    busy.value = null
  }
}

/** A provider changed (kept, tested, asked for its models): the page shows it as it is now. */
function replace(provider: AiProvider) {
  const known = ai.value as Ai
  ai.value = {
    ...known,
    providers: known.providers.map((item) => (item.key === provider.key ? provider : item)),
  }
}

onMounted(load)
</script>

<template>
  <LoadError
    v-if="loadError && !settings"
    :message="loadError"
    :loading="loading"
    retry-test-id="agent-settings-retry"
    data-test="agent-settings-error"
    @retry="load"
  />
  <template v-else-if="settings && ai">
    <SectionCard
      title="Which AI the agents use"
      description="Agents may run every hour, so they can have an AI of their own: a cheaper model than the one you ask questions of, another provider, or none. Without one they still look at your network and keep what they saw."
      data-test="agent-ai-card"
    >
      <template #actions>
        <v-chip
          :color="asking ? 'success' : undefined"
          :variant="asking ? 'tonal' : 'outlined'"
          :prepend-icon="asking ? Sparkles : Bot"
          data-test="agent-ai-state"
        >
          <template v-if="asking">{{ asking.label }}, {{ asking.model }}</template>
          <template v-else>Not asking an AI</template>
        </v-chip>
      </template>

      <v-radio-group
        v-model="source"
        label="Where the agents get their AI"
        hide-details
        data-test="agent-source"
      >
        <v-radio
          v-for="choice in SOURCES"
          :key="choice.value"
          :value="choice.value"
          :data-test="`source-${choice.value}`"
        >
          <template #label>
            <span class="source">
              <span class="text-body-large">{{ choice.title }}</span>
              <span class="text-body-medium text-medium-emphasis">{{ choice.hint }}</span>
            </span>
          </template>
        </v-radio>
      </v-radio-group>

      <p
        v-if="settings.reason && source === settings.ai_source"
        class="text-body-medium text-medium-emphasis mt-3"
        data-test="agent-ai-reason"
      >
        {{ settings.reason }}
        <RouterLink
          v-if="source === 'shared'"
          :to="{ name: 'settings-ai' }"
          data-test="agent-ai-link"
          >AI settings</RouterLink
        >
      </p>

      <div v-if="source === 'own'" class="own" data-test="agent-own">
        <AiProviderPicker
          v-model="chosen"
          :providers="ai.providers"
          :asking="asking?.provider ?? null"
        />
        <p v-if="!current" class="text-body-medium text-medium-emphasis" data-test="agent-choose">
          Choose one to set it up. Its key is kept the way every provider's is, sealed, and the same
          provider can also be used for everything else under Settings > AI.
        </p>
        <KeepAlive>
          <AiProviderForm
            v-if="current"
            :key="current.key"
            :provider="current"
            :priced-as-of="ai.priced_as_of"
            :free-models-as-of="ai.free_models_as_of"
            @changed="replace"
            @removed="load"
          >
            <v-select
              v-model="model"
              :items="modelChoices"
              item-title="title"
              item-value="value"
              label="Model for the agents"
              hint="The agents can ask a different model than the one this provider is set up with."
              persistent-hint
              :disabled="!ready"
              data-test="agent-model"
            />
          </AiProviderForm>
        </KeepAlive>
      </div>

      <div class="actions">
        <v-btn
          color="primary"
          :loading="busy === 'ai'"
          :disabled="busy !== null || (source === 'own' && !ready)"
          data-test="agent-ai-save"
          @click="save('ai')"
        >
          Save
        </v-btn>
        <span
          v-if="source === 'own' && !ready"
          class="text-body-medium text-medium-emphasis"
          data-test="agent-ai-notready"
        >
          Save the provider first: it needs a model and, if it takes one, an API key.
        </span>
      </div>
      <v-alert
        v-if="failure.ai"
        type="error"
        variant="tonal"
        class="mt-4"
        role="alert"
        data-test="agent-ai-failure"
      >
        {{ failure.ai }}
      </v-alert>
      <output
        v-else-if="saved === 'ai'"
        class="d-block text-body-medium mt-4"
        data-test="agent-ai-saved"
      >
        Saved.
      </output>
    </SectionCard>

    <SectionCard
      title="What the agents may spend"
      description="These hold only what the agents spend, on top of the limits on the AI usage page that hold everything. When one is used up the agents stop asking a provider that charges by the token, and carry on looking, until spending is back under it. A provider on your own computer costs nothing and is never stopped."
      data-test="agent-limits-card"
    >
      <ul class="limits" aria-label="How much of each limit is spent">
        <li
          v-for="limit in settings.limits"
          :key="limit.period"
          class="limits__item"
          :data-test="`agent-limit-${limit.period}`"
        >
          <div class="limits__text">
            <span class="text-label-large">{{ limitName(limit) }}</span>
            <span class="text-body-medium text-medium-emphasis">{{ limitWords(limit) }}</span>
          </div>
          <v-progress-linear
            v-if="limit.limit_micros !== null"
            :model-value="limitPercent(limit)"
            :color="limitColor(limit.state)"
            height="8"
            rounded
            :aria-label="`${limitName(limit)}: ${limitPercent(limit)} percent spent`"
          />
        </li>
      </ul>
      <form class="limits__form" novalidate @submit.prevent="save('limits')">
        <v-text-field
          v-model="daily"
          label="Daily limit"
          prefix="$"
          inputmode="decimal"
          autocomplete="off"
          hint="Spent in the last 24 hours. Empty is no limit."
          :rules="[problem]"
          :disabled="busy !== null"
          data-test="agent-limit-daily-field"
        />
        <v-text-field
          v-model="monthly"
          label="Monthly limit"
          prefix="$"
          inputmode="decimal"
          autocomplete="off"
          hint="Spent in the calendar month, in UTC, as providers bill it. Empty is no limit."
          :rules="[problem]"
          :disabled="busy !== null"
          data-test="agent-limit-monthly-field"
        />
        <v-btn
          type="submit"
          color="primary"
          :loading="busy === 'limits'"
          :disabled="invalidLimits || busy !== null"
          class="limits__save"
          data-test="agent-limits-save"
        >
          Save limits
        </v-btn>
      </form>
      <v-alert
        v-if="failure.limits"
        type="error"
        variant="tonal"
        class="mt-4"
        role="alert"
        data-test="agent-limits-failure"
      >
        {{ failure.limits }}
      </v-alert>
      <output
        v-else-if="saved === 'limits'"
        class="d-block text-body-medium mt-4"
        data-test="agent-limits-saved"
      >
        The limits are saved.
      </output>
    </SectionCard>
  </template>
  <v-skeleton-loader v-else type="card, card" />
</template>

<style scoped>
.source {
  display: flex;
  flex-direction: column;
}

.own {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  margin-top: 1.5rem;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
  margin-top: 1.5rem;
}

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
