<script setup lang="ts">
import { ChevronDown, Check, ListRestart, Square, SquareCheck, TriangleAlert } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import {
  lookUpField,
  type ConnectionDefinition,
  type Field,
  type LookupEntry,
} from '@/api/integrations'
import { formatList } from '@/format'
import {
  chosenValues,
  joinValues,
  lookupItems,
  settingsFrom,
  suggestedEntries,
  type ConnectionDraft,
} from '@/integrations'
import { useSessionStore } from '@/stores/session'

/**
 * A choice among what the system itself lists, such as the interfaces ntopng should read: a button
 * asks the system (with the address and sign-in as they are filled in, so before anything is
 * saved), and a list then names each one, so nobody has to guess which number is which. Where
 * more than one can be chosen they are chips in the box, kept as their values joined by commas.
 * A saved connection asks once the page opens, and again whenever `refresh` changes (it counts the
 * tests, which find out what the system has now). Nothing chosen is allowed: the system reads
 * every one but a loopback, which the field says. A saved choice that the system no longer has is
 * flagged, with a button that takes it off or chooses what the system lists instead, so one click
 * mends it. A failed ask says why in words and leaves the choice as it was.
 */
const props = defineProps<{
  integration: string
  definition: ConnectionDefinition
  field: Field
  draft: ConnectionDraft
  /** Makes the id of the field's input, which a problem with it moves the keyboard to. */
  id: string
  /** Whether the connection is saved, which is when a choice that has gone is not replaced. */
  saved: boolean
  /** Changes when the system should be asked again, such as after a test that passed. Nothing
   * (or 0) is not a reason to ask. */
  refresh?: number
  errorMessages?: string
}>()
const value = defineModel<string>({ required: true })
/** A request was made to the system, so a log of the requests is out of date. */
const emit = defineEmits<{ asked: [] }>()

/** The most that can be chosen, which is what the API takes. */
const MOST = 16

const session = useSessionStore()

const entries = ref<LookupEntry[]>([])
const message = ref<string | null>(null)
const failed = ref(false)
const working = ref(false)

const ready = computed(() => props.draft.url.trim() !== '')
const values = computed(() => chosenValues(value.value))
const items = computed(() => lookupItems(entries.value, values.value))
const picked = computed(() => entries.value.filter((entry) => values.value.includes(entry.value)))
const missing = computed(() =>
  entries.value.length === 0
    ? []
    : values.value.filter((each) => !entries.value.some((entry) => entry.value === each)),
)
const quiet = computed(() => picked.value.filter((entry) => entry.quiet))
const loopbacks = computed(() => picked.value.filter((entry) => entry.loopback))
/** What is read for someone who chose none, or chooses what the list suggests. */
const suggested = computed(() => suggestedEntries(entries.value, props.field.multiple, MOST))
/** What a saved choice that has gone is replaced by: what is still on the list of what was chosen,
 * or else what the list suggests. */
const remaining = computed(() => values.value.filter((each) => !missing.value.includes(each)))
const mend = computed(() =>
  remaining.value.length > 0 ? remaining.value : suggested.value.map((entry) => entry.value),
)
const mendLabel = computed(() => {
  if (remaining.value.length > 0) {
    return missing.value.length > 1 ? 'Take them off' : 'Take it off'
  }
  return `Use ${formatList(suggested.value.map((entry) => entry.label))}`
})

// What was listed belongs to the address it was listed at.
watch(
  () => props.draft.url,
  () => {
    entries.value = []
    message.value = null
    failed.value = false
  },
)

/** The words about a saved choice that the list no longer has. */
const goneText = computed(() => {
  const ids = missing.value.join(', ')
  if (!props.field.multiple) {
    return `The saved choice (ID ${ids}) isn't on the list ${props.definition.label} gave now. Choose one from it.`
  }
  const several = missing.value.length > 1
  return `${several ? 'The saved choices (IDs' : 'The saved choice (ID'} ${ids}) ${several ? "aren't" : "isn't"} on the list ${props.definition.label} gave now. Take ${several ? 'them' : 'it'} off, or choose from the list.`
})

/** The words about loopbacks: they only carry the machine's traffic to itself. */
function loopbackText(found: readonly LookupEntry[]): string {
  const names = formatList(found.map(({ label }) => label))
  return found.length > 1
    ? `${names} are loopbacks, which normally have nothing worth reading.`
    : `${names} is the loopback, which normally has nothing worth reading.`
}

/** Says what is read when nothing is chosen, from what the list holds. */
const defaultText = computed(() => {
  const names = formatList(suggested.value.map(({ label }) => label))
  const left = entries.value.filter((entry) => entry.loopback && !suggested.value.includes(entry))
  const aside = left.length > 0 ? ` ${loopbackText(left)}` : ''
  return `Nothing is chosen, so AresGate reads ${names}.${aside}`
})

/** The words about a choice that has seen nothing. */
const quietText = computed(() => {
  const names = formatList(quiet.value.map(({ label }) => label))
  if (!props.field.multiple) {
    return `${names} hasn't seen any traffic yet, so nothing will come in from it until it does. If it isn't the one you mean, choose another.`
  }
  const several = quiet.value.length > 1
  const all = quiet.value.length === picked.value.length
  return `${names} ${several ? "haven't" : "hasn't"} seen any traffic yet, so nothing will come in from ${several ? 'them' : 'it'} until ${several ? 'they do' : 'it does'}.${all ? " If that isn't what you mean, choose another." : ''}`
})

/** Nothing chosen, or a choice that isn't on the list, is replaced, for a connection that wasn't
 * saved yet, by what the list suggests (every one but a loopback, or the first that has seen
 * traffic where only one can be chosen): the choice a person looking at the list would make. */
function preselect(found: readonly LookupEntry[]) {
  if (props.saved || found.length === 0) return
  if (found.some((entry) => values.value.includes(entry.value))) return
  value.value = joinValues(suggestedEntries(found, props.field.multiple, MOST).map((e) => e.value))
}

/** Mends a saved choice that has gone, in one click. */
function mendChoice() {
  value.value = joinValues(mend.value)
}

/** A choice from the select, kept as the field holds it. */
function choose(chosen: string | string[] | null) {
  value.value = Array.isArray(chosen) ? joinValues(chosen) : (chosen ?? '')
}

async function ask() {
  working.value = true
  message.value = null
  failed.value = false
  try {
    const result = await session.change((token) =>
      lookUpField(
        props.integration,
        props.definition.key,
        props.field.key,
        settingsFrom(props.definition, props.draft),
        token,
      ),
    )
    entries.value = result.entries
    message.value = result.message
    failed.value = !result.ok
    preselect(result.entries)
  } catch (error) {
    entries.value = []
    message.value = errorMessage(error)
    failed.value = true
  } finally {
    working.value = false
    emit('asked')
  }
}

// A test that passed has found out what the system has now, so the list is asked again to match
// it.
watch(
  () => props.refresh,
  (next) => {
    if (next && props.saved && ready.value && !working.value) void ask()
  },
)

onMounted(() => {
  if (props.saved && ready.value) void ask()
})
</script>

<template>
  <div class="lookup" :data-test="`field-${field.key}`">
    <v-select
      :id="id"
      :model-value="field.multiple ? values : (values[0] ?? null)"
      :label="field.label"
      :items="items"
      :multiple="field.multiple"
      :chips="field.multiple"
      :menu-icon="ChevronDown"
      :no-data-text="`Press ${field.action} to list them.`"
      :hint="field.help || undefined"
      persistent-hint
      :error-messages="errorMessages"
      :loading="working"
      data-test="lookup-select"
      @update:model-value="choose"
    >
      <!-- Where several can be chosen, a picture of a box says what is chosen: the select's own
           checkbox is a control inside an option, which a screen reader cannot use. The list
           item gives itself the role of an option and says whether it is selected. -->
      <template v-if="field.multiple" #item="{ props: itemProps }">
        <v-list-item v-bind="itemProps">
          <template #prepend="{ isSelected }">
            <v-icon :icon="isSelected ? SquareCheck : Square" data-test="lookup-box" />
          </template>
        </v-list-item>
      </template>
    </v-select>
    <div class="lookup__actions">
      <v-btn
        variant="tonal"
        :prepend-icon="ListRestart"
        :loading="working"
        :disabled="!ready || working"
        data-test="lookup-fetch"
        @click="ask"
      >
        {{ field.action }}
      </v-btn>
      <p v-if="!ready" class="text-body-medium text-medium-emphasis" data-test="lookup-needs-url">
        Fill in the address and how to sign in first.
      </p>
    </div>
    <output
      v-if="message && !failed"
      class="lookup__message text-body-medium text-medium-emphasis"
      data-test="lookup-message"
    >
      {{ message }}
    </output>
    <v-alert
      v-if="failed && message"
      type="error"
      variant="tonal"
      density="compact"
      data-test="lookup-error"
    >
      {{ message }}
    </v-alert>
    <v-alert
      v-else-if="missing.length > 0"
      type="warning"
      variant="tonal"
      density="compact"
      :icon="TriangleAlert"
      data-test="lookup-gone"
    >
      {{ goneText }}
      <template v-if="mend.length > 0" #append>
        <v-btn
          variant="tonal"
          size="small"
          :prepend-icon="Check"
          data-test="lookup-mend"
          @click="mendChoice"
        >
          {{ mendLabel }}
        </v-btn>
      </template>
    </v-alert>
    <v-alert
      v-else-if="field.multiple && values.length === 0 && suggested.length > 0"
      type="info"
      variant="tonal"
      density="compact"
      data-test="lookup-default"
    >
      {{ defaultText }}
    </v-alert>
    <v-alert
      v-else-if="quiet.length > 0"
      type="warning"
      variant="tonal"
      density="compact"
      :icon="TriangleAlert"
      data-test="lookup-quiet"
    >
      {{ quietText }}
    </v-alert>
    <v-alert
      v-if="loopbacks.length > 0"
      type="info"
      variant="tonal"
      density="compact"
      data-test="lookup-loopback"
    >
      {{ loopbackText(loopbacks) }}
    </v-alert>
  </div>
</template>

<style scoped>
.lookup {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.lookup__message {
  display: block;
}

.lookup__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
</style>
