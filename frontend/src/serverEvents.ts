import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/**
 * Listens to a stream of server-sent events for as long as the component is on screen, and calls
 * `onChange` each time the server says something changed. `live` says whether the stream is
 * connected. A browser that has no `EventSource` just isn't live, and the page's own polling goes
 * on. The browser connects again by itself when a stream ends or breaks.
 */
export function useServerEvents(path: string, onChange: () => void): { live: Ref<boolean> } {
  const live = ref(false)
  let source: EventSource | undefined

  onMounted(() => {
    if (typeof EventSource === 'undefined') return
    source = new EventSource(path)
    source.addEventListener('ready', () => {
      live.value = true
    })
    source.addEventListener('changed', onChange)
    source.addEventListener('error', () => {
      live.value = false
    })
  })
  onBeforeUnmount(() => {
    source?.close()
    live.value = false
  })

  return { live }
}
