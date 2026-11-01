<script setup lang="ts">
import { pieces } from '@/chat'

/** A line of an answer, with each incident it names as [incident 3] turned into a link to it. */
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
    <template v-else>{{ piece.text }}</template>
  </template>
</template>
