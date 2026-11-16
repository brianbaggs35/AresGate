import type {
  BaselineDeviation,
  BaselineInterfaces,
  BaselinePlace,
  BaselinePlaces,
  BaselineSeries,
  BaselineTalker,
  BaselineTalkers,
} from '@/api/baselines'

const MEGABYTE = 1024 ** 2

/** An interface learned for a day: the evenings are the busiest hours. */
export function series(changes: Partial<BaselineSeries> = {}): BaselineSeries {
  return {
    interface: 'igc0',
    name: 'Home',
    direction: 'received',
    hours: Array.from({ length: 24 }, (_, hour) => ({
      hour,
      median: (hour >= 18 ? 400 : 100) * MEGABYTE,
      spread: 20 * MEGABYTE,
      samples: 28,
    })),
    learned_at: '2026-11-16T12:00:00Z',
    samples: 28,
    deviations: [],
    ...changes,
  }
}

export function deviation(changes: Partial<BaselineDeviation> = {}): BaselineDeviation {
  return {
    at: '2026-11-15T03:00:00Z',
    summary: 'igc0 received 900.0 MB between 03:00 and 04:00 UTC, 9 times what is usual.',
    observed: 900 * MEGABYTE,
    usual: 100 * MEGABYTE,
    severity: 2,
    ...changes,
  }
}

export function interfaces(changes: Partial<BaselineInterfaces> = {}): BaselineInterfaces {
  return {
    series: [series(), series({ direction: 'sent', deviations: [deviation()] })],
    counted: true,
    weeks: 4,
    min_hours: 8,
    ...changes,
  }
}

export function talker(changes: Partial<BaselineTalker> = {}): BaselineTalker {
  return {
    address: '192.168.1.20',
    name: 'laptop',
    places: 25,
    expected: 1,
    hits: 120,
    learning_since: '2026-11-01T00:00:00Z',
    last_seen_at: '2026-11-16T11:00:00Z',
    judged: true,
    ...changes,
  }
}

export function talkers(items: BaselineTalker[] = [talker()]): BaselineTalkers {
  return { items, total: items.length, watched_days: 7, min_places: 20, forget_days: 90 }
}

export function place(changes: Partial<BaselinePlace> = {}): BaselinePlace {
  return {
    network: '198.51.100.0/24',
    port: 443,
    first_seen_at: '2026-11-01T00:00:00Z',
    last_seen_at: '2026-11-16T11:00:00Z',
    hits: 12,
    expected: false,
    ...changes,
  }
}

export function places(
  list: BaselinePlace[] = [place(), place({ network: '203.0.113.0/24', port: 0, expected: true })],
  changes: Partial<BaselinePlaces> = {},
): BaselinePlaces {
  return { address: '192.168.1.20', name: 'laptop', places: list, ...changes }
}
