import { dashClass, TEXTURES, textureClass, textureOf } from '@/charts/patterns'

describe('textures', () => {
  it('give each of the eight hues its own, in order, and nothing past them', () => {
    expect(Array.from({ length: TEXTURES }, (_, index) => textureOf(index))).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8,
    ])
    expect(textureOf(TEXTURES)).toBeNull()
    expect(textureOf(20)).toBeNull()
  })

  it('name the classes that draw them, for a bar and for a line', () => {
    expect(textureClass(3)).toBe('chart-pat-3')
    expect(dashClass(3)).toBe('chart-dash-3')
    expect(textureClass(null)).toBeUndefined()
    expect(dashClass(undefined)).toBeUndefined()
  })
})
