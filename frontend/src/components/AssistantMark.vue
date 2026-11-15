<script setup lang="ts">
import { Sparkles } from '@lucide/vue'

/**
 * The assistant's mark: a round badge with sparkles, in the colours the app is built on. It
 * stands at the head of what the assistant says. While it is making an answer (`busy`) a ring
 * breathes around it, except for a person who asked their device for less motion.
 */
withDefaults(defineProps<{ size?: number; busy?: boolean }>(), { size: 32, busy: false })
</script>

<template>
  <span
    class="mark"
    :class="{ 'mark--busy': busy }"
    :style="{ '--mark-size': `${size}px` }"
    aria-hidden="true"
  >
    <v-icon :icon="Sparkles" :size="Math.round(size * 0.55)" />
  </span>
</template>

<style scoped>
.mark {
  position: relative;
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: var(--mark-size);
  height: var(--mark-size);
  border-radius: 50%;
  background: linear-gradient(135deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-secondary)));
  color: rgb(var(--v-theme-on-primary));
  box-shadow: 0 0.25rem 1rem rgb(var(--v-theme-primary), 0.28);
}

.mark--busy::after {
  position: absolute;
  inset: -0.25rem;
  border: 2px solid rgb(var(--v-theme-primary), 0.5);
  border-radius: 50%;
  content: '';
  animation: mark-breathe 1.6s ease-in-out infinite;
}

@keyframes mark-breathe {
  0%,
  100% {
    opacity: 0.2;
    transform: scale(0.92);
  }

  50% {
    opacity: 0.9;
    transform: scale(1.06);
  }
}

@media (prefers-reduced-motion: reduce) {
  .mark--busy::after {
    opacity: 0.6;
    animation: none;
  }
}
</style>
