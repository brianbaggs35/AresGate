<script setup lang="ts">
import { kindIcon } from '@/assetKinds'

/**
 * What the owner said an asset is, as a chip with its picture: "Router", "Camera or doorbell".
 * The picture is only for the eye, and the words say it.
 */
defineProps<{
  kind: string
  label: string
  size?: 'small' | 'default'
}>()
</script>

<template>
  <v-chip
    :prepend-icon="kindIcon(kind)"
    color="primary"
    variant="tonal"
    :size="size ?? 'small'"
    data-test="asset-kind"
  >
    {{ label }}
  </v-chip>
</template>
