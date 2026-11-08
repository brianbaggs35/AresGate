<script setup lang="ts">
import { lines } from '@/discordText'

/** The words of a Discord message, one paragraph to a line, with their bold, code and the words of
 * links drawn as what they are. Never markup: the text is only ever text. */
defineProps<{ text: string }>()
</script>

<template>
  <p v-for="(line, row) in lines(text)" :key="row" class="text__line" data-test="discord-line">
    <template v-for="(piece, place) in line" :key="place">
      <strong v-if="piece.kind === 'bold'">{{ piece.text }}</strong>
      <code v-else-if="piece.kind === 'code'" class="text__code">{{ piece.text }}</code>
      <span v-else-if="piece.kind === 'link'" class="text__link">{{ piece.text }}</span>
      <template v-else>{{ piece.text }}</template>
    </template>
  </p>
</template>

<style scoped>
.text__line {
  min-height: 0.75rem;
  margin: 0;
}

.text__link {
  color: var(--discord-link);
}

.text__code {
  padding: 0 0.25rem;
  border-radius: 3px;
  background: #1e1f22;
  color: var(--discord-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8125rem;
}
</style>
