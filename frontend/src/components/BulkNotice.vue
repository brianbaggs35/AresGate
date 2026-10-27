<script setup lang="ts">
import { ref } from 'vue'

import { errorMessage } from '@/api/client'
import { undoChange, type BulkUndo } from '@/api/incidents'
import { useSessionStore } from '@/stores/session'

/**
 * What a page says when it changed many incidents at once: what was done, with *Undo* for a
 * while. Whoever shows it calls `show` with the words and the change's way back, and asks for the
 * list again when this says `undone`, since taking a change back brings incidents back.
 */
const emit = defineEmits<{ undone: [] }>()

/** How long it offers to take a change back. It is long, as a change to many is not one to
 * second-guess in a few seconds. */
const UNDO_SECONDS = 15

const session = useSessionStore()

const said = ref<string | null>(null)
const way = ref<BulkUndo | null>(null)
const open = ref(false)
const undoing = ref(false)

function show(text: string, undo: BulkUndo | null) {
  said.value = text
  way.value = undo
  open.value = true
}

async function undo() {
  const back = way.value as BulkUndo
  undoing.value = true
  try {
    await session.change((token) => undoChange(back, token))
    said.value = 'Taken back.'
    emit('undone')
  } catch (error) {
    said.value = errorMessage(error)
  } finally {
    way.value = null
    undoing.value = false
  }
}

defineExpose({ show })
</script>

<template>
  <v-snackbar
    v-if="said"
    v-model="open"
    :timeout="UNDO_SECONDS * 1000"
    multi-line
    data-test="bulk-notice"
  >
    <span data-test="bulk-notice-text">{{ said }}</span>
    <template v-if="way" #actions>
      <v-btn variant="text" :loading="undoing" data-test="bulk-undo" @click="undo">Undo</v-btn>
    </template>
  </v-snackbar>
</template>
