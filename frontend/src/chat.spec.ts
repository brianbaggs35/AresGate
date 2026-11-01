import { blocks, citeRoute, MAX_QUESTION, pieces, questionAbout, STARTERS } from '@/chat'

describe('chat', () => {
  it('has things to try that fit in a question', () => {
    expect(STARTERS.length).toBeGreaterThan(0)
    for (const starter of STARTERS) expect(starter.length).toBeLessThan(MAX_QUESTION)
  })

  describe('where a citation leads', () => {
    it('is the page of the incident or the integration', () => {
      expect(citeRoute({ kind: 'incident', key: '3', label: 'Incident 3' })).toEqual({
        name: 'incident',
        params: { id: '3' },
      })
      expect(citeRoute({ kind: 'integration', key: 'ntopng', label: 'ntopng' })).toEqual({
        name: 'integration',
        params: { key: 'ntopng' },
      })
    })

    it('is nowhere for anything else', () => {
      expect(citeRoute({ kind: 'device', key: '1', label: 'A device' })).toBeNull()
    })
  })

  describe('the question a button starts with', () => {
    it('is about the incident it names', () => {
      expect(questionAbout('incident:12')).toBe(
        'What should I know about incident 12, and what should I do about it?',
      )
    })

    it.each(['incident:', 'incident:x', 'device:1', 'incident:1 and more', '', null, undefined])(
      'is none for %s',
      (about) => {
        expect(questionAbout(about)).toBeNull()
      },
    )
  })

  describe('the pieces of an answer', () => {
    it('are words, and the incidents it names', () => {
      expect(pieces('See [incident 3] and [incident 40], then wait.')).toEqual([
        { text: 'See ' },
        { incident: 3 },
        { text: ' and ' },
        { incident: 40 },
        { text: ', then wait.' },
      ])
    })

    it('are just words when it names none', () => {
      expect(pieces('Nothing [incident x] here')).toEqual([{ text: 'Nothing [incident x] here' }])
      expect(pieces('')).toEqual([])
    })

    it('start and end with an incident without empty words', () => {
      expect(pieces('[incident 1][incident 2]')).toEqual([{ incident: 1 }, { incident: 2 }])
    })
  })

  describe('the blocks of an answer', () => {
    it('are paragraphs, split by blank lines, with lines of one joined', () => {
      expect(blocks('First line\nsecond line\n\nAnother paragraph')).toEqual([
        { paragraph: 'First line second line' },
        { paragraph: 'Another paragraph' },
      ])
    })

    it('are lists where lines begin with a dash, a star or a bullet', () => {
      expect(blocks('Check:\n- the firewall\n* the router\n• the NAS\nThen rest.')).toEqual([
        { paragraph: 'Check:' },
        { items: ['the firewall', 'the router', 'the NAS'] },
        { paragraph: 'Then rest.' },
      ])
    })

    it('keep a list that a blank line ends and one that the end of the text does', () => {
      expect(blocks('- one\n\n- two')).toEqual([{ items: ['one'] }, { items: ['two'] }])
      expect(blocks('Intro\n\n- a\n- b')).toEqual([{ paragraph: 'Intro' }, { items: ['a', 'b'] }])
    })

    it('are none for nothing', () => {
      expect(blocks('')).toEqual([])
      expect(blocks('  \n \n')).toEqual([])
    })

    it('treat a dash with nothing after it as words', () => {
      expect(blocks('-')).toEqual([{ paragraph: '-' }])
    })
  })
})
