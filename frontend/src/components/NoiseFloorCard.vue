<script setup lang="ts">
import { computed } from 'vue'

import { FLOOR_MAX, FLOOR_MIN, FLOOR_STEP, floorSentence, levelOf } from '@/noiseFilters'
import SectionCard from '@/components/SectionCard.vue'

/**
 * How sure AresGate has to be of an incident before it asks about it: the floor that the dashboard,
 * the Needs you lane and (later) the alerts that reach you all go by. A slider from "ask about
 * more" to "ask about less", with the number and what it means said in words. Nothing is kept
 * until the page saves.
 */
const props = defineProps<{
  /** Where the floor is now (not necessarily kept). */
  modelValue: number
  /** What it is until it is changed, and where the words medium and high are drawn. */
  defaultFloor: number
  mediumFrom: number
  highFrom: number
}>()
const emit = defineEmits<{ 'update:modelValue': [number] }>()

const level = computed(() => levelOf(props.modelValue, props.mediumFrom, props.highFrom))
const sentence = computed(() => floorSentence(props.modelValue, props.mediumFrom, props.highFrom))
// What a screen reader says of the slider's place: the number and what it is called.
const spoken = ({ value }: { value: number }) =>
  `${value.toString()}, ${levelOf(value, props.mediumFrom, props.highFrom)} confidence`
</script>

<template>
  <SectionCard
    title="How sure before it asks you"
    description="AresGate adds up its reasons into a confidence for every incident. It only asks you about one once that confidence reaches this."
    data-test="floor-card"
  >
    <div class="floor__head">
      <span class="text-title-medium" data-test="floor-value">
        {{ modelValue }} out of 100
        <span class="text-medium-emphasis">({{ level }})</span>
      </span>
      <v-btn
        v-if="modelValue !== defaultFloor"
        variant="text"
        size="small"
        data-test="floor-reset"
        @click="emit('update:modelValue', defaultFloor)"
      >
        Back to {{ defaultFloor }}
      </v-btn>
    </div>
    <v-slider
      :model-value="modelValue"
      :min="FLOOR_MIN"
      :max="FLOOR_MAX"
      :step="FLOOR_STEP"
      color="primary"
      hide-details
      name="How sure AresGate has to be before it asks you"
      :value-format="spoken"
      class="floor__slider"
      data-test="floor-slider"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <div class="floor__ends text-label-medium text-medium-emphasis" aria-hidden="true">
      <span>Asks about more</span>
      <span>Asks about less</span>
    </div>
    <p class="floor__sentence text-body-large" data-test="floor-sentence">{{ sentence }}</p>
  </SectionCard>
</template>

<style scoped>
.floor__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  min-height: 2.25rem;
}

.floor__slider {
  margin-block: 0.75rem 0;
}

.floor__ends {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.floor__sentence {
  margin: 1rem 0 0;
}
</style>
