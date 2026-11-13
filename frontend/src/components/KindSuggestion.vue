<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'

import { errorMessage } from '@/api/client'
import { callFamily, dismissSuggestion, type Suggestion } from '@/api/threats'
import { useSessionStore } from '@/stores/session'
import { OWNER_CALL } from '@/threats'

/**
 * What AresGate offers to do about a kind of incident from what you have decided of its
 * incidents: stop raising it when you keep closing it as benign, or never set it aside when it
 * was set aside and you keep taking it up. It is never done by itself: nothing changes until you
 * say yes, and a kind you say not now to is offered again only when you have decided twice as
 * many of its incidents.
 */
const props = defineProps<{
  id: number
  suggestion: Suggestion
  /** The kind's words, with a link to its page, where it is not the page that is open. */
  label?: string
}>()
const emit = defineEmits<{ changed: [] }>()

const session = useSessionStore()
const busy = ref<'take' | 'dismiss' | null>(null)
const failure = ref<string | null>(null)

const title = () =>
  props.suggestion.call === 'background'
    ? 'Always treat this kind as background?'
    : 'Never set this kind aside?'

function moves(): string {
  const { moves: count, call } = props.suggestion
  const incidents = `${count.toString()} ${count === 1 ? 'incident' : 'incidents'}`
  return call === 'background'
    ? `That would set aside ${incidents} that ${count === 1 ? 'is' : 'are'} going on now.`
    : `That would bring ${incidents} that ${count === 1 ? 'is' : 'are'} set aside back into view.`
}

/** Takes the offer: it becomes your word on the kind. */
async function take() {
  busy.value = 'take'
  failure.value = null
  try {
    await session.change((token) => callFamily(props.id, props.suggestion.call, token))
    emit('changed')
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = null
  }
}

/** Says not now: the offer goes until you have decided more. */
async function dismiss() {
  busy.value = 'dismiss'
  failure.value = null
  try {
    await session.change((token) => dismissSuggestion(props.id, token))
    emit('changed')
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <v-alert
    type="info"
    variant="tonal"
    :icon="OWNER_CALL[suggestion.call].icon"
    :title="title()"
    class="suggestion"
    data-test="suggestion"
  >
    <p v-if="label" class="suggestion__kind text-body-large" data-test="suggestion-kind">
      <RouterLink :to="{ name: 'family', params: { id } }">{{ label }}</RouterLink>
    </p>
    <p class="text-body-large" data-test="suggestion-reason">{{ suggestion.reason }}</p>
    <p class="text-body-medium" data-test="suggestion-moves">
      {{ moves() }} Nothing changes unless you say so.
    </p>
    <p
      v-if="failure"
      class="text-body-medium suggestion__failure"
      role="alert"
      data-test="suggestion-failure"
    >
      {{ failure }}
    </p>
    <div class="suggestion__actions">
      <v-btn
        color="primary"
        variant="flat"
        :loading="busy === 'take'"
        :disabled="busy !== null"
        data-test="suggestion-take"
        @click="take"
      >
        {{ OWNER_CALL[suggestion.call].button }}
      </v-btn>
      <v-btn
        variant="text"
        :loading="busy === 'dismiss'"
        :disabled="busy !== null"
        data-test="suggestion-dismiss"
        @click="dismiss"
      >
        Not now
      </v-btn>
    </div>
  </v-alert>
</template>

<style scoped>
.suggestion__kind {
  margin: 0 0 0.25rem;
  overflow-wrap: anywhere;
}

.suggestion__failure {
  margin: 0.5rem 0 0;
}

.suggestion__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
</style>
