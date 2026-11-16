<script setup lang="ts">
import { X } from '@lucide/vue'
import { useId } from 'vue'

import { useKeyboardReturn } from '@/dialog'
import { SHORTCUTS } from '@/shortcuts'

/** The keys the app answers to, grouped by where they work. Opened with the ? key. */
const open = defineModel<boolean>({ required: true })

const giveBackTheKeyboard = useKeyboardReturn(open)
const titleId = useId()

const pages = [...new Set(SHORTCUTS.map(({ page }) => page))]
const on = (page: string) => SHORTCUTS.filter((shortcut) => shortcut.page === page)
</script>

<template>
  <v-dialog
    v-model="open"
    max-width="32rem"
    scrollable
    :aria-labelledby="titleId"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card data-test="shortcuts">
      <header class="shortcuts__head">
        <h2 :id="titleId" class="text-title-large">Keyboard shortcuts</h2>
        <v-btn
          icon
          variant="text"
          size="small"
          aria-label="Close"
          data-test="shortcuts-close"
          @click="open = false"
        >
          <v-icon :icon="X" />
        </v-btn>
      </header>
      <div class="shortcuts__body">
        <section v-for="page in pages" :key="page" :data-test="`shortcuts-${page.toLowerCase()}`">
          <h3 class="text-title-small">{{ page }}</h3>
          <dl class="shortcuts__list">
            <template v-for="shortcut in on(page)" :key="shortcut.does">
              <dt class="shortcuts__keys">
                <kbd v-for="key in shortcut.keys" :key="key" class="shortcuts__key">{{ key }}</kbd>
              </dt>
              <dd class="text-body-medium">{{ shortcut.does }}</dd>
            </template>
          </dl>
        </section>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.shortcuts__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem 0.5rem;
}

.shortcuts__body {
  display: grid;
  gap: 1.25rem;
  padding: 0.5rem 1.25rem 1.5rem;
  overflow-y: auto;
}

.shortcuts__list {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 0.5rem 1rem;
  align-items: center;
  margin: 0.5rem 0 0;
}

.shortcuts__keys {
  display: flex;
  gap: 0.25rem;
}

.shortcuts__key {
  min-width: 1.75rem;
  padding: 0.125rem 0.5rem;
  border: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 0.375rem;
  background: rgb(var(--v-theme-surface-variant), 0.4);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8125rem;
  text-align: center;
}
</style>
