<script setup lang="ts">
import { ArrowRight, ChevronRight, CircleAlert, Info, X } from '@lucide/vue'
import { ref, useId } from 'vue'
import { useDisplay } from 'vuetify'

import type { Guide } from '@/api/integrations'
import CopyButton from '@/components/CopyButton.vue'
import { useKeyboardReturn } from '@/dialog'

/**
 * How to get what an integration asks for, step by step, in a window over its page: a short title
 * for each step, the menus to go through, the exact values to pick or enter, and where what the
 * step produced goes in AresGate. What is easy to get wrong is said where it can go wrong, and
 * so is what was worked out rather than read, so that a guess is never passed off as
 * documentation. The pages it was written from are listed at the end. The whole screen on a
 * phone.
 */
defineProps<{ name: string; guide: Guide }>()
const open = defineModel<boolean>({ required: true })

const { xs: phone } = useDisplay()
const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)

const title = ref<HTMLElement | null>(null)

/** Moves the keyboard to the title, so a screen reader starts at the top of what opened. */
function takeTheKeyboard() {
  title.value?.focus({ preventScroll: true })
}
</script>

<template>
  <v-dialog
    v-model="open"
    :fullscreen="phone"
    scrollable
    max-width="760"
    :aria-labelledby="titleId"
    @after-enter="takeTheKeyboard"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card
      class="guide"
      :class="{ 'guide--screen': phone }"
      :rounded="phone ? 0 : undefined"
      :border="!phone"
      data-test="setup-guide"
    >
      <header class="guide__head">
        <h2
          :id="titleId"
          ref="title"
          tabindex="-1"
          class="guide__title text-title-large"
          data-test="guide-title"
        >
          Set up {{ name }}
        </h2>
        <v-btn
          icon
          variant="text"
          size="small"
          aria-label="Close"
          data-test="guide-close"
          @click="open = false"
        >
          <v-icon :icon="X" />
        </v-btn>
      </header>

      <div class="guide__body">
        <section
          v-for="part in guide.parts"
          :key="part.connection"
          class="guide__part"
          :data-test="`guide-part-${part.connection}`"
        >
          <div class="guide__part-head">
            <h3 class="text-title-medium">{{ part.title }}</h3>
            <v-chip v-if="part.optional" size="small" variant="tonal" data-test="guide-optional">
              Optional
            </v-chip>
          </div>
          <p class="text-body-large">{{ part.intro }}</p>

          <ol class="guide__steps">
            <li v-for="step in part.steps" :key="step.title" class="guide__step" data-test="step">
              <h4 class="text-title-small guide__step-title" data-test="step-title">
                {{ step.title }}
              </h4>
              <p class="text-body-large">{{ step.detail }}</p>

              <ol v-if="step.menu.length" class="guide__menu" aria-label="Where to find it">
                <li v-for="item in step.menu" :key="item" class="text-label-large">
                  {{ item }}
                  <ChevronRight class="guide__chevron" :size="16" aria-hidden="true" />
                </li>
              </ol>

              <dl v-if="step.fills.length" class="guide__fills" data-test="step-fills">
                <div v-for="fill in step.fills" :key="fill.label" class="guide__fill">
                  <dt class="text-body-medium text-medium-emphasis">{{ fill.label }}</dt>
                  <dd class="text-body-large">{{ fill.value }}</dd>
                </div>
              </dl>

              <div v-if="step.command" class="guide__command">
                <code class="text-body-medium" data-test="step-command">{{ step.command }}</code>
                <CopyButton :text="step.command" label="command" />
              </div>

              <p v-if="step.result" class="guide__result text-body-large" data-test="step-result">
                <ArrowRight :size="18" aria-hidden="true" />
                <span>{{ step.result }}</span>
              </p>
              <p
                v-if="step.watch"
                class="guide__note guide__note--watch text-body-medium"
                data-test="step-watch"
              >
                <CircleAlert :size="18" aria-hidden="true" />
                <span><strong>Easy to get wrong.</strong> {{ step.watch }}</span>
              </p>
              <p
                v-if="step.inferred"
                class="guide__note text-body-medium"
                data-test="step-inferred"
              >
                <Info :size="18" aria-hidden="true" />
                <span><strong>Not from the documentation.</strong> {{ step.inferred }}</span>
              </p>
            </li>
          </ol>
        </section>

        <section class="guide__sources" data-test="guide-sources">
          <h3 class="text-title-medium">Where this comes from</h3>
          <p class="text-body-medium text-medium-emphasis">
            Written from these pages of the product's own documentation and source. Products change
            between releases, so Connect then tells you whether a step worked.
          </p>
          <ul>
            <li v-for="source in guide.sources" :key="source.url">
              <a
                :href="source.url"
                target="_blank"
                rel="noopener noreferrer"
                class="text-body-medium"
                :aria-label="`${source.title} (opens in a new tab)`"
                >{{ source.title }}</a
              >
            </li>
          </ul>
        </section>
      </div>

      <footer class="guide__foot">
        <v-btn variant="text" data-test="guide-done" @click="open = false">Close</v-btn>
      </footer>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.guide {
  display: flex;
  flex-direction: column;
  max-height: 100%;
  padding-bottom: env(safe-area-inset-bottom);
}

/* On a phone it is the whole screen, edge to edge. */
.guide--screen {
  height: 100%;
}

.guide__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 0.75rem 0.75rem 1.5rem;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.guide__title {
  margin: 0;
  overflow-wrap: anywhere;
}

/* Focused by the window itself when it opens, which no one needs a ring to see. */
.guide__title:focus-visible {
  outline: none;
}

.guide__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2rem;
  padding: 1.5rem;
  overflow-y: auto;
}

.guide__part {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.guide__part-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.guide__part-head h3,
.guide__sources h3 {
  margin: 0;
}

.guide__part p,
.guide__sources p {
  margin: 0;
}

.guide__steps {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
  counter-reset: step;
}

.guide__step {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  padding-inline-start: 2.75rem;
  counter-increment: step;
}

/* The number sits in a circle, so the steps read as a sequence at a glance. */
.guide__step::before {
  position: absolute;
  inset-block-start: 0;
  inset-inline-start: 0;
  display: grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-on-surface));
  content: counter(step);
  font-weight: 600;
}

.guide__step-title {
  margin: 0;
  min-height: 2rem;
  display: flex;
  align-items: center;
}

.guide__step p {
  margin: 0;
}

.guide__menu {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.125rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.guide__menu li {
  display: inline-flex;
  align-items: center;
  gap: 0.125rem;
  padding: 0.125rem 0.125rem 0.125rem 0.625rem;
  border-radius: 0.5rem;
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-on-surface-variant));
}

.guide__menu li:last-child {
  padding-inline-end: 0.625rem;
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-on-surface));
}

.guide__menu li:last-child .guide__chevron {
  display: none;
}

.guide__chevron {
  opacity: 0.6;
}

.guide__fills {
  display: flex;
  flex-direction: column;
  margin: 0;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 0.75rem;
}

.guide__fill {
  display: grid;
  grid-template-columns: minmax(8rem, 11rem) 1fr;
  gap: 0.25rem 1rem;
  padding: 0.625rem 1rem;
}

.guide__fill + .guide__fill {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.guide__fill dd {
  margin: 0;
  font-weight: 500;
  overflow-wrap: anywhere;
}

@media (max-width: 599px) {
  .guide__fill {
    grid-template-columns: 1fr;
  }
}

.guide__command {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.5rem 0.5rem 0.5rem 1rem;
  border-radius: 0.75rem;
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-on-surface-variant));
}

.guide__command code {
  flex: 1;
  min-width: 0;
  padding-block: 0.25rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.guide__result {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  font-weight: 500;
}

.guide__result svg,
.guide__note svg {
  flex: none;
  margin-block-start: 0.1875rem;
}

.guide__note {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  padding: 0.625rem 0.875rem;
  border-radius: 0.75rem;
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.guide__note--watch {
  background: rgba(var(--v-theme-warning), 0.14);
}

.guide__sources ul {
  margin: 0.5rem 0 0;
  padding-inline-start: 1.25rem;
}

.guide__sources li + li {
  margin-top: 0.25rem;
}

.guide__foot {
  display: flex;
  justify-content: flex-end;
  padding: 0.5rem 1rem;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
