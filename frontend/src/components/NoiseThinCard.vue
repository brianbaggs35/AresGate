<script setup lang="ts">
import { computed } from 'vue'

import SectionCard from '@/components/SectionCard.vue'
import { THIN_CHOICES, thinSentence } from '@/noiseFilters'

/**
 * The fewest low alerts from one program that an incident needs before it is asked about. Until it
 * has that many, a lone low alert is never asked about. A verdict of yours, another program that
 * agrees, or an alert that is not low always counts at once. Nothing is kept until the page saves.
 */
const props = defineProps<{
  /** The minimum as it stands now (not necessarily kept). */
  modelValue: number
  /** What it is until it is changed. */
  defaultMinimum: number
}>()
const emit = defineEmits<{ 'update:modelValue': [number] }>()

const sentence = computed(() => thinSentence(props.modelValue))
</script>

<template>
  <SectionCard
    title="Thin incidents"
    description="An incident made of one program's low-severity alerts is set aside until it has as many as this, so a single low alert is not asked about. A verdict of yours, or another program that agrees, counts at once."
    data-test="thin-card"
  >
    <v-select
      :model-value="modelValue"
      :items="THIN_CHOICES"
      label="Low alerts from one program before it is asked about"
      hide-details
      data-test="thin-select"
      @update:model-value="emit('update:modelValue', Number($event))"
    />
    <div class="thin__foot">
      <p class="text-body-large thin__sentence" data-test="thin-sentence">{{ sentence }}</p>
      <v-btn
        v-if="modelValue !== defaultMinimum"
        variant="text"
        size="small"
        data-test="thin-reset"
        @click="emit('update:modelValue', defaultMinimum)"
      >
        Back to {{ defaultMinimum }}
      </v-btn>
    </div>
  </SectionCard>
</template>

<style scoped>
.thin__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin-top: 1rem;
}

.thin__sentence {
  margin: 0;
}
</style>
