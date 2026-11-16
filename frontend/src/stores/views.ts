import { defineStore } from 'pinia'
import { ref } from 'vue'

import { errorMessage } from '@/api/client'
import {
  changeView,
  deleteView,
  fetchViews,
  saveView,
  type SavedView,
  type ViewPage,
  type ViewQuery,
} from '@/api/views'
import { useSessionStore } from '@/stores/session'

/** By page, then by name whatever the case, as the API lists them. */
function byPageAndName(a: SavedView, b: SavedView): number {
  return (
    a.page.localeCompare(b.page) ||
    a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }) ||
    a.id - b.id
  )
}

/**
 * The views this account kept for its lists, shared by the toolbar of each list and the command
 * palette. They are asked for once, and what is changed here is changed in the list at once.
 */
export const useViewsStore = defineStore('views', () => {
  const session = useSessionStore()
  const items = ref<SavedView[]>([])
  const loaded = ref(false)
  const failure = ref<string | null>(null)
  let loading: Promise<void> | null = null

  /** Asks for the views, unless they are known. */
  function load(): Promise<void> {
    if (loaded.value) return Promise.resolve()
    loading ??= (async () => {
      try {
        items.value = await session.call(() => fetchViews())
        loaded.value = true
        failure.value = null
      } catch (error) {
        failure.value = errorMessage(error)
      } finally {
        loading = null
      }
    })()
    return loading
  }

  const of = (page: ViewPage) => items.value.filter((view) => view.page === page)
  const defaultOf = (page: ViewPage) => of(page).find((view) => view.is_default)

  /** Puts a view as the API now has it among the others. Making one the default takes it from
   * the page's other views. */
  function adopt(view: SavedView) {
    const others = items.value
      .filter((other) => other.id !== view.id)
      .map((other) =>
        view.is_default && other.page === view.page ? { ...other, is_default: false } : other,
      )
    items.value = [...others, view].sort(byPageAndName)
  }

  async function save(page: ViewPage, name: string, query: ViewQuery, makeDefault = false) {
    const saved = await session.change((token) => saveView(page, name, query, makeDefault, token))
    adopt(saved)
    return saved
  }

  async function rename(view: SavedView, name: string) {
    adopt(await session.change((token) => changeView(view.id, { name }, token)))
  }

  async function setDefault(view: SavedView, on: boolean) {
    adopt(await session.change((token) => changeView(view.id, { default: on }, token)))
  }

  async function remove(view: SavedView) {
    await session.change((token) => deleteView(view.id, token))
    items.value = items.value.filter((other) => other.id !== view.id)
  }

  return { items, loaded, failure, load, of, defaultOf, save, rename, setDefault, remove }
})
