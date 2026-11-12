import { defineStore } from 'pinia'
import { ref } from 'vue'

import { fetchWaiting } from '@/api/review'
import { useSessionStore } from '@/stores/session'

/** How many of the AI's decisions wait for the owner, for the menu's badge and the dashboard. */
export const useReviewStore = defineStore('review', () => {
  const session = useSessionStore()
  const waiting = ref(0)

  /** Asks again. A count that could not be had is left as it was: it is a nicety, and the page
   * it points to says what went wrong. */
  async function refresh() {
    try {
      waiting.value = (await session.call(fetchWaiting)).waiting
    } catch {
      // Keep what is shown.
    }
  }

  /** Says the count, when a page that has it fresh knows better. */
  function set(count: number) {
    waiting.value = count
  }

  return { waiting, refresh, set }
})
