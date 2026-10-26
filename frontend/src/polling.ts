import { onBeforeUnmount, onMounted } from 'vue'

/**
 * Runs `task` every `everyMs` for as long as the component is on screen and the page is in view.
 * A page in a background tab waits, and asks at once when it comes back if it has been longer
 * than that. The first run is the caller's to make.
 */
export function usePolling(task: () => unknown, everyMs: number): void {
  let timer: ReturnType<typeof setInterval> | undefined
  let lastRun = Date.now()

  const run = () => {
    lastRun = Date.now()
    void task()
  }
  const visible = () => document.visibilityState === 'visible'
  const tick = () => {
    if (visible()) run()
  }
  const returned = () => {
    if (visible() && Date.now() - lastRun >= everyMs) run()
  }

  onMounted(() => {
    lastRun = Date.now()
    timer = setInterval(tick, everyMs)
    document.addEventListener('visibilitychange', returned)
  })
  onBeforeUnmount(() => {
    clearInterval(timer)
    document.removeEventListener('visibilitychange', returned)
  })
}
