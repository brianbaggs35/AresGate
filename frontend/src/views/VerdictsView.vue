<script setup lang="ts">
import { CircleCheck, Gavel, RefreshCw, Undo2 } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import {
  changeVerdict,
  fetchVerdicts,
  removeVerdict,
  takeBackVerdicts,
  type Verdict,
  type VerdictChange,
} from '@/api/verdicts'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import SelectBar from '@/components/SelectBar.vue'
import VerdictDialog from '@/components/VerdictDialog.vue'
import VerdictRow from '@/components/VerdictRow.vue'
import { formatCount } from '@/format'
import { useSelection } from '@/selection'
import { useSessionStore } from '@/stores/session'
import { aboutVerdict } from '@/verdicts'

const session = useSessionStore()

const verdicts = ref<Verdict[] | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)

const notice = ref<string | null>(null)
const failure = ref<string | null>(null)
const busy = ref(false)
/** The verdict being changed or taken back. The dialogs keep showing it while they fade out. */
const target = ref<Verdict | null>(null)
const changing = ref(false)
const confirming = ref(false)
/** Which verdicts are picked, to be taken back together, and the dialog that asks first. */
const shown = computed(() => verdicts.value ?? [])
const picks = useSelection(shown)
const confirmingMany = ref(false)
const canPick = computed(() => shown.value.length > 1 || picks.any.value)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    verdicts.value = await session.call(fetchVerdicts)
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

function choose(rule: Verdict, action: 'change' | 'remove') {
  target.value = rule
  notice.value = null
  failure.value = null
  if (action === 'change') changing.value = true
  else confirming.value = true
}

async function save(change: VerdictChange) {
  const rule = target.value as Verdict
  busy.value = true
  failure.value = null
  try {
    const saved = await session.change((token) => changeVerdict(rule.id, change, token))
    verdicts.value = (verdicts.value as Verdict[]).map((item) =>
      item.id === saved.id ? saved : item,
    )
    notice.value = `Changed: ${aboutVerdict(saved)}.`
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
    changing.value = false
  }
}

async function takeBack() {
  const rule = target.value as Verdict
  busy.value = true
  failure.value = null
  try {
    await session.change((token) => removeVerdict(rule.id, token))
    verdicts.value = (verdicts.value as Verdict[]).filter((item) => item.id !== rule.id)
    notice.value = `Taken back: ${aboutVerdict(rule)}.`
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
    confirming.value = false
  }
}

const manyOf = (count: number) => `${formatCount(count)} ${count === 1 ? 'verdict' : 'verdicts'}`

async function takeBackMany() {
  const ids = [...picks.picked.value]
  busy.value = true
  failure.value = null
  notice.value = null
  try {
    const result = await session.change((token) => takeBackVerdicts(ids, token))
    notice.value =
      `Taken back: ${manyOf(result.done)}.` +
      (result.skipped ? ` ${manyOf(result.skipped)} had already gone.` : '')
    picks.clear()
    await load()
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
    confirmingMany.value = false
  }
}

onMounted(load)
</script>

<template>
  <SectionCard
    title="Verdicts"
    description="What you have told AresGate about its alerts. Each is remembered and applied to every signal that matches it, now and from here on, so what you call fine never raises an alarm."
    data-test="verdicts-card"
  >
    <template #actions>
      <v-btn
        variant="text"
        :prepend-icon="RefreshCw"
        :loading="loading"
        data-test="refresh-verdicts"
        @click="load"
      >
        Refresh
      </v-btn>
    </template>

    <output v-if="notice" class="verdicts__notice text-body-large" data-test="verdicts-notice">
      <v-icon :icon="CircleCheck" color="success" aria-hidden="true" />
      {{ notice }}
    </output>
    <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" data-test="verdicts-failure">
      {{ failure }}
    </v-alert>

    <LoadError
      v-if="loadError && !verdicts"
      :message="loadError"
      :loading="loading"
      data-test="verdicts-error"
      @retry="load"
    />
    <template v-else-if="verdicts">
      <SelectBar
        v-if="canPick"
        :count="picks.picked.value.size"
        :whole="picks.wholePage.value"
        singular="verdict"
        plural="verdicts"
        @toggle-all="picks.togglePage()"
        @clear="picks.clear()"
      >
        <v-btn
          variant="tonal"
          color="error"
          density="comfortable"
          :prepend-icon="Undo2"
          data-test="verdicts-take-back-many"
          @click="confirmingMany = true"
        >
          Take back
        </v-btn>
      </SelectBar>
      <ul v-if="verdicts.length" class="verdicts__list" data-test="verdict-list">
        <VerdictRow
          v-for="rule in verdicts"
          :key="rule.id"
          :rule="rule"
          :selectable="canPick"
          :selected="picks.has(rule.id)"
          @select="(range) => picks.toggle(rule.id, range)"
          @change="choose(rule, 'change')"
          @remove="choose(rule, 'remove')"
        />
      </ul>
      <EmptyState
        v-else
        title="You haven't given a verdict yet"
        description="Open an incident and say whether its address or its alerts are not suspicious, low priority or a real threat. AresGate remembers, and they appear here."
        :icon="Gavel"
        data-test="no-verdicts"
      >
        <v-btn
          variant="tonal"
          color="primary"
          :to="{ name: 'incidents' }"
          data-test="see-incidents"
        >
          See incidents
        </v-btn>
      </EmptyState>
    </template>
    <v-skeleton-loader v-else type="list-item-two-line, list-item-two-line" />

    <VerdictDialog v-model="changing" :rule="target" :busy="busy" @save="save" />
    <ConfirmDialog
      v-model="confirming"
      title="Take this verdict back?"
      confirm-label="Take it back"
      destructive
      :busy="busy"
      @confirm="takeBack"
    >
      <template v-if="target">
        <p class="mb-2">{{ aboutVerdict(target) }}</p>
        <p v-if="target.ai" data-test="take-back-ai">
          The AI gave this one. Taking it back also tells it not to give it again.
        </p>
        <p>
          It is judged as if {{ target.ai ? 'it' : 'you' }} had never said it, which means it can
          raise alarms again.
          {{
            target.hits > 0
              ? `${formatCount(target.hits)} ${target.hits === 1 ? 'signal' : 'signals'} it was applied to ${target.hits === 1 ? 'is' : 'are'} judged again in the incidents that are not resolved.`
              : 'It has not been applied to a signal yet.'
          }}
        </p>
      </template>
    </ConfirmDialog>
    <ConfirmDialog
      v-model="confirmingMany"
      :title="`Take back ${manyOf(picks.picked.value.size)}?`"
      confirm-label="Take them back"
      destructive
      :busy="busy"
      @confirm="takeBackMany"
    >
      <p>
        Each is judged as if you had never said it, which means what it kept quiet can raise alarms
        again. Any the AI gave also tell it not to give them again.
      </p>
    </ConfirmDialog>
  </SectionCard>
</template>

<style scoped>
.verdicts__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.verdicts__notice {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
</style>
