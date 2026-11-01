import { ref } from 'vue'

import { errorMessage } from '@/api/client'
import {
  createInterface,
  discoverFeeds,
  fetchInterfaces,
  fetchOverview,
  placeFeed,
  removeInterface,
  type Discovery,
  type Feed,
  type Listing,
  type Overview,
  type OverviewWindow,
  type Placement,
  type Suggestion,
} from '@/api/interfaces'
import { formatCount } from '@/format'
import { feedName } from '@/interfaces'
import { useSessionStore } from '@/stores/session'

/** What was done, in words, and how to take it back (null when it can't be). */
export interface Done {
  text: string
  undo: (() => Promise<void>) | null
}

/** A change that can always be taken back. */
type Undoable = Done & { undo: () => Promise<void> }

/** Not placed anywhere, and not set aside: where a feed is before anyone decides. */
export const NOT_PLACED: Placement = { interface_id: null, ignored: false }

/** Runs a step for each item one after the other, because each needs the one before it to be
 * done (or to have failed, which stops the rest). */
async function inOrder<T>(items: readonly T[], step: (item: T) => Promise<void>): Promise<void> {
  await items.reduce(async (before, item) => {
    await before
    await step(item)
  }, Promise.resolve())
}

const feeds = (count: number) => `${formatCount(count)} ${count === 1 ? 'feed' : 'feeds'}`

/**
 * The interfaces, what each has been doing, and the changes the owner makes to where feeds are
 * placed. Every change says what it did and how to take it back, and the page shows that for a
 * while; a change that fails says why and leaves things as they were.
 */
export function useInterfaceBoard() {
  const session = useSessionStore()

  const listing = ref<Listing | null>(null)
  const overview = ref<Overview | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  /** Why the last change could not be made. */
  const problem = ref<string | null>(null)
  /** What is being changed now, so the page can show that it is working. */
  const busy = ref(false)

  let window: OverviewWindow = '24h'

  /** Asks for everything again, for the window it was last asked for. */
  async function load(asked: OverviewWindow = window) {
    window = asked
    loading.value = true
    error.value = null
    try {
      const [list, stats] = await Promise.all([
        session.call(fetchInterfaces),
        session.call(() => fetchOverview(asked)),
      ])
      listing.value = list
      overview.value = stats
    } catch (loadError) {
      error.value = errorMessage(loadError)
    } finally {
      loading.value = false
    }
  }

  /** Runs a change, then reads everything again. What it said is returned, or null if it failed
   * (`problem` says why). */
  async function act(change: () => Promise<Done>): Promise<Done | null> {
    busy.value = true
    problem.value = null
    try {
      const done = await change()
      await load()
      return done
    } catch (changeError) {
      problem.value = errorMessage(changeError)
      // What did get done is still on the page.
      await load()
      return null
    } finally {
      busy.value = false
    }
  }

  /** The name of a place, for a sentence. */
  function where(placement: Placement): string {
    if (placement.ignored) return 'set aside'
    const found = listing.value?.interfaces.find((item) => item.id === placement.interface_id)
    return found ? `on ${found.name}` : 'not placed yet'
  }

  /** Puts feeds where they are asked to go. The way back puts each where it was. */
  async function putAll(
    which: readonly Feed[],
    placement: Placement,
    text: string,
  ): Promise<Undoable> {
    const before = which.map((feed) => ({
      id: feed.id,
      placement: { interface_id: feed.interface_id, ignored: feed.ignored },
    }))
    await inOrder(which, async (feed) => {
      await session.change((token) => placeFeed(feed.id, placement, token))
    })
    return {
      text,
      undo: () =>
        inOrder(before, async ({ id, placement: back }) => {
          await session.change((token) => placeFeed(id, back, token))
        }),
    }
  }

  function move(feed: Feed, placement: Placement) {
    return act(() => putAll([feed], placement, `${feedName(feed)} is now ${where(placement)}.`))
  }

  /** Every feed a suggestion names, as they are listed now. */
  function feedsOf(suggestion: Suggestion): Feed[] {
    const all = listing.value ? [...listing.value.unplaced, ...listing.value.ignored] : []
    return all.filter((feed) => suggestion.feed_ids.includes(feed.id))
  }

  /** Does what a suggestion says: the feeds join the interface of that name, which is made if
   * it isn't there. Taking it back moves the feeds off, and removes an interface it made. */
  async function applySuggestion(suggestion: Suggestion): Promise<Undoable> {
    const text = `${feeds(suggestion.feed_ids.length)} placed on ${suggestion.name}.`
    if (suggestion.interface_id !== null) {
      const target = suggestion.interface_id
      return putAll(feedsOf(suggestion), { interface_id: target }, text)
    }
    const made = await session.change((token) =>
      createInterface(
        { name: suggestion.name, role: suggestion.role, feeds: suggestion.feed_ids },
        token,
      ),
    )
    return {
      text,
      undo: async () => {
        await session.change((token) => removeInterface(made.id, token))
      },
    }
  }

  const confirm = (suggestion: Suggestion) => act(() => applySuggestion(suggestion))

  /** Confirms them all; taking it back takes back each, last first. */
  function confirmAll(suggestions: readonly Suggestion[]) {
    return act(async () => {
      /** What takes each back, the last one first, which is the order they are taken back in. */
      const undos: (() => Promise<void>)[] = []
      let placed = 0
      await inOrder(suggestions, async (suggestion) => {
        const done = await applySuggestion(suggestion)
        placed += suggestion.feed_ids.length
        undos.unshift(done.undo)
      })
      return {
        text: `${feeds(placed)} placed on ${suggestions.length} ${suggestions.length === 1 ? 'interface' : 'interfaces'}.`,
        undo: () => inOrder(undos, (undo) => undo()),
      }
    })
  }

  /** Sets what a suggestion names aside, as not wanted. */
  function dismiss(suggestion: Suggestion) {
    return act(() =>
      putAll(
        feedsOf(suggestion),
        { ignored: true },
        `${feeds(suggestion.feed_ids.length)} set aside.`,
      ),
    )
  }

  /** Takes a change back, then reads everything again. */
  async function undo(done: Done) {
    if (done.undo === null) return null
    const way = done.undo
    return act(async () => {
      await way()
      return { text: 'Taken back.', undo: null }
    })
  }

  /** Looks through what has been collected for feeds not seen before. Nothing is placed. */
  async function find(): Promise<Discovery | null> {
    busy.value = true
    problem.value = null
    try {
      const found = await session.change(discoverFeeds)
      await load()
      return found
    } catch (findError) {
      problem.value = errorMessage(findError)
      return null
    } finally {
      busy.value = false
    }
  }

  return {
    listing,
    overview,
    loading,
    error,
    problem,
    busy,
    load,
    move,
    confirm,
    confirmAll,
    dismiss,
    undo,
    find,
  }
}
