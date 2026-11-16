import * as client from '@/api/client'
import {
  fetchAddressTrends,
  fetchDeliveryTrend,
  fetchIntegrationTrends,
  fetchKindTrends,
  MOST_ADDRESSES,
} from '@/api/trends'

describe('trends API', () => {
  it('asks for the messages of each hour, for what the log is looking at', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})

    await fetchDeliveryTrend()
    await fetchDeliveryTrend({ destination_id: 4, state: 'failed' }, 12)

    expect(get).toHaveBeenNthCalledWith(1, '/trends/deliveries?hours=48')
    expect(get).toHaveBeenNthCalledWith(
      2,
      '/trends/deliveries?hours=12&destination_id=4&state=failed',
    )
  })

  it('asks for the events of addresses, a day or an hour at a time', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})

    await fetchAddressTrends(['192.168.1.20', '2001:db8::1'])
    await fetchAddressTrends(['192.168.1.20'], 'hour', 168)

    expect(get).toHaveBeenNthCalledWith(
      1,
      '/trends/addresses?step=day&count=7&address=192.168.1.20&address=2001%3Adb8%3A%3A1',
    )
    expect(get).toHaveBeenNthCalledWith(
      2,
      '/trends/addresses?step=hour&count=168&address=192.168.1.20',
    )
  })

  it('asks for no more addresses or kinds than the server answers for', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})
    const many = Array.from({ length: MOST_ADDRESSES + 5 }, (_, index) => index + 1)

    await fetchAddressTrends(many.map((number) => `10.0.0.${number}`))
    await fetchKindTrends(many)

    const asked = (call: number) =>
      (get.mock.calls[call]?.[0] as string).split('&').filter((part) => /^(address|id)=/.test(part))
    expect(asked(0)).toHaveLength(MOST_ADDRESSES)
    expect(asked(1)).toHaveLength(MOST_ADDRESSES)
  })

  it('asks for the incidents of kinds by the day, and how integrations went', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})

    await fetchKindTrends([3, 5])
    await fetchIntegrationTrends()

    expect(get).toHaveBeenNthCalledWith(1, '/trends/kinds?days=7&id=3&id=5')
    expect(get).toHaveBeenNthCalledWith(2, '/trends/integrations?hours=24')
  })
})
