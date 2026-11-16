<script setup lang="ts">
/**
 * The box that picks one row of a list, for a change to be made to all the rows picked. It is as
 * big to touch as a button, and a click with Shift held picks (or takes off) all the rows from the
 * one picked last, which is what `toggle` says.
 */
defineProps<{
  checked: boolean
  /** What picking it is for, said to those who hear it: "Select: Everything about 93.1.2.3". */
  label: string
}>()
const emit = defineEmits<{ toggle: [range: boolean] }>()
</script>

<template>
  <label class="row-check" data-test="row-pick">
    <input
      type="checkbox"
      class="row-check__box"
      :checked="checked"
      :aria-label="label"
      data-test="row-select"
      @click="emit('toggle', ($event as MouseEvent).shiftKey)"
    />
  </label>
</template>

<style scoped>
.row-check {
  display: grid;
  flex: none;
  place-items: center;
  width: 44px;
  height: 44px;
  cursor: pointer;
}

.row-check__box {
  width: 1.25rem;
  height: 1.25rem;
  margin: 0;
  accent-color: rgb(var(--v-theme-primary));
  cursor: pointer;
}

.row-check__box:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 3px;
}
</style>
