<script setup lang="ts">
import { CircleCheck, Undo2 } from '@lucide/vue'
import { computed, ref } from 'vue'

import { errorMessage } from '@/api/client'
import type { IncidentDetail } from '@/api/incidents'
import {
  VERDICTS,
  giveVerdict,
  removeVerdict,
  type Verdict,
  type VerdictKind,
} from '@/api/verdicts'
import SectionCard from '@/components/SectionCard.vue'
import VerdictChip from '@/components/VerdictChip.vue'
import { useSessionStore } from '@/stores/session'
import {
  VERDICT,
  aboutVerdict,
  givenAs,
  scopesOf,
  standing,
  verdictsIn,
  type Scope,
} from '@/verdicts'

/**
 * What the owner thinks of an incident: what the verdicts say of it now, the verdicts that were
 * applied to it, and the means to give another, about its address or one of its alerts, by
 * pressing the verdict. Verdicts are remembered, so it says so, and what they are about.
 */
const props = defineProps<{
  incident: IncidentDetail
  /** Every verdict there is: the ones that apply here are found among them. */
  verdicts: readonly Verdict[]
}>()
const emit = defineEmits<{ changed: [] }>()

const session = useSessionStore()

const scopes = computed(() => scopesOf(props.incident))
const applied = computed(() => verdictsIn(props.incident, props.verdicts))
const chosen = ref<string | null>(null)
/** The scope being used: the one chosen, or else the first. */
const scope = computed(
  () => scopes.value.find(({ key }) => key === chosen.value) ?? scopes.value[0],
)
/** What a choice says under its name in the list. */
const withHint = (choice: Scope) => ({ subtitle: choice.hint })
const note = ref('')
/** What is being done, while it is under way: the verdict being given, or the id of the one
 * being taken back. */
const giving = ref<VerdictKind | null>(null)
const takingBack = ref<number | null>(null)
const notice = ref<string | null>(null)
const failure = ref<string | null>(null)
const busy = computed(() => giving.value !== null || takingBack.value !== null)

async function give(verdict: VerdictKind) {
  // The buttons are only there where there is something to be about.
  const target = scope.value as Scope
  giving.value = verdict
  notice.value = null
  failure.value = null
  try {
    const text = note.value.trim()
    await session.change((token) =>
      giveVerdict({ verdict, ...target.request, ...(text ? { note: text } : {}) }, token),
    )
    notice.value = givenAs(target, verdict)
    note.value = ''
    emit('changed')
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    giving.value = null
  }
}

async function takeBack(verdict: Verdict) {
  takingBack.value = verdict.id
  notice.value = null
  failure.value = null
  try {
    await session.change((token) => removeVerdict(verdict.id, token))
    notice.value = `Taken back: ${aboutVerdict(verdict)}.`
    emit('changed')
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    takingBack.value = null
  }
}
</script>

<template>
  <SectionCard
    title="Your verdict"
    description="Tell AresGate what you think of this. It remembers, and judges everything that matches the same way from now on."
    data-test="verdict-card"
  >
    <div class="verdict-panel__standing">
      <VerdictChip v-if="incident.verdict" :verdict="incident.verdict" />
      <p class="text-body-large" data-test="verdict-standing">{{ standing(incident) }}</p>
    </div>

    <section v-if="applied.length" aria-labelledby="verdict-applied" class="verdict-panel__applied">
      <h3 id="verdict-applied" class="text-title-small">Verdicts that apply here</h3>
      <ul class="verdict-panel__rules">
        <li v-for="rule in applied" :key="rule.id" class="verdict-panel__rule" data-test="applied">
          <VerdictChip :verdict="rule.verdict" size="small" />
          <span class="verdict-panel__about text-body-medium" data-test="applied-about">{{
            aboutVerdict(rule)
          }}</span>
          <v-btn
            variant="text"
            size="small"
            :prepend-icon="Undo2"
            :loading="takingBack === rule.id"
            :disabled="busy && takingBack !== rule.id"
            data-test="take-back"
            @click="takeBack(rule)"
          >
            Take back
          </v-btn>
        </li>
      </ul>
    </section>

    <div v-if="scope" class="verdict-panel__form" data-test="verdict-form">
      <v-select
        :model-value="scope.key"
        :items="scopes"
        item-title="title"
        item-value="key"
        :item-props="withHint"
        label="What is it about?"
        :disabled="busy"
        hide-details
        data-test="verdict-scope"
        @update:model-value="chosen = $event as string"
      />
      <p class="text-body-medium text-medium-emphasis" data-test="verdict-scope-hint">
        {{ scope.hint }}.
      </p>
      <v-text-field
        v-model="note"
        label="Why (optional)"
        maxlength="500"
        :disabled="busy"
        hide-details
        data-test="verdict-note"
      />
      <div class="verdict-panel__choices" role="group" aria-label="Say it is">
        <v-btn
          v-for="kind in VERDICTS"
          :key="kind"
          variant="tonal"
          :color="VERDICT[kind].color"
          :prepend-icon="VERDICT[kind].icon"
          :loading="giving === kind"
          :disabled="busy && giving !== kind"
          :data-test="`give-${kind}`"
          @click="give(kind)"
        >
          {{ VERDICT[kind].label }}
        </v-btn>
      </div>
    </div>
    <p v-else class="text-body-medium text-medium-emphasis" data-test="verdict-unmatchable">
      Nothing in it can be matched later: it names no address, and its signals have no signature.
    </p>

    <output v-if="notice" class="verdict-panel__notice text-body-large" data-test="verdict-notice">
      <v-icon :icon="CircleCheck" color="success" aria-hidden="true" />
      {{ notice }}
    </output>
    <v-alert v-if="failure" type="error" variant="tonal" data-test="verdict-error">
      {{ failure }}
    </v-alert>
  </SectionCard>
</template>

<style scoped>
.verdict-panel__standing {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}

.verdict-panel__standing p,
.verdict-panel__applied h3 {
  margin: 0;
}

.verdict-panel__applied {
  margin-top: 1.25rem;
}

.verdict-panel__rules {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
}

.verdict-panel__rule {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
  padding: 0.375rem 0;
  border-block-start: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.verdict-panel__about {
  flex: 1 1 14rem;
  min-width: 0;
  overflow-wrap: anywhere;
}

.verdict-panel__form {
  display: grid;
  gap: 0.75rem;
  margin-top: 1.5rem;
}

.verdict-panel__form p {
  margin: -0.25rem 0 0;
}

.verdict-panel__choices {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0.5rem;
}

.verdict-panel__notice {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 1rem;
}

@media (min-width: 640px) {
  .verdict-panel__choices {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
