import ClearedCard from '@/components/ClearedCard.vue'
import { clearedItem } from '@/test/cleared'
import { mountWithPlugins } from '@/test/mount'
import type { ClearedItem } from '@/api/aiCleared'

async function open(item: ClearedItem = clearedItem(), selected = false) {
  const mounted = await mountWithPlugins(ClearedCard, {
    signedIn: 'admin',
    props: { item, selected, busy: false },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('ClearedCard', () => {
  it('says what the AI made of a suggestion, how sure and why', async () => {
    const { find, wrapper } = await open()

    expect(find('cleared-state').text()).toBe('Waiting for you')
    expect(find('cleared-verdict').text()).toBe('Not suspicious')
    expect(find('cleared-confidence').text()).toBe('91% sure')
    expect(find('cleared-reason').text()).toContain('It is the scanner the owner runs.')
    expect(find('cleared-by').text()).toContain('Anthropic (claude-haiku-5-5)')
    expect(find('cleared-link').attributes('href')).toBe('/incidents/4')
    expect(find('cleared-about').text()).toContain('93.184.216.34 · medium · open')
    expect(wrapper.find('[data-test="cleared-card"]').attributes('data-kind')).toBe('waiting')
  })

  it('shows what it looked at', async () => {
    const { find } = await open()

    expect(find('cleared-story').text()).toBe('It tried a port and went away.')
    expect(find('cleared-observations').text()).toContain('Three connection attempts')
    expect(find('cleared-checks').text()).toContain('research scanner')
  })

  it('leaves out what it has no word for', async () => {
    const { find } = await open(
      clearedItem({
        kind: 'cleared',
        reason: null,
        confidence: null,
        provider: null,
        model: null,
        story: null,
        checks: [],
        observations: [],
      }),
    )

    expect(find('cleared-state').text()).toBe('Cleared by the AI')
    expect(find('cleared-reason').exists()).toBe(false)
    expect(find('cleared-confidence').exists()).toBe(false)
    expect(find('cleared-evidence').exists()).toBe(false)
    expect(find('cleared-by').text()).toContain('The AI,')
  })

  it('shows only the story, or only the checks, when that is all there is', async () => {
    const story = await open(clearedItem({ checks: [], observations: [] }))
    expect(story.find('cleared-story').exists()).toBe(true)
    expect(story.find('cleared-checks').exists()).toBe(false)
    expect(story.find('cleared-observations').exists()).toBe(false)

    const checks = await open(clearedItem({ story: null, observations: [] }))
    expect(checks.find('cleared-story').exists()).toBe(false)
    expect(checks.find('cleared-checks').exists()).toBe(true)
  })

  it('says so when the incident is gone', async () => {
    const { find } = await open(clearedItem({ kind: 'cleared', incident: null }))

    expect(find('cleared-gone').text()).toBe('An incident that is gone')
    expect(find('cleared-link').exists()).toBe(false)
    expect(find('cleared-about').exists()).toBe(false)
  })

  it('offers the other verdict, whichever the AI gave', async () => {
    const waiting = await open()
    expect(waiting.find('cleared-other').text()).toBe('Clear as low priority')

    const low = await open(clearedItem({ kind: 'cleared', verdict: 'low_priority' }))
    expect(low.find('cleared-other').text()).toBe('Change to not suspicious')
    expect(low.find('cleared-confirm').text()).toBe('Confirm')
    expect(low.find('cleared-take-back').text()).toBe('Take back')
  })

  it('says what it does, and passes it on', async () => {
    const { find, wrapper } = await open()
    expect(find('cleared-confirm').text()).toBe('Clear it')
    expect(find('cleared-take-back').text()).toBe('Not nothing')

    await find('cleared-confirm').trigger('click')
    await find('cleared-other').trigger('click')
    await find('cleared-take-back').trigger('click')
    await find('cleared-pick').setValue(true)
    await find('cleared-pick').setValue(false)

    expect(wrapper.emitted('confirm')).toHaveLength(1)
    expect(wrapper.emitted('change')).toEqual([['low_priority']])
    expect(wrapper.emitted('take-back')).toHaveLength(1)
    expect(wrapper.emitted('select')).toEqual([[true], [false]])
  })

  it('shows it is picked', async () => {
    const { wrapper } = await open(clearedItem(), true)

    expect(wrapper.find('[data-test="cleared-pick"]').element).toHaveProperty('checked', true)
    expect(wrapper.find('.cleared--picked').exists()).toBe(true)
  })
})
