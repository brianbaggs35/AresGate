<script setup lang="ts">
import { Pencil, RefreshCw } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import {
  fetchStorage,
  setRetention,
  type Storage,
  type StorageKind,
  type StorageSource,
} from '@/api/storage'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import LoadError from '@/components/LoadError.vue'
import RetentionDialog from '@/components/RetentionDialog.vue'
import SectionCard from '@/components/SectionCard.vue'
import { formatAgo, formatCount, formatDateTime, formatDays } from '@/format'
import { useSessionStore } from '@/stores/session'

const props = defineProps<{ kind: StorageKind }>()

/** What each kind of data is called, and what it is. */
const KINDS: Record<StorageKind, { title: string; noun: string; singular: string; about: string }> =
  {
    events: {
      title: 'Events',
      noun: 'events',
      singular: 'event',
      about: 'What happened: firewall log lines, intrusion alerts and the like.',
    },
    metrics: {
      title: 'Measurements',
      noun: 'readings',
      singular: 'reading',
      about:
        "What was measured: a firewall's load, memory and disk, and the traffic of each interface.",
    },
  }
const DAY = 86_400_000

const session = useSessionStore()
const words = computed(() => KINDS[props.kind])

const storage = ref<Storage | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)

const notice = ref<string | null>(null)
const failure = ref<string | null>(null)
const busy = ref(false)
/** The integration being asked about, and what it was asked to keep for. The dialogs keep
 * showing it while they fade out, so it is left as it was when they close. */
const target = ref<StorageSource | null>(null)
const pendingDays = ref<number | null>(null)
/** What the question about removing says, made when it is asked. */
const warning = ref('')
const choosing = ref(false)
const confirming = ref(false)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    storage.value = await session.call(() => fetchStorage(props.kind))
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

const keptFor = (source: StorageSource) =>
  `Kept for ${formatDays(source.effective_days)}${source.days === null ? ' (the default)' : ''}`

function holds(source: StorageSource): string {
  if (source.count === 0 || source.oldest_at === null) return `No ${words.value.noun} stored`
  const count = `${formatCount(source.count)} ${source.count === 1 ? words.value.singular : words.value.noun}`
  return `${count} · the oldest ${formatAgo(source.oldest_at)}`
}

/** Whether keeping this one's data for this many days removes some that is stored. */
function removes(source: StorageSource, days: number): boolean {
  if (source.count === 0 || source.oldest_at === null) return false
  return Date.now() - new Date(source.oldest_at).getTime() > days * DAY
}

function choose(source: StorageSource) {
  target.value = source
  notice.value = null
  failure.value = null
  choosing.value = true
}

/** What was chosen: kept as it is if that is no change, set after asking if it removes what is
 * stored, and set at once if not. */
async function answer(days: number | null) {
  const source = target.value as StorageSource
  const effective = days ?? (storage.value as Storage).default_days
  if (days === source.days) {
    choosing.value = false
  } else if (removes(source, effective)) {
    pendingDays.value = days
    warning.value = `Some of ${source.name}'s ${words.value.noun} are older than ${formatDays(effective)}, back to ${formatDateTime(source.oldest_at as string)}. They are removed at the next clean-up, within a few hours, and can't be brought back.`
    choosing.value = false
    confirming.value = true
  } else {
    await apply(days)
  }
}

async function apply(days: number | null) {
  const source = target.value as StorageSource
  busy.value = true
  notice.value = null
  failure.value = null
  try {
    const changed = await session.change((token) =>
      setRetention(props.kind, source.source, days, token),
    )
    const list = storage.value as Storage
    list.sources = list.sources.map((item) => (item.source === changed.source ? changed : item))
    notice.value = `${source.name} keeps its ${words.value.noun} for ${formatDays(changed.effective_days)}${days === null ? ' (the default)' : ''}.`
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
    choosing.value = false
    confirming.value = false
  }
}

onMounted(load)
</script>

<template>
  <SectionCard
    :title="words.title"
    :description="`${words.about} Each integration keeps them for ${formatDays(storage?.default_days ?? 0)} unless you choose another time, and anything older is removed every few hours.`"
    :data-test="`${kind}-retention-card`"
  >
    <template #actions>
      <v-btn
        variant="text"
        :prepend-icon="RefreshCw"
        :loading="loading"
        :data-test="`${kind}-refresh`"
        @click="load"
      >
        Refresh
      </v-btn>
    </template>

    <v-alert v-if="notice" type="success" variant="tonal" class="mb-4" data-test="retention-notice">
      {{ notice }}
    </v-alert>
    <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" data-test="retention-failure">
      {{ failure }}
    </v-alert>

    <LoadError
      v-if="loadError"
      :message="loadError"
      :loading="loading"
      :retry-test-id="`${kind}-retry`"
      data-test="retention-error"
      @retry="load"
    />
    <v-skeleton-loader v-else-if="!storage" type="list-item-two-line, list-item-two-line" />
    <ul v-else class="sources" data-test="retention-list">
      <li
        v-for="source in storage.sources"
        :key="source.source"
        class="sources__item"
        data-test="retention-source"
      >
        <div class="sources__text">
          <div class="text-body-large" data-test="retention-name">{{ source.name }}</div>
          <div class="text-body-medium text-medium-emphasis" data-test="retention-holds">
            {{ holds(source) }}
          </div>
          <div class="text-body-medium text-medium-emphasis" data-test="retention-kept">
            {{ keptFor(source) }}
          </div>
        </div>
        <v-btn
          variant="text"
          :prepend-icon="Pencil"
          :disabled="busy"
          :aria-label="`Change how long ${source.name}'s ${words.noun} are kept`"
          data-test="retention-change"
          @click="choose(source)"
        >
          Change
        </v-btn>
      </li>
    </ul>
  </SectionCard>

  <RetentionDialog
    v-model="choosing"
    :title="`How long to keep ${target?.name ?? ''}'s ${words.noun}`"
    :noun="words.noun"
    :default-days="storage?.default_days ?? 0"
    :days="target?.days ?? null"
    :busy="busy"
    @save="answer"
  />
  <ConfirmDialog
    v-model="confirming"
    :title="`Remove older ${words.noun}?`"
    confirm-label="Keep for less time"
    destructive
    :busy="busy"
    @confirm="apply(pendingDays)"
  >
    {{ warning }}
  </ConfirmDialog>
</template>

<style scoped>
.sources {
  list-style: none;
  margin: 0;
  padding: 0;
}

.sources__item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0;
}

.sources__item + .sources__item {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.sources__text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
