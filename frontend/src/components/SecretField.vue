<script setup lang="ts">
import { Eye, EyeOff } from '@lucide/vue'
import { ref } from 'vue'

/**
 * A field for something that is only ever written: an API key, a token, a password. What was
 * saved is never sent back, so a saved one shows as saved, and leaving the field empty keeps it.
 */
defineProps<{ label: string; saved: boolean; hint?: string }>()
const secret = defineModel<string>({ required: true })
const visible = ref(false)
</script>

<template>
  <v-text-field
    v-model="secret"
    :label="label"
    :type="visible ? 'text' : 'password'"
    :placeholder="saved ? 'Saved' : undefined"
    :persistent-placeholder="saved"
    :hint="saved ? 'Saved. Leave this empty to keep it, or type a new one to replace it.' : hint"
    persistent-hint
    autocomplete="off"
    spellcheck="false"
    autocapitalize="off"
  >
    <template #append-inner>
      <v-btn
        :icon="visible ? EyeOff : Eye"
        variant="text"
        size="small"
        density="comfortable"
        :aria-label="`Show ${label}`"
        :aria-pressed="visible"
        data-test="show-secret"
        @click="visible = !visible"
      />
    </template>
  </v-text-field>
</template>
