import { readdir, readFile, writeFile } from 'node:fs/promises'
import { extname, join, resolve } from 'node:path'
import { constants, gzip } from 'node:zlib'
import { promisify } from 'node:util'

import type { Plugin } from 'vite'

const gzipped = promisify(gzip)

/** The files that shrink: text. Fonts, images and icons are compressed already or hardly shrink. */
export const COMPRESSIBLE = new Set(['.js', '.css', '.html', '.svg', '.json', '.webmanifest'])
/** Below this a file isn't worth a second copy; it is the size nginx's own gzip starts at too. */
export const MIN_BYTES = 1024

async function* filesIn(folder: string): AsyncGenerator<string> {
  for (const entry of await readdir(folder, { withFileTypes: true })) {
    const path = join(folder, entry.name)
    if (entry.isDirectory()) yield* filesIn(path)
    else yield path
  }
}

/**
 * Writes each text file of the build beside a gzip copy at the best level (`app.js.gz`), once, so
 * that nginx (`gzip_static on`) sends it as it is and compresses nothing at request time. It runs
 * in the build stage: the runtime image has no build tool. A copy is kept only if it is smaller.
 */
export function precompress(): Plugin {
  let folder = ''
  let writes = true
  return {
    name: 'aresgate:precompress',
    apply: 'build',
    configResolved(config) {
      folder = resolve(config.root, config.build.outDir)
      writes = config.build.write
    },
    async closeBundle() {
      if (!writes) return
      for await (const path of filesIn(folder)) {
        if (!COMPRESSIBLE.has(extname(path))) continue
        const body = await readFile(path)
        if (body.length < MIN_BYTES) continue
        const copy = await gzipped(body, { level: constants.Z_BEST_COMPRESSION })
        if (copy.length < body.length) await writeFile(`${path}.gz`, copy)
      }
    },
  }
}

/** The font file of the Latin letters, which every page's text is set in. */
const FONT = /(^|\/)inter-latin-wght-normal-[^/]+\.woff2$/

/**
 * Tells the browser to fetch the Latin font as soon as it has the page, instead of when the
 * stylesheet that names it has arrived and been read. The address is the one the build gave the
 * file, so it is never written out by hand and changes with the file.
 */
export function preloadFont(): Plugin {
  let base = '/'
  return {
    name: 'aresgate:preload-font',
    apply: 'build',
    configResolved(config) {
      base = config.base
    },
    transformIndexHtml: {
      order: 'post',
      handler(_html, context) {
        const font = Object.keys(context.bundle ?? {}).find((name) => FONT.test(name))
        if (!font) return undefined
        return [
          {
            tag: 'link',
            // A font is fetched with CORS even from the same address, and a preload that doesn't
            // say so is fetched twice.
            attrs: {
              rel: 'preload',
              as: 'font',
              type: 'font/woff2',
              crossorigin: '',
              href: base + font,
            },
            injectTo: 'head-prepend',
          },
        ]
      },
    },
  }
}
