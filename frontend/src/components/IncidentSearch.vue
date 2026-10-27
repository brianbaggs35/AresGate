<script setup lang="ts">
import { CircleHelp, Search, X } from '@lucide/vue'
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'

import type { SearchTerm } from '@/api/incidents'
import { SEARCH_EXAMPLES, forget, readRecent, remember, without } from '@/search'

/** How long after the last key the search is applied, so typing a term is not searching for it
 * letter by letter. */
const PAUSE = 400

/**
 * The search box for the incidents: a text field, the terms of what was typed shown back as
 * chips that each come off with one tap, and a panel of ways to search and the searches made
 * before. The text is the applied search (it lives in the address of the page); what is typed is
 * applied after a pause, or at once with Enter, and the chips are the API's reading of it.
 */
const props = defineProps<{
  /** The search that is applied. */
  modelValue: string
  /** How the API understood it. */
  terms: readonly SearchTerm[]
  /** Why it could not be understood, in words. */
  error: string | null
}>()
const emit = defineEmits<{ 'update:modelValue': [text: string] }>()

const typed = ref(props.modelValue)
const recent = ref(readRecent())
const help = ref(false)
const helpId = useId()
const field = ref<{ focus: () => void } | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined

// A search that arrives from outside (the back button, a link) is what is in the box.
watch(
  () => props.modelValue,
  (text) => {
    if (text !== typed.value.trim()) typed.value = text
  },
)

function apply(text: string) {
  clearTimeout(timer)
  timer = undefined
  if (text.trim() !== props.modelValue) emit('update:modelValue', text.trim())
}

function type(text: string | null) {
  typed.value = text ?? ''
  clearTimeout(timer)
  timer = setTimeout(() => {
    apply(typed.value)
  }, PAUSE)
}

/** The search is done with: apply it, and keep it for next time. */
function commit() {
  apply(typed.value)
  if (typed.value.trim()) recent.value = remember(typed.value)
}

function clear() {
  typed.value = ''
  apply('')
}

function use(text: string) {
  typed.value = text
  help.value = false
  commit()
}

/** An example goes after what is there, for the person to finish. */
function add(text: string) {
  typed.value = typed.value.trim() ? `${typed.value.trim()} ${text}` : text
  field.value?.focus()
  type(typed.value)
}

function drop(term: SearchTerm) {
  const text = without(props.modelValue, term)
  typed.value = text
  apply(text)
}

function forgetAll() {
  forget()
  recent.value = []
}

function onEscape() {
  help.value = false
}

const chips = computed(() =>
  props.terms.map((term, index) => ({ ...term, key: `${index.toString()}-${term.label}` })),
)

onBeforeUnmount(() => {
  clearTimeout(timer)
})

defineExpose({ focus: () => field.value?.focus() })
</script>

<template>
  <div class="search" role="search" aria-label="Search incidents" @keydown.esc="onEscape">
    <v-text-field
      ref="field"
      :model-value="typed"
      label="Search incidents"
      placeholder="severity>=high source:wazuh -port:22 ssh"
      :prepend-inner-icon="Search"
      clearable
      :error-messages="error ?? undefined"
      hide-details="auto"
      autocomplete="off"
      autocapitalize="off"
      spellcheck="false"
      enterkeyhint="search"
      data-test="search"
      @update:model-value="type"
      @keydown.enter="commit"
      @blur="commit"
      @click:clear="clear"
    >
      <template #append-inner>
        <kbd v-if="!typed" class="search__key" aria-hidden="true" data-test="search-key">/</kbd>
        <v-btn
          icon
          variant="text"
          size="small"
          density="comfortable"
          :aria-expanded="help"
          :aria-controls="helpId"
          aria-label="How to search, and recent searches"
          data-test="search-help"
          @click="help = !help"
        >
          <v-icon :icon="CircleHelp" />
        </v-btn>
      </template>
    </v-text-field>

    <section v-if="help" :id="helpId" class="search__help" data-test="search-panel">
      <div v-if="recent.length" class="search__recent">
        <div class="search__heading">
          <h2 class="text-title-small">Recent searches</h2>
          <v-btn variant="text" size="small" data-test="search-forget" @click="forgetAll">
            Clear
          </v-btn>
        </div>
        <ul class="search__list">
          <li v-for="text in recent" :key="text">
            <button type="button" class="search__row" data-test="search-recent" @click="use(text)">
              <code>{{ text }}</code>
            </button>
          </li>
        </ul>
      </div>
      <div>
        <h2 class="text-title-small">Ways to search</h2>
        <p class="text-body-medium text-medium-emphasis">
          Everything you type has to be true. Tap one to add it.
        </p>
        <ul class="search__list search__list--examples">
          <li v-for="example in SEARCH_EXAMPLES" :key="example.text">
            <button
              type="button"
              class="search__row search__row--example"
              data-test="search-example"
              @click="add(example.text)"
            >
              <code>{{ example.text }}</code>
              <span class="text-body-medium text-medium-emphasis">{{ example.meaning }}</span>
            </button>
          </li>
        </ul>
      </div>
    </section>

    <ul v-if="chips.length" class="search__terms" aria-label="What the search means">
      <li v-for="chip in chips" :key="chip.key">
        <button
          type="button"
          class="search__term"
          :class="{ 'search__term--not': chip.negated }"
          :aria-label="`Remove ${chip.label}`"
          data-test="search-term"
          @click="drop(chip)"
        >
          <span>{{ chip.label }}</span>
          <v-icon :icon="X" size="16" aria-hidden="true" />
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.search {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.search__key {
  display: inline-grid;
  place-items: center;
  min-width: 1.5rem;
  height: 1.5rem;
  margin-inline-end: 0.25rem;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 0.375rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font: inherit;
  font-size: 0.8125rem;
}

/* A hint about a key is no use where there is no keyboard. */
@media (pointer: coarse) {
  .search__key {
    display: none;
  }
}

.search__help {
  display: grid;
  gap: 1rem 2rem;
  max-height: 22rem;
  padding: 0.75rem 1rem 1rem;
  overflow-y: auto;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 0.75rem;
  background: rgb(var(--v-theme-surface));
}

.search__help h2 {
  margin: 0;
}

.search__help p {
  margin: 0.125rem 0 0.5rem;
}

.search__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.search__list {
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
}

.search__row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.125rem;
  width: 100%;
  min-height: 44px;
  padding: 0.5rem 0.5rem;
  border: 0;
  border-radius: 0.5rem;
  background: transparent;
  color: inherit;
  text-align: start;
  cursor: pointer;
}

.search__row:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.search__row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.search__row code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.875rem;
  overflow-wrap: anywhere;
}

.search__term {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  max-width: 100%;
  min-height: 36px;
  padding: 0 0.75rem;
  border-radius: 999px;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.875rem;
  cursor: pointer;
}

.search__term span {
  overflow-wrap: anywhere;
  text-align: start;
}

.search__term:hover {
  background: rgba(var(--v-theme-primary), 0.2);
}

.search__term:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

/* A term that turns the others around is told apart by more than its color: it says "Not". */
.search__term--not {
  background: rgba(var(--v-theme-warning), 0.16);
}

@media (pointer: coarse) {
  .search__term {
    min-height: 44px;
  }
}

.search__terms {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

@media (min-width: 720px) {
  .search__help {
    grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
  }

  .search__help:not(:has(.search__recent)) {
    grid-template-columns: minmax(0, 1fr);
  }

  .search__list--examples {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    column-gap: 1rem;
  }
}
</style>
