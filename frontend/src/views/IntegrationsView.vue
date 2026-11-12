<script setup lang="ts">
import { Plug, Search } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchIntegrations, type IntegrationSummary } from '@/api/integrations'
import AppPage from '@/components/AppPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import IntegrationCard from '@/components/IntegrationCard.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import { categoriesOf, narrowIntegrations } from '@/integrations'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()

const integrations = ref<IntegrationSummary[] | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
/** What is typed in the search, and the kind chosen (``ALL`` is every one). */
const ALL = 'all'
/** Clearing a field with its button leaves null in it, not an empty text. */
const query = ref<string | null>('')
const category = ref(ALL)

const isSetUp = ({ status }: IntegrationSummary) => status !== 'not_connected'

const categories = computed(() => categoriesOf(integrations.value ?? []))
const shown = computed(() =>
  narrowIntegrations(
    integrations.value ?? [],
    query.value ?? '',
    category.value === ALL ? '' : category.value,
  ),
)
const narrowed = computed(() => (query.value ?? '').trim() !== '' || category.value !== ALL)

function clearFilters() {
  query.value = ''
  category.value = ALL
}

async function load() {
  loading.value = true
  error.value = null
  try {
    integrations.value = await session.call(fetchIntegrations)
  } catch (loadError) {
    error.value = errorMessage(loadError)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <AppPage>
    <PageHeader
      title="Integrations"
      description="The systems AresGate watches your network through. It only reads from them: it never changes their settings."
    >
      <template v-if="integrations" #actions>
        <p class="text-body-large" data-test="integrations-count">
          {{ integrations.filter(isSetUp).length }} of {{ integrations.length }} set up
        </p>
      </template>
    </PageHeader>

    <LoadError
      v-if="error"
      :message="error"
      :loading="loading"
      retry-test-id="integrations-retry"
      data-test="integrations-error"
      @retry="load"
    />

    <template v-else-if="integrations">
      <v-text-field
        v-model="query"
        type="search"
        label="Search integrations"
        placeholder="Name, what it provides or its kind"
        :prepend-inner-icon="Search"
        clearable
        hide-details
        autocomplete="off"
        spellcheck="false"
        class="integrations__search"
        data-test="integrations-search"
      />

      <div v-if="categories.length" class="integrations__kinds">
        <v-btn-toggle
          v-model="category"
          mandatory
          divided
          density="comfortable"
          variant="outlined"
          color="primary"
          aria-label="Show integrations of the kind"
          data-test="integrations-kinds"
        >
          <v-btn :value="ALL" data-test="kind-all">
            All
            <span class="integrations__count text-medium-emphasis tabular-nums">{{
              integrations.length
            }}</span>
          </v-btn>
          <v-btn
            v-for="kind in categories"
            :key="kind.name"
            :value="kind.name"
            :data-test="`kind-${kind.name}`"
          >
            {{ kind.name }}
            <span class="integrations__count text-medium-emphasis tabular-nums">{{
              kind.count
            }}</span>
          </v-btn>
        </v-btn-toggle>
      </div>

      <v-row v-if="shown.length" data-test="integrations-list">
        <v-col v-for="integration in shown" :key="integration.key" cols="12" md="6">
          <IntegrationCard :integration="integration" />
        </v-col>
      </v-row>

      <EmptyState
        v-else
        title="No integration matches"
        description="Nothing has that in its name or in what it provides. Try fewer words, or show every kind."
        :icon="Plug"
        data-test="integrations-none"
      >
        <v-btn
          v-if="narrowed"
          variant="tonal"
          color="primary"
          data-test="integrations-clear"
          @click="clearFilters"
        >
          Clear the search
        </v-btn>
      </EmptyState>
    </template>

    <v-row v-else data-test="integrations-loading">
      <v-col v-for="placeholder in 4" :key="placeholder" cols="12" md="6">
        <v-skeleton-loader type="card" />
      </v-col>
    </v-row>
  </AppPage>
</template>

<style scoped>
/* Choices that don't fit across a phone scroll sideways rather than wrap into a block. */
.integrations__kinds {
  overflow-x: auto;
  padding-bottom: 0.25rem;
}

@media (max-width: 599.98px) {
  .integrations__kinds {
    mask-image: linear-gradient(to right, #000 calc(100% - 1.5rem), transparent);
    scrollbar-width: none;
  }

  .integrations__kinds > :last-child {
    margin-inline-end: 1.5rem;
  }
}

.integrations__count {
  margin-inline-start: 0.5rem;
}
</style>
