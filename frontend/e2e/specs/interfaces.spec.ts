import { expect, test } from '../support'

test.describe('interfaces', () => {
  test('says there is nothing to place on a new install', async ({ page, interfaces }) => {
    await interfaces.goto()

    await expect(page).toHaveTitle('Interfaces · AresGate')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Interfaces')
    await expect(interfaces.heroTitle).toHaveText('No interfaces yet')
    await expect(interfaces.cards).toHaveCount(0)
  })

  test('makes an interface from a sheet, with a role chosen from cards', async ({
    page,
    interfaces,
  }) => {
    await interfaces.goto()

    await interfaces.add.click()
    await expect(interfaces.editorTitle).toHaveText('Add an interface')
    await expect(interfaces.save).toBeDisabled()
    await interfaces.editorName.fill('Cameras')
    await interfaces.chooseRole('Smart devices')
    await interfaces.editorNetworks.fill('192.168.40.0/24')
    await interfaces.save.click()

    await expect(interfaces.editor).toHaveCount(0)
    await expect(interfaces.notice).toHaveText('Cameras added.')
    await expect(interfaces.card('Cameras')).toContainText('Smart devices')
    await expect(interfaces.heroTitle).toHaveText('1 interface, every feed placed')
    // It was saved, not only shown.
    await page.reload()
    await expect(interfaces.card('Cameras')).toBeVisible()
  })

  test('says why a name was refused, in the sheet, and keeps what was typed', async ({
    harness,
    interfaces,
  }) => {
    await harness.createFeeds([{ native_name: 'igc0', interface: 'Internet', role: 'internet' }])
    await interfaces.goto()

    await interfaces.add.click()
    await interfaces.editorName.fill('internet')
    await interfaces.save.click()

    await expect(interfaces.editorProblem).toHaveText(
      'There is already an interface called internet.',
    )
    await expect(interfaces.editor).toBeVisible()
    await expect(interfaces.editorName).toHaveValue('internet')
  })

  test.describe('guesses at where feeds belong', () => {
    test('are confirmed one at a time, and taken back', async ({ harness, interfaces }) => {
      await harness.createFeeds([
        { native_name: 'wan' },
        { native_name: 'lan' },
        { native_name: 'guest' },
      ])
      await interfaces.goto()

      await expect(interfaces.heroTitle).toHaveText('3 feeds need a decision')
      await expect(interfaces.suggestions).toHaveCount(3)
      await interfaces.suggestions
        .filter({ hasText: 'Internet' })
        .getByTestId('suggestion-confirm')
        .click()

      await expect(interfaces.card('Internet')).toBeVisible()
      await expect(interfaces.notice).toHaveText('1 feed placed on Internet.')
      await expect(interfaces.heroTitle).toHaveText('2 feeds need a decision')
      await expect(interfaces.suggestions).toHaveCount(2)

      await interfaces.undo.click()

      await expect(interfaces.cards).toHaveCount(0)
      await expect(interfaces.heroTitle).toHaveText('3 feeds need a decision')
      await expect(interfaces.suggestions).toHaveCount(3)
    })

    test('are confirmed all at once', async ({ harness, interfaces }) => {
      await harness.createFeeds([
        { native_name: 'wan' },
        { native_name: 'lan' },
        { native_name: 'guest' },
      ])
      await interfaces.goto()

      await interfaces.confirmAll.click()

      await expect(interfaces.cards).toHaveCount(3)
      await expect(interfaces.notice).toHaveText('3 feeds placed on 3 interfaces.')
      await expect(interfaces.heroTitle).toHaveText('3 interfaces, every feed placed')
      await expect(interfaces.unplaced).toHaveCount(0)
    })

    test('are changed first, in the sheet', async ({ harness, interfaces }) => {
      await harness.createFeeds([{ native_name: 'guest' }])
      await interfaces.goto()

      await interfaces.suggestions.getByTestId('suggestion-change').click()
      await expect(interfaces.editorTitle).toHaveText('Add an interface')
      await expect(interfaces.editorName).toHaveValue('Guests')
      await interfaces.editorName.fill('Visitors')
      await interfaces.save.click()

      await expect(interfaces.card('Visitors')).toContainText('Guests')
      await expect(interfaces.heroTitle).toHaveText('1 interface, every feed placed')
    })

    test('are ignored, which sets the feed aside', async ({ harness, interfaces }) => {
      await harness.createFeeds([{ native_name: 'guest' }])
      await interfaces.goto()

      await interfaces.suggestions.getByTestId('suggestion-ignore').click()

      await expect(interfaces.notice).toHaveText('1 feed set aside.')
      await expect(interfaces.suggestions).toHaveCount(0)
      await expect(interfaces.ignored).toContainText('Set aside (1)')
    })
  })

  test('moves a feed to an interface, sets it aside, and takes each back', async ({
    harness,
    interfaces,
  }) => {
    await harness.createFeeds([
      { native_name: 'igc0', interface: 'Internet', role: 'internet' },
      { native_name: 'igc7' },
    ])
    await interfaces.goto()
    await expect(interfaces.unplaced).toContainText('OPNsense igc7')

    await interfaces.place('igc7', 'Internet')

    await expect(interfaces.notice).toHaveText('OPNsense igc7 is now on Internet.')
    await expect(interfaces.unplaced).toHaveCount(0)
    await expect(interfaces.card('Internet')).toContainText('OPNsense')
    await interfaces.undo.click()
    await expect(interfaces.unplaced).toContainText('OPNsense igc7')

    await interfaces.place('igc7', 'Set aside')

    await expect(interfaces.notice).toHaveText('OPNsense igc7 is now set aside.')
    await expect(interfaces.ignored).toContainText('Set aside (1)')
  })

  test('starts a new interface from a feed that belongs to none', async ({
    harness,
    interfaces,
  }) => {
    await harness.createFeeds([{ native_name: 'igc9' }])
    await interfaces.goto()

    await interfaces.place('igc9', 'A new interface…')
    await expect(interfaces.editorName).toHaveValue('igc9')
    await interfaces.editorName.fill('Lab')
    await interfaces.chooseRole('Management')
    await interfaces.save.click()

    await expect(interfaces.card('Lab')).toContainText('Management')
    await expect(interfaces.heroTitle).toHaveText('1 interface, every feed placed')
  })

  test('finds the feeds that programs have reported under', async ({ harness, interfaces }) => {
    await harness.createActivity({ traffic: { igc0: 8 } })
    await interfaces.goto()
    await expect(interfaces.heroTitle).toHaveText('No interfaces yet')
    await expect(interfaces.find).toHaveText('Find interfaces')

    await interfaces.find.click()

    await expect(interfaces.found).toContainText('Found 1 new feed.')
    await expect(interfaces.heroTitle).toHaveText('1 feed needs a decision')
    await interfaces.find.click()
    await expect(interfaces.found).toContainText('Nothing new was found.')
  })

  test('has a page for each interface, with its traffic and its data sources', async ({
    page,
    harness,
    interfaces,
  }) => {
    await harness.createFeeds([{ native_name: 'igc0', interface: 'Internet', role: 'internet' }])
    await harness.createActivity({ traffic: { igc0: 8 } })
    await interfaces.goto()
    await expect(interfaces.card('Internet').getByTestId('interface-traffic')).toBeVisible()

    await interfaces.card('Internet').click()

    await expect(page).toHaveURL(/\/interfaces\/\d+$/)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Internet')
    await expect(interfaces.role).toHaveText('Internet')
    await expect(page.getByTestId('interface-chart')).toContainText('Speed through Internet')
    await expect(page.getByTestId('interface-tile-received')).toContainText('From OPNsense')
    await expect(interfaces.sources).toContainText('OPNsense igc0')
    await page.getByTestId('interface-window').getByRole('button', { name: '7 days' }).click()
    await expect(page.getByTestId('interface-tile-alerts')).toContainText('In the last 7 days')
  })

  test('is edited from its page, and removed, which leaves its feeds not placed', async ({
    page,
    harness,
    interfaces,
  }) => {
    await harness.createFeeds([{ native_name: 'igc0', interface: 'Internet', role: 'internet' }])
    await interfaces.goto()
    await interfaces.card('Internet').click()

    await interfaces.edit.click()
    await expect(interfaces.editorName).toHaveValue('Internet')
    await interfaces.editorName.fill('Fibre')
    await interfaces.save.click()

    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Fibre')
    await expect(interfaces.notice).toHaveText('Fibre saved.')

    await interfaces.edit.click()
    await interfaces.remove.click()
    await page.getByTestId('confirm-accept').click()

    await expect(page).toHaveURL('/interfaces')
    await expect(interfaces.cards).toHaveCount(0)
    await expect(interfaces.unplaced).toContainText('OPNsense igc0')
  })

  test('says so when the page of an interface that is not there is opened', async ({ page }) => {
    await page.goto('/interfaces/999999')
    await expect(page.getByTestId('interface-missing')).toContainText("That interface isn't there")
  })
})
