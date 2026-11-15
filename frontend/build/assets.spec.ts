import { randomBytes } from 'node:crypto'
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { gunzipSync } from 'node:zlib'

import type { IndexHtmlTransformContext, Plugin, ResolvedConfig } from 'vite'

import { MIN_BYTES, precompress, preloadFont } from './assets'

type Hook<T> = (this: unknown, ...args: never[]) => T

/** Runs a plugin's `configResolved`, which Vite does once the configuration is known. */
function resolved(plugin: Plugin, config: Partial<ResolvedConfig['build']> & { base?: string }) {
  const hook = plugin.configResolved as Hook<void>
  const { base, ...build } = config
  hook.call({}, {
    root: '/project',
    base: base ?? '/',
    build: { outDir: 'dist', write: true, ...build },
  } as never)
}

const text = (length: number) => 'export const a = 1\n'.repeat(Math.ceil(length / 19))

describe('precompress', () => {
  let out = ''
  const run = async (plugin = precompress()) => {
    const hook = plugin.configResolved as Hook<void>
    hook.call({}, { root: out, base: '/', build: { outDir: '.', write: true } } as never)
    await (plugin.closeBundle as Hook<Promise<void>>).call({})
  }

  beforeEach(async () => {
    out = await mkdtemp(join(tmpdir(), 'aresgate-build-'))
    await mkdir(join(out, 'static'))
  })
  afterEach(() => rm(out, { recursive: true, force: true }))

  it('keeps a gzip copy of each text file that is worth it, which reads back as the file', async () => {
    const script = text(5000)
    await writeFile(join(out, 'static', 'app.js'), script)
    await writeFile(join(out, 'index.html'), `<html>${'<p>hi</p>'.repeat(300)}</html>`)

    await run()

    expect(gunzipSync(await readFile(join(out, 'static', 'app.js.gz'))).toString()).toBe(script)
    expect((await readdir(out)).sort()).toEqual(['index.html', 'index.html.gz', 'static'])
  })

  it('leaves small files, fonts and images alone', async () => {
    await writeFile(join(out, 'static', 'tiny.css'), 'a{color:red}'.repeat(10))
    await writeFile(join(out, 'static', 'font.woff2'), text(5000))
    await writeFile(join(out, 'favicon.ico'), text(5000))

    await run()

    expect(await readdir(join(out, 'static'))).toEqual(['font.woff2', 'tiny.css'])
    expect(await readdir(out)).not.toContain('favicon.ico.gz')
  })

  it('keeps no copy that is not smaller than the file', async () => {
    await writeFile(join(out, 'noise.js'), randomBytes(MIN_BYTES * 3))

    await run()

    expect(await readdir(out)).not.toContain('noise.js.gz')
  })

  it('does not compress a copy again when it runs twice', async () => {
    await writeFile(join(out, 'app.js'), text(5000))

    await run()
    await run()

    expect((await readdir(out)).sort()).toEqual(['app.js', 'app.js.gz', 'static'])
  })

  it('writes nothing when the build writes nothing', async () => {
    await writeFile(join(out, 'app.js'), text(5000))
    const plugin = precompress()
    const hook = plugin.configResolved as Hook<void>
    hook.call({}, { root: out, base: '/', build: { outDir: '.', write: false } } as never)

    await (plugin.closeBundle as Hook<Promise<void>>).call({})

    expect(await readdir(out)).not.toContain('app.js.gz')
  })

  it('only takes part in a build', () => {
    expect(precompress().apply).toBe('build')
  })
})

describe('preloadFont', () => {
  const handler = (plugin: Plugin) => {
    const hook = plugin.transformIndexHtml as {
      order: string
      handler: (html: string, context: IndexHtmlTransformContext) => unknown
    }
    expect(hook.order).toBe('post')
    return hook.handler
  }
  const context = (...names: string[]) =>
    ({ bundle: Object.fromEntries(names.map((name) => [name, {}])) }) as never

  it('preloads the Latin font under the address the build gave it', () => {
    const plugin = preloadFont()
    resolved(plugin, {})

    const tags = handler(plugin)(
      '',
      context(
        'static/inter-latin-ext-wght-normal-AAA.woff2',
        'static/inter-latin-wght-normal-Bx9_k.woff2',
        'static/index-Cq.js',
      ),
    )

    expect(tags).toEqual([
      {
        tag: 'link',
        attrs: {
          rel: 'preload',
          as: 'font',
          type: 'font/woff2',
          crossorigin: '',
          href: '/static/inter-latin-wght-normal-Bx9_k.woff2',
        },
        injectTo: 'head-prepend',
      },
    ])
  })

  it('follows the base the app is served from', () => {
    const plugin = preloadFont()
    resolved(plugin, { base: '/aresgate/' })

    const [tag] = handler(plugin)('', context('static/inter-latin-wght-normal-Bx.woff2')) as {
      attrs: { href: string }
    }[]

    expect(tag?.attrs.href).toBe('/aresgate/static/inter-latin-wght-normal-Bx.woff2')
  })

  it.each([
    ['the build has no Latin font', context('static/inter-greek-wght-normal-A.woff2')],
    ['the page is not built', {} as never],
  ])('adds nothing when %s', (_name, given) => {
    const plugin = preloadFont()
    resolved(plugin, {})

    expect(handler(plugin)('', given)).toBeUndefined()
  })

  it('only takes part in a build', () => {
    expect(preloadFont().apply).toBe('build')
  })
})
