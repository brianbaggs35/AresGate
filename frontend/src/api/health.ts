import { ApiError, apiGet } from '@/api/client'

/** Public, so it says nothing about the install beyond whether it's up. */
export interface Health {
  status: 'ok' | 'degraded'
  database: 'ok' | 'unavailable'
}

export async function fetchHealth(): Promise<Health> {
  try {
    return await apiGet<Health>('/health')
  } catch (error) {
    // A 503 still means the API answered; it reports the database as unavailable.
    if (error instanceof ApiError && error.status === 503) {
      return { status: 'degraded', database: 'unavailable' }
    }
    throw error
  }
}
