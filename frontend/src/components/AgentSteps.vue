<script setup lang="ts">
import { Check, X } from '@lucide/vue'
import { ref } from 'vue'

import { approveStep, dismissStep, type PlanStep, type PlanStepList } from '@/api/agents'
import { errorMessage } from '@/api/client'
import { PLAN_STATUS } from '@/agents'
import { formatAgo } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * The steps the response planner proposes, each with what to do and what it risks, which the
 * owner approves or dismisses. Approving records the decision and puts the step on its incident
 * as a task: nothing is changed by an agent, and the owner carries the step out themselves. What
 * was decided lately is listed under the waiting ones. It tells whoever shows it when something
 * was decided, so that they look again.
 */
defineProps<{ steps: PlanStepList }>()
const emit = defineEmits<{ changed: [text: string] }>()

const session = useSessionStore()
const busy = ref<number | null>(null)
const problem = ref<string | null>(null)

async function decide(
  step: PlanStep,
  call: (id: number, token: string) => Promise<PlanStep>,
  text: string,
) {
  busy.value = step.id
  problem.value = null
  try {
    await session.change((token) => call(step.id, token))
    emit('changed', text)
  } catch (error) {
    problem.value = errorMessage(error)
  } finally {
    busy.value = null
  }
}

const approve = (step: PlanStep) =>
  decide(step, approveStep, 'Approved. It is on the incident as a task for you.')
const turnDown = (step: PlanStep) => decide(step, dismissStep, 'Dismissed.')
</script>

<template>
  <div class="steps" data-test="steps-root">
    <v-alert
      v-if="problem"
      type="error"
      variant="tonal"
      density="compact"
      role="alert"
      data-test="step-problem"
    >
      {{ problem }}
    </v-alert>

    <p
      v-if="!steps.pending.length && !steps.recent.length"
      class="text-body-large text-medium-emphasis"
      data-test="steps-none"
    >
      No steps yet. When the Response planner plans what to do about a finding, its steps wait here
      for you to approve or dismiss.
    </p>

    <ul v-if="steps.pending.length" class="steps__list" data-test="steps-pending">
      <li v-for="step in steps.pending" :key="step.id">
        <v-card class="step" data-test="step">
          <div class="step__head">
            <h3 class="text-title-medium step__title" data-test="step-title">{{ step.title }}</h3>
            <span class="text-body-small text-medium-emphasis">
              {{ step.agent_name }} · {{ formatAgo(step.created_at) }}
            </span>
          </div>
          <p v-if="step.detail" class="text-body-large step__text" data-test="step-detail">
            {{ step.detail }}
          </p>
          <p v-if="step.risk" class="text-body-medium step__text" data-test="step-risk">
            <strong>What it risks:</strong> {{ step.risk }}
          </p>
          <p
            v-if="step.incident_id !== null"
            class="text-body-medium text-medium-emphasis step__text"
          >
            About
            <RouterLink
              :to="{ name: 'incident', params: { id: step.incident_id } }"
              data-test="step-incident"
              >incident {{ step.incident_id }}</RouterLink
            >.
          </p>
          <div class="step__actions">
            <v-btn
              color="primary"
              variant="flat"
              :prepend-icon="Check"
              :loading="busy === step.id"
              :disabled="busy !== null"
              data-test="step-approve"
              @click="approve(step)"
            >
              I will do this
            </v-btn>
            <v-btn
              variant="text"
              :prepend-icon="X"
              :disabled="busy !== null"
              data-test="step-dismiss"
              @click="turnDown(step)"
            >
              Dismiss
            </v-btn>
          </div>
        </v-card>
      </li>
    </ul>

    <section v-if="steps.recent.length" aria-labelledby="steps-recent-title">
      <h3 id="steps-recent-title" class="text-title-small">Decided lately</h3>
      <ul class="steps__recent" data-test="steps-recent">
        <li v-for="step in steps.recent" :key="step.id" class="recent">
          <v-chip
            size="small"
            variant="tonal"
            :color="PLAN_STATUS[step.status].color"
            data-test="recent-status"
          >
            {{ PLAN_STATUS[step.status].label }}
          </v-chip>
          <span class="text-body-medium recent__title" data-test="recent-title">
            {{ step.title }}
          </span>
          <span
            v-if="step.decided_at"
            class="text-body-small text-medium-emphasis"
            data-test="recent-when"
          >
            {{ formatAgo(step.decided_at) }}
          </span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.steps {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.steps p,
.steps h3 {
  margin: 0;
}

.steps__list,
.steps__recent {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.step {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem 1.25rem;
}

.step__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.25rem 0.75rem;
}

.step__title,
.step__text {
  overflow-wrap: anywhere;
}

.step__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.recent {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
}

.recent__title {
  flex: 1 1 14rem;
  overflow-wrap: anywhere;
}
</style>
