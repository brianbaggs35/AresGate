import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'

import { stepIndex, useElementWidth } from '@/charts/interaction'

describe('stepIndex', () => {
  it('steps forward with the right and down arrows, from the start when there is no place yet', () => {
    expect(stepIndex('ArrowRight', null, 5)).toBe(0)
    expect(stepIndex('ArrowDown', 1, 5)).toBe(2)
  })

  it('steps back with the left and up arrows, from the end when there is no place yet', () => {
    expect(stepIndex('ArrowLeft', null, 5)).toBe(4)
    expect(stepIndex('ArrowUp', 3, 5)).toBe(2)
  })

  it('stops at the ends', () => {
    expect(stepIndex('ArrowRight', 4, 5)).toBe(4)
    expect(stepIndex('ArrowLeft', 0, 5)).toBe(0)
  })

  it('goes to the ends with Home and End', () => {
    expect(stepIndex('Home', 3, 5)).toBe(0)
    expect(stepIndex('End', 1, 5)).toBe(4)
  })

  it('puts the readout away with Escape', () => {
    expect(stepIndex('Escape', 2, 5)).toBeNull()
  })

  it('leaves every other key alone', () => {
    expect(stepIndex('a', 2, 5)).toBeUndefined()
    expect(stepIndex('Tab', null, 5)).toBeUndefined()
  })
})

describe('useElementWidth', () => {
  const original = globalThis.ResizeObserver
  const observers: { callback: () => void; disconnected: boolean; target?: Element }[] = []

  beforeEach(() => {
    observers.length = 0
    globalThis.ResizeObserver = class {
      private readonly record: (typeof observers)[number]
      constructor(callback: () => void) {
        this.record = { callback, disconnected: false }
        observers.push(this.record)
      }
      observe(target: Element) {
        this.record.target = target
      }
      unobserve() {}
      disconnect() {
        this.record.disconnected = true
      }
    } as unknown as typeof ResizeObserver
  })
  afterEach(() => {
    globalThis.ResizeObserver = original
  })

  /** A component with an element that can be there or not, and a width it reports. */
  function mountWith(clientWidth: number) {
    const present = ref(true)
    const shown = ref(0)
    const Probe = defineComponent({
      setup() {
        const target = ref<HTMLElement | null>(null)
        const width = useElementWidth(target, 300)
        return () =>
          h('div', [
            h('span', { 'data-test': 'width' }, String(width.value)),
            present.value
              ? h('p', {
                  ref: target,
                  key: shown.value,
                  onVue: undefined,
                })
              : null,
          ])
      },
    })
    const wrapper = mount(Probe, { attachTo: document.body })
    const element = () => wrapper.find('p').element
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get: () => clientWidth,
    })
    return { wrapper, element, present, shown }
  }

  afterEach(() => {
    Reflect.deleteProperty(HTMLElement.prototype, 'clientWidth')
  })

  it('starts with the fallback, then measures the element once it is there', async () => {
    const { wrapper } = mountWith(480)
    expect(wrapper.find('[data-test="width"]').text()).toBe('300')
    await nextTick()
    await nextTick()
    expect(wrapper.find('[data-test="width"]').text()).toBe('480')
    expect(observers).toHaveLength(1)
    wrapper.unmount()
    expect(observers[0]?.disconnected).toBe(true)
  })

  it('keeps the fallback for an element with no width yet', async () => {
    const { wrapper } = mountWith(0)
    await nextTick()
    await nextTick()
    expect(wrapper.find('[data-test="width"]').text()).toBe('300')
    wrapper.unmount()
  })

  it('follows the element as it changes size, and follows its replacement', async () => {
    const { wrapper, present, shown } = mountWith(480)
    await nextTick()
    await nextTick()
    Reflect.deleteProperty(HTMLElement.prototype, 'clientWidth')
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get: () => 520,
    })
    observers[0]?.callback()
    await nextTick()
    expect(wrapper.find('[data-test="width"]').text()).toBe('520')

    present.value = false
    await nextTick()
    await nextTick()
    expect(observers[0]?.disconnected).toBe(true)
    present.value = true
    shown.value++
    await nextTick()
    await nextTick()
    expect(observers).toHaveLength(2)
    expect(observers[1]?.disconnected).toBe(false)
    wrapper.unmount()
  })
})
