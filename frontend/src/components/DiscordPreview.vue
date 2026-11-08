<script setup lang="ts">
import { useId } from 'vue'

import type { DiscordMessage } from '@/api/alerts'
import DiscordText from '@/components/DiscordText.vue'
import { colorOf } from '@/discordText'

/**
 * A message as it will look in Discord, drawn from the message AresGate itself makes (not a
 * picture of one), so that what is shown is what arrives: the colour bar, the title, the words
 * with their bold and code, the fields in their columns and the footer. It always has Discord's
 * dark look, since that is the look it is meant to show. Nothing in it is a link or takes
 * anywhere, and the words are drawn as text, never as markup.
 */
defineProps<{
  message: DiscordMessage
}>()

const titleId = useId()
</script>

<template>
  <section class="discord" :aria-labelledby="titleId" data-test="discord-preview">
    <p :id="titleId" class="sr-only">How the message looks in Discord</p>
    <div class="discord__row">
      <span class="discord__avatar" aria-hidden="true">A</span>
      <div class="discord__main">
        <p class="discord__who">
          <strong data-test="discord-name">{{ message.username }}</strong>
          <span class="discord__app" aria-hidden="true">APP</span>
        </p>
        <article
          v-for="(embed, number) in message.embeds"
          :key="number"
          class="discord__embed"
          :style="{ borderInlineStartColor: colorOf(embed.color) }"
          data-test="discord-embed"
        >
          <p class="discord__title" data-test="discord-title">{{ embed.title }}</p>
          <div class="discord__description" data-test="discord-description">
            <DiscordText :text="embed.description" />
          </div>
          <dl v-if="embed.fields?.length" class="discord__fields" data-test="discord-fields">
            <div
              v-for="field in embed.fields"
              :key="field.name"
              :class="['discord__field', { 'discord__field--wide': !field.inline }]"
            >
              <dt>{{ field.name }}</dt>
              <dd><DiscordText :text="field.value" /></dd>
            </div>
          </dl>
          <p v-if="embed.footer" class="discord__footer" data-test="discord-footer">
            {{ embed.footer.text }}
          </p>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* Discord's own dark colours, whatever the app's theme: this is a picture of Discord. */
.discord {
  --discord-bg: #313338;
  --discord-embed: #2b2d31;
  --discord-text: #dbdee1;
  --discord-strong: #f2f3f5;
  --discord-muted: #b5bac1;
  --discord-link: #00a8fc;

  padding: 1rem;
  border-radius: 12px;
  background: var(--discord-bg);
  color: var(--discord-text);
}

.discord p {
  margin: 0;
}

.discord__row {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.discord__avatar {
  display: grid;
  flex: none;
  place-items: center;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 50%;
  background: #5865f2;
  color: #fff;
  font-weight: 700;
}

.discord__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}

.discord__who {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  color: var(--discord-strong);
}

.discord__app {
  padding: 0 0.25rem;
  border-radius: 4px;
  background: #5865f2;
  color: #fff;
  font-size: 0.6875rem;
  font-weight: 600;
  line-height: 1rem;
}

.discord__embed {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 32rem;
  padding: 0.75rem 1rem;
  border-inline-start: 4px solid transparent;
  border-radius: 4px;
  background: var(--discord-embed);
  overflow-wrap: anywhere;
}

.discord__title {
  color: var(--discord-link);
  font-weight: 600;
}

.discord__description {
  display: flex;
  flex-direction: column;
  font-size: 0.875rem;
}

.discord__fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem 1rem;
  margin: 0;
  font-size: 0.875rem;
}

.discord__field--wide {
  grid-column: 1 / -1;
}

.discord__field dt {
  color: var(--discord-strong);
  font-weight: 600;
}

.discord__field dd {
  margin: 0;
}

.discord__footer {
  color: var(--discord-muted);
  font-size: 0.75rem;
}

@media (max-width: 479.98px) {
  .discord__fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
