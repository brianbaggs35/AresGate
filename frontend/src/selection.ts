import { computed, ref, watch, type Ref } from 'vue'

/**
 * Which of the incidents on a list are picked, for a change to be made to all of them. It is the
 * ones ticked, or everything that matches what the list was asked, which is more than the list
 * shows and so is only said ("all 143"), never listed. Ticking another one, or taking one off,
 * goes back to the ones ticked, since the others can't be told apart from them.
 */
export function useSelection(items: Ref<readonly { id: number }[]>) {
  const picked = ref<ReadonlySet<number>>(new Set())
  /** All that match, whether they are on the list or not. */
  const everything = ref(false)
  /** The one ticked last, which a range of them goes on from. */
  let anchor: number | null = null

  const ids = computed(() => items.value.map(({ id }) => id))
  const onPage = computed(() => ids.value.filter((id) => picked.value.has(id)).length)
  /** Every incident on the list is ticked, and there is something on it. */
  const wholePage = computed(() => ids.value.length > 0 && onPage.value === ids.value.length)
  const any = computed(() => everything.value || picked.value.size > 0)

  /** Whether an incident is picked: ticked, or among all that match. */
  function has(id: number) {
    return everything.value || picked.value.has(id)
  }

  function set(next: Iterable<number>) {
    picked.value = new Set(next)
    everything.value = false
  }

  /** Ticks an incident, or takes it off. With `range`, all between it and the one ticked last
   * are ticked, or taken off, the way that one was left. */
  function toggle(id: number, range = false) {
    const from = range && anchor !== null ? ids.value.indexOf(anchor) : -1
    const to = ids.value.indexOf(id)
    const on = !picked.value.has(id)
    const next = new Set(picked.value)
    if (from >= 0 && to >= 0) {
      const wanted = picked.value.has(anchor as number)
      for (const between of ids.value.slice(Math.min(from, to), Math.max(from, to) + 1)) {
        if (wanted) next.add(between)
        else next.delete(between)
      }
    } else if (on) {
      next.add(id)
    } else {
      next.delete(id)
    }
    anchor = id
    set(next)
  }

  /** Ticks every incident on the list, or if all are ticked already, takes them all off. */
  function togglePage() {
    anchor = null
    set(wholePage.value ? [] : ids.value)
  }

  function pickEverything() {
    anchor = null
    picked.value = new Set(ids.value)
    everything.value = true
  }

  function clear() {
    anchor = null
    set([])
  }

  // An incident that leaves the list (it was dealt with, or the list was narrowed) is no longer
  // ticked, so nothing is changed that is not in front of the person.
  watch(ids, (now) => {
    const here = new Set(now)
    const kept = [...picked.value].filter((id) => here.has(id))
    if (kept.length !== picked.value.size) picked.value = new Set(kept)
    if (anchor !== null && !here.has(anchor)) anchor = null
  })

  return {
    picked,
    everything,
    any,
    onPage,
    wholePage,
    has,
    toggle,
    togglePage,
    pickEverything,
    clear,
  }
}
