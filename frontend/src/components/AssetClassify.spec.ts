import * as assetsApi from '@/api/assets'
import { ApiError } from '@/api/client'
import AssetClassify from '@/components/AssetClassify.vue'
import { asset, kindGroups, profile } from '@/test/assets'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open(item = asset(), kinds: Error | ReturnType<typeof kindGroups> = kindGroups()) {
  const fetchKinds = vi.spyOn(assetsApi, 'fetchKinds')
  if (kinds instanceof Error) fetchKinds.mockRejectedValue(kinds)
  else fetchKinds.mockResolvedValue(kinds)
  const classify = vi.spyOn(assetsApi, 'classifyAsset').mockResolvedValue(profile())
  const unclassify = vi.spyOn(assetsApi, 'unclassifyAsset').mockResolvedValue(undefined)
  const mounted = await mountWithPlugins(AssetClassify, {
    signedIn: 'admin',
    props: { asset: item },
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const choices = () => mounted.wrapper.findAll('[data-test="asset-kind-choice"]')
  const choose = async (label: string) => {
    const found = choices().find((each) => each.text() === label)
    await found?.trigger('click')
  }
  const type = async (text: string) => {
    await mounted.wrapper.find('[data-test="asset-purpose"] input').setValue(text)
  }
  return { ...mounted, fetchKinds, classify, unclassify, find, choices, choose, type }
}

describe('AssetClassify', () => {
  it('offers every kind, grouped', async () => {
    const { wrapper, choices } = await open()

    expect(choices().map((each) => each.text())).toEqual([
      'Router',
      'Network switch',
      'Camera or doorbell',
      'Smart home device',
    ])
    expect(wrapper.findAll('legend').map((each) => each.text())).toEqual([
      'The network',
      'Around the home',
      'How much does it matter?',
    ])
  })

  it('cannot be saved until a kind is chosen', async () => {
    const { find, choose } = await open()

    expect(find('asset-classify-save').attributes('disabled')).toBeDefined()
    await choose('Router')
    expect(find('asset-classify-save').attributes('disabled')).toBeUndefined()
  })

  it('saves the kind and what it is for, and tells the page', async () => {
    const { wrapper, find, choose, type, classify } = await open(asset({ key: 'device-4' }))

    await choose('Camera or doorbell')
    await type('  Watches the door  ')
    await find('asset-classify-save').trigger('click')
    await flushPromises()

    expect(classify).toHaveBeenCalledWith(
      'device-4',
      'camera',
      'Watches the door',
      'important',
      expect.any(String),
    )
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('saves no purpose when none was typed', async () => {
    const { find, choose, classify } = await open()

    await choose('Router')
    await find('asset-classify-save').trigger('click')
    await flushPromises()

    expect(classify).toHaveBeenCalledWith(
      'device-1',
      'router',
      null,
      'critical',
      expect.any(String),
    )
  })

  it('offers how much a kind usually matters, and says so', async () => {
    const { find, choose } = await open()

    expect(find('asset-importance-note').exists()).toBe(false)
    await choose('Router')

    expect(find('asset-importance-choice-critical').classes()).toContain('v-btn--active')
    expect(find('asset-importance-note').text()).toContain('critical was filled in for you')
  })

  it('leaves what the owner chose alone when another kind is picked', async () => {
    const { find, choose, classify } = await open()

    await choose('Router')
    await find('asset-importance-choice-important').trigger('click')
    await choose('Network switch')
    await find('asset-classify-save').trigger('click')
    await flushPromises()

    expect(find('asset-importance-choice-important').classes()).toContain('v-btn--active')
    expect(classify).toHaveBeenCalledWith(
      'device-1',
      'switch',
      null,
      'important',
      expect.any(String),
    )
  })

  it('says that a gadget takes more proof, until the owner says it matters', async () => {
    const { find, choose } = await open()

    await choose('Smart home device')
    expect(find('asset-importance-note').text()).toContain('needs more proof')

    await find('asset-importance-choice-important').trigger('click')
    expect(find('asset-importance-note').exists()).toBe(false)
  })

  it('shows how much it matters when it was said, and saves a change of only that', async () => {
    const { find, classify } = await open(
      asset({ profile: profile({ importance: 'critical', purpose: null }) }),
    )

    expect(find('asset-importance-choice-critical').classes()).toContain('v-btn--active')
    expect(find('asset-classify-save').attributes('disabled')).toBeDefined()

    await find('asset-importance-choice-normal').trigger('click')
    await find('asset-classify-save').trigger('click')
    await flushPromises()

    expect(classify).toHaveBeenCalledWith('device-1', 'camera', null, 'normal', expect.any(String))
  })

  it('says it was saved, until it is changed again', async () => {
    const saved = asset({ profile: profile({ kind: 'router', purpose: null }) })
    const { wrapper, find, choose, type } = await open(saved)

    await choose('Camera or doorbell')
    await find('asset-classify-save').trigger('click')
    await flushPromises()
    await wrapper.setProps({
      asset: asset({ profile: profile({ kind: 'camera', purpose: null }) }),
    })
    expect(find('asset-classify-saved').exists()).toBe(true)

    await type('Something else')
    expect(find('asset-classify-saved').exists()).toBe(false)
  })

  it('shows what was said, and does not save it again until it changes', async () => {
    const { find, choices } = await open(
      asset({ profile: profile({ kind: 'camera', purpose: 'Watches the door' }) }),
    )

    expect(
      choices()
        .find((each) => each.text() === 'Camera or doorbell')
        ?.attributes('aria-pressed'),
    ).toBe('true')
    expect(find('asset-purpose').find('input').element.value).toBe('Watches the door')
    expect(find('asset-classify-save').attributes('disabled')).toBeDefined()
  })

  it('suggests a kind when the name or maker says one, and uses it when asked', async () => {
    const { find, choices } = await open(
      asset({ suggested_kind: 'camera', suggested_label: 'Camera or doorbell' }),
    )

    expect(find('asset-suggestion').text()).toContain('camera or doorbell')
    expect(choices().some((each) => each.attributes('aria-pressed') === 'true')).toBe(false)

    await find('asset-suggestion-use').trigger('click')

    expect(
      choices()
        .find((each) => each.text() === 'Camera or doorbell')
        ?.attributes('aria-pressed'),
    ).toBe('true')
    expect(find('asset-suggestion').exists()).toBe(false)
  })

  it('does not suggest once the owner has said, and has no suggestion to make otherwise', async () => {
    const said = await open(
      asset({
        profile: profile(),
        suggested_kind: 'camera',
        suggested_label: 'Camera or doorbell',
      }),
    )
    expect(said.find('asset-suggestion').exists()).toBe(false)

    const none = await open()
    expect(none.find('asset-suggestion').exists()).toBe(false)
  })

  it('takes back what was said, and tells the page', async () => {
    const { wrapper, find, unclassify } = await open(asset({ key: 'device-2', profile: profile() }))

    await find('asset-classify-clear').trigger('click')
    await flushPromises()

    expect(unclassify).toHaveBeenCalledWith('device-2', expect.any(String))
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('has nothing to take back when nothing was said', async () => {
    const { find } = await open()

    expect(find('asset-classify-clear').exists()).toBe(false)
  })

  it('says when the kinds could not be fetched', async () => {
    const { find } = await open(asset(), new ApiError(0, "Can't reach AresGate.", 'offline'))

    expect(find('asset-classify-failure').text()).toBe("Can't reach AresGate.")
  })

  it('says when saving failed, and does not tell the page', async () => {
    const { wrapper, find, choose, classify } = await open()
    classify.mockRejectedValue(new ApiError(500, 'Could not save.', 'server'))

    await choose('Router')
    await find('asset-classify-save').trigger('click')
    await flushPromises()

    expect(find('asset-classify-failure').text()).toBe('Could not save.')
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('says when taking it back failed', async () => {
    const { find, unclassify } = await open(asset({ profile: profile() }))
    unclassify.mockRejectedValue(new ApiError(500, 'Could not take it back.', 'server'))

    await find('asset-classify-clear').trigger('click')
    await flushPromises()

    expect(find('asset-classify-failure').text()).toBe('Could not take it back.')
  })

  it('starts again for another asset', async () => {
    const { wrapper, find, choices } = await open(asset({ profile: profile({ kind: 'camera' }) }))
    await find('asset-classify-save').trigger('click')

    await wrapper.setProps({ asset: asset({ key: 'device-9', profile: null }) })

    expect(choices().some((each) => each.attributes('aria-pressed') === 'true')).toBe(false)
    expect(find('asset-classify-saved').exists()).toBe(false)
  })
})
