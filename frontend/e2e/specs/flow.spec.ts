import { expect, test } from '../support'

const LAPTOP = '192.168.1.20'
const SERVER = '93.184.216.34'
const SCANNER = '8.8.8.8'

test.describe('network flow', () => {
  test('is in the menu, and has a title of its own', async ({ page, shell, flow }) => {
    await page.goto('/')

    await shell.goTo('flow')

    await expect(page).toHaveURL('/flow')
    await expect(page).toHaveTitle('Network Flow · AresGate')
    await shell.expectCurrent('flow')
    await expect(flow.heading).toHaveText('Network Flow')
  })

  test('says that nothing was written down, and still has a timeline', async ({ flow }) => {
    await flow.goto()

    await expect(flow.events).toHaveText('0')
    await expect(flow.empty.first()).toBeVisible()
  })

  test.describe('with connections written down', () => {
    test.beforeEach(async ({ harness }) => {
      await harness.createEvents([
        {
          src_address: LAPTOP,
          dst_address: SERVER,
          dst_port: 443,
          protocol: 'tcp',
          repeat: 3,
          seconds_ago: 120,
        },
        {
          src_address: SCANNER,
          dst_address: LAPTOP,
          dst_port: 22,
          protocol: 'tcp',
          severity: 'low',
          repeat: 2,
          seconds_ago: 60,
        },
      ])
    })

    test('draws the paths, with how many connections and how many were refused', async ({
      flow,
    }) => {
      await flow.goto()

      await expect(flow.events).toHaveText('5')
      await expect(flow.blocked).toHaveText('2 (40%)')
      await expect(flow.bands).toHaveCount(4)
      await expect(flow.node(`source:${LAPTOP}`)).toHaveAccessibleName(
        `From ${LAPTOP}: 3 connections`,
      )
    })

    test('says what a block is when it is picked, and leads to the logs that make it up', async ({
      page,
      flow,
    }) => {
      await flow.goto()

      await flow.node('service:tcp/22').click()

      await expect(flow.detailName).toHaveText('tcp/22 (SSH)')
      await expect(flow.detail).toContainText('2 (100%)')
      await flow.readLogs.click()
      await expect(page).toHaveURL(/\/logs\?q=.*protocol:tcp.*port:22/)
    })

    test('is picked and put down with the keyboard, and shows the same numbers as a table', async ({
      page,
      flow,
    }) => {
      await flow.goto()

      await flow.node(`source:${SCANNER}`).focus()
      await page.keyboard.press('Enter')
      await expect(flow.detail).toBeVisible()
      await page.keyboard.press('Space')
      await expect(flow.detail).toHaveCount(0)

      await page.getByTestId('chart-view').first().click()
      await expect(page.getByRole('table').first()).toContainText(`${LAPTOP}`)
    })

    test('narrows to one direction and one window, which are in the address', async ({
      page,
      flow,
    }) => {
      await flow.goto()

      await flow.direction('incoming').click()
      await expect(page).toHaveURL('/flow?direction=incoming')
      await expect(flow.events).toHaveText('2')

      await flow.window(1).click()
      await expect(page).toHaveURL('/flow?hours=1&direction=incoming')

      await flow.direction('inside').click()
      await expect(flow.events).toHaveText('0')
      await page.reload()
      await expect(flow.direction('inside')).toHaveAttribute('aria-pressed', 'true')
    })
  })
})
