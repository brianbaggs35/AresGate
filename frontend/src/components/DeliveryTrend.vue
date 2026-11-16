<script setup lang="ts">
import { computed } from 'vue'

import { fetchDeliveryTrend } from '@/api/trends'
import BarChart from '@/charts/BarChart.vue'
import { deliverySeries, hourLabel, useTrend } from '@/trends'

/**
 * How many messages were made in each of the last two days' hours, by how serious what they were
 * about, for the destination and the state the delivery log is looking at, so a burst is seen as
 * one and the log below it is read with that in mind.
 */
const props = defineProps<{ destination?: number; state?: string }>()

const { trend, loading } = useTrend(
  () => `${props.destination ?? ''}|${props.state ?? ''}`,
  () => fetchDeliveryTrend({ destination_id: props.destination, state: props.state }),
)

const categories = computed(() => (trend.value?.times ?? []).map(hourLabel))
const series = computed(() => (trend.value ? deliverySeries(trend.value) : []))
</script>

<template>
  <BarChart
    v-if="trend || loading"
    title="Messages by severity"
    caption="Messages made in each hour of the last two days."
    category-label="Hour"
    orientation="vertical"
    stacked
    whole
    :categories="categories"
    :series="series"
    :loading="loading"
    empty-title="No messages"
    empty-description="Nothing was sent or held in the last two days."
    data-test="delivery-trend"
  />
</template>
