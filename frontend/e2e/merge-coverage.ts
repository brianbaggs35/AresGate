import path from 'node:path'
import process from 'node:process'

import MCR from 'monocart-coverage-reports'

import { WEB_COVERAGE_DIR, webCoverageOptions } from './support/coverage.ts'

/**
 * Merges the web app's end-to-end coverage from the raw data of one run, or of every shard and
 * test server a CI run used, and reports it: `npm run e2e:coverage [raw directory …]` (by
 * default the last run's). It never fails a build, because the unit tests are what hold the
 * code to 100%. Lines, statements and functions are expected to stay above 90%, and a run that
 * falls short says so as a warning. Branches are reported only, because some defensive ones can
 * only be reached by a unit test.
 */

const AIM = 90
const METRICS = ['lines', 'statements', 'functions'] as const

const given = process.argv.slice(2)
const inputDir = given.length > 0 ? given : [path.join(WEB_COVERAGE_DIR, 'raw')]

const results = await MCR({
  ...webCoverageOptions,
  name: 'AresGate web app: merged end-to-end coverage',
  outputDir: path.resolve(import.meta.dirname, '../e2e-results/coverage-merged'),
  reports: ['v8', 'lcovonly', 'console-summary'],
  inputDir,
}).generate()

if (!results) {
  console.error(`No end-to-end coverage found in ${inputDir.join(', ')}`)
  process.exit(1)
}

const below = METRICS.filter((metric) => Number(results.summary[metric].pct) < AIM).map(
  (metric) => `${metric}: ${results.summary[metric].pct.toString()}%`,
)
if (below.length > 0) {
  // GitHub shows a line like this as a warning on the run, without failing it.
  console.warn(
    `::warning::End-to-end coverage is below the ${AIM.toString()}% aim: ${below.join(', ')}`,
  )
} else {
  console.log(`End-to-end coverage is above the ${AIM.toString()}% aim.`)
}
