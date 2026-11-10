<script setup lang="ts">
import { Plus } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { fetchAgents, startRun, type Agent, type Overview } from '@/api/agents'
import { errorMessage } from '@/api/client'
import { agentIcon } from '@/agents'
import AgentCard from '@/components/AgentCard.vue'
import AgentDialog from '@/components/AgentDialog.vue'
import AppPage from '@/components/AppPage.vue'
import LoadError from '@/components/LoadError.vue'
import PageHeader from '@/components/PageHeader.vue'
import UndoNotice from '@/components/UndoNotice.vue'
import { usePolling } from '@/polling'
import { useSessionStore } from '@/stores/session'

/**
 * The agents the owner made, each a card that says whether it is going and how it has done, and,
 * before there is one, the kinds there are to make one from. The page looks again every few
 * seconds, so that an agent that starts by its schedule is seen starting.
 */
const session = useSessionStore()

const REFRESH_MS = 4000

const overview = ref<Overview | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const problem = ref<string | null>(null)
/** The agent whose run was just asked for. */
const asking = ref<number | null>(null)
const making = ref(false)
const starter = ref<string | null>(null)
const notice = ref<{ show: (done: { text: string; undo: null }) => void } | null>(null)

const agents = computed(() => overview.value?.agents ?? [])
const templates = computed(() => overview.value?.templates ?? [])

async function load(quiet = false) {
  if (!quiet) loading.value = true
  try {
    overview.value = await session.call(fetchAgents)
    error.value = null
  } catch (loadError) {
    // A refresh that fails leaves what is on screen; only a first look has nothing to leave.
    if (!quiet || overview.value === null) error.value = errorMessage(loadError)
  } finally {
    loading.value = false
  }
}

function make(kind: string | null = null) {
  starter.value = kind
  making.value = true
}

async function run(agent: Agent) {
  asking.value = agent.id
  problem.value = null
  try {
    await session.change((token) => startRun(agent.id, token))
    await load(true)
  } catch (runError) {
    problem.value = errorMessage(runError)
  } finally {
    asking.value = null
  }
}

async function saved(text: string) {
  await load(true)
  notice.value?.show({ text, undo: null })
}

usePolling(() => load(true), REFRESH_MS)
onMounted(() => load())
</script>

<template>
  <AppPage width="wide">
    <PageHeader
      title="Agents"
      description="Agents look at your network for you, on a schedule or when you ask, and tell you what is worth your attention."
    >
      <template #actions>
        <v-btn
          color="primary"
          variant="flat"
          :prepend-icon="Plus"
          :disabled="!overview"
          data-test="agents-make"
          @click="make()"
        >
          Make an agent
        </v-btn>
      </template>
    </PageHeader>

    <LoadError
      v-if="error"
      :message="error"
      :loading="loading"
      retry-test-id="agents-retry"
      data-test="agents-error"
      @retry="load()"
    />

    <template v-else-if="overview">
      <v-alert
        v-if="overview.ai"
        type="info"
        variant="tonal"
        density="compact"
        data-test="agents-ai"
      >
        {{ overview.ai }} Agents still collect what they look at, but the AI can't read it until
        this is fixed.
        <RouterLink :to="{ name: 'settings-ai' }" data-test="agents-ai-link"
          >AI settings</RouterLink
        >
      </v-alert>

      <v-alert
        v-if="problem"
        type="error"
        variant="tonal"
        density="compact"
        data-test="agents-problem"
      >
        {{ problem }}
      </v-alert>

      <ul v-if="agents.length" class="cards" data-test="agents-list">
        <li v-for="agent in agents" :key="agent.id">
          <AgentCard :agent="agent" :busy="asking === agent.id" @run="run(agent)" />
        </li>
      </ul>

      <section v-else class="welcome" aria-labelledby="welcome-title" data-test="agents-empty">
        <h2 id="welcome-title" class="text-title-large">Make your first agent</h2>
        <p class="text-body-large text-medium-emphasis">
          Each kind of agent knows what to look at. Pick one, add your own instructions, and run it
          now or on a schedule.
        </p>
        <ul class="kinds">
          <li v-for="item in templates" :key="item.key">
            <v-card class="kind" data-test="agents-kind">
              <span class="kind__icon" aria-hidden="true">
                <v-icon :icon="agentIcon(item.icon)" size="24" />
              </span>
              <div class="kind__text">
                <h3 class="text-title-medium">{{ item.name }}</h3>
                <p class="text-body-medium text-medium-emphasis">{{ item.tagline }}</p>
              </div>
              <v-btn variant="tonal" data-test="agents-kind-make" @click="make(item.key)">
                Make it
              </v-btn>
            </v-card>
          </li>
        </ul>
      </section>

      <AgentDialog
        v-model="making"
        :agent="null"
        :templates="templates"
        :starter="starter"
        @saved="saved"
      />
    </template>

    <v-skeleton-loader v-else type="heading, card, card" data-test="agents-loading" />

    <UndoNotice ref="notice" />
  </AppPage>
</template>

<style scoped>
.cards,
.kinds {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(19rem, 1fr));
  gap: 1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.cards > li {
  display: flex;
}

.cards > li > * {
  flex: 1;
}

.welcome {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.welcome h2,
.welcome p {
  margin: 0;
}

.kinds {
  margin-top: 0.75rem;
}

.kind {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.75rem;
  height: 100%;
  padding: 1.25rem;
}

.kind__icon {
  display: grid;
  place-items: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 0.875rem;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.kind__text {
  flex: 1;
}

.kind__text h3,
.kind__text p {
  margin: 0;
}
</style>
