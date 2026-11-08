import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

const BUSY: IncidentRequest[] = [
  {
    address: '93.184.216.34',
    severity: 'critical',
    programs: ['wazuh', 'opnsense'],
    signals: 4,
    exploit: true,
    compromise: true,
    minutes_ago: 6,
    device_name: 'nas',
  },
  { address: '1.1.1.1', severity: 'high', programs: ['wazuh'], signals: 2, minutes_ago: 20 },
  {
    address: '8.8.4.10',
    severity: 'low',
    programs: ['opnsense'],
    twin: 'ntopng',
    signals: 6,
    scan: true,
    neighbours: 2,
    waves: 2,
    ports: [22, 80, 443],
    minutes_ago: 30,
  },
]

async function overflow(page: import('@playwright/test').Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
}

test.describe('threats on a phone', () => {
  test('are in the bar at the bottom, between the dashboard and the incidents', async ({
    page,
    shell,
    threats,
  }) => {
    await page.goto('/')

    await shell.threatsLink.click()

    await expect(page).toHaveURL('/threats')
    await expect(threats.heading).toHaveText('Threats')
    await expect(shell.threatsLink).toHaveAttribute('aria-current', 'page')
  })

  test('fit the screen, with the funnel, the lanes and the cards', async ({
    harness,
    threats,
    page,
  }) => {
    await harness.createIncidents(BUSY)

    await threats.goto()
    await expect(threats.cards).toHaveCount(1)
    expect(await overflow(page)).toBeLessThanOrEqual(0)

    await threats.lane('suspect').click()
    await expect(threats.cards).toHaveCount(1)
    expect(await overflow(page)).toBeLessThanOrEqual(0)

    await threats.lane('background').click()
    await expect(threats.kinds.first()).toBeVisible()
    expect(await overflow(page)).toBeLessThanOrEqual(0)
    // The funnel is still readable: each step has its name and number on screen.
    await threats.goto()
    await expect(threats.step('reports')).toBeVisible()
    await expect(threats.stepCount('reports')).toBeVisible()
  })

  test('have a list of kinds and a page for a kind that fit the screen', async ({
    harness,
    kinds,
    kind,
    page,
  }) => {
    await harness.createIncidents(BUSY)

    await kinds.goto()
    await expect(kinds.cards).toHaveCount(2)
    expect(await overflow(page)).toBeLessThanOrEqual(0)

    await kinds.cards.first().getByTestId('family').click()
    await expect(kind.judgementNone).toBeVisible()
    await expect(kind.judge).toBeVisible()
    expect(await overflow(page)).toBeLessThanOrEqual(0)
  })

  test('have settings that fit the screen, with the slider reachable by touch', async ({
    threatSettings,
    page,
  }) => {
    await threatSettings.goto()
    await expect(threatSettings.levelValue).toBeVisible()
    expect(await overflow(page)).toBeLessThanOrEqual(0)

    await threatSettings.exposure('some').check()
    await expect(threatSettings.ports).toBeVisible()
    expect(await overflow(page)).toBeLessThanOrEqual(0)
    // The track a finger can land on is taller than the thumb the keyboard works.
    const box = await page.getByTestId('threat-slider').boundingBox()
    expect(box?.height).toBeGreaterThanOrEqual(24)
  })
})
