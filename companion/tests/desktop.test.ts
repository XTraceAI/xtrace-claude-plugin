// The companion on the desktop, through the engine. The desktop lists a Raster
// but draws nothing for one and refuses its blits (a probe in a live 2.1.287
// session), so there the band is an SVG of the same cells, redrawn for each
// changed frame, with the ♥ and a proposal's buttons in rows of their own.
// Its session.start names no surface, so the companion starts at its first draw.

import type { On } from 'claude-code'
import { describe, type Engine, expect, mock, test } from 'claude-code/testing'

const PLUGIN = 'memhub-staging'
const RULE_ID = 'b43d6914-4cb3-4a91-84ad-cadbeb6dcfe4'
const FILED = JSON.stringify({ proposed: [{ title: 'Run only the touched test suites', rule_id: RULE_ID, env: 'staging' }] })

const BAND = {
  hasSurvey: false,
  isWorking: false,
  maxRows: 24,
  bodyColumns: 120,
  scroll: { offset: 0, bodyRows: 24 },
  view: {},
}

async function started($: Engine, on: On, listed = '{"proposed":[]}') {
  const clock = mock.clock(on)
  const store: Record<string, unknown> = { 'companion.pin': 'goose' }
  on('store.get', async (_, e) => ({ value: store[e.key] }))
  on('store.set', async (_, e) => {
    store[e.key] = JSON.parse(JSON.stringify(e.value))
    return { value: undefined }
  })
  on('store.delete', async (_, e) => {
    delete store[e.key]
    return { value: undefined }
  })
  on('store.keys', async () => ({ value: Object.keys(store) }))
  mock.env(on, { HOME: '/home/tester' })
  on('session.id', async () => ({ value: 'sess-desktop-1' }))
  on('session.start', async (_, e) => ({ cwd: e.cwd }))
  on('classic.Stop', async () => ({}))
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => $.ui.resolve(e).Box({ key: 'engine-band' }))
  on('command.register', async (_, e) => ({ value: { command: e.name } }))
  on('process.run', async (_, e) => {
    if (e.argv[2] === 'proposed') return { value: { exitCode: 0, stdout: `${listed}\n`, stderr: '' } }
    return { value: { exitCode: 0, stdout: `${JSON.stringify({ url: '' })}\n`, stderr: '' } }
  })
  let blits = 0
  on('ui.blit', async () => {
    blits += 1
    return { value: {} }
  })
  // what the desktop's session.start says: no surface, not interactive (a live 2.1.287 session)
  await $.session.start({ cwd: '/work', surface: null, isInteractive: false } as never)
  const band = await $.ui.mount({ plugin: PLUGIN, surface: 'desktop', component: 'AbovePrompt', props: BAND })
  const art = async () => (await band.find({ type: 'Svg', key: 'companion-art' }))?.props.source as string | undefined
  return { $, band, clock, art, blits: () => blits }
}

describe('the companion on the desktop', () => {
  test('draws the animal as an SVG, not a Raster, with the ♥ beside it', { timeoutMs: 60_000 }, async ($, on) => {
    const { band, clock, art } = await started($, on)
    await clock.advance(2_000)
    expect(await band.find({ type: 'Raster' }), 'no Raster: the desktop draws none').toBeUndefined()
    expect(await art(), 'the animal is one SVG').toMatch(/^<svg /)
    expect(await band.find({ type: 'Button', key: 'companion-pet' }), 'the ♥ that pets it').toBeDefined()
    await band.unmount()
  })

  test('set up from its first draw: the commands are registered though session.start named no surface', { timeoutMs: 60_000 }, async ($, on) => {
    const registered: string[] = []
    on('command.register', async (_, e) => {
      registered.push(e.name)
      return { value: { command: e.name } }
    })
    const { band, clock } = await started($, on)
    await clock.advance(500)
    expect(registered).toEqual(expect.arrayContaining(['goose', 'hippo', 'penguin', 'shiba']))
    await band.unmount()
  })

  test('the animal moves by redraws: the SVG changes and nothing is blitted', { timeoutMs: 60_000 }, async ($, on) => {
    const { band, clock, art, blits } = await started($, on)
    const seen = new Set<string>()
    for (let t = 0; t < 6_000; t += 100) {
      seen.add((await art()) ?? '')
      await clock.advance(100)
    }
    expect(seen.size, 'more than one frame was drawn').toBeGreaterThan(2)
    expect(blits(), 'no blits: the desktop refuses them').toBe(0)
    await band.unmount()
  })

  test('a proposed rule speaks in the SVG and asks on a row of its own', { timeoutMs: 60_000 }, async ($, on) => {
    const { band, clock, art } = await started($, on, FILED)
    await $.classic.Stop({ stop_hook_active: false, session_id: 'sess-desktop-1' })
    let isAsking = false
    for (let t = 0; t < 30_000 && !isAsking; t += 100) {
      await clock.advance(100)
      isAsking = (await band.find({ type: 'Button', key: 'rule-activate' })) !== undefined
    }
    expect(isAsking, 'Activate came up').toBe(true)
    expect(await band.find({ key: 'rule-waiting' }), 'on the row under the animal').toBeDefined()
    expect(await band.find({ key: 'rule-word' }), 'nothing laid over the SVG').toBeUndefined()
    expect(await art()).toMatch(/Run only the touched/)
    await band.unmount()
  })
})
