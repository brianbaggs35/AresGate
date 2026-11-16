import type {
  AddressTrends,
  DeliveryTrend,
  HourState,
  IntegrationTrends,
  KindTrends,
} from '@/api/trends'

const TIMES = ['2026-11-16T10:00:00Z', '2026-11-16T11:00:00Z', '2026-11-16T12:00:00Z']

export function deliveryTrend(changes: Partial<DeliveryTrend> = {}): DeliveryTrend {
  return {
    times: TIMES,
    step: 'hour',
    severities: {
      info: [0, 0, 0],
      low: [0, 0, 0],
      medium: [0, 1, 0],
      high: [2, 0, 1],
      critical: [0, 0, 0],
    },
    ...changes,
  }
}

export function addressTrends(
  items: AddressTrends['items'] = { '192.168.1.20': { incoming: [1, 2, 3], outgoing: [0, 1, 0] } },
): AddressTrends {
  return { times: TIMES, step: 'day', items }
}

export function kindTrends(items: KindTrends['items'] = { '1': [0, 2, 5] }): KindTrends {
  return { times: TIMES, step: 'day', items }
}

export function integrationTrends(
  items: Record<string, HourState[]> = { wazuh: ['ok', 'problem', 'none'] },
): IntegrationTrends {
  return { times: TIMES, step: 'hour', items }
}
