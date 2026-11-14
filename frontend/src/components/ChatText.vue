<script setup lang="ts">
import { pieces } from '@/chat'

/** A line of an answer, with each incident it names as [incident 3] and each device as [device 12]
 * turned into a link to it. */
defineProps<{ text: string }>()
</script>

<template>
  <template v-for="(piece, at) in pieces(text)" :key="at">
    <RouterLink
      v-if="'incident' in piece"
      :to="{ name: 'incident', params: { id: piece.incident } }"
      data-test="message-incident"
      >incident {{ piece.incident }}</RouterLink
    >
    <RouterLink
      v-else-if="'device' in piece"
      :to="{ name: 'asset', params: { key: `device-${piece.device}` } }"
      data-test="message-device"
      >device {{ piece.device }}</RouterLink
    >
    <template v-else>{{ piece.text }}</template>
  </template>
</template>
