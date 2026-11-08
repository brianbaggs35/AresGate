import ThreatEffect from '@/components/ThreatEffect.vue'
import { mountWithPlugins } from '@/test/mount'
import { threatPreview } from '@/test/threats'

const QUIET = {
  preview: null,
  changed: false,
  loading: false,
  saving: false,
  failure: null,
  saved: false,
}

async function show(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(ThreatEffect, { props: { ...QUIET, ...props } })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('ThreatEffect', () => {
  it('asks for a change when there is none to show', async () => {
    const { find } = await show()

    expect(find('effect-idle').text()).toBe('Change something above to see what it would do.')
    expect(find('effect-table').exists()).toBe(false)
    expect(find('effect-save').attributes('disabled')).toBeDefined()
    expect(find('effect-discard').attributes('disabled')).toBeDefined()
  })

  it('says it could not be worked out when the page differs and there is no answer', async () => {
    const { find } = await show({ changed: true })

    expect(find('effect-idle').text()).toBe("It couldn't be worked out.")
    expect(find('effect-save').attributes('disabled')).toBeUndefined()
  })

  it('sets the lanes as they are beside what they would be', async () => {
    const { find, wrapper } = await show({ preview: threatPreview(), changed: true })

    expect(find('effect-sentence').text()).toBe(
      'Saving would change the lanes by +1 threat, −1 suspect.',
    )
    expect(find('effect-threats').find('[data-test="effect-now"]').text()).toBe('2')
    expect(find('effect-threats').find('[data-test="effect-after"]').text()).toBe('3')
    expect(wrapper.findAll('.effect__changed')).toHaveLength(2)
    expect(find('effect-idle').exists()).toBe(false)
  })

  it('does not mark a figure that stays as it is', async () => {
    const { wrapper } = await show({
      preview: threatPreview({ after: threatPreview().now }),
      changed: true,
    })

    expect(wrapper.findAll('.effect__changed')).toHaveLength(0)
  })

  it('shows that it is working, without saying it could not be worked out', async () => {
    const { find, wrapper } = await show({ loading: true, changed: true })

    expect(wrapper.find('[role="progressbar"]').exists()).toBe(true)
    expect(find('effect-idle').exists()).toBe(false)
  })

  it('saves and discards on request', async () => {
    const { find, wrapper } = await show({ preview: threatPreview(), changed: true })

    await find('effect-save').trigger('click')
    await find('effect-discard').trigger('click')

    expect(wrapper.emitted('save')).toHaveLength(1)
    expect(wrapper.emitted('discard')).toHaveLength(1)
  })

  it('says what went wrong, and that a save went through', async () => {
    const failed = await show({ failure: "Can't reach AresGate.", changed: true })
    expect(failed.find('effect-failure').text()).toBe("Can't reach AresGate.")

    const saved = await show({ saved: true })
    expect(saved.find('effect-saved').text()).toContain('Saved.')
  })
})
