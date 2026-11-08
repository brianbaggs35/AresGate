<script setup lang="ts">
import { computed } from 'vue'

import SectionCard from '@/components/SectionCard.vue'
import { THREAT_MAX, THREAT_MIN, THREAT_STEP, threatSentence } from '@/threats'

/**
 * How sure AresGate has to be of an incident to call it a threat: the line between the threats
 * you are told about and the suspects you can look at when you have time. A slider from "more
 * threats" to "fewer", with the number and what it means said in words. Nothing is kept until the
 * page saves.
 */
const props = defineProps<{
  /** Where the bar is now (not necessarily kept). */
  modelValue: number
  /** What it is until it is changed. */
  defaultValue: number
}>()
const emit = defineEmits<{ 'update:modelValue': [number] }>()

const sentence = computed(() => threatSentence(props.modelValue, props.defaultValue))
const spoken = ({ value }: { value: number }) => `${value.toString()} out of 100`
</script>

<template>
  <SectionCard
    title="How sure before it is a threat"
    description="Every incident has a confidence from AresGate's rules. A threat is one at or above this, and an AI that is watching agrees."
    data-test="threat-level-card"
  >
    <div class="level__head">
      <span class="text-title-medium" data-test="threat-value">{{ modelValue }} out of 100</span>
      <v-btn
        v-if="modelValue !== defaultValue"
        variant="text"
        size="small"
        data-test="threat-reset"
        @click="emit('update:modelValue', defaultValue)"
      >
        Back to {{ defaultValue }}
      </v-btn>
    </div>
    <v-slider
      :model-value="modelValue"
      :min="THREAT_MIN"
      :max="THREAT_MAX"
      :step="THREAT_STEP"
      color="primary"
      hide-details
      name="How sure AresGate has to be to call an incident a threat"
      :value-format="spoken"
      data-test="threat-slider"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <div class="level__ends text-label-medium text-medium-emphasis" aria-hidden="true">
      <span>More threats</span>
      <span>Fewer threats</span>
    </div>
    <p class="level__sentence text-body-large" data-test="threat-sentence">{{ sentence }}</p>
  </SectionCard>
</template>

<style scoped>
.level__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  min-height: 2.25rem;
}

.level__ends {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.level__sentence {
  margin: 1rem 0 0;
}
</style>
