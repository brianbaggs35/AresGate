<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, ref, useId, watch } from 'vue'

import {
  changeAgent,
  createAgent,
  removeAgent,
  type Agent,
  type AgentChoices,
  type Template,
} from '@/api/agents'
import { errorMessage } from '@/api/client'
import { INTERVALS, agentIcon } from '@/agents'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { useKeyboardReturn } from '@/dialog'
import { useSessionStore } from '@/stores/session'

/**
 * Makes an agent from one of the kinds there are, or changes one. It is a sheet from the side on a
 * desktop and the screen above the bottom bar on a phone. Choosing a kind fills in what that kind
 * starts with, which the owner may change; a kind that tests the network is never on a schedule
 * and has to be allowed to test, in words that say what it does. It makes the change itself and
 * tells whoever shows it what it did; a refusal is said inside it, in the API's words.
 */
const props = defineProps<{
  /** The agent to change, or none to make a new one. */
  agent: Agent | null
  templates: readonly Template[]
  /** The kind a new agent starts as. */
  starter?: string | null
}>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ saved: [text: string, agent: Agent]; removed: [text: string] }>()

const MAX_NAME = 80
const MAX_GOAL = 2000

const session = useSessionStore()
const titleId = useId()
const groupId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)

const kind = ref('')
const name = ref('')
const goal = ref('')
const interval = ref<number | null>(null)
const enabled = ref(true)
const allow = ref(false)
const problem = ref<string | null>(null)
const saving = ref(false)
const confirming = ref(false)
const removing = ref(false)
/** Whether the owner has typed a name, so choosing another kind doesn't take it away. */
const named = ref(false)

const editing = computed(() => props.agent !== null)
const template = computed(() => props.templates.find((item) => item.key === kind.value) ?? null)
const active = computed(() => template.value?.active ?? props.agent?.active ?? false)
const title = computed(() => (props.agent ? `Edit ${props.agent.name}` : 'Make an agent'))
const ready = computed(() => name.value.trim() !== '' && kind.value !== '' && !saving.value)

function begin(item: Template) {
  kind.value = item.key
  if (!named.value) name.value = item.name
  goal.value = item.goal
  interval.value = item.interval_minutes
  allow.value = false
}

watch(
  open,
  (opening) => {
    if (!opening) return
    const from = props.agent
    problem.value = null
    named.value = from !== null
    if (from) {
      kind.value = from.template
      name.value = from.name
      goal.value = from.goal
      interval.value = from.interval_minutes
      enabled.value = from.enabled
      allow.value = from.allow_active
      return
    }
    enabled.value = true
    const first = props.templates.find((item) => item.key === props.starter) ?? props.templates[0]
    if (first) begin(first)
  },
  { immediate: true },
)

const typed = () => {
  named.value = true
}

function choices(): AgentChoices {
  return {
    name: name.value.trim(),
    goal: goal.value.trim(),
    interval_minutes: active.value ? null : interval.value,
    enabled: enabled.value,
    allow_active: active.value && allow.value,
  }
}

async function save() {
  if (!ready.value) return
  saving.value = true
  problem.value = null
  const wanted = choices()
  try {
    if (props.agent) {
      const id = props.agent.id
      const saved = await session.change((token) => changeAgent(id, wanted, token))
      emit('saved', `${wanted.name} saved.`, saved)
    } else {
      const made = await session.change((token) => createAgent(kind.value, wanted, token))
      emit('saved', `${wanted.name} is ready.`, made)
    }
    open.value = false
  } catch (error) {
    problem.value = errorMessage(error)
  } finally {
    saving.value = false
  }
}

async function remove() {
  const gone = props.agent as Agent
  removing.value = true
  try {
    await session.change((token) => removeAgent(gone.id, token))
    confirming.value = false
    open.value = false
    emit('removed', `${gone.name} removed, with its runs.`)
  } catch (error) {
    confirming.value = false
    problem.value = errorMessage(error)
  } finally {
    removing.value = false
  }
}
</script>

<template>
  <v-dialog
    v-model="open"
    scrollable
    transition="slide-x-reverse-transition"
    :aria-labelledby="titleId"
    class="sheet"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card class="sheet__card" :rounded="0" data-test="agent-dialog">
      <header class="sheet__head">
        <h2 :id="titleId" class="text-title-large sheet__title" data-test="dialog-title">
          {{ title }}
        </h2>
        <v-btn
          icon
          variant="text"
          size="small"
          aria-label="Close"
          data-test="dialog-close"
          @click="open = false"
        >
          <v-icon :icon="X" />
        </v-btn>
      </header>

      <form class="sheet__body" @submit.prevent="save">
        <v-alert
          v-if="problem"
          type="error"
          variant="tonal"
          density="compact"
          data-test="dialog-problem"
        >
          {{ problem }}
        </v-alert>

        <fieldset v-if="!editing" class="kinds" :aria-labelledby="groupId">
          <legend :id="groupId" class="text-title-small kinds__legend">What should it do?</legend>
          <label
            v-for="item in templates"
            :key="item.key"
            class="kind"
            :class="{ 'kind--on': kind === item.key }"
            data-test="dialog-kind"
          >
            <input
              type="radio"
              class="kind__input"
              name="agent-kind"
              :value="item.key"
              :checked="kind === item.key"
              @change="begin(item)"
            />
            <span class="kind__icon" aria-hidden="true">
              <v-icon :icon="agentIcon(item.icon)" size="22" />
            </span>
            <span class="kind__text">
              <span class="text-title-small">{{ item.name }}</span>
              <span class="text-body-medium text-medium-emphasis">{{ item.tagline }}</span>
            </span>
          </label>
        </fieldset>

        <p
          v-if="template"
          class="text-body-medium text-medium-emphasis kinds__about"
          data-test="dialog-about"
        >
          {{ template.description }}
        </p>

        <v-text-field
          v-model="name"
          label="Name"
          hint="What you call it."
          persistent-hint
          :counter="MAX_NAME"
          :maxlength="MAX_NAME"
          autocomplete="off"
          data-test="dialog-name"
          @update:model-value="typed"
        />

        <v-textarea
          v-model="goal"
          label="Instructions"
          hint="Optional. Tell it what matters to you, in your own words. It is added to what this kind of agent already does."
          persistent-hint
          :counter="MAX_GOAL"
          :maxlength="MAX_GOAL"
          rows="3"
          auto-grow
          data-test="dialog-goal"
        />

        <v-select
          v-if="!active"
          v-model="interval"
          :items="INTERVALS"
          label="How often"
          hint="It runs by itself this often. You can always run it by hand too."
          persistent-hint
          data-test="dialog-interval"
        />
        <v-switch
          v-if="!active && interval !== null"
          v-model="enabled"
          color="primary"
          label="Run on this schedule"
          hide-details
          data-test="dialog-enabled"
        />

        <section v-if="active" class="allow" data-test="dialog-active">
          <p class="text-body-medium allow__text">
            This agent connects to devices on your network, so it only runs when you press Run,
            never by itself. It tries a short list of risky ports (such as Telnet, remote desktop
            and open databases) on devices AresGate has already seen at home. It only connects and
            never sends anything else.
          </p>
          <v-switch
            v-model="allow"
            color="primary"
            label="Allow it to test my network"
            hide-details
            data-test="dialog-allow"
          />
        </section>
      </form>

      <footer class="sheet__foot">
        <v-btn
          v-if="editing"
          variant="text"
          color="error"
          :disabled="saving"
          data-test="dialog-remove"
          @click="confirming = true"
        >
          Remove
        </v-btn>
        <span class="sheet__spacer" />
        <v-btn variant="text" :disabled="saving" data-test="dialog-cancel" @click="open = false">
          Cancel
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :disabled="!ready"
          :loading="saving"
          data-test="dialog-save"
          @click="save"
        >
          {{ editing ? 'Save' : 'Make it' }}
        </v-btn>
      </footer>
    </v-card>
  </v-dialog>

  <ConfirmDialog
    v-model="confirming"
    :title="`Remove ${agent?.name ?? 'this agent'}?`"
    confirm-label="Remove"
    destructive
    :busy="removing"
    @confirm="remove"
  >
    It stops, and its runs and what they found are deleted. Nothing else changes.
  </ConfirmDialog>
</template>

<style scoped>
/* A sheet from the side, as tall as the screen; on a phone as wide as it too, and above the bar
   along the bottom, which stays where it is under the dimmed page. */
.sheet {
  justify-content: flex-end;
}

.sheet > :deep(.v-overlay__content) {
  width: min(34rem, 100%);
  max-width: none;
  height: 100%;
  max-height: 100%;
  margin: 0;
}

@media (max-width: 599.98px) {
  .sheet > :deep(.v-overlay__content) {
    align-self: flex-start;
    height: calc(100% - var(--bottom-bar-height));
    max-height: calc(100% - var(--bottom-bar-height));
  }
}

.sheet__card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding-bottom: env(safe-area-inset-bottom);
}

.sheet__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 0.75rem 0.75rem 1.5rem;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.sheet__title {
  margin: 0;
  overflow-wrap: anywhere;
}

.sheet__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.5rem;
  overflow-y: auto;
}

.sheet__foot {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.sheet__spacer {
  flex: 1;
}

.kinds {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.kinds__legend {
  margin-bottom: 0.5rem;
  padding: 0;
}

.kinds__about {
  margin: -0.5rem 0 0;
}

.kind {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.875rem;
  padding: 0.75rem 1rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 1rem;
  cursor: pointer;
  transition:
    border-color 0.2s,
    background-color 0.2s;
}

.kind:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.kind--on {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}

.kind:has(.kind__input:focus-visible) {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.kind__input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}

.kind__icon {
  display: grid;
  flex: none;
  place-items: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.75rem;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}

.kind__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.allow {
  padding: 1rem 1.25rem;
  border: 1px solid rgba(var(--v-theme-warning), 0.6);
  border-radius: 1rem;
  background: rgba(var(--v-theme-warning), 0.08);
}

.allow__text {
  margin: 0 0 0.5rem;
}
</style>
