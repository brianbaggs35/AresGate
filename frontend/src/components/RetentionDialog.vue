<script setup lang="ts">
import { ref, useId, watch } from 'vue'
import type { SubmitEventPromise } from 'vuetify'

import { MAX_DAYS, MIN_DAYS } from '@/api/storage'
import { useKeyboardReturn } from '@/dialog'
import { isValid } from '@/form'
import { formatDays } from '@/format'

/**
 * Asks how long one integration's data is kept: the default, or a number of days of its own. It
 * only asks; what is done with the answer (and whether that needs another question, because it
 * removes what is stored) is up to the page.
 */
const props = defineProps<{
  title: string
  /** What is kept, as a plural: "events". */
  noun: string
  defaultDays: number
  /** The days this integration has been given, or null while it keeps its data for the default. */
  days: number | null
  /** The answer is being saved. */
  busy?: boolean
}>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ save: [days: number | null] }>()

const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)

const useDefault = ref(true)
const custom = ref('')

// Each time it opens it shows what is set now, not what an earlier visit left in the field.
watch(open, (opening) => {
  if (!opening) return
  useDefault.value = props.days === null
  custom.value = String(props.days ?? props.defaultDays)
})

const rule = (value: string) =>
  useDefault.value ||
  (/^\d+$/.test(value) && Number(value) >= MIN_DAYS && Number(value) <= MAX_DAYS) ||
  `Enter a whole number of days from ${MIN_DAYS.toString()} to ${MAX_DAYS.toString()}.`

async function submit(event: SubmitEventPromise) {
  if (!(await isValid(event))) return
  emit('save', useDefault.value ? null : Number(custom.value))
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
    <v-card class="pa-6" data-test="retention-dialog">
      <h2 :id="titleId" class="text-title-large mb-3" data-test="retention-title">{{ title }}</h2>
      <v-form validate-on="submit" @submit.prevent="submit">
        <v-radio-group v-model="useDefault" hide-details class="mb-2">
          <v-radio
            :value="true"
            :label="`Use the default, ${formatDays(defaultDays)}`"
            data-test="retention-default"
          />
          <v-radio
            :value="false"
            :label="`Choose a number of days, from ${MIN_DAYS.toString()} to ${MAX_DAYS.toString()}`"
            data-test="retention-custom"
          />
        </v-radio-group>
        <v-text-field
          v-model="custom"
          label="Days"
          type="number"
          inputmode="numeric"
          :min="MIN_DAYS"
          :max="MAX_DAYS"
          step="1"
          :disabled="useDefault"
          :rules="[rule]"
          data-test="retention-days"
        />
        <p class="text-body-medium text-medium-emphasis mt-4 mb-6">
          A longer time keeps more {{ noun }} to look back through, and takes more room.
        </p>
        <div class="d-flex flex-wrap justify-end ga-3">
          <v-btn variant="text" :disabled="busy" data-test="retention-cancel" @click="open = false">
            Cancel
          </v-btn>
          <v-btn type="submit" color="primary" :loading="busy" data-test="retention-save">
            Save
          </v-btn>
        </div>
      </v-form>
    </v-card>
  </v-dialog>
</template>
