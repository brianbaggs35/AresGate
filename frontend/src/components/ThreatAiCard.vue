<script setup lang="ts">
import { computed } from 'vue'

import SectionCard from '@/components/SectionCard.vue'
import { THREAT_MAX, THREAT_STEP, clearSentence } from '@/threats'

/**
 * What the AI may do about the threats: set incidents aside as background when it is sure they
 * are harmless or a probe, and whether it has to agree before something is called a threat. Both
 * only apply while an AI is watching (on, with a provider, and reading by itself), and the card
 * says so when none is. An incident that is critical, that you called a threat or that has
 * more than one stage of an attack is never set aside, whatever these say.
 */
const props = defineProps<{
  mayClear: boolean
  clearFrom: number
  confirms: boolean
  defaultClearFrom: number
  minClearFrom: number
  /** Whether an AI is watching. */
  watching: boolean
}>()
const emit = defineEmits<{
  'update:mayClear': [boolean]
  'update:clearFrom': [number]
  'update:confirms': [boolean]
}>()

const sentence = computed(() => clearSentence(props.clearFrom, props.minClearFrom))
const spoken = ({ value }: { value: number }) => `${value.toString()} percent sure`
</script>

<template>
  <SectionCard
    title="What the AI may do"
    description="It judges kinds of incident, not every alert, so this costs a few questions a day and not thousands."
    data-test="threat-ai-card"
  >
    <v-alert v-if="!watching" type="info" variant="tonal" class="mb-4" data-test="threat-ai-off">
      No AI is watching, so these two do nothing yet. Turn on AI, choose a provider and let it read
      by itself in Settings > AI, and they take effect.
      <template #append>
        <v-btn variant="text" :to="{ name: 'settings-ai' }" data-test="threat-ai-link">
          AI settings
        </v-btn>
      </template>
    </v-alert>

    <v-switch
      :model-value="mayClear"
      label="Let the AI set harmless incidents aside"
      color="primary"
      density="comfortable"
      hide-details
      data-test="threat-clear"
      @update:model-value="emit('update:mayClear', Boolean($event))"
    />
    <p class="ai__hint text-body-medium text-medium-emphasis">
      Probes and noise the AI is sure about go to the background instead of your list. They are
      still kept, and you can see and overrule each kind.
    </p>

    <div v-if="mayClear" class="ai__bar" data-test="threat-clear-bar">
      <div class="ai__head">
        <span class="text-title-medium" data-test="clear-value">{{ clearFrom }}% sure</span>
        <v-btn
          v-if="clearFrom !== defaultClearFrom"
          variant="text"
          size="small"
          data-test="clear-reset"
          @click="emit('update:clearFrom', defaultClearFrom)"
        >
          Back to {{ defaultClearFrom }}
        </v-btn>
      </div>
      <v-slider
        :model-value="clearFrom"
        :min="minClearFrom"
        :max="THREAT_MAX"
        :step="THREAT_STEP"
        color="primary"
        hide-details
        name="How sure the AI has to be to set an incident aside"
        :value-format="spoken"
        data-test="clear-slider"
        @update:model-value="emit('update:clearFrom', $event)"
      />
      <p class="text-body-large" data-test="clear-sentence">{{ sentence }}</p>
    </div>

    <v-switch
      :model-value="confirms"
      label="A threat needs the AI to agree"
      color="primary"
      density="comfortable"
      hide-details
      class="mt-4"
      data-test="threat-confirm"
      @update:model-value="emit('update:confirms', Boolean($event))"
    />
    <p class="ai__hint text-body-medium text-medium-emphasis">
      While the AI is watching, an incident is only a threat once it has read it and thinks it is
      real. A critical one never waits for it. Without this, the rules alone decide.
    </p>
  </SectionCard>
</template>

<style scoped>
.ai__hint {
  margin: 0.25rem 0 0;
  padding-inline-start: 3.5rem;
}

.ai__bar {
  margin: 1rem 0 0;
  padding-inline-start: 0.5rem;
}

.ai__bar p {
  margin: 0.75rem 0 0;
}

.ai__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  min-height: 2.25rem;
}
</style>
