import { defineStore } from 'pinia'
import { ref } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchHealth, type Health } from '@/api/health'

export const useHealthStore = defineStore('health', () => {
  const health = ref<Health | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function refresh() {
    loading.value = true
    error.value = null
    try {
      health.value = await fetchHealth()
    } catch (refreshError) {
      health.value = null
      error.value = errorMessage(refreshError)
    } finally {
      loading.value = false
    }
  }

  return { health, loading, error, refresh }
})
