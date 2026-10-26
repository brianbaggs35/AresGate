import { ref, watch, type Ref } from 'vue'

/**
 * Where the keys take a readout that is on position `current` of `count` (or on none): the arrows
 * step through them, Home and End go to the ends and Escape puts the readout away (`null`). Any
 * other key is not for the chart (`undefined`).
 */
export function stepIndex(
  key: string,
  current: number | null,
  count: number,
): number | null | undefined {
  switch (key) {
    case 'ArrowRight':
    case 'ArrowDown':
      return current === null ? 0 : Math.min(count - 1, current + 1)
    case 'ArrowLeft':
    case 'ArrowUp':
      return current === null ? count - 1 : Math.max(0, current - 1)
    case 'Home':
      return 0
    case 'End':
      return count - 1
    case 'Escape':
      return null
    default:
      return undefined
  }
}

/** How wide an element is, kept up to date as it changes, so a chart can draw at the size it
 * has. The element comes and goes (the chart is swapped for its table and back), so this follows
 * whichever is there. `fallback` is the width until it is measured. */
export function useElementWidth(target: Ref<HTMLElement | null>, fallback: number): Ref<number> {
  const width = ref(fallback)
  watch(
    target,
    (element, _before, onCleanup) => {
      if (!element) return
      const measure = () => {
        width.value = element.clientWidth || fallback
      }
      measure()
      const observer = new ResizeObserver(measure)
      observer.observe(element)
      onCleanup(() => {
        observer.disconnect()
      })
    },
    { flush: 'post', immediate: true },
  )
  return width
}
