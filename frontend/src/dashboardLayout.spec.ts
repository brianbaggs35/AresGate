import {
  DEFAULT_PLACES,
  WIDGETS,
  change,
  connectWords,
  moveBy,
  moveTo,
  placesFrom,
  shownPlaces,
  widgetInfo,
  type Place,
} from '@/dashboardLayout'

const ids = (places: readonly Place[]) => places.map((place) => place.id)
const some = (...list: Place['id'][]): Place[] =>
  list.map((id) => ({ id, size: 'half', hidden: false }))

describe('the dashboard widgets', () => {
  it('names each widget once, and starts each as the API does', () => {
    expect(new Set(ids(DEFAULT_PLACES)).size).toBe(WIDGETS.length)
    expect(ids(DEFAULT_PLACES)).toEqual(WIDGETS.map((widget) => widget.id))
    expect(DEFAULT_PLACES.map((place) => place.size)).toEqual([
      'full',
      'full',
      'full',
      'half',
      'half',
      'full',
      'full',
      'half',
      'half',
    ])
    expect(DEFAULT_PLACES.some((place) => place.hidden)).toBe(false)
  })

  it('has words for each widget', () => {
    for (const widget of WIDGETS) {
      expect(widget.title).not.toBe('')
      expect(widget.description.endsWith('.')).toBe(true)
    }
    expect(widgetInfo('traffic').title).toBe('Traffic')
  })

  it('reads what the API sent, leaving out a widget it cannot draw and adding one that is missing', () => {
    const places = placesFrom([
      { id: 'latest', size: 'full', hidden: true },
      { id: 'from-the-future', size: 'half', hidden: false },
      { id: 'traffic', size: 'half', hidden: false },
    ])

    expect(ids(places).slice(0, 2)).toEqual(['latest', 'traffic'])
    expect(places).toHaveLength(WIDGETS.length)
    expect(places[0]).toEqual({ id: 'latest', size: 'full', hidden: true })
    expect(places.at(-1)).toEqual(DEFAULT_PLACES.filter((place) => place.id === 'sources')[0])
  })

  it('gives back places of its own, so a change to them is not a change to the default', () => {
    const places = placesFrom([])

    places[0]!.hidden = true

    expect(DEFAULT_PLACES[0]!.hidden).toBe(false)
  })

  it('shows the places that are not hidden, in order', () => {
    const places = [...some('traffic', 'alerts', 'latest')]
    places[1] = { ...places[1]!, hidden: true }

    expect(ids(shownPlaces(places))).toEqual(['traffic', 'latest'])
  })

  it('moves a place towards the end or the start, and stops at either', () => {
    const places = some('traffic', 'alerts', 'latest')

    expect(ids(moveBy(places, 'traffic', 1))).toEqual(['alerts', 'traffic', 'latest'])
    expect(ids(moveBy(places, 'latest', -1))).toEqual(['traffic', 'latest', 'alerts'])
    expect(ids(moveBy(places, 'traffic', -1))).toEqual(['traffic', 'alerts', 'latest'])
    expect(ids(moveBy(places, 'latest', 1))).toEqual(['traffic', 'alerts', 'latest'])
    expect(ids(places)).toEqual(['traffic', 'alerts', 'latest'])
  })

  it('puts a place where another was dropped, after it when it came from above and before it when from below', () => {
    const places = some('traffic', 'alerts', 'latest', 'sources')

    expect(ids(moveTo(places, 'traffic', 'latest'))).toEqual([
      'alerts',
      'latest',
      'traffic',
      'sources',
    ])
    expect(ids(moveTo(places, 'sources', 'alerts'))).toEqual([
      'traffic',
      'sources',
      'alerts',
      'latest',
    ])
    expect(ids(moveTo(places, 'alerts', 'alerts'))).toEqual(ids(places))
    expect(ids(moveTo(places, 'traffic', 'sources'))).toEqual([
      'alerts',
      'latest',
      'sources',
      'traffic',
    ])
  })

  it('changes one place and leaves the rest', () => {
    const places = some('traffic', 'alerts')

    const changed = change(places, 'alerts', { hidden: true, size: 'full' })

    expect(changed).toEqual([places[0], { id: 'alerts', size: 'full', hidden: true }])
    expect(places[1]).toEqual({ id: 'alerts', size: 'half', hidden: false })
  })
})

describe('what a widget needs connected', () => {
  const nothing = new Set<string>()

  it('needs nothing of a widget that reads what AresGate holds', () => {
    expect(connectWords(widgetInfo('needs_you'), nothing)).toBeNull()
    expect(connectWords(widgetInfo('filtered'), nothing)).toBeNull()
    expect(connectWords(widgetInfo('review'), nothing)).toBeNull()
  })

  it('says what to connect when none of what feeds it is', () => {
    expect(connectWords(widgetInfo('blocked'), nothing)).toBe('Connect OPNsense to see this.')
    expect(connectWords(widgetInfo('traffic'), nothing)).toBe(
      'Connect OPNsense or ntopng to see this.',
    )
    expect(connectWords(widgetInfo('latest'), nothing)).toBe(
      'Connect OPNsense, Wazuh, CrowdSec or ntopng to see this.',
    )
  })

  it('is satisfied by any one of them', () => {
    expect(connectWords(widgetInfo('traffic'), new Set(['ntopng']))).toBeNull()
    expect(connectWords(widgetInfo('latest'), new Set(['wazuh']))).toBeNull()
    expect(connectWords(widgetInfo('blocked'), new Set(['wazuh']))).not.toBeNull()
  })

  it('names an integration it has no name for as it is', () => {
    const info = { ...widgetInfo('traffic'), needs: ['pihole'] }

    expect(connectWords(info, nothing)).toBe('Connect pihole to see this.')
  })
})
