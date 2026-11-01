<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, ref, useId, watch } from 'vue'

import { errorMessage } from '@/api/client'
import {
  changeInterface,
  createInterface,
  removeInterface,
  type Interface,
  type Role,
} from '@/api/interfaces'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import RolePicker from '@/components/RolePicker.vue'
import { useKeyboardReturn } from '@/dialog'
import { useSessionStore } from '@/stores/session'

/**
 * Names a part of the network and says what it is for. It is a sheet from the side on a desktop
 * and the screen above the bottom bar on a phone. With an `interface` it changes that one (and can remove it);
 * without, it makes a new one, starting from `starter` when a suggestion or a feed has already
 * said some of what it should be. It makes the change itself and tells whoever shows it what it
 * did; a refusal is said inside it, in the API's words, and nothing closes.
 */
const props = defineProps<{
  interface: Interface | null
  /** What a new interface starts as, and the feeds that are placed on it as it is made. */
  starter?: { name: string; role: Role; feeds: number[] } | null
}>()
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ saved: [string]; removed: [string] }>()

const MAX_NAME = 40
const MAX_NOTES = 300

const session = useSessionStore()
const titleId = useId()
const giveBackTheKeyboard = useKeyboardReturn(open)

const name = ref('')
const role = ref<Role>('home')
const notes = ref('')
const networks = ref('')
const problem = ref<string | null>(null)
const saving = ref(false)
const confirming = ref(false)
const removing = ref(false)

const editing = computed(() => props.interface !== null)
const title = computed(() =>
  props.interface ? `Edit ${props.interface.name}` : 'Add an interface',
)
const ready = computed(() => name.value.trim() !== '' && !saving.value)

watch(
  open,
  (opening) => {
    if (!opening) return
    const from = props.interface
    name.value = from?.name ?? props.starter?.name ?? ''
    role.value = from?.role ?? props.starter?.role ?? 'home'
    notes.value = from?.notes ?? ''
    networks.value = (from?.networks ?? []).join('\n')
    problem.value = null
  },
  { immediate: true },
)

const blocks = () => networks.value.split(/[\s,]+/).filter((block) => block !== '')

async function save() {
  if (!ready.value) return
  saving.value = true
  problem.value = null
  const wanted = {
    name: name.value.trim(),
    role: role.value,
    notes: notes.value.trim(),
    networks: blocks(),
  }
  try {
    if (props.interface) {
      const id = props.interface.id
      await session.change((token) => changeInterface(id, wanted, token))
      emit('saved', `${wanted.name} saved.`)
    } else {
      const feeds = props.starter?.feeds ?? []
      await session.change((token) => createInterface({ ...wanted, feeds }, token))
      emit('saved', `${wanted.name} added.`)
    }
    open.value = false
  } catch (error) {
    problem.value = errorMessage(error)
  } finally {
    saving.value = false
  }
}

async function remove() {
  const gone = props.interface as Interface
  removing.value = true
  try {
    await session.change((token) => removeInterface(gone.id, token))
    confirming.value = false
    open.value = false
    emit('removed', `${gone.name} removed. Its feeds are not placed now.`)
  } catch (error) {
    confirming.value = false
    problem.value = errorMessage(error)
  } finally {
    removing.value = false
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
    <v-card class="sheet__card" :rounded="0" data-test="interface-editor">
      <header class="sheet__head">
        <h2 :id="titleId" class="text-title-large sheet__title" data-test="editor-title">
          {{ title }}
        </h2>
        <v-btn
          icon
          variant="text"
          size="small"
          aria-label="Close"
          data-test="editor-close"
          @click="open = false"
        >
          <v-icon :icon="X" />
        </v-btn>
      </header>

      <form class="sheet__body" @submit.prevent="save">
        <v-alert
          v-if="problem"
          type="error"
          variant="tonal"
          density="compact"
          data-test="editor-problem"
        >
          {{ problem }}
        </v-alert>

        <v-text-field
          v-model="name"
          label="Name"
          hint="What you call it, such as Internet, Guests or Cameras."
          persistent-hint
          :counter="MAX_NAME"
          :maxlength="MAX_NAME"
          autocomplete="off"
          data-test="editor-name"
        />

        <RolePicker v-model="role" />

        <v-textarea
          v-model="networks"
          label="Networks"
          hint="Optional. One per line, like 192.168.20.0/24. They tell AresGate which devices live here."
          persistent-hint
          rows="2"
          auto-grow
          spellcheck="false"
          autocomplete="off"
          data-test="editor-networks"
        />

        <v-textarea
          v-model="notes"
          label="Notes"
          hint="Optional. Anything worth remembering about it."
          persistent-hint
          :counter="MAX_NOTES"
          :maxlength="MAX_NOTES"
          rows="2"
          auto-grow
          data-test="editor-notes"
        />
      </form>

      <footer class="sheet__foot">
        <v-btn
          v-if="editing"
          variant="text"
          color="error"
          :disabled="saving"
          data-test="editor-remove"
          @click="confirming = true"
        >
          Remove
        </v-btn>
        <span class="sheet__spacer" />
        <v-btn variant="text" :disabled="saving" data-test="editor-cancel" @click="open = false">
          Cancel
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :disabled="!ready"
          :loading="saving"
          data-test="editor-save"
          @click="save"
        >
          {{ editing ? 'Save' : 'Add' }}
        </v-btn>
      </footer>
    </v-card>
  </v-dialog>

  <ConfirmDialog
    v-model="confirming"
    :title="`Remove ${interface?.name ?? 'this interface'}?`"
    confirm-label="Remove"
    destructive
    :busy="removing"
    @confirm="remove"
  >
    Its feeds stay, and are not placed on anything again until you place them. Nothing that was
    collected is lost.
  </ConfirmDialog>
</template>

<style scoped>
/* A sheet from the side, as tall as the screen; on a phone as wide as it too, and above the bar
   along the bottom, which stays where it is under the dimmed page. */
.sheet {
  justify-content: flex-end;
}

.sheet > :deep(.v-overlay__content) {
  width: min(34rem, 100%);
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

.sheet__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 0.75rem 0.75rem 1.5rem;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.sheet__title {
  margin: 0;
  overflow-wrap: anywhere;
}

.sheet__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.5rem;
  overflow-y: auto;
}

.sheet__foot {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.sheet__spacer {
  flex: 1;
}
</style>
