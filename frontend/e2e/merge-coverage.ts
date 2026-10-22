import path from 'node:path'
import process from 'node:process'

import MCR from 'monocart-coverage-reports'

import { WEB_COVERAGE_DIR, webCoverageOptions } from './support/coverage.ts'

/**
 * Merges the web app's end-to-end coverage from the raw data of one run, or of every shard and
 * test server a CI run used, and fails when too little of the source ran:
 * `npm run e2e:coverage [raw directory …]` (by default the last run's). Lines, statements and
 * functions must reach ARESGATE_E2E_COVERAGE_MIN percent (95 unless set). Branches are
 * reported but not held to it, because some defensive ones only a unit test can reach.
 */

const MINIMUM = Number(process.env.ARESGATE_E2E_COVERAGE_MIN ?? '95')
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

const below = METRICS.filter((metric) => Number(results.summary[metric].pct) < MINIMUM).map(
  (metric) => `${metric}: ${results.summary[metric].pct.toString()}%`,
)
if (below.length > 0) {
  console.error(
    `End-to-end coverage is below the ${MINIMUM.toString()}% minimum: ${below.join(', ')}`,
  )
  process.exit(1)
}
console.log(`End-to-end coverage meets the ${MINIMUM.toString()}% minimum.`)
