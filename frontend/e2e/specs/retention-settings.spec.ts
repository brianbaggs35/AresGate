import { expect, test } from '../support'

test.describe('retention settings', () => {
  test('is one of the settings pages, switched off on a new install', async ({
    page,
    settings,
    retentionSettings,
  }) => {
    await settings.goto()

    await settings.retentionLink.click()

    await expect(page).toHaveURL('/settings/retention')
    await expect(page).toHaveTitle('Settings · AresGate')
    await expect(settings.retentionLink).toHaveAttribute('aria-current', 'page')
    await expect(retentionSettings.managed).not.toBeChecked()
    await expect(retentionSettings.builtIn).toContainText('Events 30 days')
    await expect(retentionSettings.timeCard).toBeHidden()
    await expect(retentionSettings.save).toBeDisabled()
    await expect(retentionSettings.usageTotal).toContainText(/B$/)
  })

  test('keeps a number of days and a size limit, and they are there after a reload', async ({
    page,
    retentionSettings,
  }) => {
    await retentionSettings.goto()

    await retentionSettings.managed.check()
    await retentionSettings.days.fill('14')
    await retentionSettings.limited.check()
    await retentionSettings.quota.fill('40')
    await retentionSettings.save.click()

    await expect(retentionSettings.saved).toHaveText('Saved.')
    await page.reload()
    await expect(retentionSettings.managed).toBeChecked()
    await expect(retentionSettings.days).toHaveValue('14')
    await expect(retentionSettings.quota).toHaveValue('40')
    await expect(page.getByTestId('retention-limit')).toContainText('limit')
  })

  test('will not save days that are not a whole number in range', async ({ retentionSettings }) => {
    await retentionSettings.goto()
    await retentionSettings.managed.check()

    await retentionSettings.days.fill('0')

    await expect(retentionSettings.timeCard).toContainText('from 1 to 3650')
    await expect(retentionSettings.save).toBeDisabled()
  })

  test('keeps everything forever, which leaves no days or limit to give', async ({
    page,
    retentionSettings,
  }) => {
    await retentionSettings.goto()

    await retentionSettings.managed.check()
    await retentionSettings.keepForever.check()
    await retentionSettings.save.click()

    await expect(retentionSettings.saved).toHaveText('Saved.')
    await page.reload()
    await expect(retentionSettings.keepForever).toBeChecked()
    await expect(retentionSettings.days).toBeHidden()
  })

  test('goes back to what is kept when changes are discarded', async ({ retentionSettings }) => {
    await retentionSettings.goto()

    await retentionSettings.managed.check()
    await retentionSettings.discard.click()

    await expect(retentionSettings.managed).not.toBeChecked()
  })
})
