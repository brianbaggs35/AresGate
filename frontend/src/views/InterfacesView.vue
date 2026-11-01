<script setup lang="ts">
import { Plus, Radar } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import type { Discovery, Feed, Interface, Role, Stats, Suggestion } from '@/api/interfaces'
import AppPage from '@/components/AppPage.vue'
import FeedRow from '@/components/FeedRow.vue'
import HeroSurface from '@/components/HeroSurface.vue'
import InterfaceCard from '@/components/InterfaceCard.vue'
import InterfaceEditor from '@/components/InterfaceEditor.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import SuggestionCard from '@/components/SuggestionCard.vue'
import UndoNotice from '@/components/UndoNotice.vue'
import { formatCount } from '@/format'
import { useInterfaceBoard, type Done } from '@/interface-board'
import { hero } from '@/interfaces'

/**
 * The parts of the network and the feeds of data that belong to them. It says first how much is
 * left to decide, offers the guesses AresGate has for the owner to confirm, and shows each
 * interface as a card; feeds not placed yet are listed below with a control to place each.
 */
const board = useInterfaceBoard()
const { listing, overview, loading, error, problem, busy } = board

const notice = ref<{ show: (done: Done) => void } | null>(null)
const editing = ref(false)
const editTarget = ref<Interface | null>(null)
const starter = ref<{ name: string; role: Role; feeds: number[] } | null>(null)
const found = ref<Discovery | null>(null)

const said = computed(() => (listing.value ? hero(listing.value) : null))
const full = computed(
  () => (listing.value?.interfaces.length ?? 0) >= (listing.value?.max_interfaces ?? Infinity),
)

const statsOf = (id: number): Stats | undefined =>
  overview.value?.stats.find((item) => item.interface_id === id)

/** The feeds a suggestion names, which are waiting to be placed or were set aside. */
function feedsOf(suggestion: Suggestion): Feed[] {
  const waiting = listing.value ? [...listing.value.unplaced, ...listing.value.ignored] : []
  return waiting.filter((feed) => suggestion.feed_ids.includes(feed.id))
}

function show(done: Done | null) {
  if (done) notice.value?.show(done)
}

function add() {
  editTarget.value = null
  starter.value = null
  editing.value = true
}

/** A new interface that already has a feed on it, for a feed that belongs to none yet. */
function addFor(feed: Feed) {
  editTarget.value = null
  starter.value = {
    name: feed.label || feed.native_name || feed.integration_name,
    role: 'home',
    feeds: [feed.id],
  }
  editing.value = true
}

/** Changing a suggestion is making the interface it would make, with its name and role to edit. */
function change(suggestion: Suggestion) {
  editTarget.value = null
  starter.value = {
    name: suggestion.name,
    role: suggestion.role,
    feeds: suggestion.feed_ids,
  }
  editing.value = true
}

async function find() {
  found.value = await board.find()
}

async function saved(text: string) {
  await board.load()
  show({ text, undo: null })
}

async function undo(done: Done) {
  show(await board.undo(done))
}

onMounted(() => board.load())
</script>

<template>
  <AppPage width="wide">
    <PageHeader
      title="Interfaces"
      description="The parts of your network, such as the internet, your home and your guests. Place what each program reports on the part it belongs to, and AresGate can tell them apart."
    >
      <template v-if="listing" #actions>
        <div class="actions">
          <v-btn
            variant="tonal"
            :prepend-icon="Radar"
            :loading="busy"
            data-test="interfaces-find"
            @click="find"
          >
            Find feeds
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :prepend-icon="Plus"
            :disabled="full"
            data-test="interfaces-add"
            @click="add"
          >
            Add interface
          </v-btn>
        </div>
      </template>
    </PageHeader>

    <LoadError
      v-if="error"
      :message="error"
      :loading="loading"
      retry-test-id="interfaces-retry"
      data-test="interfaces-error"
      @retry="board.load()"
    />

    <template v-else-if="listing && said">
      <HeroSurface
        :tone="said.tone"
        :eyebrow="said.eyebrow"
        :title="said.title"
        :detail="said.detail"
        :level="said.level"
        :mood="said.mood"
        test-id="interfaces-hero"
      />

      <v-alert
        v-if="problem"
        type="error"
        variant="tonal"
        density="compact"
        data-test="interfaces-problem"
      >
        {{ problem }}
      </v-alert>

      <v-alert
        v-if="found"
        :type="found.complete && found.notes.length === 0 ? 'success' : 'info'"
        variant="tonal"
        density="compact"
        closable
        data-test="interfaces-found"
        @click:close="found = null"
      >
        <p class="found__line">
          {{
            found.new === 0
              ? 'Nothing new was found.'
              : `Found ${formatCount(found.new)} new ${found.new === 1 ? 'feed' : 'feeds'}.`
          }}
        </p>
        <p v-if="!found.complete" class="found__line" data-test="interfaces-found-partial">
          Looking through the events took too long, so some may be missing. Try again in a minute.
        </p>
        <p v-for="note in found.notes" :key="note" class="found__line" data-test="interfaces-note">
          {{ note }}
        </p>
      </v-alert>

      <section
        v-if="listing.suggestions.length"
        class="section"
        aria-labelledby="suggestions-title"
        data-test="interfaces-suggestions"
      >
        <header class="section__head">
          <div>
            <h2 id="suggestions-title" class="text-title-large">Needs you</h2>
            <p class="text-body-medium text-medium-emphasis">
              AresGate's guesses from the names. Nothing is placed until you confirm it.
            </p>
          </div>
          <v-btn
            v-if="listing.suggestions.length > 1"
            variant="tonal"
            :disabled="busy"
            data-test="suggestions-confirm-all"
            @click="board.confirmAll(listing.suggestions).then(show)"
          >
            Confirm all {{ listing.suggestions.length }}
          </v-btn>
        </header>
        <ul class="list">
          <li v-for="suggestion in listing.suggestions" :key="suggestion.name">
            <SuggestionCard
              :suggestion="suggestion"
              :feeds="feedsOf(suggestion)"
              :busy="busy"
              @confirm="board.confirm(suggestion).then(show)"
              @change="change(suggestion)"
              @ignore="board.dismiss(suggestion).then(show)"
            />
          </li>
        </ul>
      </section>

      <section
        v-if="listing.interfaces.length"
        class="section"
        aria-labelledby="interfaces-title"
        data-test="interfaces-grid"
      >
        <h2 id="interfaces-title" class="text-title-large">Your interfaces</h2>
        <v-row>
          <v-col v-for="item in listing.interfaces" :key="item.id" cols="12" sm="6" lg="4">
            <InterfaceCard :item="item" :stats="statsOf(item.id)" />
          </v-col>
        </v-row>
      </section>

      <section
        v-if="listing.unplaced.length"
        class="section"
        aria-labelledby="unplaced-title"
        data-test="interfaces-unplaced"
      >
        <header>
          <h2 id="unplaced-title" class="text-title-large">Not placed yet</h2>
          <p class="text-body-medium text-medium-emphasis">
            {{ formatCount(listing.unplaced.length) }}
            {{ listing.unplaced.length === 1 ? 'feed has' : 'feeds have' }} not been placed on an
            interface, so what they report is not told apart by where it came in.
          </p>
        </header>
        <v-card class="rows">
          <FeedRow
            v-for="feed in listing.unplaced"
            :key="feed.id"
            :feed="feed"
            :interfaces="listing.interfaces"
            :disabled="busy"
            @move="board.move(feed, $event).then(show)"
            @create="addFor(feed)"
          />
        </v-card>
      </section>

      <section
        v-if="listing.ignored.length"
        class="section"
        aria-labelledby="ignored-title"
        data-test="interfaces-ignored"
      >
        <v-expansion-panels variant="accordion">
          <v-expansion-panel>
            <v-expansion-panel-title>
              <h2 id="ignored-title" class="text-title-medium">
                Set aside ({{ formatCount(listing.ignored.length) }})
              </h2>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <p class="text-body-medium text-medium-emphasis">
                Left out of everything. Place one on an interface to bring it back.
              </p>
              <FeedRow
                v-for="feed in listing.ignored"
                :key="feed.id"
                :feed="feed"
                :interfaces="listing.interfaces"
                :disabled="busy"
                @move="board.move(feed, $event).then(show)"
                @create="addFor(feed)"
              />
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </section>
    </template>

    <v-skeleton-loader v-else type="card, card" data-test="interfaces-loading" />

    <InterfaceEditor
      v-model="editing"
      :interface="editTarget"
      :starter="starter"
      @saved="saved"
      @removed="saved"
    />
    <UndoNotice ref="notice" @undo="undo" />
  </AppPage>
</template>

<style scoped>
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.section h2,
.section p {
  margin: 0;
}

.section__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.5rem 1rem;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.rows {
  padding: 0.25rem 1.25rem;
}

.rows > :deep(.feed + .feed) {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.found__line {
  margin: 0;
}
</style>
