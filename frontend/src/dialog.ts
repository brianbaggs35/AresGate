import { watch, type Ref } from 'vue'

/**
 * For a dialog: remembers what had the keyboard when it opened, and gives it back when it has
 * closed (call the returned function when the dialog has left), so that someone who uses the
 * keyboard isn't sent to the top of the page.
 */
export function useKeyboardReturn(open: Readonly<Ref<boolean>>): () => void {
  /** What had the keyboard when the dialog opened. */
  let opener: HTMLElement | null = null

  watch(open, (opening) => {
    // Buttons are HTML elements, and that is what has the keyboard when a dialog is asked for.
    if (opening) opener = document.activeElement as HTMLElement | null
  })

  return () => {
    opener?.focus()
    opener = null
  }
}
