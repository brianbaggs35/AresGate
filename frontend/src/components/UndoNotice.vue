<script setup lang="ts">
import { ref } from 'vue'

import type { Done } from '@/interface-board'

/**
 * What a page says when it changed something that can be taken back: what was done, with *Undo*
 * for a while. Whoever shows it calls `show` with what the change said, and is told with `undo`
 * when the owner asks to take it back.
 */
const emit = defineEmits<{ undo: [Done] }>()

/** How long it offers to take a change back. */
const UNDO_SECONDS = 12

const done = ref<Done | null>(null)
const open = ref(false)

function show(what: Done) {
  done.value = what
  open.value = true
}

function undo() {
  const what = done.value as Done
  open.value = false
  emit('undo', what)
}

defineExpose({ show })
</script>

<template>
  <v-snackbar
    v-if="done"
    v-model="open"
    :timeout="UNDO_SECONDS * 1000"
    multi-line
    data-test="undo-notice"
  >
    <span data-test="undo-notice-text">{{ done.text }}</span>
    <template v-if="done.undo" #actions>
      <v-btn variant="text" data-test="undo-notice-undo" @click="undo">Undo</v-btn>
    </template>
  </v-snackbar>
</template>
