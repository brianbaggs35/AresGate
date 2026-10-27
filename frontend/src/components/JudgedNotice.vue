<script setup lang="ts">
import { computed, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { changeVerdict, removeVerdict } from '@/api/verdicts'
import { useSessionStore } from '@/stores/session'
import { VERDICT, givenAs, type Judged } from '@/verdicts'

/**
 * What a page says when a card gave a verdict: what AresGate remembered, with *Undo* for a few
 * seconds. Whoever shows the cards calls `show` with what the card said, and asks for its list
 * again when this says `undone`, since a verdict that is taken back brings an incident back.
 */
const emit = defineEmits<{ undone: [] }>()

/** How long it offers to take back a verdict it was just told about. */
const UNDO_SECONDS = 10

const session = useSessionStore()

/** The verdict that was just given, while the page says so and offers to take it back. */
const lately = ref<Judged | null>(null)
const saying = ref(false)
const undoing = ref(false)
const undone = ref<string | null>(null)

/** What it says of the verdict just given, or of what happened when it was taken back. */
const said = computed(() => {
  if (undone.value) return undone.value
  const { scope, kind, rule } = lately.value as Judged
  const was = rule.replaced ? ` It was ${VERDICT[rule.replaced].label.toLowerCase()}.` : ''
  return `${givenAs(scope, kind)}${was}`
})

function show(verdict: Judged) {
  lately.value = verdict
  undone.value = null
  saying.value = true
}

/** Takes it back: a verdict that was new goes, and one that changed another is changed back. */
async function undo() {
  const { rule } = lately.value as Judged
  const { replaced } = rule
  undoing.value = true
  try {
    await session.change((token) =>
      replaced
        ? changeVerdict(rule.id, { verdict: replaced }, token)
        : removeVerdict(rule.id, token),
    )
    undone.value = 'Taken back.'
    emit('undone')
  } catch (error) {
    undone.value = errorMessage(error)
  } finally {
    undoing.value = false
  }
}

defineExpose({ show })
</script>

<template>
  <v-snackbar v-if="lately" v-model="saying" :timeout="UNDO_SECONDS * 1000" data-test="judged">
    <span data-test="judged-text">{{ said }}</span>
    <template v-if="!undone" #actions>
      <v-btn variant="text" :loading="undoing" data-test="undo" @click="undo">Undo</v-btn>
    </template>
  </v-snackbar>
</template>
