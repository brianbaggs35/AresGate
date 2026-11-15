import { ApiError } from '@/api/client'
import * as catalog from '@/api/threatCatalog'
import type { DeviceIntelPage } from '@/api/threatCatalog'
import ThreatDevices from '@/components/ThreatDevices.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { CAMERA, deviceIntelPage } from '@/test/threatCatalog'

const NONE: DeviceIntelPage = deviceIntelPage({
  total: 0,
  items: [],
  counts: { identified: 0, unknown: 0, private: 0 },
})

async function mountDevices(result: DeviceIntelPage | Error = deviceIntelPage()) {
  const fetch = vi.spyOn(catalog, 'fetchDeviceIntel')
  if (result instanceof Error) fetch.mockRejectedValue(result)
  else fetch.mockResolvedValue(result)
  const mounted = await mountWithPlugins(ThreatDevices, {
    signedIn: 'brian',
    props: { version: 0 },
  })
  await flushPromises()
  const { wrapper } = mounted
  const find = (selector: string) => wrapper.find(`[data-test="${selector}"]`)
  const rows = () => wrapper.findAll('[data-test="devices-row"]')
  return { ...mounted, fetch, find, rows }
}

describe('ThreatDevices', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('reads the first page of every device that was asked about', async () => {
    const { fetch } = await mountDevices()

    expect(fetch).toHaveBeenCalledWith({ q: '', state: null, limit: 25 })
  })

  it('shows what Fingerbank made of a device, and what AresGate knows of it', async () => {
    const { rows } = await mountDevices()
    const camera = rows()[0]

    expect(camera?.attributes('data-state')).toBe('identified')
    expect(camera?.find('[data-test="devices-state"]').text()).toBe('Identified')
    expect(camera?.find('[data-test="devices-name"]').text()).toBe('Nest Cam')
    expect(camera?.find('[data-test="devices-score"]').text()).toBe('87% sure')
    expect(camera?.find('[data-test="devices-path"]').text()).toBe(
      'Hardware Manufacturer/Google/Camera',
    )
    expect(camera?.find('[data-test="devices-manufacturer"]').text()).toBe('Google')
    expect(camera?.find('[data-test="devices-os"]').text()).toBe('Linux OS')
    expect(camera?.find('[data-test="devices-vendor"]').text()).toBe('Google, Inc.')
    expect(camera?.find('[data-test="devices-address"]').text()).toBe('192.168.1.50')
    expect(camera?.find('[data-test="devices-mac"]').text()).toBe('3c:5a:b4:00:00:01')
    expect(camera?.find('[data-test="devices-seen"]').text()).toMatch(/\S/)
    expect(camera?.find('[data-test="devices-checked"]').text()).toMatch(/as an asset$/)
    expect(camera?.find('[data-test="devices-about"]').exists()).toBe(false)
  })

  it('names a device by its hostname, or by its hardware address where it has no other name', async () => {
    const { rows } = await mountDevices(
      deviceIntelPage({
        items: [
          { ...CAMERA, name: null },
          { ...CAMERA, device_id: 2, name: null, hostname: null },
        ],
      }),
    )

    expect(rows().map((row) => row.find('[data-test="devices-name"]').text())).toEqual([
      'driveway-cam',
      '3c:5a:b4:00:00:01',
    ])
  })

  it('says why a device was not recognised, or not asked about, and leaves out what is not known', async () => {
    const { rows } = await mountDevices()
    const unknown = rows()[1]
    const hidden = rows()[2]

    expect(unknown?.find('[data-test="devices-about"]').text()).toBe(
      'Fingerbank has no match for it.',
    )
    expect(unknown?.find('[data-test="devices-score"]').exists()).toBe(false)
    expect(hidden?.find('[data-test="devices-state"]').text()).toBe('Private address')
    expect(hidden?.find('[data-test="devices-about"]').text()).toContain('Fingerbank was not asked')
    expect(hidden?.find('[data-test="devices-checked"]').text()).toMatch(/for an incident$/)
    for (const left of ['manufacturer', 'os', 'vendor', 'address', 'path']) {
      expect(hidden?.find(`[data-test="devices-${left}"]`).exists()).toBe(false)
    }
  })

  it('counts what was made of each device on its filters', async () => {
    const { find } = await mountDevices()

    expect(find('devices-filter-all').text()).toBe('All 3')
    expect(find('devices-filter-identified').text()).toBe('Identified 1')
    expect(find('devices-filter-unknown').text()).toBe('Not recognised 1')
    expect(find('devices-filter-private').text()).toBe('Private address 1')
    expect(find('devices-filter-all').attributes('aria-pressed')).toBe('true')
  })

  it('narrows the list to one state, and back to all', async () => {
    const { fetch, find } = await mountDevices()

    await find('devices-filter-private').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({ q: '', state: 'private', limit: 25 })
    expect(find('devices-filter-private').attributes('aria-pressed')).toBe('true')

    await find('devices-filter-all').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({ q: '', state: null, limit: 25 })
  })

  it('finds what is typed, without its spaces, and everything again once it is cleared', async () => {
    const { wrapper, fetch, find } = await mountDevices()
    await wrapper.find<HTMLInputElement>('[data-test="devices-text"] input').setValue('  nest ')

    await find('devices-form').trigger('submit')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({ q: 'nest', state: null, limit: 25 })

    await wrapper.find('[data-test="devices-text"] .v-field__clearable .v-icon').trigger('click')
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({ q: '', state: null, limit: 25 })
  })

  it('says when nothing matches, and keeps the search and filters there', async () => {
    const { fetch, find } = await mountDevices()
    fetch.mockResolvedValue(NONE)
    await find('devices-filter-unknown').trigger('click')
    await flushPromises()

    expect(find('devices-none').text()).toBe('Nothing kept matches.')
    expect(find('devices-form').exists()).toBe(true)
    expect(find('devices-empty').exists()).toBe(false)
  })

  it('says when no device was asked about yet, with a way to connect Fingerbank', async () => {
    const { find } = await mountDevices(NONE)

    expect(find('devices-empty').text()).toContain('No devices identified yet')
    expect(find('devices-set-up').attributes('href')).toBe('/integrations')
    expect(find('devices-form').exists()).toBe(false)
  })

  it('shows more of a long list on request, and starts over when the filter changes', async () => {
    const { fetch, find } = await mountDevices(deviceIntelPage({ total: 40 }))

    expect(find('devices-more').text()).toBe('Show more (37 left)')
    await find('devices-more').trigger('click')
    await flushPromises()
    expect(fetch).toHaveBeenLastCalledWith({ q: '', state: null, limit: 50 })

    await find('devices-filter-identified').trigger('click')
    await flushPromises()
    expect(fetch).toHaveBeenLastCalledWith({ q: '', state: 'identified', limit: 25 })
  })

  it('reads the list again when the page says something was answered', async () => {
    const { wrapper, fetch } = await mountDevices()

    await wrapper.setProps({ version: 1 })
    await flushPromises()

    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('shows a placeholder while the list is on its way', async () => {
    vi.spyOn(catalog, 'fetchDeviceIntel').mockReturnValue(new Promise(() => undefined))
    const { wrapper } = await mountWithPlugins(ThreatDevices, { signedIn: 'brian' })

    expect(wrapper.find('[data-test="devices-loading"]').exists()).toBe(true)
  })

  it('says the list did not load, and tries again', async () => {
    const { fetch, find, rows } = await mountDevices(
      new ApiError(503, 'Service unavailable', 'unavailable'),
    )
    expect(find('devices-error').exists()).toBe(true)
    fetch.mockResolvedValue(deviceIntelPage())

    await find('devices-retry').trigger('click')
    await flushPromises()

    expect(rows()).toHaveLength(3)
  })

  it('keeps the list and says what went wrong when reading it again fails', async () => {
    const { fetch, find, rows } = await mountDevices()
    fetch.mockRejectedValue(new ApiError(503, 'Service unavailable', 'unavailable'))

    await find('devices-filter-unknown').trigger('click')
    await flushPromises()

    expect(rows()).toHaveLength(3)
    expect(find('devices-problem').text()).toBe('Service unavailable')
  })
})
