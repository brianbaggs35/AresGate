<script setup lang="ts">
import { computed } from 'vue'

import SectionCard from '@/components/SectionCard.vue'
import { GAP_CHOICES, gapSentence } from '@/noiseFilters'

/**
 * How long a scan or a brute force may go quiet before its next signal is another incident. A quiet
 * shorter than this is one incident however many addresses and waves it takes, up to a day. What is
 * chosen applies to the signals that arrive after it is saved: the incidents already made keep their
 * grouping. Nothing is kept until the page saves.
 */
const props = defineProps<{
  /** Where each is now (not necessarily kept). */
  scanHours: number
  bruteForceHours: number
  /** What each is until it is changed. */
  defaultScanHours: number
  defaultBruteForceHours: number
}>()
const emit = defineEmits<{
  'update:scanHours': [number]
  'update:bruteForceHours': [number]
}>()

const sentence = computed(() => gapSentence(props.scanHours, props.bruteForceHours))
const changed = computed(
  () =>
    props.scanHours !== props.defaultScanHours ||
    props.bruteForceHours !== props.defaultBruteForceHours,
)

function back() {
  emit('update:scanHours', props.defaultScanHours)
  emit('update:bruteForceHours', props.defaultBruteForceHours)
}
</script>

<template>
  <SectionCard
    title="Repeating scans and brute force"
    description="A scan or a brute force that pauses for less than this is still one incident, however many addresses and waves it takes. A longer pause starts another."
    data-test="gap-card"
  >
    <div class="gap__selects">
      <v-select
        :model-value="scanHours"
        :items="GAP_CHOICES"
        label="Scans: the longest pause within one incident"
        hide-details
        data-test="gap-scan"
        @update:model-value="emit('update:scanHours', Number($event))"
      />
      <v-select
        :model-value="bruteForceHours"
        :items="GAP_CHOICES"
        label="Brute force: the longest pause within one incident"
        hide-details
        data-test="gap-brute-force"
        @update:model-value="emit('update:bruteForceHours', Number($event))"
      />
    </div>
    <div class="gap__foot">
      <p class="text-body-large gap__sentence" data-test="gap-sentence">{{ sentence }}</p>
      <v-btn v-if="changed" variant="text" size="small" data-test="gap-reset" @click="back">
        Back to the defaults
      </v-btn>
    </div>
  </SectionCard>
</template>

<style scoped>
.gap__selects {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.75rem 1.5rem;
}

.gap__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin-top: 1rem;
}

.gap__sentence {
  margin: 0;
}
</style>
