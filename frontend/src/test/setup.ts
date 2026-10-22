import type { EventEmitter } from 'node:events'
import { performance } from 'node:perf_hooks'
import { format } from 'node:util'

import { unmountAll } from '@/test/cleanup'

// Time in tests comes from the monotonic clock. Vue ignores an event dated no later than the moment
// its handler was attached, so a wall clock that steps back drops a click or an input that lands
// just after the step, and a test fails at random. WSL2's does that about every half minute.
const clockOrigin = Date.now() - performance.now()
Date.now = () => Math.floor(clockOrigin + performance.now())

// jsdom lacks the layout APIs Vuetify relies on.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub

// Tests run as if motion were reduced: Vuetify animates a field's label by reading computed
// styles, which jsdom is far too slow at, and there is nothing to see here. What the animation
// looks like is checked in a real browser. Vuetify also finds its breakpoints by asking whether
// `(min-width: Npx)` matches, so those are answered from the window's width, which
// `mountWithPlugins` sets from a test's `width`.
const minWidthQuery = /^\(min-width: (\d+(?:\.\d+)?)px\)$/

function queryMatches(query: string) {
  const minWidth = minWidthQuery.exec(query)?.[1]
  if (minWidth === undefined) return query === '(prefers-reduced-motion: reduce)'
  return window.innerWidth >= Number(minWidth)
}

window.matchMedia = (query: string) =>
  ({
    matches: queryMatches(query),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }) as unknown as MediaQueryList

// Vuetify's menu positioning reads the visual viewport.
globalThis.visualViewport = Object.assign(new EventTarget(), {
  width: window.innerWidth,
  height: window.innerHeight,
  offsetLeft: 0,
  offsetTop: 0,
  pageLeft: 0,
  pageTop: 0,
  scale: 1,
  onresize: null,
  onscroll: null,
  onscrollend: null,
})

// Vue and Vuetify warn on the console, and jsdom reports there what it can't do, such as really
// submitting a form. A test that sets any of them off fails, so a warning is fixed where it starts
// rather than scrolling past in CI's output.
const consoleOutput: string[] = []
for (const level of ['warn', 'error'] as const) {
  console[level] = (...args: unknown[]) => {
    consoleOutput.push(format(...args))
  }
}
// jsdom's reports skip that console and go straight to the terminal, so they're collected here.
const { jsdom } = globalThis as unknown as { jsdom: { virtualConsole: EventEmitter } }
jsdom.virtualConsole.removeAllListeners('jsdomError')
jsdom.virtualConsole.on('jsdomError', (error: Error) => {
  consoleOutput.push(error.message)
})

function failOnConsoleOutput() {
  const output = consoleOutput.splice(0)
  if (output.length) {
    throw new Error(
      `Tests must run without warnings or errors, but this printed:\n\n${output.join('\n\n')}`,
    )
  }
}

// Nothing reaches a real network; tests mock the API functions they rely on.
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('fetch is not mocked')))
})

afterEach(() => {
  unmountAll()
  localStorage.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  failOnConsoleOutput()
})

// Catches anything printed after a file's last test, such as work left running when it ended.
afterAll(failOnConsoleOutput)
