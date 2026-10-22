import type { FullConfig } from '@playwright/test'

import { coverageEnabled, writeApiReport, writeWebReport } from './coverage'
import { Harness } from './harness'

/** Writes the web app's and the API's end-to-end coverage reports. */
export default async function globalTeardown(config: FullConfig): Promise<void> {
  if (!coverageEnabled()) return
  await writeWebReport()
  const baseURL = config.projects[0]?.use.baseURL
  if (!baseURL) return
  const harness = await Harness.connect(baseURL)
  try {
    const report = await harness.coverage()
    if (report) await writeApiReport(report)
  } finally {
    await harness.dispose()
  }
}
