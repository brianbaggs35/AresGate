import {
  addDestination,
  changeDestination,
  changeRules,
  fetchDeliveries,
  fetchDestinations,
  fetchSample,
  previewRules,
  removeDestination,
  sendSample,
  testDestination,
} from '@/api/alerts'
import * as client from '@/api/client'
import { rules } from '@/test/alerts'

describe('alerts', () => {
  it('lists the destinations', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [{ id: 3 }] })

    await expect(fetchDestinations()).resolves.toEqual({ items: [{ id: 3 }] })
    expect(get).toHaveBeenCalledWith('/alerts/destinations')
  })

  it('adds one, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 4 })
    const add = { name: 'Security', url: 'https://discord.com/api/webhooks/1/x' }

    await expect(addDestination(add, 'a-token')).resolves.toEqual({ id: 4 })
    expect(post).toHaveBeenCalledWith('/alerts/destinations', add, 'a-token')
  })

  it('changes one, with the sign-in token', async () => {
    const patch = vi.spyOn(client, 'apiPatch').mockResolvedValue({ id: 4 })

    await expect(changeDestination(4, { enabled: false }, 'a-token')).resolves.toEqual({ id: 4 })
    expect(patch).toHaveBeenCalledWith('/alerts/destinations/4', { enabled: false }, 'a-token')
  })

  it('removes one, with the sign-in token', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await removeDestination(4, 'a-token')

    expect(remove).toHaveBeenCalledWith('/alerts/destinations/4', 'a-token')
  })

  it('sends a test message, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ ok: true })

    await expect(testDestination(4, 'a-token')).resolves.toEqual({ ok: true })
    expect(post).toHaveBeenCalledWith('/alerts/destinations/4/test', undefined, 'a-token')
  })

  it('sends a sample alert, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ ok: true })

    await expect(sendSample(4, 'a-token')).resolves.toEqual({ ok: true })
    expect(post).toHaveBeenCalledWith('/alerts/destinations/4/sample', undefined, 'a-token')
  })

  it('asks what a message looks like, for a mode, a detail and a part of the story', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ payload: {} })

    await expect(fetchSample('threats', 'full', 'worse')).resolves.toEqual({ payload: {} })
    expect(get).toHaveBeenCalledWith('/alerts/sample?mode=threats&detail=full&reason=worse')
  })

  it('asks for the first message of the story when no part is named', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ payload: {} })

    await fetchSample('custom', 'brief')

    expect(get).toHaveBeenCalledWith('/alerts/sample?mode=custom&detail=brief&reason=new')
  })

  it('replaces the rules of one, with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ id: 4 })

    await expect(changeRules(4, rules(), 'a-token')).resolves.toEqual({ id: 4 })
    expect(put).toHaveBeenCalledWith('/alerts/destinations/4/rules', rules(), 'a-token')
  })

  it('asks what rules would have sent, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ would_send: 2 })

    await expect(previewRules(4, rules(), 'a-token')).resolves.toEqual({ would_send: 2 })
    expect(post).toHaveBeenCalledWith('/alerts/destinations/4/preview', rules(), 'a-token')
  })

  it('asks for the log, narrowed by what is given', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [] })

    await expect(fetchDeliveries()).resolves.toEqual({ items: [] })
    expect(get).toHaveBeenLastCalledWith('/alerts/deliveries')
    await fetchDeliveries({ destination_id: 3, state: 'failed', before: 40 })
    expect(get).toHaveBeenLastCalledWith(
      '/alerts/deliveries?destination_id=3&state=failed&before=40',
    )
    await fetchDeliveries({ state: 'sent' })
    expect(get).toHaveBeenLastCalledWith('/alerts/deliveries?state=sent')
  })
})
