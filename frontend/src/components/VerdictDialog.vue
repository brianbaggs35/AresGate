<script setup lang="ts">
import { ref, useId, watch } from 'vue'

import { VERDICTS, type Verdict, type VerdictChange, type VerdictKind } from '@/api/verdicts'
import { useKeyboardReturn } from '@/dialog'
import { VERDICT, aboutVerdict } from '@/verdicts'

/**
 * Changes what a verdict says, or why. What it is about can't be changed: that would be another
 * verdict. It only asks; saving the answer is up to the page.
 */
const props = defineProps<{
  /** The verdict being changed. The dialog keeps showing it as it fades out. */
  rule: Verdict | null
  /** The answer is being saved. */
  busy?: boolean
}>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ save: [change: VerdictChange] }>()

const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)

const verdict = ref<VerdictKind>('not_suspicious')
const note = ref('')

// Each time it opens it shows what the verdict says now, not what an earlier visit left.
watch(open, (opening) => {
  if (!opening || !props.rule) return
  verdict.value = props.rule.verdict
  note.value = props.rule.note ?? ''
})

function save() {
  emit('save', { verdict: verdict.value, note: note.value.trim() || null })
}
</script>

<template>
  <v-dialog
    v-model="open"
    :persistent="busy"
    max-width="520"
    :aria-labelledby="titleId"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card class="pa-6" data-test="verdict-dialog">
      <h2 :id="titleId" class="text-title-large mb-1">Change this verdict</h2>
      <p v-if="rule" class="text-body-medium text-medium-emphasis mb-4" data-test="dialog-about">
        {{ aboutVerdict(rule) }}
      </p>
      <v-form @submit.prevent="save">
        <v-radio-group v-model="verdict" hide-details class="mb-2" aria-label="What you say">
          <v-radio v-for="kind in VERDICTS" :key="kind" :value="kind" :data-test="`say-${kind}`">
            <template #label>
              <span class="verdict-dialog__label">
                <span class="text-body-large">{{ VERDICT[kind].label }}</span>
                <span class="text-body-medium text-medium-emphasis">{{
                  VERDICT[kind].meaning
                }}</span>
              </span>
            </template>
          </v-radio>
        </v-radio-group>
        <v-text-field
          v-model="note"
          label="Why (optional)"
          maxlength="500"
          class="mb-4"
          data-test="dialog-note"
        />
        <div class="d-flex flex-wrap justify-end ga-3">
          <v-btn variant="text" :disabled="busy" data-test="dialog-cancel" @click="open = false">
            Cancel
          </v-btn>
          <v-btn type="submit" color="primary" :loading="busy" data-test="dialog-save">
            Save
          </v-btn>
        </div>
      </v-form>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.verdict-dialog__label {
  display: flex;
  flex-direction: column;
  padding-block: 0.25rem;
}
</style>
