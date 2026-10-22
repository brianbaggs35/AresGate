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
