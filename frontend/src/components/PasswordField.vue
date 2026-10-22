<script setup lang="ts">
import { Eye, EyeOff } from '@lucide/vue'
import { ref } from 'vue'

/** `creating` is for choosing a password, so a password manager offers to make one. */
defineProps<{ label: string; creating?: boolean }>()
const password = defineModel<string>({ required: true })
const visible = ref(false)
</script>

<template>
  <v-text-field
    v-model="password"
    :label="label"
    :type="visible ? 'text' : 'password'"
    :autocomplete="creating ? 'new-password' : 'current-password'"
    spellcheck="false"
    autocapitalize="off"
  >
    <template #append-inner>
      <v-btn
        :icon="visible ? EyeOff : Eye"
        variant="text"
        size="small"
        density="comfortable"
        aria-label="Show password"
        :aria-pressed="visible"
        data-test="show-password"
        @click="visible = !visible"
      />
    </template>
  </v-text-field>
</template>
