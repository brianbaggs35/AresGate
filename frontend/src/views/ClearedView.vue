<script setup lang="ts">
import { Bot, Check, Settings, Undo2 } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import {
  confirmCleared,
  fetchCleared,
  takeBackCleared,
  type ClearedItem,
  type ClearedPage,
  type ClearedPick,
  type ClearedState,
  type ClearedVerdict,
} from '@/api/aiCleared'
import { errorMessage } from '@/api/client'
import { changeVerdict } from '@/api/verdicts'
import AppPage from '@/components/AppPage.vue'
import ChoiceToggle from '@/components/ChoiceToggle.vue'
import ClearedCard from '@/components/ClearedCard.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import { CLEARED_LISTS, countOf } from '@/cleared'
import { formatCount } from '@/format'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'

/**
 * Cleared by the AI: the incidents the AI cleared as false positives, and the ones it suggests
 * clearing, for the owner to look at. Confirming makes a clearing the owner's own word and gives
 * a suggestion as the owner's verdict. Taking back judges the incident again, and tells the AI not
 * to clear that kind of thing again. Many can be done at once.
 */
const PAGE = 20
const MAX = 100
const REFRESH_SECONDS = 60

const session = useSessionStore()
const route = useRoute()

const list = ref<ClearedState>(route.query.state === 'cleared' ? 'cleared' : 'waiting')
const page = ref<ClearedPage | null>(null)
const items = ref<ClearedItem[]>([])
const picked = ref<ReadonlySet<string>>(new Set())
const loadError = ref<string | null>(null)
const loading = ref(false)
const more = ref(false)
const busy = ref(false)
const confirming = ref(false)
const failure = ref<string | null>(null)
const notice = ref<string | null>(null)
let latest = 0

const keyOf = (item: ClearedPick) => `${item.kind}-${item.id.toString()}`

// These are read only once the page has loaded: nothing on screen asks for them before.
const loaded = computed(() => page.value as ClearedPage)
const options = computed(() =>
  CLEARED_LISTS.map((each) => ({
    key: each.key,
    label: `${each.label} ${formatCount(countOf(loaded.value.counts, each.key))}`,
  })),
)
const empty = computed(
  () => (CLEARED_LISTS.find((each) => each.key === list.value) as { empty: string }).empty,
)
const remaining = computed(() => loaded.value.total - items.value.length)
const chosen = computed(() =>
  items.value.filter((each) => picked.value.has(keyOf(each))).map(({ kind, id }) => ({ kind, id })),
)
const allPicked = computed(
  () => items.value.length > 0 && chosen.value.length === items.value.length,
)
const off = computed(() => loaded.value.mode === 'off')

/** Fetches the list. A quiet fetch keeps what is shown, and asks for at least as many as are. */
async function load(quiet = false) {
  const mine = ++latest
  const wanted = list.value
  if (!quiet) loading.value = true
  try {
    const limit = quiet ? Math.min(MAX, Math.max(PAGE, items.value.length)) : PAGE
    const found = await session.call(() => fetchCleared(wanted, limit))
    if (mine !== latest) return
    page.value = found
    items.value = found.items
    const here = new Set(found.items.map(keyOf))
    picked.value = new Set([...picked.value].filter((key) => here.has(key)))
    loadError.value = null
  } catch (error) {
    if (mine !== latest) return
    loadError.value = errorMessage(error)
  } finally {
    if (mine === latest) loading.value = false
  }
}

async function showMore() {
  more.value = true
  try {
    const found = await session.call(() => fetchCleared(list.value, PAGE, items.value.length))
    page.value = found
    items.value = [...items.value, ...found.items]
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    more.value = false
  }
}

function pick(item: ClearedPick, on: boolean) {
  const next = new Set(picked.value)
  if (on) next.add(keyOf(item))
  else next.delete(keyOf(item))
  picked.value = next
}

function pickAll(on: boolean) {
  picked.value = on ? new Set(items.value.map(keyOf)) : new Set()
}

const things = (count: number) => `${count.toString()} ${count === 1 ? 'incident' : 'incidents'}`

/** Does something to some of what is shown, says what came of it and asks again. */
async function act(
  what: string,
  request: () => Promise<{ done: number; skipped: number } | undefined>,
) {
  busy.value = true
  failure.value = null
  notice.value = null
  try {
    const result = await request()
    confirming.value = false
    if (result) {
      const verb = result.skipped === 1 ? 'was' : 'were'
      const gone = result.skipped ? ` ${things(result.skipped)} ${verb} no longer there.` : ''
      notice.value = `${what} ${things(result.done)}.${gone}`
    } else {
      notice.value = `${what} 1 incident.`
    }
    await load(true)
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
  }
}

function confirm(picks: readonly ClearedPick[], verdict?: ClearedVerdict) {
  return act('You confirmed', () =>
    session.change((token) => confirmCleared(picks, token, verdict)),
  )
}

function takeBack(picks: readonly ClearedPick[]) {
  return act('You took back', () => session.change((token) => takeBackCleared(picks, token)))
}

/** Says the other verdict: for a suggestion that is to give it, for a clearing to change it. */
function change(item: ClearedItem, verdict: ClearedVerdict) {
  if (item.kind === 'waiting') return confirm([{ kind: item.kind, id: item.id }], verdict)
  return act('You changed', async () => {
    await session.change((token) => changeVerdict(item.id, { verdict }, token))
    return undefined
  })
}

watch(list, () => {
  items.value = []
  picked.value = new Set()
  notice.value = null
  failure.value = null
  void load()
})

onMounted(() => load())
usePolling(() => load(true), REFRESH_SECONDS * 1000)
</script>

<template>
  <AppPage width="regular" class="cleared-page">
    <PageHeader
      title="Cleared by the AI"
      description="What the AI set aside as a false positive, and what it suggests setting aside. Nothing it clears is hidden from you."
    >
      <template #actions>
        <v-btn
          variant="tonal"
          :prepend-icon="Settings"
          :to="{ name: 'settings-ai' }"
          data-test="cleared-settings"
        >
          Clearing settings
        </v-btn>
      </template>
    </PageHeader>

    <LoadError
      v-if="loadError && !page"
      :message="loadError"
      :loading="loading"
      data-test="cleared-error"
      @retry="load()"
    />
    <v-skeleton-loader v-else-if="!page" type="card, card" data-test="cleared-loading" />

    <template v-else>
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="cleared-stale">
        {{ loadError }} What is shown is from earlier.
      </v-alert>
      <v-alert v-if="off" type="info" variant="tonal" :icon="Bot" data-test="cleared-off">
        The AI is not clearing anything: it is switched off in the clearing settings.
      </v-alert>
      <v-alert
        v-if="loaded.held"
        type="warning"
        variant="tonal"
        :icon="Bot"
        data-test="cleared-held"
      >
        {{ loaded.held }}
      </v-alert>

      <ChoiceToggle v-model="list" :options="options" label="Which list" name="cleared-list" />

      <v-alert v-if="failure" type="error" variant="tonal" role="alert" data-test="cleared-failure">
        {{ failure }}
      </v-alert>
      <output v-if="notice" class="text-body-large" data-test="cleared-notice">{{ notice }}</output>

      <div v-if="items.length" class="cleared-page__bulk" data-test="cleared-bulk">
        <label class="cleared-page__all text-body-large">
          <input
            type="checkbox"
            :checked="allPicked"
            data-test="cleared-pick-all"
            @change="pickAll(($event.target as HTMLInputElement).checked)"
          />
          Select all {{ items.length }} shown
        </label>
        <template v-if="chosen.length">
          <v-btn
            color="primary"
            variant="flat"
            :prepend-icon="Check"
            :disabled="busy"
            data-test="cleared-confirm-picked"
            @click="confirm(chosen)"
          >
            Confirm {{ chosen.length }}
          </v-btn>
          <v-btn
            variant="tonal"
            :prepend-icon="Undo2"
            :disabled="busy"
            data-test="cleared-take-back-picked"
            @click="confirming = true"
          >
            Take back {{ chosen.length }}
          </v-btn>
        </template>
      </div>

      <v-skeleton-loader v-if="loading" type="card, card" data-test="cleared-reloading" />
      <ul v-else-if="items.length" class="cleared-page__list" data-test="cleared-items">
        <li v-for="item in items" :key="keyOf(item)">
          <ClearedCard
            :item="item"
            :selected="picked.has(keyOf(item))"
            :busy="busy"
            @select="pick(item, $event)"
            @confirm="confirm([{ kind: item.kind, id: item.id }])"
            @change="change(item, $event)"
            @take-back="takeBack([{ kind: item.kind, id: item.id }])"
          />
        </li>
      </ul>
      <v-card v-else data-test="cleared-empty">
        <EmptyState
          :title="list === 'waiting' ? 'Nothing is waiting' : 'Nothing to confirm'"
          :description="empty"
          :icon="Bot"
        />
      </v-card>

      <div v-if="remaining > 0 && !loading" class="cleared-page__more">
        <v-btn variant="text" :loading="more" data-test="cleared-more" @click="showMore">
          Show {{ Math.min(PAGE, remaining) }} more ({{ formatCount(remaining) }} left)
        </v-btn>
      </div>
    </template>

    <ConfirmDialog
      v-model="confirming"
      :title="`Take back ${chosen.length.toString()}?`"
      :confirm-label="`Take back ${chosen.length.toString()}`"
      :busy="busy"
      @confirm="takeBack(chosen)"
    >
      What the AI cleared is judged again, and what it suggests is turned down. The AI is told not
      to clear or suggest the same again.
    </ConfirmDialog>
  </AppPage>
</template>

<style scoped>
.cleared-page__list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.cleared-page__bulk {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
}

.cleared-page__all {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.cleared-page__more {
  display: flex;
  justify-content: flex-start;
}
</style>
