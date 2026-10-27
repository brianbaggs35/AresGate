<script setup lang="ts">
import { ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import { changeIncidents, type BulkResult, type BulkSelection } from '@/api/incidents'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { askedAs, labelOf, nothingToDo, wouldDo, type Change } from '@/bulk'
import { useSessionStore } from '@/stores/session'

/**
 * The look over before a change to many incidents: it asks the API what the change would do,
 * which is not only the incidents picked (a verdict holds for everything about an address), says
 * so in words, and goes ahead only when told to. A verdict can say why, which is kept with it.
 */
const props = defineProps<{
  change: Change
  selection: BulkSelection
  /** How many incidents it was asked of, before the API says. */
  count: number
  busy: boolean
  /** Why the change itself failed, when it did. */
  error: string | null
}>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ confirm: [note: string] }>()

const session = useSessionStore()
const result = ref<BulkResult | null>(null)
const problem = ref<string | null>(null)
const note = ref('')
/** Which look is the newest, so the answer to an older one (another change) is dropped. */
let latest = 0

async function look() {
  const mine = ++latest
  result.value = null
  problem.value = null
  try {
    const answer = await session.change((token) =>
      changeIncidents(props.selection, props.change, token, true),
    )
    if (mine === latest) result.value = answer
  } catch (error) {
    if (mine === latest) problem.value = errorMessage(error)
  }
}

// Each time it opens, which it may already be as it appears.
watch(
  open,
  (now) => {
    if (now) {
      note.value = ''
      void look()
    }
  },
  { immediate: true },
)
</script>

<template>
  <ConfirmDialog
    v-model="open"
    :title="askedAs(change, result?.incidents ?? count)"
    :confirm-label="labelOf(change)"
    :busy="busy"
    :disabled="!result || nothingToDo(change, result)"
    @confirm="emit('confirm', note)"
  >
    <p v-if="!result && !problem" class="text-medium-emphasis" data-test="bulk-looking">
      Counting what it would change…
    </p>
    <template v-if="result">
      <p v-for="line in wouldDo(change, result)" :key="line" class="mb-2" data-test="bulk-would">
        {{ line }}
      </p>
    </template>
    <v-textarea
      v-if="'verdict' in change && result"
      v-model="note"
      label="Why (optional)"
      hint="Kept with the verdict, so you remember."
      persistent-hint
      rows="2"
      auto-grow
      counter="500"
      maxlength="500"
      class="mt-3"
      data-test="bulk-note"
    />
    <v-alert
      v-if="problem || error"
      type="error"
      variant="tonal"
      density="compact"
      class="mt-3"
      data-test="bulk-problem"
    >
      {{ problem ?? error }}
    </v-alert>
  </ConfirmDialog>
</template>
