<script setup lang="ts">
import { RefreshCw, Sparkles } from '@lucide/vue'
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { errorMessage } from '@/api/client'
import type { IncidentDetail } from '@/api/incidents'
import { giveVerdict } from '@/api/verdicts'
import SectionCard from '@/components/SectionCard.vue'
import VerdictChip from '@/components/VerdictChip.vue'
import { useSessionStore } from '@/stores/session'
import { CLASSIFICATION, newSignals, newSince, readBy } from '@/triage'
import { VERDICT, givenAs, scopesOf } from '@/verdicts'

/**
 * What an AI makes of an incident: the kind of thing it thinks it is, how sure it is, the story in
 * plain words, what to check and the verdict it would give. It is shown as the AI's opinion, with
 * who read it and when, and it never changes anything by itself: the verdict is a button, and the
 * owner presses it or doesn't. When nothing could be asked, it says why in words and where to fix
 * that. Whoever shows it asks (`ask`), because asking can also follow from starting to
 * investigate.
 */
const props = defineProps<{
  incident: IncidentDetail
  /** Whether the AI is being asked now. */
  asking: boolean
  /** Why the AI could not be asked, if that was the last thing to happen. */
  failure: string | null
}>()
const emit = defineEmits<{ ask: []; changed: [] }>()

const session = useSessionStore()

const reading = computed(() => props.incident.reading)
const look = computed(() => (reading.value ? CLASSIFICATION[reading.value.classification] : null))
const fresh = computed(() => newSince(props.incident))

/** The verdict it suggests, unless the owner has already said something of the incident: then it
 * has been decided, and the suggestion is only noise. */
const suggested = computed(() => {
  const kind = reading.value?.verdict
  return kind && !props.incident.verdict ? kind : null
})
const scope = computed(() => scopesOf(props.incident)[0])

const giving = ref(false)
const notice = ref<string | null>(null)
const problem = ref<string | null>(null)

async function accept() {
  const kind = suggested.value
  const target = scope.value
  if (!kind || !target) return
  giving.value = true
  notice.value = null
  problem.value = null
  try {
    const why = reading.value?.verdict_reason
    const note = why ? `Suggested by the AI: ${why}`.slice(0, 500) : 'Suggested by the AI.'
    await session.change((token) => giveVerdict({ verdict: kind, ...target.request, note }, token))
    notice.value = givenAs(target, kind)
    emit('changed')
  } catch (error) {
    problem.value = errorMessage(error)
  } finally {
    giving.value = false
  }
}
</script>

<template>
  <SectionCard
    title="What the AI makes of it"
    description="An AI provider reads the incident and says what it thinks. It is an opinion: it never changes anything by itself."
    data-test="ai-card"
  >
    <template v-if="reading && !asking" #actions>
      <v-btn
        variant="text"
        size="small"
        :prepend-icon="RefreshCw"
        data-test="ai-again"
        @click="emit('ask')"
      >
        Read again
      </v-btn>
    </template>

    <output v-if="asking" class="ai-reading__busy text-body-large" data-test="ai-busy">
      <v-progress-circular indeterminate size="20" width="2" aria-hidden="true" />
      The AI is reading this incident. It can take up to a minute.
    </output>

    <v-alert v-if="failure" type="warning" variant="tonal" data-test="ai-failure">
      {{ failure }}
      <RouterLink :to="{ name: 'settings-ai' }" data-test="ai-settings-link">
        Open the AI settings
      </RouterLink>
    </v-alert>

    <div v-if="reading && look" class="ai-reading" data-test="ai-reading">
      <div class="ai-reading__chips">
        <v-chip
          :color="look.color"
          :prepend-icon="look.icon"
          :title="look.meaning"
          variant="tonal"
          data-test="ai-class"
        >
          {{ look.label }}
        </v-chip>
        <v-chip variant="outlined" data-test="ai-confidence">
          {{ reading.confidence }} of 100 sure
        </v-chip>
        <v-chip variant="outlined" :prepend-icon="Sparkles" data-test="ai-opinion">
          The AI's opinion
        </v-chip>
      </div>

      <p class="text-title-medium" data-test="ai-headline">{{ reading.headline }}</p>
      <p class="text-body-large" data-test="ai-story">{{ reading.story }}</p>

      <section v-if="reading.checks.length" aria-labelledby="ai-checks" class="ai-reading__checks">
        <h3 id="ai-checks" class="text-title-small">What to check</h3>
        <ul class="text-body-large">
          <li v-for="line in reading.checks" :key="line" data-test="ai-check">{{ line }}</li>
        </ul>
      </section>

      <section
        v-if="suggested"
        aria-labelledby="ai-suggestion"
        class="ai-reading__suggestion"
        data-test="ai-suggestion"
      >
        <h3 id="ai-suggestion" class="text-title-small">What the AI would tell AresGate</h3>
        <div class="ai-reading__verdict">
          <VerdictChip :verdict="suggested" />
          <span class="text-body-large" data-test="ai-reason">{{ reading.verdict_reason }}</span>
        </div>
        <v-btn
          v-if="scope"
          variant="tonal"
          :color="VERDICT[suggested].color"
          :loading="giving"
          data-test="ai-accept"
          @click="accept"
        >
          Mark {{ scope.title }} as {{ VERDICT[suggested].label.toLowerCase() }}
        </v-btn>
      </section>

      <output v-if="notice" class="text-body-large" data-test="ai-notice">{{ notice }}</output>
      <v-alert v-if="problem" type="error" variant="tonal" data-test="ai-problem">
        {{ problem }}
      </v-alert>

      <p class="text-body-medium text-medium-emphasis" data-test="ai-source">
        {{ readBy(reading) }}
        <span v-if="fresh > 0" data-test="ai-new">{{ newSignals(fresh) }}</span>
      </p>
    </div>

    <div v-else-if="!asking" class="ai-reading__unread" data-test="ai-unread">
      <p class="text-body-large">
        The AI has not read this incident. Ask it, and it says what it thinks this is, how sure it
        is and what to check.
      </p>
      <v-btn
        variant="tonal"
        color="primary"
        :prepend-icon="Sparkles"
        data-test="ai-ask"
        @click="emit('ask')"
      >
        Ask the AI
      </v-btn>
    </div>
  </SectionCard>
</template>

<style scoped>
.ai-reading,
.ai-reading__unread {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.75rem;
}

.ai-reading p,
.ai-reading h3 {
  margin: 0;
}

.ai-reading__busy {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.ai-reading__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.ai-reading__checks ul {
  margin: 0.25rem 0 0;
  padding-left: 1.25rem;
}

.ai-reading__suggestion {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
  align-self: stretch;
  padding: 1rem;
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.ai-reading__verdict {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}
</style>
