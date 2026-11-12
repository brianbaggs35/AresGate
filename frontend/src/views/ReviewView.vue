<script setup lang="ts">
import { CheckCheck, PartyPopper, Settings } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import {
  agreeWith,
  fetchReview,
  type Decision,
  type ReviewList,
  type ReviewPage,
} from '@/api/review'
import AppPage from '@/components/AppPage.vue'
import ChoiceToggle from '@/components/ChoiceToggle.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import ReviewCard from '@/components/ReviewCard.vue'
import { formatCount } from '@/format'
import { usePolling } from '@/polling'
import { REVIEW_LISTS, agreePercent, standingLine } from '@/review'
import { useReviewStore } from '@/stores/review'
import { useSessionStore } from '@/stores/session'

/**
 * Review: what the AI decided, for the owner to agree or disagree with. An agreed decision
 * counts and a disagreed one doesn't, and what they say, with the reason if they give one, is
 * what the AI is told the next time it decides. How much of it waits here is the owner's choice
 * in Settings > Review, and the page says when the AI has earned enough trust to be left alone.
 */
const PAGE = 20
const MAX = 100
const REFRESH_SECONDS = 60

const session = useSessionStore()
const review = useReviewStore()

const list = ref<ReviewList>('waiting')
const page = ref<ReviewPage | null>(null)
const items = ref<Decision[]>([])
const loadError = ref<string | null>(null)
const loading = ref(false)
const more = ref(false)
const confirming = ref(false)
const agreeing = ref(false)
const failure = ref<string | null>(null)
const notice = ref<string | null>(null)
let latest = 0

// These are read only once the page has loaded: nothing on screen asks for them before.
const loaded = computed(() => page.value as ReviewPage)
const options = computed(() =>
  REVIEW_LISTS.map((each) => ({
    key: each.key,
    label: `${each.label} ${formatCount(loaded.value.counts[each.key])}`,
  })),
)
const empty = computed(
  () => (REVIEW_LISTS.find((each) => each.key === list.value) as { empty: string }).empty,
)
const standing = computed(() => loaded.value.standing)
const percent = computed(() => agreePercent(standing.value))
/** The AI has earned it, and the owner has not yet let it decide alone. */
const offer = computed(() => standing.value.trusted && loaded.value.mode !== 'auto')
const remaining = computed(() => loaded.value.total - items.value.length)

/** Fetches the list. A quiet fetch keeps what is shown, and asks for at least as many as are. */
async function load(quiet = false) {
  const mine = ++latest
  const wanted = list.value
  if (!quiet) loading.value = true
  try {
    const limit = quiet ? Math.min(MAX, Math.max(PAGE, items.value.length)) : PAGE
    const found = await session.call(() => fetchReview(wanted, limit))
    if (mine !== latest) return
    page.value = found
    items.value = found.items
    review.set(found.counts.waiting)
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
    const found = await session.call(() => fetchReview(list.value, PAGE, items.value.length))
    page.value = found
    items.value = [...items.value, ...found.items]
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    more.value = false
  }
}

/** Takes an answered decision out of the list it was in, and asks for the counts again. */
function answered(done: Decision) {
  notice.value = null
  items.value = items.value.filter((each) => each.subject !== done.subject || each.id !== done.id)
  void load(true)
}

async function agreeAll() {
  agreeing.value = true
  failure.value = null
  try {
    const shown = items.value.map(({ subject, id }) => ({ subject, id }))
    const result = await session.change((token) => agreeWith(shown, token))
    confirming.value = false
    notice.value = `You agreed with ${result.agreed.toString()} ${result.agreed === 1 ? 'decision' : 'decisions'}.`
    await load(true)
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    agreeing.value = false
  }
}

watch(list, () => {
  items.value = []
  notice.value = null
  failure.value = null
  void load()
})

onMounted(() => load())
usePolling(() => load(true), REFRESH_SECONDS * 1000)
</script>

<template>
  <AppPage width="regular" class="review">
    <PageHeader
      title="Review"
      description="What the AI decided, for you to agree or disagree with. It learns from what you say."
    >
      <template #actions>
        <v-btn
          variant="tonal"
          :prepend-icon="Settings"
          :to="{ name: 'settings-review' }"
          data-test="review-settings"
        >
          Review settings
        </v-btn>
      </template>
    </PageHeader>

    <LoadError
      v-if="loadError && !page"
      :message="loadError"
      :loading="loading"
      data-test="review-error"
      @retry="load()"
    />
    <v-skeleton-loader v-else-if="!page" type="card, card" data-test="review-loading" />

    <template v-else>
      <v-alert v-if="loadError" type="warning" variant="tonal" data-test="review-stale">
        {{ loadError }} What is shown is from earlier.
      </v-alert>

      <v-card class="trust pa-4 pa-sm-5" data-test="review-standing">
        <div class="trust__row">
          <p class="text-body-large trust__line" data-test="review-standing-line">
            {{ standingLine(standing) }}
          </p>
          <v-btn
            v-if="offer"
            color="primary"
            variant="flat"
            :to="{ name: 'settings-review' }"
            data-test="review-offer"
          >
            Let it decide on its own
          </v-btn>
        </div>
        <v-progress-linear
          v-if="percent !== null"
          :model-value="percent"
          :color="standing.trusted ? 'success' : 'primary'"
          height="8"
          rounded
          :aria-label="`You agree with the AI ${percent.toString()} percent of the time`"
        />
      </v-card>

      <ChoiceToggle v-model="list" :options="options" label="Which decisions" name="review-list" />

      <v-alert
        v-if="failure"
        type="error"
        variant="tonal"
        role="alert"
        data-test="review-action-failure"
      >
        {{ failure }}
      </v-alert>
      <output v-if="notice" class="text-body-large" data-test="review-notice">{{ notice }}</output>

      <div v-if="list === 'waiting' && items.length > 1" class="review__bulk">
        <v-btn
          variant="tonal"
          color="success"
          :prepend-icon="CheckCheck"
          data-test="review-agree-all"
          @click="confirming = true"
        >
          Agree with all {{ items.length }} shown
        </v-btn>
      </div>

      <v-skeleton-loader v-if="loading" type="card, card" data-test="review-reloading" />
      <ul v-else-if="items.length" class="review__list" data-test="review-items">
        <li v-for="item in items" :key="`${item.subject}-${item.id}`">
          <ReviewCard :decision="item" @answered="answered" />
        </li>
      </ul>
      <v-card v-else data-test="review-empty">
        <EmptyState
          :title="list === 'waiting' ? 'All caught up' : 'Nothing here'"
          :description="empty"
          :icon="PartyPopper"
        />
      </v-card>

      <div v-if="remaining > 0 && !loading" class="review__more">
        <v-btn variant="text" :loading="more" data-test="review-more" @click="showMore">
          Show {{ Math.min(PAGE, remaining) }} more ({{ formatCount(remaining) }} left)
        </v-btn>
      </div>
    </template>

    <ConfirmDialog
      v-model="confirming"
      title="Agree with all of them?"
      :confirm-label="`Agree with ${items.length.toString()}`"
      :busy="agreeing"
      @confirm="agreeAll"
    >
      Each of the {{ items.length }} decisions shown will count as the AI made it. You can take any
      of them back afterwards.
    </ConfirmDialog>
  </AppPage>
</template>

<style scoped>
.trust {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.trust__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem 1rem;
}

.trust__line {
  margin: 0;
  flex: 1 1 20rem;
}

.review__list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.review__bulk,
.review__more {
  display: flex;
  justify-content: flex-start;
}
</style>
