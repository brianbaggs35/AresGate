<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import {
  fetchRetentionSettings,
  saveRetentionSettings,
  type RetentionDraft,
  type RetentionSettings,
} from '@/api/retentionSettings'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatAgo, formatBytes, formatDays } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * Settings > Retention: how long AresGate keeps what it has collected, and how big its database
 * may get. It starts switched off, which leaves each kind of data kept for the time its own
 * setting gives, as it always was. Switched on, the owner either keeps everything forever or sets
 * the days and, if they want, a quota: past it the oldest weeks of events and measurements are
 * removed to make room, and nothing new is ever refused.
 */
const session = useSessionStore()

/** What is typed in, as text so a half-typed number is not a surprise. */
interface Typed {
  managed: boolean
  keepForever: boolean
  days: string
  limited: boolean
  quota: string
}

const kept = ref<RetentionSettings | null>(null)
const draft = ref<Typed | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)
const saving = ref(false)
const saved = ref(false)
const failure = ref<string | null>(null)

function typedOf(settings: RetentionSettings): Typed {
  return {
    managed: settings.managed,
    keepForever: settings.keep_forever,
    days: settings.days.toString(),
    limited: settings.quota_gb !== null,
    quota: (settings.quota_gb ?? 10).toString(),
  }
}

const whole = /^\d+$/

const daysProblem = computed(() => {
  const { min_days: min, max_days: max } = kept.value as RetentionSettings
  const text = (draft.value as Typed).days
  return whole.test(text) && Number(text) >= min && Number(text) <= max
    ? null
    : `Enter a whole number of days from ${min.toString()} to ${max.toString()}.`
})
const quotaProblem = computed(() => {
  const { min_quota_gb: min, max_quota_gb: max } = kept.value as RetentionSettings
  const text = (draft.value as Typed).quota
  return whole.test(text) && Number(text) >= min && Number(text) <= max
    ? null
    : `Enter a whole number of gigabytes from ${min.toString()} to ${max.toString()}.`
})

/** What would be saved, or null while a number that matters is not a number. */
const wanted = computed<RetentionDraft | null>(() => {
  const now = draft.value as Typed
  const days =
    daysProblem.value === null ? Number(now.days) : (kept.value as RetentionSettings).days
  const withTime = now.managed && !now.keepForever
  if (withTime && daysProblem.value !== null) return null
  if (withTime && now.limited && quotaProblem.value !== null) return null
  return {
    managed: now.managed,
    keep_forever: now.keepForever,
    days,
    quota_gb: withTime && now.limited ? Number(now.quota) : null,
  }
})

const changed = computed(() => {
  const was = kept.value as RetentionSettings
  const now = wanted.value
  return (
    now === null ||
    was.managed !== now.managed ||
    was.keep_forever !== now.keep_forever ||
    was.days !== now.days ||
    was.quota_gb !== now.quota_gb
  )
})

const period = computed(() => {
  const { built_in: periods } = kept.value as RetentionSettings
  return [
    ['Events', periods.events],
    ['Measurements', periods.metrics],
    ['API log', periods.api_log],
    ['AI requests', periods.ai_log],
    ['Alert deliveries', periods.alert_log],
    ['Activity', periods.audit],
  ] as const
})

const share = computed(() => {
  const { usage } = kept.value as RetentionSettings
  if (usage.quota_bytes === null) return null
  return Math.min(100, Math.round((usage.database_bytes / usage.quota_bytes) * 100))
})

async function load() {
  loading.value = true
  loadError.value = null
  try {
    const found = await session.call(fetchRetentionSettings)
    kept.value = found
    draft.value = typedOf(found)
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

async function save() {
  const asked = wanted.value as RetentionDraft
  saving.value = true
  failure.value = null
  try {
    const found = await session.change((token) => saveRetentionSettings(asked, token))
    kept.value = found
    draft.value = typedOf(found)
    saved.value = true
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    saving.value = false
  }
}

function discard() {
  draft.value = typedOf(kept.value as RetentionSettings)
  saved.value = false
}

onMounted(load)
</script>

<template>
  <LoadError
    v-if="loadError && !kept"
    :message="loadError"
    :loading="loading"
    data-test="retention-settings-error"
    @retry="load"
  />
  <v-skeleton-loader
    v-else-if="!kept || !draft"
    type="card, card"
    data-test="retention-settings-loading"
  />
  <template v-else>
    <SectionCard
      title="Manage retention here"
      description="Off, which is how it starts, leaves each kind of data kept for the time its own setting gives. On, what you choose below is used instead."
      data-test="retention-manage-card"
    >
      <v-switch
        v-model="draft.managed"
        label="Manage how long data is kept"
        color="primary"
        density="comfortable"
        hide-details
        data-test="retention-managed"
        @update:model-value="saved = false"
      />
      <template v-if="!draft.managed">
        <p class="note text-body-medium text-medium-emphasis" data-test="retention-built-in">
          Kept as it is now:
          <template v-for="([name, days], index) in period" :key="name">
            {{ name }} {{ formatDays(days) }}{{ index < period.length - 1 ? ', ' : '.' }}
          </template>
        </p>
      </template>
    </SectionCard>

    <template v-if="draft.managed">
      <SectionCard
        title="How long to keep data"
        description="Events and measurements from your integrations, the API log, the record of AI requests and of alerts sent."
        data-test="retention-time-card"
      >
        <v-radio-group
          v-model="draft.keepForever"
          hide-details
          color="primary"
          aria-label="How long to keep data"
          data-test="retention-mode"
          @update:model-value="saved = false"
        >
          <v-radio :value="false" data-test="retention-mode-time">
            <template #label>
              <span class="mode">
                <span class="text-title-medium">Keep it for a number of days</span>
                <span class="text-body-medium text-medium-emphasis">
                  Older data is removed every few hours. The default is
                  {{ formatDays(kept.default_days) }}.
                </span>
              </span>
            </template>
          </v-radio>
          <v-radio :value="true" data-test="retention-mode-forever">
            <template #label>
              <span class="mode">
                <span class="text-title-medium">Keep everything forever</span>
                <span class="text-body-medium text-medium-emphasis">
                  Nothing is removed because of its age or the size of the database. It takes more
                  room the longer AresGate runs.
                </span>
              </span>
            </template>
          </v-radio>
        </v-radio-group>

        <v-text-field
          v-if="!draft.keepForever"
          v-model="draft.days"
          label="Days"
          type="number"
          inputmode="numeric"
          :min="kept.min_days"
          :max="kept.max_days"
          step="1"
          :error-messages="daysProblem ?? undefined"
          class="field"
          data-test="retention-days"
          @update:model-value="saved = false"
        />
        <p
          v-if="!draft.keepForever"
          class="text-body-medium text-medium-emphasis"
          data-test="retention-own"
        >
          An integration you gave its own time on the Data page keeps that time. Activity, the
          record of what was done in AresGate, is kept for {{ formatDays(kept.built_in.audit) }}
          whatever you choose here.
        </p>
      </SectionCard>

      <SectionCard
        v-if="!draft.keepForever"
        title="Size of the database"
        description="A limit on how big the database may get. Past it, the oldest weeks of events and measurements are removed to make room, and new data is always kept."
        data-test="retention-quota-card"
      >
        <v-switch
          v-model="draft.limited"
          label="Limit the size of the database"
          color="primary"
          density="comfortable"
          hide-details
          data-test="retention-limited"
          @update:model-value="saved = false"
        />
        <v-text-field
          v-if="draft.limited"
          v-model="draft.quota"
          label="Gigabytes"
          type="number"
          inputmode="numeric"
          :min="kept.min_quota_gb"
          :max="kept.max_quota_gb"
          step="1"
          :error-messages="quotaProblem ?? undefined"
          class="field"
          data-test="retention-quota"
          @update:model-value="saved = false"
        />
        <p class="note text-body-medium text-medium-emphasis">
          The week being collected is never removed, so the limit has to be larger than about a week
          of your data and everything else AresGate keeps. It is checked every fifteen minutes.
        </p>
      </SectionCard>
    </template>

    <v-alert
      v-if="failure"
      type="error"
      variant="tonal"
      role="alert"
      data-test="retention-save-failure"
    >
      {{ failure }}
    </v-alert>
    <div class="actions">
      <v-btn
        color="primary"
        :loading="saving"
        :disabled="!changed || wanted === null || saving"
        data-test="retention-save"
        @click="save"
      >
        Save
      </v-btn>
      <v-btn
        variant="text"
        :disabled="!changed || saving"
        data-test="retention-discard"
        @click="discard"
      >
        Discard changes
      </v-btn>
      <output v-if="saved && !changed" class="text-body-large" data-test="retention-saved"
        >Saved.</output
      >
    </div>
    <p class="text-body-medium text-medium-emphasis">
      What is past its time, or over the limit, is removed at the next clean-up. Removing it cannot
      be undone.
    </p>

    <SectionCard
      title="What the database holds"
      description="How much disk AresGate's database uses now."
      data-test="retention-usage-card"
    >
      <p class="text-headline-small" data-test="retention-usage-total">
        {{ formatBytes(kept.usage.database_bytes) }}
      </p>
      <v-progress-linear
        v-if="share !== null"
        :model-value="share"
        :color="kept.usage.over_quota ? 'error' : 'primary'"
        height="8"
        rounded
        aria-label="How much of the limit the database uses"
        data-test="retention-usage-bar"
      />
      <p
        v-if="kept.usage.quota_bytes !== null"
        class="text-body-medium"
        data-test="retention-limit"
      >
        {{ share }}% of the {{ formatBytes(kept.usage.quota_bytes) }} limit.
      </p>
      <v-alert
        v-if="kept.usage.over_quota"
        type="warning"
        variant="tonal"
        role="alert"
        data-test="retention-over"
      >
        The database is over its limit and nothing more can be removed: only the week being
        collected is left. Raise the limit, or remove other data.
      </v-alert>
      <dl class="usage text-body-medium">
        <dt>Events</dt>
        <dd data-test="retention-usage-events">{{ formatBytes(kept.usage.events_bytes) }}</dd>
        <dt>Measurements</dt>
        <dd data-test="retention-usage-metrics">{{ formatBytes(kept.usage.metrics_bytes) }}</dd>
        <dt>Oldest event</dt>
        <dd data-test="retention-usage-oldest">
          {{ kept.usage.oldest_event_at ? formatAgo(kept.usage.oldest_event_at) : 'None yet' }}
        </dd>
      </dl>
    </SectionCard>
  </template>
</template>

<style scoped>
.mode {
  display: flex;
  flex-direction: column;
  padding: 0.5rem 0;
}

.field {
  max-width: 16rem;
  margin-top: 1rem;
}

.note {
  margin: 0.75rem 0 0;
}

.usage {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1.5rem;
  margin: 1rem 0 0;
}

.usage dd {
  margin: 0;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}
</style>
