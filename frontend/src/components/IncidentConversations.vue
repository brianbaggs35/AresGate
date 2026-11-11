<script setup lang="ts">
import { Clock, Target, Timer } from '@lucide/vue'
import { computed } from 'vue'

import type { Conversations } from '@/api/incidents'
import ConversationEnd from '@/components/ConversationEnd.vue'
import SeverityChip from '@/components/SeverityChip.vue'
import { conversationVolume, namedLook, serviceFor } from '@/evidence'
import { formatAgo, formatCount, formatList, formatSpan } from '@/format'
import { SEVERITY } from '@/severity'

/**
 * Who talked to whom, as a picture: for each conversation the alerts are about, the two ends with
 * what is known of each (where it is, whether it is on a blacklist, what the reputation service
 * says), what it was over, how much each side sent and for how long. What the programs said of the
 * same flow is put together once, so what two of them both saw is one conversation, and a program
 * that knew more than the others adds to it. The busiest come first. On a phone the ends stack and
 * the arrow points down.
 */
const props = defineProps<{ conversations: Conversations }>()
const emit = defineEmits<{ ruled: [] }>()

const items = computed(() =>
  props.conversations.items.map((conversation) => {
    const { protocol, app, server } = conversation
    const service = serviceFor(server)
    return {
      conversation,
      // What it went over: the transport, the kind of traffic, and the service on the port.
      over: [protocol?.toUpperCase(), app?.toUpperCase(), service]
        .filter((word): word is string => Boolean(word))
        .filter(
          (word, place, words) =>
            words.findIndex((other) => other.toLowerCase() === word.toLowerCase()) === place,
        ),
      volume: conversationVolume(conversation),
      programs: formatList(conversation.programs.map(({ source_name: name }) => name)),
    }
  }),
)
const left = computed(() => props.conversations.total - props.conversations.items.length)
</script>

<template>
  <div class="talks">
    <ol class="talks__list" data-test="conversations">
      <li
        v-for="{ conversation, over, volume, programs } in items"
        :key="`${conversation.client.address}-${conversation.server.address}-${conversation.server.port}`"
        class="talk"
        :style="{ '--tone': `var(--v-theme-${SEVERITY[conversation.severity].color})` }"
        data-test="conversation"
      >
        <div class="talk__head">
          <SeverityChip :severity="conversation.severity" />
          <span class="text-body-large" data-test="conversation-alerts">
            {{ formatCount(conversation.alerts) }}
            {{ conversation.alerts === 1 ? 'alert' : 'alerts' }}
            <template v-if="conversation.kinds > 1">
              of {{ formatCount(conversation.kinds) }} kinds
            </template>
          </span>
          <span
            class="text-body-medium text-medium-emphasis talk__last"
            data-test="conversation-last"
          >
            <v-icon :icon="Clock" size="16" aria-hidden="true" />
            last {{ formatAgo(conversation.last_at) }}
          </span>
        </div>

        <div class="talk__flow">
          <ConversationEnd :end="conversation.client" side="client" @ruled="emit('ruled')" />
          <div class="talk__link">
            <div v-if="over.length" class="talk__over" data-test="conversation-over">
              <v-chip v-for="word in over" :key="word" size="small" variant="flat" color="primary">
                {{ word }}
              </v-chip>
            </div>
            <svg
              class="talk__arrow"
              viewBox="0 0 120 12"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <line x1="0" y1="6" x2="108" y2="6" class="talk__line" />
              <path d="M104 1 L117 6 L104 11 Z" class="talk__head-mark" />
            </svg>
          </div>
          <ConversationEnd :end="conversation.server" side="server" @ruled="emit('ruled')" />
        </div>

        <div class="talk__facts">
          <figure v-if="volume" class="talk__volume" data-test="conversation-volume">
            <figcaption class="text-label-large text-medium-emphasis">
              The biggest flow, as the programs counted it
            </figcaption>
            <div class="talk__split" aria-hidden="true">
              <span class="talk__out" :style="{ width: `${volume.outShare.toString()}%` }" />
            </div>
            <p class="text-body-medium talk__sides">
              <span><b>Sent</b> {{ volume.outText }}</span>
              <span><b>Got back</b> {{ volume.inText }}</span>
            </p>
          </figure>
          <p
            v-if="conversation.duration !== null"
            class="text-body-large talk__duration"
            data-test="conversation-duration"
          >
            <v-icon :icon="Timer" size="20" aria-hidden="true" />
            Lasted {{ formatSpan(conversation.duration) }}
          </p>
        </div>

        <p
          v-if="conversation.purpose"
          class="text-body-large talk__purpose"
          data-test="conversation-purpose"
        >
          <v-icon :icon="Target" size="18" aria-hidden="true" />
          <span class="text-medium-emphasis">What it was for</span>
          {{ conversation.purpose }}
        </p>

        <ul v-if="conversation.names.length" class="talk__names" data-test="conversation-names">
          <li
            v-for="name in conversation.names"
            :key="`${name.kind}-${name.value}`"
            class="text-body-large talk__name"
          >
            <v-icon :icon="namedLook(name.kind).icon" size="18" aria-hidden="true" />
            <span class="text-medium-emphasis">{{ namedLook(name.kind).label }}</span>
            {{ name.value }}
          </li>
        </ul>

        <p class="text-body-medium text-medium-emphasis" data-test="conversation-programs">
          Reported by {{ programs }}
        </p>
      </li>
    </ol>
    <p v-if="left > 0" class="text-body-medium text-medium-emphasis" data-test="conversations-left">
      And {{ formatCount(left) }} more {{ left === 1 ? 'conversation' : 'conversations' }}, with
      fewer alerts.
    </p>
  </div>
</template>

<style scoped>
.talks {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.talks__list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.talk {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  padding: 1rem 1.125rem;
  border: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-left: 4px solid rgb(var(--tone));
  border-radius: 16px;
}

.talk p {
  margin: 0;
}

.talk__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}

.talk__last {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  margin-left: auto;
}

/* The two ends with the arrow between them; on a phone they stack and the arrow points down. */
.talk__flow {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(7rem, 11rem) minmax(0, 1fr);
  align-items: center;
  gap: 0.75rem;
}

.talk__link {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.375rem;
}

.talk__over {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.25rem;
}

.talk__arrow {
  width: 100%;
  height: 0.75rem;
  overflow: visible;
}

.talk__line {
  stroke: rgb(var(--v-theme-primary));
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-dasharray: 6 6;
  animation: talk-flow 1.2s linear infinite;
}

.talk__head-mark {
  fill: rgb(var(--v-theme-primary));
}

@keyframes talk-flow {
  to {
    stroke-dashoffset: -12;
  }
}

@media (prefers-reduced-motion: reduce) {
  .talk__line {
    animation: none;
  }
}

@media (max-width: 760px) {
  .talk__flow {
    grid-template-columns: minmax(0, 1fr);
  }

  .talk__link {
    flex-direction: row;
    justify-content: center;
    gap: 0.75rem;
  }

  .talk__arrow {
    width: 3rem;
    height: 0.75rem;
    margin: 1.125rem 0;
    transform: rotate(90deg);
  }
}

.talk__facts {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 0.75rem 2rem;
}

.talk__volume {
  flex: 1 1 16rem;
  margin: 0;
}

.talk__split {
  height: 0.5rem;
  margin: 0.375rem 0;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(var(--v-theme-secondary), 0.35);
}

.talk__out {
  display: block;
  height: 100%;
  background: rgb(var(--v-theme-primary));
}

.talk__sides {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
}

.talk__duration {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}

.talk__names {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.talk__name {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.375rem;
  overflow-wrap: anywhere;
}

.talk__purpose {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.375rem 0.5rem;
  margin: 0;
}
</style>
