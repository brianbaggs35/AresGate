<script setup lang="ts">
import logoMark from '@/assets/logo-mark.png'

withDefaults(defineProps<{ size?: number }>(), { size: 36 })
</script>

<template>
  <span class="app-logo" data-test="app-logo">
    <img :src="logoMark" alt="" :width="size" :height="size" class="app-logo__mark" />
    <span class="app-logo__wordmark">Ares<span class="text-brand">Gate</span></span>
  </span>
</template>

<style scoped>
.app-logo {
  display: inline-flex;
  align-items: center;
  gap: 0.625rem;
}

/* The mark keeps its own near-black tile in both themes, like an app icon. */
.app-logo__mark {
  border-radius: 8px;
  flex: none;
}

.app-logo__wordmark {
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 1.125rem;
  line-height: 1;
}
</style>
