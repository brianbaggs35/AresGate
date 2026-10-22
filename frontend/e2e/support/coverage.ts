import { mkdir, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'

import MCR, { type CoverageReportOptions, type V8CoverageEntry } from 'monocart-coverage-reports'

import type { ApiCoverage } from './harness'

/**
 * End-to-end coverage: which of the web app's source the tests ran (from Chromium's own
 * coverage, mapped back to src/ through the test build's source maps) and which of the API's
 * code (measured by coverage.py inside the test server). Reports land in e2e-results/coverage;
 * there's no minimum, since the unit tests hold the thresholds. Set ARESGATE_E2E_COVERAGE=off
 * to skip collecting it.
 */

const RESULTS = path.resolve(import.meta.dirname, '../../e2e-results/coverage')
export const WEB_COVERAGE_DIR = path.join(RESULTS, 'web')
export const API_COVERAGE_DIR = path.join(RESULTS, 'api')

export function coverageEnabled(): boolean {
  return process.env.ARESGATE_E2E_COVERAGE !== 'off'
}

export const webCoverageOptions: CoverageReportOptions = {
  name: 'AresGate web app: end-to-end coverage',
  outputDir: WEB_COVERAGE_DIR,
  reports: ['v8', 'lcovonly', 'console-summary'],
  // Only AresGate's own scripts, not the browser's.
  entryFilter: (entry) => new URL(entry.url).pathname.startsWith('/assets/'),
  // Only the web app's source, not the libraries bundled with it.
  sourceFilter: (sourcePath) => sourcePath.startsWith('src/'),
}

/** Adds one test's coverage; the global teardown turns it all into the report. */
export async function addWebCoverage(entries: V8CoverageEntry[]): Promise<void> {
  // A test that only calls the API never loads the app, so it has nothing to add.
  if (entries.length) await MCR(webCoverageOptions).add(entries)
}

/** Forgets coverage from earlier runs. */
export async function clearCoverage(): Promise<void> {
  MCR(webCoverageOptions).cleanCache()
  await rm(API_COVERAGE_DIR, { recursive: true, force: true })
}

export async function writeWebReport(): Promise<void> {
  await MCR(webCoverageOptions).generate()
}

/** Saves the API's report: an HTML report in html/ and lcov.info, both relative to backend/. */
export async function writeApiReport(report: ApiCoverage): Promise<void> {
  for (const file of report.files) {
    const destination = path.join(API_COVERAGE_DIR, file.path)
    await mkdir(path.dirname(destination), { recursive: true })
    await writeFile(destination, Buffer.from(file.content, 'base64'))
  }
  console.log(
    `API coverage from the end-to-end tests: ${report.percent_covered.toString()}% ` +
      `(${path.relative(process.cwd(), path.join(API_COVERAGE_DIR, 'html', 'index.html'))})`,
  )
}
