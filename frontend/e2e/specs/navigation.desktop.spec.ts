import { expect, test } from '../support'

// The side menu is only on a computer: a phone has a bar at the bottom, with More.
test.describe('navigation on a computer', () => {
  test('divides the menu under headings, each with the places that belong to it', async ({
    page,
    shell,
  }) => {
    await page.goto('/')

    await expect(shell.menu.getByTestId('nav-heading')).toHaveText([
      'Overview',
      'Security',
      'AI',
      'Network',
      'System',
    ])
    await expect(shell.menu.getByRole('region', { name: 'AI' }).getByRole('link')).toHaveText([
      'Assistant',
      'Agents',
      'AI usage',
    ])
    await expect(
      shell.menu.getByRole('region', { name: 'Security' }).getByRole('link'),
    ).toContainText(['Threats', 'Incidents'])
  })
})
