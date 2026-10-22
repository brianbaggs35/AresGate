import type { Directive } from 'vue'
import type { SubmitEventPromise } from 'vuetify'

/**
 * Whether a form passed its checks. If it didn't, the first field with a problem gets the
 * keyboard's focus, which is where people who can't see the page need to be told to look.
 */
export async function isValid(event: SubmitEventPromise): Promise<boolean> {
  const { valid, errors } = await event
  if (!valid) document.getElementById(String(errors[0]?.id))?.focus()
  return valid
}

/**
 * `v-focus` on a field puts the keyboard in it when it shows. Vuetify's own `autofocus` focuses
 * the field a second time, 50 milliseconds after the page notices it, which takes the focus back
 * from whatever someone has tabbed to by then.
 */
export const vFocus: Directive<HTMLElement> = {
  mounted(element) {
    element.querySelector('input')?.focus()
  },
}
