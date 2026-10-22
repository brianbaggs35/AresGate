import { expect, test } from '../support'

// The harness is what every other spec builds on, so these check what it promises: a known
// starting point, named states and records made on demand.
test.describe('test harness', () => {
  test('every test starts from the baseline', async ({ harness, baseline }) => {
    const counts = await harness.rowCounts()

    expect(counts.system_info).toBe(Object.keys(baseline.system_info).length)
  })

  test('makes a record from what it is given, and makes up the rest', async ({ harness }) => {
    const before = await harness.rowCounts()

    const chosen = await harness.createSystemInfo({ key: 'chosen', value: 'kept' })
    const invented = await harness.createSystemInfo()

    expect(chosen).toMatchObject({ key: 'chosen', value: 'kept' })
    expect(invented.key).not.toBe(chosen.key)
    expect(invented.value).not.toBe('')
    expect(await harness.rowCounts()).toEqual({
      ...before,
      system_info: (before.system_info ?? 0) + 2,
    })
  })

  test('loads the fresh-install state, which has no rows at all', async ({ harness }) => {
    const loaded = await harness.loadFixture('fresh-install')

    expect(loaded.fixture).toBe('fresh-install')
    expect(loaded.tables_emptied).toContain('system_info')
    expect(Object.values(await harness.rowCounts()).every((rows) => rows === 0)).toBe(true)
  })

  test('puts the baseline back after anything else', async ({ harness, baseline }) => {
    await harness.loadFixture('fresh-install')
    await harness.createSystemInfo()

    await harness.clean()

    expect((await harness.rowCounts()).system_info).toBe(Object.keys(baseline.system_info).length)
  })

  test('never touches the migration history', async ({ harness }) => {
    const { tables_emptied: emptied } = await harness.clean()

    expect(emptied).not.toContain('alembic_version')
  })
})
