<script setup lang="ts">
import { computed } from 'vue'

import SectionCard from '@/components/SectionCard.vue'
import { importanceSentence } from '@/threats'

/**
 * What the devices that matter do to the bar. An attack on the NAS that holds the backups is worth
 * a look at a lower confidence than one on a smart plug: an incident that touched a device you
 * said is important is shown to you when AresGate is a few points less sure than usual, and one
 * that touched only guests and IoT devices when it is a few points surer. Each is a slider, and
 * the page says what the two would change. Nothing is kept until the page saves.
 */
const props = defineProps<{
  /** How many points the bar falls for an important device, and rises for guest and IoT ones. */
  drop: number
  raise: number
  /** What each is until it is changed, and the most either may move the bar. */
  defaultDrop: number
  defaultRaise: number
  max: number
}>()
const emit = defineEmits<{ 'update:drop': [number]; 'update:raise': [number] }>()

const dropSentence = computed(() => importanceSentence('drop', props.drop))
const raiseSentence = computed(() => importanceSentence('raise', props.raise))
const spoken = ({ value }: { value: number }) => `${value.toString()} points`
</script>

<template>
  <SectionCard
    title="Devices that matter"
    description="You say which devices matter on the Assets page. This is what that does to the bar for being shown an incident."
    data-test="threat-importance-card"
  >
    <div class="shift">
      <div class="shift__head">
        <span class="text-title-medium" data-test="importance-drop-value">
          Important devices: {{ drop }} points lower
        </span>
        <v-btn
          v-if="drop !== defaultDrop"
          variant="text"
          size="small"
          data-test="importance-drop-reset"
          @click="emit('update:drop', defaultDrop)"
        >
          Back to {{ defaultDrop }}
        </v-btn>
      </div>
      <v-slider
        :model-value="drop"
        :min="0"
        :max="max"
        :step="1"
        color="primary"
        hide-details
        name="How many points lower the bar is for an incident that touched an important device"
        :value-format="spoken"
        data-test="importance-drop-slider"
        @update:model-value="emit('update:drop', $event)"
      />
      <p class="text-body-large shift__sentence" data-test="importance-drop-sentence">
        {{ dropSentence }}
      </p>
    </div>

    <div class="shift">
      <div class="shift__head">
        <span class="text-title-medium" data-test="importance-raise-value">
          Guests and IoT devices: {{ raise }} points higher
        </span>
        <v-btn
          v-if="raise !== defaultRaise"
          variant="text"
          size="small"
          data-test="importance-raise-reset"
          @click="emit('update:raise', defaultRaise)"
        >
          Back to {{ defaultRaise }}
        </v-btn>
      </div>
      <v-slider
        :model-value="raise"
        :min="0"
        :max="max"
        :step="1"
        color="primary"
        hide-details
        name="How many points higher the bar is for an incident that touched only guest or IoT devices"
        :value-format="spoken"
        data-test="importance-raise-slider"
        @update:model-value="emit('update:raise', $event)"
      />
      <p class="text-body-large shift__sentence" data-test="importance-raise-sentence">
        {{ raiseSentence }}
      </p>
    </div>
  </SectionCard>
</template>

<style scoped>
.shift + .shift {
  margin-top: 1.5rem;
}

.shift__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  min-height: 2.25rem;
}

.shift__sentence {
  margin: 0.75rem 0 0;
}
</style>
