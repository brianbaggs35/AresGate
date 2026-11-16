<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchIncidentTimeline, fetchPlanSteps, type Moment, type PlanStepList } from '@/api/agents'
import AgentInvestigation from '@/components/AgentInvestigation.vue'
import AgentSteps from '@/components/AgentSteps.vue'
import SectionCard from '@/components/SectionCard.vue'
import { useSessionStore } from '@/stores/session'

/**
 * What the agents made of one incident: which of them looked at it and what they concluded, whom
 * they asked, and the steps the response planner proposes for it, which are the owner's to approve
 * or dismiss (an approved one stays here as a task). Nothing is shown for an incident no agent has
 * looked at, and a failure to ask leaves the page as it was.
 */
const props = defineProps<{ incidentId: number }>()

const session = useSessionStore()
const moments = ref<Moment[]>([])
const steps = ref<PlanStepList>({ pending: [], recent: [] })

const has = computed(
  () => moments.value.length > 0 || steps.value.pending.length + steps.value.recent.length > 0,
)

async function load() {
  try {
    const [found, planned] = await Promise.all([
      session.call(() => fetchIncidentTimeline(props.incidentId)),
      session.call(() => fetchPlanSteps(props.incidentId)),
    ])
    moments.value = found
    steps.value = planned
  } catch {
    // The incident is still there to read without what the agents made of it.
  }
}

onMounted(load)
</script>

<template>
  <SectionCard
    v-if="has"
    title="What the agents made of it"
    description="Which agents looked at this, what they asked each other and concluded, and what is left for you to decide."
    data-test="agents-card"
  >
    <div class="incident-agents">
      <AgentSteps
        v-if="steps.pending.length || steps.recent.length"
        :steps="steps"
        @changed="load"
      />
      <AgentInvestigation :moments="moments" />
    </div>
  </SectionCard>
</template>

<style scoped>
.incident-agents {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}
</style>
