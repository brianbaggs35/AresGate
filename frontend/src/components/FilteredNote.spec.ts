import FilteredNote from '@/components/FilteredNote.vue'
import { attention } from '@/test/dashboard'
import { mountWithPlugins } from '@/test/mount'

const SINCE = '2026-11-01T10:00:00Z'

async function open(
  counted = attention({ incidents: 12, unsure: 7, muted: 3, handled: 1, needs_you: 1 }),
) {
  const mounted = await mountWithPlugins(FilteredNote, {
    signedIn: 'admin',
    withApp: true,
    props: { attention: counted, since: SINCE, lastWords: 'the last 24 hours' },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find, text: (selector: string) => find(selector).text() }
}

describe('FilteredNote', () => {
  it('says how many incidents there were, how many need you and how many were filtered out', async () => {
    const { text } = await open()

    expect(text('filtered-summary')).toBe(
      '12 incidents in the last 24 hours: 1 needs you, 11 filtered out.',
    )
  })

  it('says it in the singular, and in the plural for nothing', async () => {
    const one = await open(attention({ incidents: 1, needs_you: 1 }))
    expect(one.text('filtered-summary')).toBe(
      '1 incident in the last 24 hours: 1 needs you, 0 filtered out.',
    )
    expect(one.wrapper.find('ul').exists()).toBe(false)

    const none = await open(attention({ incidents: 3, unsure: 3 }))
    expect(none.text('filtered-summary')).toContain('0 need you')
  })

  it('has a link for each reason there is a count for, named by what it shows', async () => {
    const { find, text, wrapper } = await open()

    expect(text('filtered-unsure')).toBe('7 not sure enough')
    expect(find('filtered-unsure').attributes('aria-label')).toBe('7 not sure enough: see them')
    expect(find('filtered-muted').attributes('href')).toContain('/incidents?')
    expect(wrapper.findAll('li')).toHaveLength(3)
  })

  it('leaves out the reasons nothing was filtered for', async () => {
    const { find } = await open(attention({ incidents: 4, unsure: 4 }))

    expect(find('filtered-unsure').exists()).toBe(true)
    expect(find('filtered-muted').exists()).toBe(false)
    expect(find('filtered-handled').exists()).toBe(false)
  })

  it('is a named region', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('section').attributes('aria-labelledby')).toBe('filtered-title')
  })
})
