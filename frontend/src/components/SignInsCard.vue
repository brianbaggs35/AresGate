<script setup lang="ts">
import { LogOut, Monitor, Smartphone } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'

import { endOtherSignIns, endSignIn, fetchSignIns, type SignIn } from '@/api/account'
import { errorMessage } from '@/api/client'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import LoadError from '@/components/LoadError.vue'
import SectionCard from '@/components/SectionCard.vue'
import { describeBrowser, formatAgo, formatDateTime } from '@/format'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()

const signIns = ref<SignIn[] | null>(null)
const loadError = ref<string | null>(null)
const loading = ref(false)

const notice = ref<string | null>(null)
const failure = ref<string | null>(null)
const busy = ref(false)
/** One browser being asked about, or every other. The dialog keeps showing what it was asked
 * about while it fades out, so the target is left as it was when it closes. */
const askingAboutOne = ref(false)
const askingAboutOthers = ref(false)
const target = ref<SignIn | null>(null)

const others = computed(() => signIns.value?.filter((signIn) => !signIn.current) ?? [])

const nameOf = (signIn: SignIn) => describeBrowser(signIn.user_agent)
const iconOf = (signIn: SignIn) =>
  /Android|iPhone|iPad|iPod/.test(signIn.user_agent ?? '') ? Smartphone : Monitor

async function load() {
  loading.value = true
  loadError.value = null
  try {
    signIns.value = await session.call(fetchSignIns)
  } catch (error) {
    loadError.value = errorMessage(error)
  } finally {
    loading.value = false
  }
}

function askAboutOne(signIn: SignIn) {
  target.value = signIn
  askingAboutOne.value = true
}

/** Runs a change, then lists again, since what it did (or what someone else did meanwhile)
 * decides what is there. The dialog closes either way, so what happened shows behind it. */
async function change(request: (token: string) => Promise<string>) {
  busy.value = true
  notice.value = null
  failure.value = null
  try {
    notice.value = await session.change(request)
  } catch (error) {
    failure.value = errorMessage(error)
  } finally {
    busy.value = false
    askingAboutOne.value = false
    askingAboutOthers.value = false
  }
  await load()
}

const endOne = () =>
  change(async (token) => {
    const signIn = target.value as SignIn
    await endSignIn(signIn.id, token)
    return `${nameOf(signIn)} was signed out.`
  })

const endOthers = () =>
  change(async (token) => {
    const { ended } = await endOtherSignIns(token)
    return ended === 1
      ? '1 other sign-in was ended.'
      : `${ended.toString()} other sign-ins were ended.`
  })

onMounted(load)
</script>

<template>
  <SectionCard
    title="Where you're signed in"
    description="Each browser that is signed in to this account. Sign out any you don't recognise, then change your password."
    data-test="sign-ins-card"
  >
    <template v-if="others.length" #actions>
      <v-btn
        variant="tonal"
        color="error"
        :prepend-icon="LogOut"
        :disabled="busy"
        data-test="end-others"
        @click="askingAboutOthers = true"
      >
        Sign out everywhere else
      </v-btn>
    </template>

    <v-alert v-if="notice" type="success" variant="tonal" class="mb-4" data-test="sign-ins-notice">
      {{ notice }}
    </v-alert>
    <v-alert v-if="failure" type="error" variant="tonal" class="mb-4" data-test="sign-ins-failure">
      {{ failure }}
    </v-alert>

    <LoadError
      v-if="loadError"
      :message="loadError"
      :loading="loading"
      retry-test-id="sign-ins-retry"
      data-test="sign-ins-error"
      @retry="load"
    />
    <v-skeleton-loader v-else-if="!signIns" type="list-item-two-line, list-item-two-line" />
    <ul v-else class="sign-ins" data-test="sign-in-list">
      <li v-for="signIn in signIns" :key="signIn.id" class="sign-ins__item" data-test="sign-in">
        <component :is="iconOf(signIn)" class="sign-ins__icon" aria-hidden="true" />
        <div class="sign-ins__text">
          <div class="text-body-large">
            <span data-test="sign-in-name">{{ nameOf(signIn) }}</span>
            <v-chip
              v-if="signIn.current"
              size="small"
              color="primary"
              variant="tonal"
              class="ml-2"
              data-test="sign-in-current"
            >
              This browser
            </v-chip>
          </div>
          <div class="text-body-medium text-medium-emphasis" data-test="sign-in-details">
            Signed in {{ formatDateTime(signIn.started_at) }} · Last active
            {{ formatAgo(signIn.last_seen_at) }}
            <template v-if="signIn.address"> · {{ signIn.address }}</template>
          </div>
        </div>
        <v-btn
          v-if="!signIn.current"
          variant="text"
          color="error"
          :prepend-icon="LogOut"
          :disabled="busy"
          :aria-label="`Sign out ${nameOf(signIn)}`"
          data-test="end-sign-in"
          @click="askAboutOne(signIn)"
        >
          Sign out
        </v-btn>
      </li>
    </ul>
  </SectionCard>

  <ConfirmDialog
    v-model="askingAboutOne"
    :title="`Sign out ${target ? nameOf(target) : ''}?`"
    confirm-label="Sign out"
    destructive
    :busy="busy"
    @confirm="endOne"
  >
    That browser is signed out at once and has to sign in again.
  </ConfirmDialog>
  <ConfirmDialog
    v-model="askingAboutOthers"
    title="Sign out everywhere else?"
    confirm-label="Sign out"
    destructive
    :busy="busy"
    @confirm="endOthers"
  >
    Every other browser is signed out at once and has to sign in again. This one stays signed in.
  </ConfirmDialog>
</template>

<style scoped>
.sign-ins {
  list-style: none;
  margin: 0;
  padding: 0;
}

.sign-ins__item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0;
}

.sign-ins__item + .sign-ins__item {
  border-top: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
}

.sign-ins__icon {
  flex: none;
}

.sign-ins__text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
