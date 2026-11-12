import AssetIdentity from '@/components/AssetIdentity.vue'
import { identity } from '@/test/assets'
import { mountWithPlugins } from '@/test/mount'

async function open(item = identity()) {
  const mounted = await mountWithPlugins(AssetIdentity, { props: { identity: item } })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('AssetIdentity', () => {
  it('names what it is, who said so and when it was asked', async () => {
    const { find } = await open()

    expect(find('identity-name').text()).toBe('Apple iPhone 16')
    expect(find('identity-source').text()).toContain('Said by Fingerbank, checked')
    expect(find('identity-source').find('time').attributes('datetime')).toBe('2026-11-01T11:00:00Z')
  })

  it('lists the steps from the widest kind to the model', async () => {
    const { find } = await open()

    const steps = find('identity-steps')
      .findAll('li')
      .map((step) => step.text())
    expect(steps).toEqual([
      'Phone, Tablet, or Wearable',
      'Apple iOS, macOS, and tvOS',
      'Apple iPhone',
      'Apple iPhone 16',
    ])
  })

  it('has no steps when the path is one step or none', async () => {
    const { find } = await open(identity({ path: 'Apple iPhone 16' }))
    expect(find('identity-steps').exists()).toBe(false)

    const { find: bare } = await open(identity({ path: null }))
    expect(bare('identity-steps').exists()).toBe(false)
  })

  it('shows the maker, the operating system and how sure it is in words and in numbers', async () => {
    const { find } = await open()

    expect(find('identity-maker').text()).toBe('Apple, Inc.')
    expect(find('identity-os').text()).toBe('Apple iOS')
    expect(find('identity-score').text()).toContain('High')
    expect(find('identity-score').text()).toContain('72 of 100')
  })

  it('leaves out what Fingerbank did not say', async () => {
    const { find } = await open(
      identity({ manufacturer: null, operating_system: null, score: null }),
    )

    expect(find('identity-maker').exists()).toBe(false)
    expect(find('identity-os').exists()).toBe(false)
    expect(find('identity-score').exists()).toBe(false)
  })

  it('names the last step when Fingerbank gave no model name', async () => {
    const { find } = await open(identity({ name: null }))

    expect(find('identity-name').text()).toBe('Apple iPhone 16')
  })

  it('says when Fingerbank has no match, and that it asks again', async () => {
    const { find } = await open(
      identity({
        state: 'unknown',
        name: null,
        path: null,
        manufacturer: null,
        operating_system: null,
        score: null,
      }),
    )

    expect(find('identity-none').text()).toBe('No match')
    expect(find('identity-source').text()).toContain('Asked of Fingerbank')
    expect(find('identity-unknown').text()).toContain('asked again after a week')
    expect(find('identity-steps').exists()).toBe(false)
  })

  it('says why a device was asked about', async () => {
    const { find } = await open()
    expect(find('identity-reason').text()).toBe('Asked about because it is one of your devices.')

    const { find: threat } = await open(identity({ reason: 'incident' }))
    expect(threat('identity-reason').text()).toContain('in an incident or threat')
  })
})
