import { connectFirewall, expect, test } from '../support'

test.describe('data page', () => {
  test('is one of the settings pages, with a card for events and one for measurements', async ({
    page,
    settings,
    data,
  }) => {
    await settings.goto()

    await settings.dataLink.click()

    await expect(page).toHaveURL('/settings/data')
    await expect(page).toHaveTitle('Settings · AresGate')
    await expect(settings.dataLink).toHaveAttribute('aria-current', 'page')
    await expect(data.eventsCard.getByTestId('section-title')).toHaveText('Events')
    await expect(data.metricsCard.getByTestId('section-title')).toHaveText('Measurements')
  })

  test('lists each integration, with nothing stored and the default time, on a new install', async ({
    data,
  }) => {
    await data.goto()

    for (const card of [data.eventsCard, data.metricsCard]) {
      await expect(card.getByTestId('retention-name')).toHaveText([
        'OPNsense',
        'ntopng',
        'Wazuh',
        'CrowdSec',
      ])
      await expect(card.getByTestId('retention-kept')).toHaveText(
        new Array<string>(4).fill('Kept for 30 days (the default)'),
      )
    }
    await expect(data.eventsCard.getByTestId('retention-holds').first()).toHaveText(
      'No events stored',
    )
    await expect(data.metricsCard.getByTestId('retention-holds').first()).toHaveText(
      'No readings stored',
    )
  })

  test('shows what a firewall that is being read has stored', async ({
    harness,
    integration,
    data,
  }) => {
    await connectFirewall(harness, integration, [])
    await harness.setWorker('running')
    await harness.runCollectors()

    await data.goto()

    // The three lines of its firewall log, and what it measures: 28 numbers each time.
    await expect(
      data.source(data.eventsCard, 'OPNsense').getByTestId('retention-holds'),
    ).toHaveText('3 events · the oldest just now')
    await expect(
      data.source(data.metricsCard, 'OPNsense').getByTestId('retention-holds'),
    ).toHaveText('28 readings · the oldest just now')
    await expect(data.source(data.eventsCard, 'Wazuh').getByTestId('retention-holds')).toHaveText(
      'No events stored',
    )

    await harness.runCollectors()
    await data.eventsCard.getByTestId('events-refresh').click()
    await data.metricsCard.getByTestId('metrics-refresh').click()

    await expect(
      data.source(data.metricsCard, 'OPNsense').getByTestId('retention-holds'),
    ).toHaveText('56 readings · the oldest just now')
  })

  test('has no chart until something is stored', async ({ data }) => {
    await data.goto()
    await expect(data.eventsCard.getByTestId('retention-source')).toHaveCount(4)

    await expect(data.eventsChart).toBeHidden()
    await expect(data.metricsChart).toBeHidden()
  })

  test('charts what each integration has stored, and reads it with the pointer or the keys', async ({
    page,
    harness,
    integration,
    data,
  }) => {
    await connectFirewall(harness, integration, [])
    await harness.setWorker('running')
    await harness.runCollectors()

    await data.goto()

    const chart = data.eventsChart
    await expect(chart.getByTestId('chart-title')).toHaveText('Stored by integration')
    await expect(chart.getByTestId('chart-caption')).toHaveText(
      'How many events each one has stored now.',
    )
    await expect(chart.getByTestId('bar-category')).toHaveText([
      'OPNsense',
      'ntopng',
      'Wazuh',
      'CrowdSec',
    ])
    await expect(chart.getByTestId('bar-value')).toHaveText(['3'])
    await expect(chart.getByTestId('chart-tooltip')).toBeHidden()

    await chart.getByTestId('bar-slot').first().hover()
    await expect(chart.getByTestId('chart-tooltip')).toContainText('OPNsense')
    await expect(chart.getByTestId('chart-tooltip-row')).toContainText('3')
    await page.mouse.move(0, 0)
    await expect(chart.getByTestId('chart-tooltip')).toBeHidden()

    await chart.getByRole('img').focus()
    await page.keyboard.press('ArrowDown')
    await expect(chart.getByRole('status')).toHaveText('OPNsense: 3 Events')
    await expect(chart.getByTestId('chart-tooltip')).toBeVisible()
    await page.keyboard.press('End')
    await expect(chart.getByRole('status')).toHaveText('CrowdSec: 0 Events')
    await page.keyboard.press('Escape')
    await expect(chart.getByTestId('chart-tooltip')).toBeHidden()

    // The measurements have a chart of their own, with the 28 readings.
    await expect(data.metricsChart.getByTestId('bar-value')).toHaveText(['28'])
  })

  test('shows the same numbers as a table, and back as a chart', async ({
    harness,
    integration,
    data,
  }) => {
    await connectFirewall(harness, integration, [])
    await harness.setWorker('running')
    await harness.runCollectors()
    await data.goto()
    const chart = data.eventsChart

    await chart.getByTestId('chart-view').click()

    await expect(chart.getByTestId('bar-chart')).toBeHidden()
    await expect(chart.getByRole('columnheader')).toHaveText(['Integration', 'Events'])
    await expect(chart.getByTestId('chart-table-row')).toHaveCount(4)
    await expect(chart.getByTestId('chart-table-row').first()).toContainText('OPNsense')
    await expect(chart.getByTestId('chart-table-row').first()).toContainText('3')

    await chart.getByTestId('chart-view').click()

    await expect(chart.getByTestId('bar-chart')).toBeVisible()
    await expect(chart.getByTestId('chart-table')).toBeHidden()
  })

  test('keeps one integration’s events for the days chosen, and remembers it', async ({
    page,
    data,
  }) => {
    await data.goto()
    const opnsense = data.source(data.eventsCard, 'OPNsense')

    await opnsense.getByTestId('retention-change').click()
    await expect(data.dialogTitle).toHaveText("How long to keep OPNsense's events")
    await expect(data.useDefault).toBeChecked()
    await expect(data.days).toBeDisabled()
    await data.useDays.check()
    await data.days.fill('90')
    await data.save.click()

    await expect(data.eventsCard.getByTestId('retention-notice')).toHaveText(
      'OPNsense keeps its events for 90 days.',
    )
    await expect(opnsense.getByTestId('retention-kept')).toHaveText('Kept for 90 days')
    await expect(data.dialog).toBeHidden()
    // The others, and the measurements, are as they were.
    await expect(data.source(data.eventsCard, 'Wazuh').getByTestId('retention-kept')).toHaveText(
      'Kept for 30 days (the default)',
    )
    await expect(
      data.source(data.metricsCard, 'OPNsense').getByTestId('retention-kept'),
    ).toHaveText('Kept for 30 days (the default)')

    await page.reload()

    await expect(opnsense.getByTestId('retention-kept')).toHaveText('Kept for 90 days')
  })

  test('goes back to the default', async ({ data }) => {
    await data.goto()
    const opnsense = data.source(data.metricsCard, 'OPNsense')
    await opnsense.getByTestId('retention-change').click()
    await data.useDays.check()
    await data.days.fill('7')
    await data.save.click()
    await expect(opnsense.getByTestId('retention-kept')).toHaveText('Kept for 7 days')

    await opnsense.getByTestId('retention-change').click()
    await expect(data.dialogTitle).toHaveText("How long to keep OPNsense's readings")
    await expect(data.useDays).toBeChecked()
    await expect(data.days).toHaveValue('7')
    await data.useDefault.check()
    await data.save.click()

    await expect(data.metricsCard.getByTestId('retention-notice')).toHaveText(
      'OPNsense keeps its readings for 30 days (the default).',
    )
    await expect(opnsense.getByTestId('retention-kept')).toHaveText(
      'Kept for 30 days (the default)',
    )
  })

  test('refuses a number of days that is not allowed, and says what is', async ({ data }) => {
    await data.goto()
    await data.source(data.eventsCard, 'ntopng').getByTestId('retention-change').click()
    await data.useDays.check()

    for (const typed of ['0', '3651', '']) {
      await data.days.fill(typed)
      await data.save.click()

      await expect(data.dialog).toContainText('Enter a whole number of days from 1 to 3650.')
      await expect(data.days).toBeFocused()
    }
    await data.days.fill('3650')
    await data.save.click()

    await expect(data.eventsCard.getByTestId('retention-notice')).toHaveText(
      'ntopng keeps its events for 3650 days.',
    )
  })

  test('leaves things as they are when it is cancelled', async ({ data }) => {
    await data.goto()
    const wazuh = data.source(data.eventsCard, 'Wazuh')
    await wazuh.getByTestId('retention-change').click()
    await data.useDays.check()
    await data.days.fill('5')

    await data.cancel.click()

    await expect(data.dialog).toBeHidden()
    await expect(data.eventsCard.getByTestId('retention-notice')).toHaveCount(0)
    await expect(wazuh.getByTestId('retention-kept')).toHaveText('Kept for 30 days (the default)')
    // And it shows what is set now, not what was typed.
    await wazuh.getByTestId('retention-change').click()
    await expect(data.useDefault).toBeChecked()
  })

  test('puts the change in the activity log', async ({ data, activity }) => {
    await data.goto()
    await data.source(data.eventsCard, 'Wazuh').getByTestId('retention-change').click()
    await data.useDays.check()
    await data.days.fill('14')
    await data.save.click()
    await expect(data.eventsCard.getByTestId('retention-notice')).toBeVisible()

    await activity.goto()

    await expect(activity.entries.first()).toContainText('How long events are kept was changed')
  })
})
