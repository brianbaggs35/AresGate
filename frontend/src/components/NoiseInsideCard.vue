<script setup lang="ts">
import SectionCard from '@/components/SectionCard.vue'

/**
 * Whether alerts between two devices on the owner's own network are set aside. A device talking to
 * another is usually a printer or a backup; a ban by a program is never set aside whatever this says.
 */
defineProps<{ modelValue: boolean }>()
defineEmits<{ 'update:modelValue': [boolean] }>()
</script>

<template>
  <SectionCard
    title="Inside your network"
    description="An alert whose source and destination are both addresses on a network of yours (10.x, 172.16 to 172.31, 192.168.x, and the like) is usually one device talking to another."
    data-test="inside-card"
  >
    <v-switch
      :model-value="modelValue"
      label="Set aside alerts between two devices on my network"
      color="primary"
      hide-details
      inset
      data-test="inside-switch"
      @update:model-value="$emit('update:modelValue', Boolean($event))"
    />
    <p class="text-body-medium text-medium-emphasis mt-2" data-test="inside-note">
      They are kept and listed in the incident, and count for nothing. A program's ban is never set
      aside, and neither is anything you called a real threat.
    </p>
  </SectionCard>
</template>
