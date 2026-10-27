import { nextTick, ref } from 'vue'

import { useSelection } from '@/selection'

const ids = (...numbers: number[]) => ref(numbers.map((id) => ({ id })))

function picking(...numbers: number[]) {
  const items = ids(...numbers)
  return { items, ...useSelection(items) }
}

describe('picking incidents', () => {
  it('starts with none', () => {
    const { any, wholePage, picked, everything } = picking(1, 2, 3)

    expect([any.value, wholePage.value, everything.value]).toEqual([false, false, false])
    expect(picked.value.size).toBe(0)
  })

  it('ticks one and takes it off', () => {
    const { toggle, has, any, onPage } = picking(1, 2, 3)

    toggle(2)
    expect([has(1), has(2), any.value, onPage.value]).toEqual([false, true, true, 1])

    toggle(2)
    expect([has(2), any.value]).toEqual([false, false])
  })

  it('ticks all between this one and the last ticked when shift is held', () => {
    const { toggle, picked } = picking(1, 2, 3, 4, 5)

    toggle(2)
    toggle(4, true)

    expect([...picked.value].sort()).toEqual([2, 3, 4])
  })

  it('takes off all between when the last one was taken off', () => {
    const { toggle, picked, togglePage } = picking(1, 2, 3, 4, 5)
    togglePage()
    toggle(1)

    toggle(4, true)

    expect([...picked.value]).toEqual([5])
  })

  it('goes either way along the list for a range', () => {
    const { toggle, picked } = picking(1, 2, 3, 4, 5)

    toggle(5)
    toggle(3, true)

    expect([...picked.value].sort()).toEqual([3, 4, 5])
  })

  it('ticks just the one when shift is held and there is no last one', () => {
    const { toggle, picked } = picking(1, 2, 3)

    toggle(3, true)

    expect([...picked.value]).toEqual([3])
  })

  it('ticks every one on the page, or takes them all off if they are all ticked', () => {
    const { togglePage, wholePage, picked } = picking(1, 2, 3)

    togglePage()
    expect([wholePage.value, picked.value.size]).toEqual([true, 3])

    togglePage()
    expect([wholePage.value, picked.value.size]).toEqual([false, 0])
  })

  it('has no whole page when the page is empty', () => {
    const { wholePage } = picking()

    expect(wholePage.value).toBe(false)
  })

  it('picks all that match, which are more than the page, and says every one is picked', () => {
    const { pickEverything, everything, has, any, picked } = picking(1, 2)

    pickEverything()

    expect([everything.value, has(1), has(999), any.value, picked.value.size]).toEqual([
      true,
      true,
      true,
      true,
      2,
    ])
  })

  it('goes back to the ones ticked when one is taken off or another ticked', () => {
    const { pickEverything, toggle, everything, has } = picking(1, 2, 3)
    pickEverything()

    toggle(2)

    expect(everything.value).toBe(false)
    expect([has(1), has(2), has(3)]).toEqual([true, false, true])
  })

  it('lets go of all of them', () => {
    const { pickEverything, clear, any, everything, picked } = picking(1, 2)
    pickEverything()

    clear()

    expect([any.value, everything.value, picked.value.size]).toEqual([false, false, 0])
  })

  it('lets go of an incident that leaves the list', async () => {
    const { items, togglePage, picked, toggle } = picking(1, 2, 3)
    togglePage()

    items.value = [{ id: 2 }, { id: 3 }, { id: 4 }]
    await nextTick()

    expect([...picked.value].sort()).toEqual([2, 3])
    toggle(4, true)
    expect([...picked.value].sort()).toEqual([2, 3, 4])
  })

  it('forgets the last one ticked when it leaves the list', async () => {
    const { items, toggle, picked } = picking(1, 2, 3)
    toggle(1)

    items.value = [{ id: 2 }, { id: 3 }]
    await nextTick()
    toggle(3, true)

    expect([...picked.value]).toEqual([3])
  })

  it('keeps what is picked while the list is asked for again with the same incidents', async () => {
    const { items, togglePage, picked } = picking(1, 2)
    togglePage()
    const before = picked.value

    items.value = [{ id: 1 }, { id: 2 }]
    await nextTick()

    expect(picked.value).toBe(before)
  })
})
