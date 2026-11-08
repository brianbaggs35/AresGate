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
