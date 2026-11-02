import type { RulesPreview } from '@/api/alerts'
import RulesPreviewPanel from '@/components/RulesPreview.vue'
import { preview } from '@/test/alerts'
import { mountWithPlugins } from '@/test/mount'

async function show(answer: RulesPreview | null, props: Record<string, unknown> = {}) {
  const { wrapper } = await mountWithPlugins(RulesPreviewPanel, {
    props: { preview: answer, perHour: 6, ...props },
  })
  const find = (selector: string) => wrapper.find(`[data-test="${selector}"]`)
  return { wrapper, find, text: (selector: string) => find(selector).text().replace(/\s+/g, ' ') }
}

describe('RulesPreview', () => {
  it('says it is working it out before there is an answer', async () => {
    const { find } = await show(null)

    expect(find('preview-wait').text()).toContain('Working out')
    expect(find('preview-answer').exists()).toBe(false)
  })

  it('says why there is no answer', async () => {
    const { find } = await show(null, { failure: "Can't reach AresGate." })

    expect(find('preview-failure').text()).toContain("Can't reach AresGate.")
    expect(find('preview-wait').exists()).toBe(false)
  })

  it('says how many it would have sent of how many were going on', async () => {
    const { text } = await show(preview())

    expect(text('preview-summary')).toBe(
      'In the last 24 hours these rules would have sent 2 messages, out of 5 incidents going on.',
    )
  })

  it('says one message, and one incident', async () => {
    const { text } = await show(preview({ would_send: 1, considered: 1 }))

    expect(text('preview-summary')).toBe(
      'In the last 24 hours these rules would have sent 1 message, out of 1 incident going on.',
    )
  })

  it('says when they would have sent nothing', async () => {
    const { text } = await show(preview({ would_send: 0, examples: [] }))

    expect(text('preview-summary')).toBe(
      'In the last 24 hours these rules would have sent nothing. 5 incidents were going on, and none met them.',
    )
  })

  it('says it for a single incident', async () => {
    const { text } = await show(preview({ would_send: 0, considered: 1, examples: [] }))

    expect(text('preview-summary')).toContain('1 incident was going on, and none met them.')
  })

  it('says when nothing was going on', async () => {
    const { text } = await show(
      preview({ considered: 0, would_send: 0, left_out: [], examples: [] }),
    )

    expect(text('preview-summary')).toBe(
      'No incidents were going on in the last 24 hours, so there is nothing to show yet.',
    )
  })

  it('lists why the rest were left out', async () => {
    const { wrapper } = await show(preview())

    const reasons = wrapper.findAll('[data-test="preview-left-out"] li').map((li) => li.text())

    expect(reasons).toEqual([
      'AresGate is less than 65% sure: 2',
      'You called it not suspicious or low priority: 1',
    ])
  })

  it('links the newest it would have sent to their incidents', async () => {
    const { wrapper } = await show(preview())

    const links = wrapper.findAll('[data-test="preview-examples"] a')

    expect(links.map((link) => link.attributes('href'))).toEqual(['/incidents/12', '/incidents/9'])
    expect(links[0]?.text()).toBe('Port scan from 203.0.113.7')
    expect(wrapper.find('[data-test="preview-examples"]').text()).toContain('82% sure')
  })

  it('leaves out the lists when there is nothing in them', async () => {
    const { find } = await show(preview({ left_out: [], examples: [] }))

    expect(find('preview-left-out').exists()).toBe(false)
    expect(find('preview-examples').exists()).toBe(false)
  })

  it('says how many would have waited for quiet hours to end', async () => {
    const { find, text } = await show(preview({ held: 1 }))

    expect(text('preview-held')).toBe(
      '1 of them would have come in quiet hours and waited until those ended.',
    )
    expect((await show(preview())).find('preview-held').exists()).toBe(false)
    expect(find('preview-limit').exists()).toBe(false)
  })

  it('says what the limit of messages an hour would have caught', async () => {
    const { text } = await show(preview({ busiest_hour: 9, over_limit: 3 }), { perHour: 6 })

    expect(text('preview-limit')).toBe(
      '9 came in one hour. With at most 6 messages an hour, 3 would have been said in one summary instead.',
    )
  })

  it('says when it could not look at everything', async () => {
    const { text, find } = await show(preview({ truncated: true, considered: 2000 }))

    expect(text('preview-truncated')).toContain('this is the newest 2000')
    expect((await show(preview())).find('preview-truncated').exists()).toBe(false)
    expect(find('preview-answer').exists()).toBe(true)
  })

  it('dims an answer while a newer one is worked out, and says it is busy', async () => {
    const { wrapper, find } = await show(preview(), { loading: true })

    expect(find('preview-answer').classes()).toContain('preview--stale')
    expect(wrapper.find('[data-test="rules-preview"]').attributes('aria-busy')).toBe('true')
  })
})
