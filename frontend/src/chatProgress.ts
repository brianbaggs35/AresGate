import { ref } from 'vue'

import type { AnswerEvent, ChatLookup } from '@/api/aiChat'

/** What can be shown of an answer while it is being made: what it has looked at, and what it has
 * written so far. */
export function useAnswerProgress() {
  const looked = ref<ChatLookup[]>([])
  const writing = ref('')

  function reset() {
    looked.value = []
    writing.value = ''
  }

  function follow(event: AnswerEvent) {
    if (event.kind === 'looked') looked.value.push(event.lookup)
    else if (event.kind === 'wrote') writing.value += event.text
    else writing.value = ''
  }

  return { looked, writing, reset, follow }
}
