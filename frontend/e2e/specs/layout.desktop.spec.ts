import { expect, test } from '../support'

test.describe('layout on a computer', () => {
  test('the overview stays a readable column on a wide screen', async ({ overview }) => {
    await overview.goto()

    const box = await overview.card.boundingBox()

    expect(box?.width).toBeLessThanOrEqual(720)
  })
})
