<script setup lang="ts">
import { Pencil, Star, Trash2 } from '@lucide/vue'
import { computed, ref, useId } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { errorMessage } from '@/api/client'
import { fetchIntegrations, type IntegrationSummary } from '@/api/integrations'
import type { SavedView, ViewPage } from '@/api/views'
import { programsOf, queryOfRoute, sameQuery } from '@/lists'
import { useSessionStore } from '@/stores/session'
import { useViewsStore } from '@/stores/views'

/**
 * The views kept for a list: the filters and the order it shows now, under a name, so a
 * combination worth having is one tap. A tap uses one, the star makes the page open on it, and a
 * view can be renamed or forgotten. A view that names a program that is no longer connected still
 * opens, and says so.
 */
const props = defineProps<{ list: ViewPage }>()

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const views = useViewsStore()
const headingId = useId()

const name = ref('')
const asDefault = ref(false)
const saving = ref(false)
/** The view being renamed, and what it is being renamed to. */
const renaming = ref<number | null>(null)
const renamed = ref('')
/** The id of the view a change is under way for. */
const busy = ref<number | null>(null)
const notice = ref<string | null>(null)
const failure = ref<string | null>(null)

const items = computed(() => views.of(props.list))
const current = computed(() => queryOfRoute(route.query))
const trimmed = computed(() => name.value.trim())
const replaces = computed(() => items.value.some((view) => view.name === trimmed.value))

void views.load()

function fail(error: unknown) {
  failure.value = errorMessage(error)
}

async function save() {
  saving.value = true
  notice.value = failure.value = null
  try {
    const saved = await views.save(props.list, trimmed.value, current.value, asDefault.value)
    notice.value = `Saved as ${saved.name}.`
    name.value = ''
    asDefault.value = false
  } catch (error) {
    fail(error)
  } finally {
    saving.value = false
  }
}

/** The programs a view is narrowed to that are not connected now, by name. */
async function missing(view: SavedView): Promise<string[]> {
  const programs = programsOf(view.query)
  if (programs.length === 0) return []
  let known: IntegrationSummary[]
  try {
    known = await session.call(() => fetchIntegrations())
  } catch {
    // Not knowing is no reason to say anything.
    return []
  }
  return programs
    .filter((program) => {
      const found = known.find((integration) => integration.key === program)
      return found === undefined || found.status === 'not_connected'
    })
    .map((program) => known.find((integration) => integration.key === program)?.name ?? program)
}

async function use(view: SavedView) {
  notice.value = failure.value = null
  await router.replace({ query: view.query })
  const gone = await missing(view)
  if (gone.length) {
    notice.value = `${view.name} is narrowed to ${gone.join(' and ')}, which ${
      gone.length === 1 ? 'is' : 'are'
    } not connected any more. It opens anyway, and shows what is left.`
  }
}

async function act(view: SavedView, change: () => Promise<void>, done: string) {
  busy.value = view.id
  notice.value = failure.value = null
  try {
    await change()
    notice.value = done
  } catch (error) {
    fail(error)
  } finally {
    busy.value = null
  }
}

function startRenaming(view: SavedView) {
  renaming.value = view.id
  renamed.value = view.name
}

async function rename(view: SavedView) {
  const to = renamed.value.trim()
  if (to !== '' && to !== view.name) {
    await act(view, () => views.rename(view, to), `Renamed to ${to}.`)
  }
  if (failure.value === null) renaming.value = null
}

const toggleDefault = (view: SavedView) =>
  act(
    view,
    () => views.setDefault(view, !view.is_default),
    view.is_default
      ? `${view.name} is no longer the one this page opens on.`
      : `This page now opens on ${view.name}.`,
  )

const forget = (view: SavedView) => act(view, () => views.remove(view), `Forgot ${view.name}.`)
</script>

<template>
  <section class="views" :aria-labelledby="headingId" data-test="list-views">
    <h2 :id="headingId" class="text-title-small">Views</h2>
    <p v-if="!views.loaded && !views.failure" class="text-body-medium text-medium-emphasis">
      Loading…
    </p>
    <ul v-else-if="items.length" class="views__list">
      <li v-for="view in items" :key="view.id" class="views__item" data-test="view">
        <form
          v-if="renaming === view.id"
          class="views__rename"
          data-test="view-rename-form"
          @submit.prevent="rename(view)"
        >
          <v-text-field
            v-model="renamed"
            label="Name"
            maxlength="60"
            density="comfortable"
            hide-details
            autocomplete="off"
            autofocus
            data-test="view-rename"
          />
          <v-btn
            type="submit"
            color="primary"
            :loading="busy === view.id"
            data-test="view-rename-save"
          >
            Save
          </v-btn>
          <v-btn variant="text" data-test="view-rename-cancel" @click="renaming = null">
            Cancel
          </v-btn>
        </form>
        <template v-else>
          <button
            type="button"
            class="views__use"
            :aria-current="sameQuery(view.query, current) ? 'true' : undefined"
            data-test="view-use"
            @click="use(view)"
          >
            <span class="text-body-large">{{ view.name }}</span>
            <v-chip v-if="view.is_default" size="x-small" data-test="view-default"
              >Opens first</v-chip
            >
          </button>
          <v-btn
            icon
            variant="text"
            size="small"
            density="comfortable"
            :aria-label="
              view.is_default ? `Stop opening on ${view.name}` : `Open this page on ${view.name}`
            "
            :aria-pressed="view.is_default"
            :disabled="busy !== null"
            data-test="view-default-toggle"
            @click="toggleDefault(view)"
          >
            <v-icon :icon="Star" :class="{ views__on: view.is_default }" />
          </v-btn>
          <v-btn
            icon
            variant="text"
            size="small"
            density="comfortable"
            :aria-label="`Rename ${view.name}`"
            :disabled="busy !== null"
            data-test="view-rename-start"
            @click="startRenaming(view)"
          >
            <v-icon :icon="Pencil" />
          </v-btn>
          <v-btn
            icon
            variant="text"
            size="small"
            density="comfortable"
            :aria-label="`Forget ${view.name}`"
            :disabled="busy !== null"
            data-test="view-forget"
            @click="forget(view)"
          >
            <v-icon :icon="Trash2" />
          </v-btn>
        </template>
      </li>
    </ul>
    <p
      v-else-if="views.loaded"
      class="text-body-medium text-medium-emphasis"
      data-test="views-none"
    >
      Nothing is saved yet. Set the filters you want, then give them a name here.
    </p>

    <form class="views__form" data-test="view-form" @submit.prevent="save">
      <v-text-field
        v-model="name"
        label="Name this view"
        maxlength="60"
        density="comfortable"
        hide-details
        autocomplete="off"
        data-test="view-name"
      />
      <v-btn
        type="submit"
        color="primary"
        :loading="saving"
        :disabled="!trimmed"
        data-test="view-save"
      >
        {{ replaces ? 'Replace' : 'Save this view' }}
      </v-btn>
      <v-checkbox
        v-model="asDefault"
        label="Open this page on it"
        density="comfortable"
        hide-details
        data-test="view-as-default"
      />
    </form>

    <output class="text-body-medium" data-test="views-notice">{{ notice }}</output>
    <p
      v-if="failure || views.failure"
      class="text-body-medium views__failure"
      role="alert"
      data-test="views-failure"
    >
      {{ failure ?? views.failure }}
    </p>
  </section>
</template>

<style scoped>
.views {
  display: grid;
  gap: 0.5rem;
}

.views h2,
.views p {
  margin: 0;
}

.views__list {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
}

.views__item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.views__use {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
  min-height: 44px;
  padding: 0.5rem;
  border: 0;
  border-radius: 0.5rem;
  background: transparent;
  color: inherit;
  text-align: start;
  cursor: pointer;
  overflow-wrap: anywhere;
}

.views__use:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.views__use:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.views__use[aria-current='true'] {
  font-weight: 600;
  box-shadow: inset 3px 0 0 rgb(var(--v-theme-primary));
}

.views__on {
  fill: currentcolor;
}

.views__rename,
.views__form {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.views__rename .v-input,
.views__form .v-input:first-child {
  flex: 1 1 12rem;
}

.views__failure {
  color: rgb(var(--v-theme-error));
}
</style>
