<script setup lang="ts">
import { ChevronDown, ChevronUp, GripVertical, RotateCcw, X } from '@lucide/vue'
import { ref, useId } from 'vue'

import { change, moveBy, moveTo, widgetInfo, type Place, type WidgetId } from '@/dashboardLayout'
import { useDashboardLayoutStore } from '@/stores/dashboardLayout'
import { useKeyboardReturn } from '@/dialog'

/**
 * Where the owner makes the dashboard their own: which widgets show, in what order and how wide,
 * or a preset to start from. Each change is shown at once and saved. A widget moves by dragging
 * its handle, and by the buttons beside it, which are the way to do it with a keyboard or a finger.
 * It is a sheet from the side on a computer and the screen above the bottom bar on a phone.
 */
const open = defineModel<boolean>({ required: true })

const layout = useDashboardLayoutStore()
const giveBackTheKeyboard = useKeyboardReturn(open)
const titleId = useId()
const presetsId = useId()

/** The widget whose handle was pressed, the one being dragged, and the one it is over. A row is
 * only dragged by its handle, so that the switch and the buttons in it keep working. */
const grabbed = ref<WidgetId | null>(null)
const dragging = ref<WidgetId | null>(null)
const over = ref<WidgetId | null>(null)
/** What was said to a screen reader after a move, since the list moves under it. */
const announced = ref('')

const titleOf = (id: WidgetId) => widgetInfo(id).title

function save(next: readonly Place[]) {
  void layout.save(next)
}

function move(id: WidgetId, by: number) {
  const next = moveBy(layout.places, id, by)
  save(next)
  const at = next.findIndex((place) => place.id === id)
  announced.value = `${titleOf(id)} is now number ${at + 1} of ${next.length}.`
}

function pick(event: DragEvent, id: WidgetId) {
  if (grabbed.value !== id) {
    event.preventDefault()
    return
  }
  dragging.value = id
  // Firefox does not begin a drag that carries nothing.
  event.dataTransfer?.setData('text/plain', id)
}

function release() {
  grabbed.value = dragging.value = over.value = null
}

function drop(target: WidgetId) {
  const id = dragging.value
  release()
  if (id && id !== target) {
    save(moveTo(layout.places, id, target))
    announced.value = `${titleOf(id)} moved.`
  }
}
</script>

<template>
  <v-dialog
    v-model="open"
    scrollable
    transition="slide-x-reverse-transition"
    :aria-labelledby="titleId"
    class="sheet"
    @after-leave="giveBackTheKeyboard"
  >
    <v-card class="sheet__card" :rounded="0" data-test="customize">
      <header class="sheet__head">
        <h2 :id="titleId" class="text-title-large sheet__title">Customize the dashboard</h2>
        <v-btn
          icon
          variant="text"
          size="small"
          aria-label="Close"
          data-test="customize-close"
          @click="open = false"
        >
          <v-icon :icon="X" />
        </v-btn>
      </header>

      <div class="sheet__body">
        <v-alert
          v-if="layout.error"
          type="error"
          variant="tonal"
          density="compact"
          data-test="customize-error"
        >
          {{ layout.error }}
        </v-alert>

        <section v-if="layout.presets.length" :aria-labelledby="presetsId">
          <h3 :id="presetsId" class="text-title-small">Start from</h3>
          <ul class="presets">
            <li v-for="preset in layout.presets" :key="preset.key">
              <button
                type="button"
                class="preset"
                :class="{ 'preset--on': layout.preset === preset.key }"
                :aria-pressed="layout.preset === preset.key"
                :disabled="layout.saving"
                :data-test="`preset-${preset.key}`"
                @click="layout.apply(preset.key)"
              >
                <span class="text-title-small">{{ preset.title }}</span>
                <span class="text-body-small text-medium-emphasis">{{ preset.description }}</span>
              </button>
            </li>
          </ul>
        </section>

        <section aria-labelledby="widgets-title">
          <h3 id="widgets-title" class="text-title-small">Widgets</h3>
          <p class="text-body-medium text-medium-emphasis">
            Drag a handle, or use the arrows, to change the order. The numbers under the banner at
            the top stay where they are.
          </p>
          <ul class="widgets" data-test="widget-list">
            <li
              v-for="(place, at) in layout.places"
              :key="place.id"
              class="widget"
              :class="{
                'widget--off': place.hidden,
                'widget--over': over === place.id && dragging !== place.id,
              }"
              draggable="true"
              :data-test="`widget-${place.id}`"
              @dragstart="pick($event, place.id)"
              @dragover.prevent="over = place.id"
              @drop.prevent="drop(place.id)"
              @dragend="release"
            >
              <span
                class="widget__grip"
                aria-hidden="true"
                data-test="widget-grip"
                @mousedown="grabbed = place.id"
              >
                <v-icon :icon="GripVertical" size="20" />
              </span>
              <span class="widget__text">
                <span class="text-title-small">{{ titleOf(place.id) }}</span>
                <span class="text-body-small text-medium-emphasis">
                  {{ widgetInfo(place.id).description }}
                </span>
              </span>
              <span class="widget__controls">
                <v-switch
                  :model-value="!place.hidden"
                  color="primary"
                  density="compact"
                  hide-details
                  :aria-label="`Show ${titleOf(place.id)}`"
                  data-test="widget-show"
                  @update:model-value="save(change(layout.places, place.id, { hidden: !$event }))"
                />
                <v-btn-toggle
                  :model-value="place.size"
                  mandatory
                  density="compact"
                  variant="outlined"
                  divided
                  color="primary"
                  :aria-label="`Width of ${titleOf(place.id)}`"
                  data-test="widget-size"
                  @update:model-value="save(change(layout.places, place.id, { size: $event }))"
                >
                  <v-btn value="half" size="small" data-test="widget-half">Half</v-btn>
                  <v-btn value="full" size="small" data-test="widget-full">Full</v-btn>
                </v-btn-toggle>
                <span class="widget__moves">
                  <v-btn
                    icon
                    variant="text"
                    size="small"
                    :disabled="at === 0"
                    :aria-label="`Move ${titleOf(place.id)} up`"
                    data-test="widget-up"
                    @click="move(place.id, -1)"
                  >
                    <v-icon :icon="ChevronUp" />
                  </v-btn>
                  <v-btn
                    icon
                    variant="text"
                    size="small"
                    :disabled="at === layout.places.length - 1"
                    :aria-label="`Move ${titleOf(place.id)} down`"
                    data-test="widget-down"
                    @click="move(place.id, 1)"
                  >
                    <v-icon :icon="ChevronDown" />
                  </v-btn>
                </span>
              </span>
            </li>
          </ul>
          <p class="sr-only" role="status" data-test="customize-status">{{ announced }}</p>
        </section>
      </div>

      <footer class="sheet__foot">
        <v-btn
          variant="text"
          :prepend-icon="RotateCcw"
          :loading="layout.saving"
          data-test="customize-reset"
          @click="layout.reset()"
        >
          Back to the default
        </v-btn>
        <v-spacer />
        <v-btn color="primary" variant="flat" data-test="customize-done" @click="open = false">
          Done
        </v-btn>
      </footer>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.sheet {
  justify-content: flex-end;
}

.sheet > :deep(.v-overlay__content) {
  width: min(38rem, 100%);
  max-width: none;
  height: 100%;
  max-height: 100%;
  margin: 0;
}

@media (max-width: 599.98px) {
  .sheet > :deep(.v-overlay__content) {
    align-self: flex-start;
    height: calc(100% - var(--bottom-bar-height));
    max-height: calc(100% - var(--bottom-bar-height));
  }
}

.sheet__card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding-bottom: env(safe-area-inset-bottom);
}

.sheet__head,
.sheet__foot {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
}

.sheet__head {
  justify-content: space-between;
  padding-left: 1.5rem;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.sheet__foot {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.sheet__title {
  margin: 0;
}

.sheet__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.5rem;
  overflow-y: auto;
}

h3,
p {
  margin: 0;
}

.presets,
.widgets {
  display: grid;
  gap: 0.5rem;
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
}

.presets {
  grid-template-columns: repeat(auto-fit, minmax(min(11rem, 100%), 1fr));
}

.preset {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  width: 100%;
  height: 100%;
  padding: 0.75rem 1rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 1rem;
  background: transparent;
  color: inherit;
  text-align: start;
  cursor: pointer;
  transition:
    border-color 0.2s,
    background-color 0.2s;
}

.preset:hover,
.preset:focus-visible {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.preset--on {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}

.widget {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.5rem 0.75rem;
  align-items: center;
  padding: 0.75rem;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 1rem;
  background: rgb(var(--v-theme-surface));
  transition:
    border-color 0.2s,
    opacity 0.2s;
}

.widget--off {
  opacity: 0.65;
}

.widget--over {
  border-color: rgb(var(--v-theme-primary));
}

.widget__grip {
  display: grid;
  place-items: center;
  width: 2rem;
  height: 2rem;
  cursor: grab;
  color: rgba(var(--v-theme-on-surface), 0.6);
  touch-action: none;
}

.widget__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.widget__controls {
  display: flex;
  flex-wrap: wrap;
  grid-column: 1 / -1;
  align-items: center;
  gap: 0.5rem 1rem;
}

.widget__moves {
  display: flex;
  margin-inline-start: auto;
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
