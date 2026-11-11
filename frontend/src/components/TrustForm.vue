<script setup lang="ts">
import { ref, watch } from 'vue'

import type { Trust, TrustRequest } from '@/api/trust'
import { vFocus } from '@/form'
import { LEVEL, LEVELS, SOURCES, fieldsOf, problemWith, requestOf } from '@/trust'

/**
 * What to trust and how much: the address, where that address sends its traffic, the program and
 * the alert it is about (at least one), why, and whether it is safe or only low priority. It only
 * asks; saving the answer is up to whoever shows it.
 */
const props = defineProps<{
  /** The decision being changed, or null for a new one. */
  rule: Trust | null
  busy?: boolean
  /** What the button that saves it says. */
  saveLabel: string
  /** A reason the answer could not be saved, from the server. */
  failure?: string | null
}>()
const emit = defineEmits<{ save: [request: TrustRequest]; cancel: [] }>()

const fields = ref(fieldsOf(props.rule))
const problem = ref<string | null>(null)

watch(
  () => props.rule,
  (rule) => {
    fields.value = fieldsOf(rule)
    problem.value = null
  },
)

function save() {
  problem.value = problemWith(fields.value)
  if (problem.value) return
  emit('save', requestOf(fields.value))
}
</script>

<template>
  <v-form class="trust-form" data-test="trust-form" @submit.prevent="save">
    <v-radio-group v-model="fields.verdict" hide-details aria-label="How much to trust it">
      <v-radio v-for="kind in LEVELS" :key="kind" :value="kind" :data-test="`level-${kind}`">
        <template #label>
          <span class="trust-form__label">
            <span class="text-body-large">{{ LEVEL[kind].label }}</span>
            <span class="text-body-medium text-medium-emphasis">{{ LEVEL[kind].meaning }}</span>
          </span>
        </template>
      </v-radio>
    </v-radio-group>

    <div class="trust-form__grid">
      <v-text-field
        v-model="fields.address"
        v-focus
        label="Address"
        placeholder="203.0.113.7"
        hint="What an alert is about or came from. Not where it was going."
        persistent-hint
        autocomplete="off"
        data-test="field-address"
      />
      <v-text-field
        v-model="fields.destination"
        label="Only what it sends to"
        placeholder="52.0.0.0/8"
        hint="An address or a whole network. Then only what that address sends there is trusted."
        persistent-hint
        autocomplete="off"
        data-test="field-destination"
      />
      <v-select
        v-model="fields.source"
        :items="SOURCES"
        label="Only as reported by"
        clearable
        hint="Left empty, it holds for every program."
        persistent-hint
        data-test="field-source"
      />
      <v-text-field
        v-model="fields.signature"
        label="Only the alert"
        placeholder="ET SCAN Potential SSH Scan"
        hint="The alert's exact name."
        persistent-hint
        autocomplete="off"
        data-test="field-signature"
      />
    </div>
    <v-text-field
      v-model="fields.note"
      label="Why (optional)"
      maxlength="500"
      autocomplete="off"
      data-test="field-note"
    />

    <v-alert v-if="problem" type="warning" variant="tonal" data-test="trust-problem">
      {{ problem }}
    </v-alert>
    <v-alert v-if="failure" type="error" variant="tonal" data-test="trust-failure">
      {{ failure }}
    </v-alert>
    <div class="trust-form__actions">
      <v-btn variant="text" :disabled="busy" data-test="trust-cancel" @click="emit('cancel')">
        Cancel
      </v-btn>
      <v-btn type="submit" color="primary" :loading="busy" data-test="trust-save">
        {{ saveLabel }}
      </v-btn>
    </div>
  </v-form>
</template>

<style scoped>
.trust-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.trust-form__label {
  display: flex;
  flex-direction: column;
  padding-block: 0.25rem;
}

.trust-form__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 17rem), 1fr));
  gap: 1rem 1.5rem;
}

.trust-form__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.75rem;
}
</style>
