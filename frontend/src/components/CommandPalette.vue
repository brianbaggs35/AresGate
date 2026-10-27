<script setup lang="ts">
import { Search } from '@lucide/vue'
import { computed, ref, useId, watch } from 'vue'

import { commandsFor, GROUPS } from '@/commands'
import { useKeyboardReturn } from '@/dialog'
import { formatCount } from '@/format'
import { useThemeStore, type ThemePreference } from '@/stores/theme'

/**
 * Search for a page or an action from the keyboard (Ctrl or ⌘ and K), or from the search button
 * on a phone. Type to narrow the list, press Enter to take the first, or use the arrow keys to
 * move through the rest. Every row is an ordinary link or button, so nothing here needs more than
 * the keyboard already does; the count of what was found is read out as it changes.
 */
const open = defineModel<boolean>({ required: true })

const theme = useThemeStore()
const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)

const search = ref('')
const field = ref<{ focus: () => void } | null>(null)
const list = ref<HTMLElement | null>(null)

const found = computed(() => commandsFor(search.value))
const groups = computed(() =>
  GROUPS.map((group, index) => ({
    group,
    id: `${titleId}-group-${index}`,
    commands: found.value.filter((command) => command.group === group),
  })).filter(({ commands }) => commands.length > 0),
)
const count = computed(() => {
  const total = found.value.length
  return total === 0 ? 'Nothing found' : `${formatCount(total)} found`
})

// Each time it opens, it opens empty.
watch(open, (opening) => {
  if (opening) search.value = ''
})

const rows = () =>
  Array.from((list.value as HTMLElement).querySelectorAll<HTMLElement>('.palette__row'))

/** Down goes from the field into the list, and Enter takes the first thing found. */
function fromField(event: KeyboardEvent) {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    rows()[0]?.focus()
  } else if (event.key === 'Enter') {
    rows()[0]?.click()
  }
}

/** Up and down move through the list, and up from the first goes back to the field. */
function fromRow(event: KeyboardEvent) {
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
  event.preventDefault()
  const all = rows()
  const step = event.key === 'ArrowDown' ? 1 : -1
  const next = all.indexOf(document.activeElement as HTMLElement) + step
  if (next < 0) field.value?.focus()
  else all[next]?.focus()
}

/** Changes the theme, which is the one command that isn't a link. */
function chooseTheme(preference: ThemePreference) {
  theme.setPreference(preference)
  open.value = false
}
</script>

<template>
  <v-dialog
    v-model="open"
    max-width="560"
    :aria-labelledby="titleId"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card class="palette" data-test="palette">
      <h2 :id="titleId" class="palette__hidden">Search AresGate</h2>
      <v-text-field
        ref="field"
        v-model="search"
        label="Search for a page or an action"
        :prepend-inner-icon="Search"
        autofocus
        clearable
        hide-details
        autocomplete="off"
        spellcheck="false"
        data-test="palette-search"
        @keydown="fromField"
      />
      <output class="palette__hidden" data-test="palette-count">{{ count }}</output>
      <div ref="list" class="palette__list" data-test="palette-list">
        <div v-for="{ group, id, commands } in groups" :key="group" class="palette__group">
          <h3 :id="id" class="palette__heading text-label-medium">{{ group }}</h3>
          <ul class="palette__rows" :aria-labelledby="id">
            <li v-for="command in commands" :key="command.id">
              <router-link
                v-if="command.action.kind === 'go'"
                :to="command.action.to"
                class="palette__row"
                :data-test="`command-${command.id}`"
                @click="open = false"
                @keydown="fromRow"
              >
                <component :is="command.icon" :size="18" aria-hidden="true" />
                <span>{{ command.title }}</span>
              </router-link>
              <button
                v-else
                type="button"
                class="palette__row"
                :data-test="`command-${command.id}`"
                @click="chooseTheme(command.action.preference)"
                @keydown="fromRow"
              >
                <component :is="command.icon" :size="18" aria-hidden="true" />
                <span>{{ command.title }}</span>
              </button>
            </li>
          </ul>
        </div>
        <p
          v-if="groups.length === 0"
          class="palette__empty text-body-medium"
          data-test="palette-empty"
        >
          Nothing matches “{{ search.trim() }}”. Try the name of a page.
        </p>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
/* A height that doesn't change with the results, so the box doesn't jump as someone types. */
.palette {
  display: flex;
  flex-direction: column;
  height: min(72vh, 520px);
  padding: 1rem;
  gap: 0.5rem;
}

/* Read out, not shown: the field's label says what to do, and the count follows what is typed. */
.palette__hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.palette__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.palette__group + .palette__group {
  margin-top: 0.5rem;
}

.palette__heading {
  margin: 0;
  padding: 0.5rem 0.75rem 0.25rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.palette__rows {
  margin: 0;
  padding: 0;
  list-style: none;
}

.palette__row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  min-height: 44px;
  padding: 0.5rem 0.75rem;
  border: 0;
  border-radius: 8px;
  background: none;
  color: inherit;
  font: inherit;
  text-align: start;
  text-decoration: none;
  cursor: pointer;
}

.palette__row:hover {
  background: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.palette__row:focus-visible {
  background: rgba(var(--v-theme-primary), 0.12);
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.palette__empty {
  margin: 0;
  padding: 1rem 0.75rem;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
</style>
