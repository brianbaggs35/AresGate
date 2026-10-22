import type { SubmitEventPromise } from 'vuetify'

import { isValid } from '@/form'

/** What a form hands its submit handler: the event, which also says how the checks went. */
const submitted = (valid: boolean, errors: { id: string; errorMessages: string[] }[] = []) =>
  Promise.resolve({ valid, errors }) as unknown as SubmitEventPromise

describe('isValid', () => {
  let field: HTMLInputElement

  beforeEach(() => {
    field = document.createElement('input')
    field.id = 'input-1'
    document.body.append(field)
  })

  afterEach(() => {
    field.remove()
  })

  it('says a form that passed its checks is valid, and leaves the focus alone', async () => {
    await expect(isValid(submitted(true))).resolves.toBe(true)
    expect(document.activeElement).not.toBe(field)
  })

  it('says a form that failed is not, and focuses the first field with a problem', async () => {
    const errors = [
      { id: 'input-1', errorMessages: ['Enter your username.'] },
      { id: 'input-2', errorMessages: ['Enter your password.'] },
    ]
    await expect(isValid(submitted(false, errors))).resolves.toBe(false)
    expect(document.activeElement).toBe(field)
  })

  it('copes with a problem it can’t find a field for', async () => {
    await expect(isValid(submitted(false))).resolves.toBe(false)
    await expect(isValid(submitted(false, [{ id: 'gone', errorMessages: ['x'] }]))).resolves.toBe(
      false,
    )
  })
})
