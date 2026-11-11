<script setup lang="ts">
import { Check, Undo2, X } from '@lucide/vue'
import { computed, ref } from 'vue'

import {
  applyProposal,
  dismissProposal,
  undoProposal,
  type Proposal,
  type ProposalList,
} from '@/api/agents'
import { errorMessage } from '@/api/client'
import { PROPOSAL_ACTION, PROPOSAL_STATUS, incidentsWords } from '@/agents'
import { formatAgo } from '@/format'
import { useSessionStore } from '@/stores/session'

/**
 * What the cleanup agent suggests tidying: each with what it would do, how sure it is and the
 * incidents it is about, which the owner applies with one press or turns down; and what was
 * decided lately, where what was applied can be taken back. It makes each change itself and tells
 * whoever shows it, so that they look again.
 */
defineProps<{ suggestions: ProposalList }>()
const emit = defineEmits<{ changed: [text: string] }>()

const session = useSessionStore()
const busy = ref<number | null>(null)
const problem = ref<string | null>(null)

const SHOWN = 6

const shown = (proposal: Proposal) => proposal.incident_ids.slice(0, SHOWN)
const more = (proposal: Proposal) => Math.max(0, proposal.incident_ids.length - SHOWN)

async function decide(
  proposal: Proposal,
  call: (id: number, token: string) => Promise<Proposal>,
  text: string,
) {
  busy.value = proposal.id
  problem.value = null
  try {
    await session.change((token) => call(proposal.id, token))
    emit('changed', text)
  } catch (error) {
    problem.value = errorMessage(error)
  } finally {
    busy.value = null
  }
}

const apply = (proposal: Proposal) =>
  decide(proposal, applyProposal, `Done: ${proposal.title.toLowerCase()}.`)
const turnDown = (proposal: Proposal) => decide(proposal, dismissProposal, 'Left as it is.')
const undo = (proposal: Proposal) => decide(proposal, undoProposal, 'Taken back.')

const has = computed(() => (list: ProposalList) => list.pending.length + list.recent.length > 0)
</script>

<template>
  <div class="proposals" data-test="proposals-root">
    <v-alert
      v-if="problem"
      type="error"
      variant="tonal"
      density="compact"
      role="alert"
      data-test="proposal-problem"
    >
      {{ problem }}
    </v-alert>

    <p
      v-if="!has(suggestions)"
      class="text-body-large text-medium-emphasis"
      data-test="proposals-none"
    >
      Nothing to tidy yet. When it finds duplicates or noise, what it suggests will be here.
    </p>

    <ul v-if="suggestions.pending.length" class="proposals__list" data-test="proposals-pending">
      <li v-for="proposal in suggestions.pending" :key="proposal.id">
        <v-card class="proposal" data-test="proposal">
          <div class="proposal__head">
            <h3 class="text-title-medium proposal__title" data-test="proposal-title">
              {{ proposal.title }}
            </h3>
            <v-chip size="small" variant="tonal" data-test="proposal-sure">
              {{ proposal.confidence }}% sure
            </v-chip>
          </div>
          <p class="text-body-large proposal__detail" data-test="proposal-detail">
            {{ proposal.detail }}
          </p>
          <p class="text-body-medium text-medium-emphasis proposal__does" data-test="proposal-does">
            {{ PROPOSAL_ACTION[proposal.action] ?? proposal.action }}
            {{ incidentsWords(proposal.incident_ids.length) }}:
            <template v-for="(id, at) in shown(proposal)" :key="id">
              <RouterLink
                :to="{ name: 'incident', params: { id } }"
                data-test="proposal-incident"
                >{{ id }}</RouterLink
              ><template v-if="at < shown(proposal).length - 1">, </template>
            </template>
            <template v-if="more(proposal)"> and {{ more(proposal) }} more</template>
            <template v-if="proposal.keep_id !== null">
              . Incident
              <RouterLink
                :to="{ name: 'incident', params: { id: proposal.keep_id } }"
                data-test="proposal-keep"
                >{{ proposal.keep_id }}</RouterLink
              >
              stays open.
            </template>
          </p>
          <div class="proposal__actions">
            <v-btn
              color="primary"
              variant="flat"
              :prepend-icon="Check"
              :loading="busy === proposal.id"
              :disabled="busy !== null"
              data-test="proposal-apply"
              @click="apply(proposal)"
            >
              Do it
            </v-btn>
            <v-btn
              variant="text"
              :prepend-icon="X"
              :disabled="busy !== null"
              data-test="proposal-dismiss"
              @click="turnDown(proposal)"
            >
              Leave it
            </v-btn>
          </div>
        </v-card>
      </li>
    </ul>

    <section v-if="suggestions.recent.length" aria-labelledby="proposals-recent-title">
      <h3 id="proposals-recent-title" class="text-title-small">Decided lately</h3>
      <ul class="proposals__recent" data-test="proposals-recent">
        <li v-for="proposal in suggestions.recent" :key="proposal.id" class="recent">
          <v-chip
            size="small"
            variant="tonal"
            :color="PROPOSAL_STATUS[proposal.status].color"
            data-test="recent-status"
          >
            {{ PROPOSAL_STATUS[proposal.status].label }}
          </v-chip>
          <span class="text-body-medium recent__title" data-test="recent-title">
            {{ proposal.title }}
          </span>
          <span class="text-body-small text-medium-emphasis" data-test="recent-when">
            <template v-if="proposal.decided_by === 'agent'">by the agent, </template>
            <template v-if="proposal.decided_at">{{ formatAgo(proposal.decided_at) }}</template>
          </span>
          <v-btn
            v-if="proposal.status === 'applied'"
            size="small"
            variant="text"
            :prepend-icon="Undo2"
            :loading="busy === proposal.id"
            :disabled="busy !== null"
            data-test="proposal-undo"
            @click="undo(proposal)"
          >
            Take it back
          </v-btn>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.proposals {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.proposals p,
.proposals h3 {
  margin: 0;
}

.proposals__list,
.proposals__recent {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.proposal {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem 1.25rem;
}

.proposal__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 0.75rem;
}

.proposal__title,
.proposal__detail {
  overflow-wrap: anywhere;
}

.proposal__actions {
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
