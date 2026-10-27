import AxeBuilder from '@axe-core/playwright'
import { expect, type Page } from '@playwright/test'

/** The WCAG 2.2 A and AA rules, which axe checks automatically. */
const WCAG_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']

/**
 * Waits until what comes in, such as a page's cards rising into place or a fade, has arrived, so
 * that what is measured or checked is where it will stay. Spinners and the other animations that
 * never end don't count.
 */
export async function waitForMotion(page: Page): Promise<void> {
  await page.waitForFunction(() =>
    document
      .getAnimations()
      .every(
        (animation) =>
          animation.playState !== 'running' ||
          animation.effect?.getComputedTiming().iterations === Infinity,
      ),
  )
}

/**
 * Fails the test when axe finds WCAG 2.2 AA problems on the page, listing each one with the
 * elements it found it on. `include` narrows the check to part of the page, e.g. a dialog.
 */
export async function expectAccessible(
  page: Page,
  { include, disableRules = [] }: { include?: string; disableRules?: string[] } = {},
): Promise<void> {
  // Text caught halfway through a fade looks faint to axe, so let transitions finish first.
  await waitForMotion(page)
  let axe = new AxeBuilder({ page }).withTags(WCAG_AA).disableRules(disableRules)
  if (include) axe = axe.include(include)
  const { violations } = await axe.analyze()
  const found = violations.map((violation) => ({
    rule: violation.id,
    impact: violation.impact,
    help: violation.help,
    elements: violation.nodes.map((node) => node.target.join(' ')),
  }))
  expect(found, 'axe found accessibility problems').toEqual([])
}
