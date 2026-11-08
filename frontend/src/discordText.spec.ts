import { describe, expect, it } from 'vitest'

import { colorOf, lines, pieces } from '@/discordText'

describe('pieces', () => {
  it('leaves plain words as they are', () => {
    expect(pieces('Nothing special')).toEqual([{ kind: 'text', text: 'Nothing special' }])
    expect(pieces('')).toEqual([])
  })

  it('takes out bold, code and the words of a link, in order', () => {
    expect(pieces('A **bold** move, `code`, and [a link](https://x.example/y) end')).toEqual([
      { kind: 'text', text: 'A ' },
      { kind: 'bold', text: 'bold' },
      { kind: 'text', text: ' move, ' },
      { kind: 'code', text: 'code' },
      { kind: 'text', text: ', and ' },
      { kind: 'link', text: 'a link' },
      { kind: 'text', text: ' end' },
    ])
  })

  it('never keeps where a link goes', () => {
    const [piece] = pieces('[click](https://evil.example)')
    expect(piece).toEqual({ kind: 'link', text: 'click' })
  })

  it('leaves what it does not know as text', () => {
    expect(pieces('[no](javascript:alert(1)) and **open')).toEqual([
      { kind: 'text', text: '[no](javascript:alert(1)) and **open' },
    ])
  })

  it('leaves a mark that is never closed, and what is empty, as text', () => {
    expect(pieces('**open')).toEqual([{ kind: 'text', text: '**open' }])
    expect(pieces('`open')).toEqual([{ kind: 'text', text: '`open' }])
    expect(pieces('**** and ``')).toEqual([{ kind: 'text', text: '**** and ``' }])
    expect(pieces('[open')).toEqual([{ kind: 'text', text: '[open' }])
    expect(pieces('[]() [](https://x.example)')).toEqual([
      { kind: 'text', text: '[]() [](https://x.example)' },
    ])
  })

  it('leaves a link that goes nowhere on the web, or never ends, as text', () => {
    expect(pieces('[a](https://x.example/y')).toEqual([
      { kind: 'text', text: '[a](https://x.example/y' },
    ])
    expect(pieces('[a](https://) [b](http://x y)')).toEqual([
      { kind: 'text', text: '[a](https://) [b](http://x y)' },
    ])
    expect(pieces('[a](ftp://x.example/y)')).toEqual([
      { kind: 'text', text: '[a](ftp://x.example/y)' },
    ])
  })

  it('takes a link that goes to http as well as https', () => {
    expect(pieces('[a](http://x.example/y)')).toEqual([{ kind: 'link', text: 'a' }])
  })

  it('reads a line of marks that never close without taking long over it', () => {
    const line = '[a'.repeat(10_000)
    const started = performance.now()

    const read = pieces(line)

    expect(read).toEqual([{ kind: 'text', text: line }])
    expect(performance.now() - started).toBeLessThan(2000)
  })
})

describe('lines', () => {
  it('splits a message at its line breaks and keeps the gaps', () => {
    expect(lines('One\n\n**Two**')).toEqual([
      [{ kind: 'text', text: 'One' }],
      [],
      [{ kind: 'bold', text: 'Two' }],
    ])
  })
})

describe('colorOf', () => {
  it('writes a number as a colour', () => {
    expect(colorOf(0xef4444)).toBe('#ef4444')
    expect(colorOf(0x0000ff)).toBe('#0000ff')
    expect(colorOf(0x6b7280)).toBe('#6b7280')
  })
})
