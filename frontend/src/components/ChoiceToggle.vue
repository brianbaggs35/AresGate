<script setup lang="ts" generic="Key extends string">
/**
 * A row of buttons of which exactly one is chosen, such as the stretch of time a page shows. Each
 * button is `${name}-${key}` for tests, and the row is named `name`.
 */
const { options, label, name } = defineProps<{
  options: readonly { key: Key; label: string }[]
  /** What the choice is, for a screen reader. */
  label: string
  name: string
}>()
const model = defineModel<Key>({ required: true })
</script>

<template>
  <v-btn-toggle
    v-model="model"
    mandatory
    divided
    density="comfortable"
    variant="outlined"
    color="primary"
    :aria-label="label"
    :data-test="name"
  >
    <v-btn
      v-for="option in options"
      :key="option.key"
      :value="option.key"
      :data-test="`${name}-${option.key}`"
    >
      {{ option.label }}
    </v-btn>
  </v-btn-toggle>
</template>
