<script setup lang="ts">
import { ChevronDown, ListRestart, TriangleAlert } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import {
  lookUpField,
  type ConnectionDefinition,
  type Field,
  type LookupEntry,
} from '@/api/integrations'
import { lookupItems, settingsFrom, type ConnectionDraft } from '@/integrations'
import { useSessionStore } from '@/stores/session'

/**
 * A choice among what the system itself lists, such as the interface ntopng should read: a button
 * asks the system (with the address and sign-in as they are filled in, so before anything is
 * saved), and a list then names each one, so nobody has to guess which number is which. A saved
 * connection asks once the page opens. A failed ask says why in words and leaves the choice as it
 * was.
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
  errorMessages?: string
}>()
const value = defineModel<string>({ required: true })
/** A request was made to the system, so a log of the requests is out of date. */
const emit = defineEmits<{ asked: [] }>()

const session = useSessionStore()

const entries = ref<LookupEntry[]>([])
const message = ref<string | null>(null)
const failed = ref(false)
const working = ref(false)

const ready = computed(() => props.draft.url.trim() !== '')
const items = computed(() => lookupItems(entries.value, value.value))
const chosen = computed(() => entries.value.find((entry) => entry.value === value.value))
const gone = computed(() => entries.value.length > 0 && chosen.value === undefined)

// What was listed belongs to the address it was listed at.
watch(
  () => props.draft.url,
  () => {
    entries.value = []
    message.value = null
    failed.value = false
  },
)

/** A choice that isn't on the list is replaced, for a connection that wasn't saved yet, by the
 * first one that has seen something: the one a person looking at the list would pick. */
function preselect(found: readonly LookupEntry[]) {
  const [first] = found
  if (props.saved || first === undefined || found.some((entry) => entry.value === value.value)) {
    return
  }
  value.value = (found.find((entry) => !entry.quiet) ?? first).value
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

onMounted(() => {
  if (props.saved && ready.value) void ask()
})
</script>

<template>
  <div class="lookup" :data-test="`field-${field.key}`">
    <v-select
      :id="id"
      :model-value="value || null"
      :label="field.label"
      :items="items"
      :menu-icon="ChevronDown"
      :no-data-text="`Press ${field.action} to list them.`"
      :hint="field.help || undefined"
      persistent-hint
      :error-messages="errorMessages"
      :loading="working"
      data-test="lookup-select"
      @update:model-value="value = $event ?? ''"
    />
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
    <p
      v-if="message && !failed"
      class="text-body-medium text-medium-emphasis"
      role="status"
      data-test="lookup-message"
    >
      {{ message }}
    </p>
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
      v-else-if="gone"
      type="warning"
      variant="tonal"
      density="compact"
      :icon="TriangleAlert"
      data-test="lookup-gone"
    >
      The saved choice (ID {{ value }}) isn't on the list {{ definition.label }} gave now. Choose
      one from it.
    </v-alert>
    <v-alert
      v-else-if="chosen?.quiet"
      type="warning"
      variant="tonal"
      density="compact"
      :icon="TriangleAlert"
      data-test="lookup-quiet"
    >
      {{ chosen.label }} hasn't seen any traffic yet, so nothing will come in from it until it does.
      If it isn't the one you mean, choose another.
    </v-alert>
  </div>
</template>

<style scoped>
.lookup {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.lookup__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
</style>
