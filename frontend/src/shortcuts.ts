import { onBeforeUnmount, onMounted } from 'vue'

/** The keys the app answers to, for the page that lists them (`ShortcutsDialog`). A key that only
 * does something on one page says which. */
export interface Shortcut {
  keys: readonly string[]
  does: string
  page: 'Everywhere' | 'Incidents' | 'Logs'
}

export const SHORTCUTS: readonly Shortcut[] = [
  { keys: ['Ctrl', 'K'], does: 'Open the command palette (⌘ K on a Mac)', page: 'Everywhere' },
  { keys: ['?'], does: 'Show these shortcuts', page: 'Everywhere' },
  { keys: ['/'], does: 'Go to the search box', page: 'Incidents' },
  { keys: ['J'], does: 'Move to the next incident', page: 'Incidents' },
  { keys: ['K'], does: 'Move to the previous incident', page: 'Incidents' },
  { keys: ['Enter'], does: 'Open the incident you are on', page: 'Incidents' },
  { keys: ['X'], does: 'Pick the incident you are on, or take it off', page: 'Incidents' },
  { keys: ['/'], does: 'Go to the search box', page: 'Logs' },
  { keys: ['↑', '↓'], does: 'Move through the events', page: 'Logs' },
  { keys: ['Enter'], does: 'Open the event you are on', page: 'Logs' },
]

/** Whether a key pressed on this goes into a field, and so is not a shortcut. */
export function typingIn(target: EventTarget | null): boolean {
  return (
    target instanceof Element &&
    target.closest('input, textarea, select, [contenteditable]') !== null
  )
}

/** Whether a dialog, sheet or menu is over the page: what is under it is not what a key is for. */
export function overlayOpen(): boolean {
  return document.querySelector('.v-overlay--active') !== null
}

/**
 * Answers to single keys for as long as the component is on screen. A key with Ctrl, ⌘ or Alt is
 * the browser's, one typed into a field is the field's, and none is answered while something is
 * over the page.
 */
export function useShortcuts(handlers: Readonly<Record<string, () => void>>): void {
  function onKey(event: KeyboardEvent) {
    if (event.ctrlKey || event.metaKey || event.altKey) return
    if (typingIn(event.target) || overlayOpen()) return
    const run = handlers[event.key]
    if (!run) return
    event.preventDefault()
    run()
  }

  onMounted(() => {
    window.addEventListener('keydown', onKey)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('keydown', onKey)
  })
}
