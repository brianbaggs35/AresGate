<script setup lang="ts">
import { Sparkles, Undo2 } from '@lucide/vue'
import { computed } from 'vue'

import type { OwnerCall } from '@/api/incidents'
import type { FamilyDetail } from '@/api/threats'
import SectionCard from '@/components/SectionCard.vue'
import { formatAgo } from '@/format'
import { OWNER_CALL } from '@/threats'
import { CLASSIFICATION } from '@/triage'

/**
 * What is thought of a whole kind of incident, and the means to change it. An AI judges a kind
 * once, from a few of its incidents, and that one answer covers every incident of it, which is
 * what keeps the cost of reading seventy thousand alerts to a few questions. Your word on a kind
 * comes before the AI's: you can set all of it aside, or say it must never be set aside.
 */
const props = defineProps<{
  family: FamilyDetail
  /** Whether the AI is being asked about it, which can take a minute. */
  asking: boolean
  /** Why the AI could not be asked, or why your word could not be kept. */
  failure: string | null
  /** The word being kept, while it is under way (`null` is taking yours back). */
  calling: OwnerCall | 'clear' | null
}>()
defineEmits<{ call: [OwnerCall | null]; ask: [] }>()

const judged = computed(() => {
  const { classification, confidence } = props.family
  if (!classification) return null
  return { look: CLASSIFICATION[classification], confidence: confidence as number }
})
const by = computed(() => {
  const { provider, model, judged_at: at } = props.family
  if (!at) return ''
  const named = model ? ` (${model})` : ''
  return `Judged by ${provider ?? 'the AI'}${named} ${formatAgo(at)}.`
})
const OWNER_CALLS = Object.keys(OWNER_CALL) as OwnerCall[]
</script>

<template>
  <SectionCard
    title="What is thought of this kind"
    description="One answer for every incident of it. Your word comes before the AI's."
    data-test="judgement-card"
  >
    <div v-if="judged" class="judgement__ai" data-test="judgement-ai">
      <v-chip
        :color="judged.look.color"
        :prepend-icon="judged.look.icon"
        variant="outlined"
        data-test="judgement-class"
      >
        AI: {{ judged.look.label }}, {{ judged.confidence }}% sure
      </v-chip>
      <p class="text-body-large" data-test="judgement-reason">{{ family.reason }}</p>
      <p class="text-body-medium text-medium-emphasis" data-test="judgement-by">{{ by }}</p>
    </div>
    <p v-else class="text-body-large" data-test="judgement-none">
      No AI has judged this kind yet. It is judged from a few of its incidents, once, when the AI is
      watching, or when you ask.
    </p>

    <p
      v-if="family.owner_call"
      class="judgement__owner text-body-large"
      data-test="judgement-owner"
    >
      <v-icon :icon="OWNER_CALL[family.owner_call].icon" aria-hidden="true" />
      <span
        ><b>{{ OWNER_CALL[family.owner_call].label }}.</b>
        {{ OWNER_CALL[family.owner_call].meaning }}</span
      >
    </p>

    <v-alert
      v-if="failure"
      type="warning"
      variant="tonal"
      class="mt-4"
      role="alert"
      data-test="judgement-failure"
    >
      {{ failure }}
    </v-alert>

    <div class="judgement__actions">
      <v-btn
        v-for="call in OWNER_CALLS"
        :key="call"
        :variant="family.owner_call === call ? 'flat' : 'tonal'"
        :color="family.owner_call === call ? 'primary' : undefined"
        :prepend-icon="OWNER_CALL[call].icon"
        :loading="calling === call"
        :disabled="calling !== null || family.owner_call === call"
        :data-test="`call-${call}`"
        @click="$emit('call', call)"
      >
        {{ OWNER_CALL[call].button }}
      </v-btn>
      <v-btn
        v-if="family.owner_call"
        variant="text"
        :prepend-icon="Undo2"
        :loading="calling === 'clear'"
        :disabled="calling !== null"
        data-test="call-clear"
        @click="$emit('call', null)"
      >
        Take my word back
      </v-btn>
      <v-btn
        variant="outlined"
        :prepend-icon="Sparkles"
        :loading="asking"
        :disabled="asking"
        data-test="judge"
        @click="$emit('ask')"
      >
        {{ judged ? 'Ask the AI again' : 'Ask the AI' }}
      </v-btn>
    </div>
  </SectionCard>
</template>

<style scoped>
.judgement__ai {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
}

.judgement__ai p,
.judgement__owner {
  margin: 0;
}

.judgement__owner {
  display: flex;
  gap: 0.75rem;
  margin-top: 1rem;
}

.judgement__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
  margin-top: 1.25rem;
}
</style>
