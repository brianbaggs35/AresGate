import { createPinia, setActivePinia } from 'pinia'

import { ApiError } from '@/api/client'
import * as interfacesApi from '@/api/interfaces'
import { useInterfaceBoard } from '@/interface-board'
import { useSessionStore } from '@/stores/session'
import { feed, iface, listing, overview, suggestion } from '@/test/interfaces'

const TOKEN = 'a-security-token'

const PORT = feed({ id: 1 })
const OTHER = feed({ id: 2, native_name: 'igc2' })
const THIRD = feed({ id: 3, native_name: 'igc3', ignored: true })
const INTERNET = iface({ id: 5, name: 'Internet', feeds: [] })

/** What the page reads: one interface, two feeds waiting, one set aside. */
const LISTED = listing({
  interfaces: [INTERNET],
  unplaced: [PORT, OTHER],
  ignored: [THIRD],
})

function start() {
  setActivePinia(createPinia())
  useSessionStore().$patch({ known: true, username: 'admin', csrfToken: TOKEN })
  const fetchList = vi.spyOn(interfacesApi, 'fetchInterfaces').mockResolvedValue(LISTED)
  const fetchStats = vi.spyOn(interfacesApi, 'fetchOverview').mockResolvedValue(overview())
  const place = vi.spyOn(interfacesApi, 'placeFeed').mockResolvedValue(PORT)
  const create = vi.spyOn(interfacesApi, 'createInterface').mockResolvedValue(iface({ id: 8 }))
  const remove = vi.spyOn(interfacesApi, 'removeInterface').mockResolvedValue(undefined)
  const discover = vi
    .spyOn(interfacesApi, 'discoverFeeds')
    .mockResolvedValue({ new: 2, complete: true, notes: [] })
  return { board: useInterfaceBoard(), fetchList, fetchStats, place, create, remove, discover }
}

describe('useInterfaceBoard', () => {
  describe('loading', () => {
    it('reads the interfaces and what each has been doing', async () => {
      const { board, fetchStats } = start()

      await board.load('7d')

      expect(board.listing.value).toEqual(LISTED)
      expect(board.overview.value).toEqual(overview())
      expect(fetchStats).toHaveBeenCalledWith('7d')
      expect(board.loading.value).toBe(false)
      expect(board.error.value).toBeNull()
    })

    it('asks for the window it was last asked for', async () => {
      const { board, fetchStats } = start()
      await board.load('7d')

      await board.load()

      expect(fetchStats).toHaveBeenLastCalledWith('7d')
    })

    it('says why it could not, and recovers when asked again', async () => {
      const { board, fetchList } = start()
      fetchList.mockRejectedValueOnce(new ApiError(0, "Can't reach AresGate.", 'offline'))

      await board.load()
      expect(board.error.value).toBe("Can't reach AresGate.")
      expect(board.listing.value).toBeNull()

      await board.load()
      expect(board.error.value).toBeNull()
      expect(board.listing.value).not.toBeNull()
    })
  })

  describe('moving a feed', () => {
    it('puts it there, reads everything again, and says what it did', async () => {
      const { board, place, fetchList } = start()
      await board.load()

      const done = await board.move(PORT, { interface_id: 5 })

      expect(place).toHaveBeenCalledWith(1, { interface_id: 5 }, TOKEN)
      expect(done?.text).toBe('OPNsense igc0 is now on Internet.')
      expect(fetchList).toHaveBeenCalledTimes(2)
      expect(board.busy.value).toBe(false)
    })

    it.each([
      [{ ignored: true }, 'OPNsense igc0 is now set aside.'],
      [{ interface_id: null, ignored: false }, 'OPNsense igc0 is now not placed yet.'],
    ])('says %j in words', async (placement, text) => {
      const { board } = start()
      await board.load()

      expect((await board.move(PORT, placement))?.text).toBe(text)
    })

    it('can be taken back, which puts the feed where it was', async () => {
      const { board, place } = start()
      await board.load()
      const done = await board.move(THIRD, { interface_id: 5 })
      place.mockClear()

      const back = await board.undo(done!)

      expect(place).toHaveBeenCalledWith(3, { interface_id: null, ignored: true }, TOKEN)
      expect(back?.text).toBe('Taken back.')
      expect(back?.undo).toBeNull()
    })

    it('says why it could not, and reads everything again so the page is true', async () => {
      const { board, place, fetchList } = start()
      await board.load()
      place.mockRejectedValue(new ApiError(404, 'That feed is not there.', 'x'))

      const done = await board.move(PORT, { interface_id: 5 })

      expect(done).toBeNull()
      expect(board.problem.value).toBe('That feed is not there.')
      expect(fetchList).toHaveBeenCalledTimes(2)
      expect(board.busy.value).toBe(false)
    })

    it('forgets an earlier problem when the next change is made', async () => {
      const { board, place } = start()
      await board.load()
      place.mockRejectedValueOnce(new ApiError(404, 'No.', 'x'))
      await board.move(PORT, { interface_id: 5 })

      await board.move(PORT, { interface_id: 5 })

      expect(board.problem.value).toBeNull()
    })
  })

  describe('suggestions', () => {
    it('confirming one that joins an interface places its feeds on it', async () => {
      const { board, place, create } = start()
      await board.load()

      const done = await board.confirm(
        suggestion({ interface_id: 5, feed_ids: [1, 2], name: 'Internet' }),
      )

      expect(place.mock.calls.map(([id, placement]) => [id, placement])).toEqual([
        [1, { interface_id: 5 }],
        [2, { interface_id: 5 }],
      ])
      expect(create).not.toHaveBeenCalled()
      expect(done?.text).toBe('2 feeds placed on Internet.')
    })

    it('confirming one for an interface that is not there makes it, with its feeds', async () => {
      const { board, create } = start()
      await board.load()

      const done = await board.confirm(suggestion({ feed_ids: [2] }))

      expect(create).toHaveBeenCalledWith({ name: 'Guests', role: 'guest', feeds: [2] }, TOKEN)
      expect(done?.text).toBe('1 feed placed on Guests.')
    })

    it('taking it back removes the interface it made', async () => {
      const { board, remove } = start()
      await board.load()
      const done = await board.confirm(suggestion())

      await board.undo(done!)

      expect(remove).toHaveBeenCalledWith(8, TOKEN)
    })

    it('taking it back moves the feeds back to where they were', async () => {
      const { board, place } = start()
      await board.load()
      const done = await board.confirm(suggestion({ interface_id: 5, feed_ids: [1] }))
      place.mockClear()

      await board.undo(done!)

      expect(place).toHaveBeenCalledWith(1, { interface_id: null, ignored: false }, TOKEN)
    })

    it('confirming all does each, and taking it back takes back each, last first', async () => {
      const { board, place, create, remove } = start()
      await board.load()
      create.mockResolvedValueOnce(iface({ id: 8 })).mockResolvedValueOnce(iface({ id: 9 }))

      const done = await board.confirmAll([
        suggestion({ name: 'Guests', feed_ids: [1] }),
        suggestion({ name: 'Cameras', role: 'iot', feed_ids: [2, 3] }),
      ])
      expect(done?.text).toBe('3 feeds placed on 2 interfaces.')
      place.mockClear()

      await board.undo(done!)

      expect(remove.mock.calls.map(([id]) => id)).toEqual([9, 8])
      expect(place).not.toHaveBeenCalled()
    })

    it('says interface in the singular when it confirms all of one', async () => {
      const { board } = start()
      await board.load()

      const done = await board.confirmAll([suggestion({ feed_ids: [1] })])

      expect(done?.text).toBe('1 feed placed on 1 interface.')
    })

    it('ignoring one sets its feeds aside', async () => {
      const { board, place } = start()
      await board.load()

      const done = await board.dismiss(suggestion({ feed_ids: [1, 2] }))

      expect(place.mock.calls.map(([id, placement]) => [id, placement])).toEqual([
        [1, { ignored: true }],
        [2, { ignored: true }],
      ])
      expect(done?.text).toBe('2 feeds set aside.')
    })

    it('does not look for feeds before the page has read any', async () => {
      const { board, place } = start()

      await board.dismiss(suggestion({ feed_ids: [1] }))

      expect(place).not.toHaveBeenCalled()
    })

    it('does not look for feeds that the page does not have', async () => {
      const { board, place } = start()
      await board.load()

      await board.dismiss(suggestion({ feed_ids: [99] }))

      expect(place).not.toHaveBeenCalled()
    })
  })

  describe('taking a change back', () => {
    it('has nothing to do for a change that cannot be', async () => {
      const { board, place } = start()

      expect(await board.undo({ text: 'Saved.', undo: null })).toBeNull()
      expect(place).not.toHaveBeenCalled()
    })

    it('says why it could not', async () => {
      const { board } = start()
      const failing = () => Promise.reject(new ApiError(409, 'Something else changed.', 'x'))

      expect(await board.undo({ text: 'x', undo: failing })).toBeNull()
      expect(board.problem.value).toBe('Something else changed.')
    })
  })

  describe('finding feeds', () => {
    it('looks, reads everything again and says what was found', async () => {
      const { board, discover, fetchList } = start()

      const found = await board.find()

      expect(discover).toHaveBeenCalledWith(TOKEN)
      expect(found).toEqual({ new: 2, complete: true, notes: [] })
      expect(fetchList).toHaveBeenCalledOnce()
      expect(board.busy.value).toBe(false)
    })

    it('says why it could not', async () => {
      const { board, discover } = start()
      discover.mockRejectedValue(new ApiError(500, 'It broke.', 'x'))

      expect(await board.find()).toBeNull()
      expect(board.problem.value).toBe('It broke.')
      expect(board.busy.value).toBe(false)
    })
  })
})
