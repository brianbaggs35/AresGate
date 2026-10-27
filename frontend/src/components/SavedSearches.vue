<script setup lang="ts">
import { Trash2 } from '@lucide/vue'
import { computed, onMounted, ref, useId } from 'vue'

import { errorMessage } from '@/api/client'
import {
  deleteSavedSearch,
  fetchSavedSearches,
  saveSearch,
  type SavedSearch,
  type SearchScope,
} from '@/api/searches'
import { useSessionStore } from '@/stores/session'

/**
 * The searches kept under a name for a page, in the panel of its search box: a tap uses one, a
 * button forgets it, and what is in the box can be given a name and kept. Saving under a name
 * that is taken changes that search, so the button says so.
 */
const props = defineProps<{
  scope: SearchScope
  /** What is in the box, which is what would be saved. */
  current: string
  /** Whether it can be saved: it is something, and the API understood it. */
  savable: boolean
}>()
const emit = defineEmits<{ use: [query: string] }>()

const session = useSessionStore()
const headingId = useId()

const items = ref<SavedSearch[]>([])
const loading = ref(true)
const name = ref('')
const saving = ref(false)
/** The id of the one being forgotten. */
const forgetting = ref<number | null>(null)
const notice = ref<string | null>(null)
const failure = ref<string | null>(null)

const trimmed = computed(() => name.value.trim())
const replaces = computed(() => items.value.some((item) => item.name === trimmed.value))

onMounted(async () => {
  try {
    items.value = await fetchSavedSearches(props.scope)
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  notice.value = null
  failure.value = null
  try {
    const saved = await session.change((token) =>
      saveSearch(props.scope, trimmed.value, props.current, token),
    )
    items.value = [...items.value.filter((item) => item.id !== saved.id), saved].sort(byName)
    notice.value = `Saved as ${saved.name}.`
    name.value = ''
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    saving.value = false
  }
}

async function forget(item: SavedSearch) {
  forgetting.value = item.id
  notice.value = null
  failure.value = null
  try {
    await session.change((token) => deleteSavedSearch(item.id, token))
    items.value = items.value.filter((other) => other.id !== item.id)
    notice.value = `Forgot ${item.name}.`
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    forgetting.value = null
  }
}

/** By name, whatever the case, as the API lists them. */
function byName(a: SavedSearch, b: SavedSearch): number {
  return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }) || a.id - b.id
}
</script>

<template>
  <section class="saved" :aria-labelledby="headingId" data-test="saved-searches">
    <h2 :id="headingId" class="text-title-small">Saved searches</h2>
    <p v-if="loading" class="text-body-medium text-medium-emphasis" data-test="saved-loading">
      Loading…
    </p>
    <ul v-else-if="items.length" class="saved__list">
      <li v-for="item in items" :key="item.id" class="saved__item">
        <button
          type="button"
          class="saved__use"
          data-test="saved-use"
          @click="emit('use', item.query)"
        >
          <span class="text-body-large">{{ item.name }}</span>
          <code>{{ item.query }}</code>
        </button>
        <v-btn
          icon
          variant="text"
          size="small"
          density="comfortable"
          :aria-label="`Forget ${item.name}`"
          :loading="forgetting === item.id"
          :disabled="forgetting !== null"
          data-test="saved-forget"
          @click="forget(item)"
        >
          <v-icon :icon="Trash2" />
        </v-btn>
      </li>
    </ul>
    <p v-else-if="!failure" class="text-body-medium text-medium-emphasis" data-test="saved-none">
      Nothing is saved yet. Search for something, then give it a name here.
    </p>

    <form v-if="savable" class="saved__form" data-test="saved-form" @submit.prevent="save">
      <v-text-field
        v-model="name"
        label="Name this search"
        maxlength="60"
        density="comfortable"
        hide-details
        autocomplete="off"
        data-test="saved-name"
      />
      <v-btn
        type="submit"
        color="primary"
        :loading="saving"
        :disabled="!trimmed"
        data-test="saved-save"
      >
        {{ replaces ? 'Replace' : 'Save' }}
      </v-btn>
    </form>

    <output class="text-body-medium" data-test="saved-notice">{{ notice }}</output>
    <p
      v-if="failure"
      class="text-body-medium saved__failure"
      role="alert"
      data-test="saved-failure"
    >
      {{ failure }}
    </p>
  </section>
</template>

<style scoped>
.saved {
  display: grid;
  gap: 0.5rem;
}

.saved h2,
.saved p {
  margin: 0;
}

.saved__list {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
}

.saved__item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.saved__use {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.125rem;
  min-width: 0;
  min-height: 44px;
  padding: 0.5rem;
  border: 0;
  border-radius: 0.5rem;
  background: transparent;
  color: inherit;
  text-align: start;
  cursor: pointer;
}

.saved__use:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.saved__use:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.saved__use code {
  max-width: 100%;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}

.saved__form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.saved__form .v-input {
  flex: 1 1 12rem;
}

.saved__failure {
  color: rgb(var(--v-theme-error));
}

/* What is tapped is as big as a thumb. */
@media (pointer: coarse) {
  .saved__item .v-btn,
  .saved__form .v-btn {
    min-width: 44px;
    min-height: 44px;
  }
}

/* An empty note takes no room. */
output:empty {
  display: none;
}
</style>
