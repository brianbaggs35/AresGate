import { readChoice, saveChoice } from '@/stores/saved-choice'

const KEY = 'aresgate.test'
const COLOURS = ['red', 'blue'] as const

describe('saved choice', () => {
  it('reads what was saved', () => {
    saveChoice(KEY, 'blue')
    expect(readChoice(KEY, COLOURS)).toBe('blue')
  })

  it('has nothing when nothing was saved', () => {
    expect(readChoice(KEY, COLOURS)).toBeNull()
  })

  it('ignores a value that is not one of the choices', () => {
    saveChoice(KEY, 'green')
    expect(readChoice(KEY, COLOURS)).toBeNull()
  })

  it('has nothing when storage cannot be read', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied')
    })
    expect(readChoice(KEY, COLOURS)).toBeNull()
  })

  it('carries on when storage cannot be written', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    expect(() => {
      saveChoice(KEY, 'red')
    }).not.toThrow()
  })
})
