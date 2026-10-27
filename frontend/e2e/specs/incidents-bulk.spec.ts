import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

/** Each from a block of its own: addresses side by side are one bot. */
function many(count: number): IncidentRequest[] {
  return Array.from({ length: count }, (_, number) => ({
    address: `20.20.${(number + 1).toString()}.20`,
    minutes_ago: number + 1,
    signals: 2,
  }))
}

const title = (address: string) => `Brute force on ssh (${address})`

test.describe('incidents changed many at a time', () => {
  test('are picked with the box on each, and the box above the list picks the page', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(many(3))
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(3)
    await expect(incidents.bulk).toContainText('Select incidents to change them together')

    await incidents.picks.nth(0).click()

    await expect(incidents.picked).toHaveText('1 selected')
    await expect(incidents.pickPage).toHaveJSProperty('indeterminate', true)

    await incidents.pickPage.click()

    await expect(incidents.picked).toHaveText('3 selected')
    await expect(incidents.pickPage).toBeChecked()

    await incidents.pickPage.click()

    await expect(incidents.picked).toBeHidden()
    await expect(incidents.picks.nth(0)).not.toBeChecked()
  })

  test('are picked as a range with the shift key, and let go of with the clear button', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(many(5))
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(5)

    await incidents.picks.nth(1).click()
    await incidents.picks.nth(3).click({ modifiers: ['Shift'] })

    await expect(incidents.picked).toHaveText('3 selected')
    await expect(incidents.picks.nth(0)).not.toBeChecked()
    await expect(incidents.picks.nth(2)).toBeChecked()
    await expect(incidents.picks.nth(4)).not.toBeChecked()

    await incidents.letGo.click()

    await expect(incidents.picked).toBeHidden()
  })

  test('are let go of with the escape key', async ({ harness, incidents, page }) => {
    await harness.createIncidents(many(2))
    await incidents.goto()
    await incidents.picks.nth(0).click()
    await expect(incidents.picked).toHaveText('1 selected')

    await page.keyboard.press('Escape')

    await expect(incidents.picked).toBeHidden()
  })

  test('are marked with a status at once when they are few, and that is taken back', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(many(3))
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(3)
    await incidents.picks.nth(0).click()
    await incidents.picks.nth(1).click()

    await incidents.bulkStatus.click()
    await incidents.bulkTo('resolved').click()

    await expect(incidents.changed).toHaveText('Marked 2 incidents as resolved.')
    await expect(incidents.cards).toHaveCount(1)
    await expect(incidents.picked).toBeHidden()

    await incidents.takeBack.click()

    await expect(incidents.changed).toHaveText('Taken back.')
    await expect(incidents.cards).toHaveCount(3)
  })

  test('are looked over before a verdict is given, which can say why', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(many(3))
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(3)
    await incidents.picks.nth(0).click()
    await incidents.picks.nth(2).click()

    await incidents.bulkVerdict('not_suspicious').click()

    await expect(incidents.dialogTitle).toHaveText('Say 2 incidents are not suspicious?')
    await expect(incidents.dialogLines.first()).toHaveText('2 incidents, with 4 signals.')
    await expect(incidents.dialogLines.nth(1)).toContainText('2 verdicts will be remembered')
    await expect(incidents.dialogAccept).toBeEnabled()
    await incidents.dialogNote.fill('My own scanner')
    await incidents.dialogAccept.click()

    await expect(incidents.changed).toHaveText(
      'Remembered 2 verdicts as not suspicious, for 2 incidents.',
    )
    await expect(incidents.cards).toHaveCount(1)

    await incidents.takeBack.click()

    await expect(incidents.changed).toHaveText('Taken back.')
    await expect(incidents.cards).toHaveCount(3)
  })

  test('are not changed when the look over is cancelled', async ({ harness, incidents }) => {
    await harness.createIncidents(many(2))
    await incidents.goto()
    await incidents.picks.nth(0).click()
    await incidents.bulkVerdict('threat').click()
    await expect(incidents.dialogTitle).toHaveText('Say 1 incident is a real threat?')

    await incidents.dialogCancel.click()

    await expect(incidents.dialog).toBeHidden()
    await expect(incidents.picked).toHaveText('1 selected')
    await expect(incidents.cards).toHaveCount(2)
    await expect(incidents.changed).toBeHidden()
  })

  test('are all picked that match, more than the page shows, and looked over before a change', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(many(27))
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(25)

    await incidents.pickPage.click()

    await expect(incidents.picked).toHaveText('25 selected')
    await expect(incidents.pickEverything).toHaveText('Select all 27 incidents that match')

    await incidents.pickEverything.click()

    await expect(incidents.picked).toHaveText('27 selected')
    await expect(incidents.pickedEverything).toHaveText('All 27 incidents that match are selected.')

    await incidents.bulkStatus.click()
    await incidents.bulkTo('dismissed').click()

    await expect(incidents.dialogTitle).toHaveText('Dismiss 27 incidents?')
    await expect(incidents.dialogLines.first()).toHaveText('27 incidents, with 54 signals.')
    await expect(incidents.dialogLines.nth(1)).toHaveText('All will be marked as dismissed.')
    await incidents.dialogAccept.click()

    await expect(incidents.changed).toHaveText('Marked 27 incidents as dismissed.')
    await expect(incidents.empty).toContainText('Nothing needs you')

    await incidents.takeBack.click()

    await expect(incidents.changed).toHaveText('Taken back.')
    await expect(incidents.cards).toHaveCount(25)
  })

  test('are changed only among what a search found, when all that match are picked', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents([
      { address: '20.20.1.20', signals: 1, minutes_ago: 1 },
      { address: '30.30.1.30', signals: 1, minutes_ago: 2 },
      { address: '30.30.2.30', signals: 1, minutes_ago: 3 },
    ])
    await incidents.goto()
    await incidents.search('30.30')
    await expect(incidents.cards).toHaveCount(2)

    await incidents.pickPage.click()
    await incidents.bulkStatus.click()
    await incidents.bulkTo('resolved').click()

    await expect(incidents.changed).toHaveText('Marked 2 incidents as resolved.')
    await incidents.goto()
    await expect(incidents.titles()).toHaveText([title('20.20.1.20')])
  })

  test('say so when nothing would change, and do not offer to go ahead', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(many(2))
    await harness.createVerdicts([{ verdict: 'not_suspicious', address: '20.20.1.20' }])
    await incidents.goto('?quieted=1')
    await expect(incidents.cards).toHaveCount(2)
    await incidents.pickOf('20.20.1.20').click()

    await incidents.bulkVerdict('not_suspicious').click()

    await expect(incidents.dialogLines.nth(1)).toHaveText(
      'Nothing to change: it is already said of all of them.',
    )
    await expect(incidents.dialogAccept).toBeDisabled()
  })
})
