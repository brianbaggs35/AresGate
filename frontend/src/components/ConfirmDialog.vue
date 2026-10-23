<script setup lang="ts">
import { useId, watch } from 'vue'

/**
 * Asks before something that can't be undone, in a dialog that every page uses the same way: it
 * says what will happen in the slot, has Cancel and a button named for the action, and gives the
 * keyboard back to whatever opened it. While the action is under way (`busy`) it can't be closed.
 */
withDefaults(
  defineProps<{
    title: string
    /** What the button that goes ahead says: the action, such as "Disconnect". */
    confirmLabel: string
    /** The action is under way. */
    busy?: boolean
    /** The action removes something, so the button is red. */
    destructive?: boolean
  }>(),
  { busy: false, destructive: false },
)
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ confirm: [] }>()

const titleId = useId()
/** What had the keyboard when the dialog opened. */
let opener: HTMLElement | null = null

watch(open, (opening) => {
  // Buttons are HTML elements, and that is what has the keyboard when a dialog is asked for.
  if (opening) opener = document.activeElement as HTMLElement | null
})

function giveBackTheKeyboard() {
  opener?.focus()
  opener = null
}
</script>

<template>
  <v-dialog
    v-model="open"
    :persistent="busy"
    max-width="480"
    :aria-labelledby="titleId"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card class="pa-6" data-test="confirm-dialog">
      <h2 :id="titleId" class="text-title-large mb-3" data-test="confirm-title">{{ title }}</h2>
      <div class="text-body-large mb-6" data-test="confirm-message"><slot /></div>
      <div class="d-flex flex-wrap justify-end ga-3">
        <v-btn variant="text" :disabled="busy" data-test="confirm-cancel" @click="open = false">
          Cancel
        </v-btn>
        <v-btn
          :color="destructive ? 'error' : 'primary'"
          :loading="busy"
          data-test="confirm-accept"
          @click="emit('confirm')"
        >
          {{ confirmLabel }}
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>
