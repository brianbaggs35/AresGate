import * as usageApi from '@/api/aiUsage'
import { ApiError } from '@/api/client'
import AiCallDialog from '@/components/AiCallDialog.vue'
import { callDetail } from '@/test/aiUsage'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { VDialog } from 'vuetify/components'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function show(callId: number | null = 7, open = true) {
  const fetchCall = vi.spyOn(usageApi, 'fetchUsageCall')
  const mounted = await mountWithPlugins(AiCallDialog, {
    signedIn: 'admin',
    props: { callId, modelValue: open, 'onUpdate:modelValue': () => {} },
  })
  return { ...mounted, fetchCall }
}

/** The dialog is teleported out of the component, so it is looked for in the document. */
function find(selector: string) {
  return document.body.querySelector(`[data-test="${selector}"]`)
}

describe('AiCallDialog', () => {
  it('shows what the provider was sent and what it said', async () => {
    const fetchCall = vi.spyOn(usageApi, 'fetchUsageCall').mockResolvedValue(callDetail())
    await mountWithPlugins(AiCallDialog, {
      signedIn: 'admin',
      props: { callId: 7, modelValue: true },
    })
    await flushPromises()

    expect(fetchCall).toHaveBeenCalledWith(7)
    expect(find('call-summary')?.textContent).toContain('Reading incidents about incident 12')
    expect(find('call-summary')?.textContent).toContain('Claude Haiku 5.5 (Anthropic)')
    expect(find('call-summary')?.textContent).toContain('$0.0015 (an estimate)')
    expect(find('call-prompt')?.textContent).toBe('HOST_1 was scanned by WAN_1 on port 22.')
    expect(find('call-answer')?.textContent).toBe('HOST_1 was probed by WAN_1; nothing got in.')
  })

  it('says why there was no answer', async () => {
    vi.spyOn(usageApi, 'fetchUsageCall').mockResolvedValue(
      callDetail({ ok: false, answer: null, error: "It didn't answer in time.", about: null }),
    )
    await mountWithPlugins(AiCallDialog, {
      signedIn: 'admin',
      props: { callId: 7, modelValue: true },
    })
    await flushPromises()

    expect(find('call-answer')).toBeNull()
    expect(find('call-error')?.textContent.trim()).toBe("It didn't answer in time.")
    expect(find('call-summary')?.textContent).not.toContain(' about ')
  })

  it('says so when there is neither an answer nor a reason', async () => {
    vi.spyOn(usageApi, 'fetchUsageCall').mockResolvedValue(
      callDetail({ answer: null, error: null }),
    )
    await mountWithPlugins(AiCallDialog, {
      signedIn: 'admin',
      props: { callId: 7, modelValue: true },
    })
    await flushPromises()

    expect(find('call-error')?.textContent.trim()).toBe('There was no answer.')
  })

  it('shows a placeholder while it asks', async () => {
    vi.spyOn(usageApi, 'fetchUsageCall').mockReturnValue(new Promise(() => {}))
    await mountWithPlugins(AiCallDialog, {
      signedIn: 'admin',
      props: { callId: 7, modelValue: true },
    })
    await flushPromises()

    expect(find('call-loading')).not.toBeNull()
  })

  it('says when the call could not be read, and asks again', async () => {
    const fetchCall = vi
      .spyOn(usageApi, 'fetchUsageCall')
      .mockRejectedValueOnce(offline())
      .mockResolvedValueOnce(callDetail())
    await mountWithPlugins(AiCallDialog, {
      signedIn: 'admin',
      props: { callId: 7, modelValue: true },
    })
    await flushPromises()

    expect(find('load-error-message')?.textContent).toBe("Can't reach AresGate.")
    ;(find('call-retry') as HTMLElement).click()
    await flushPromises()

    expect(fetchCall).toHaveBeenCalledTimes(2)
    expect(find('call-prompt')).not.toBeNull()
  })

  it('asks for nothing while it is closed or has no call', async () => {
    const closed = vi.spyOn(usageApi, 'fetchUsageCall')
    await show(7, false)
    await show(null, true)

    expect(closed).not.toHaveBeenCalled()
  })

  it('keeps the answer for the call it was asked about', async () => {
    let answerFirst: (value: usageApi.UsageCallDetail) => void = () => {}
    const fetchCall = vi
      .spyOn(usageApi, 'fetchUsageCall')
      .mockReturnValueOnce(new Promise((resolve) => (answerFirst = resolve)))
      .mockResolvedValueOnce(callDetail({ id: 8, prompt: 'the second' }))
    const { wrapper } = await mountWithPlugins(AiCallDialog, {
      signedIn: 'admin',
      props: { callId: 7, modelValue: true },
    })
    await wrapper.setProps({ callId: 8 })
    await flushPromises()
    answerFirst(callDetail({ id: 7, prompt: 'the first' }))
    await flushPromises()

    expect(fetchCall).toHaveBeenCalledTimes(2)
    expect(find('call-prompt')?.textContent).toBe('the second')
  })

  it('drops the failure of a call it is no longer showing', async () => {
    let failFirst: (error: Error) => void = () => {}
    vi.spyOn(usageApi, 'fetchUsageCall')
      .mockReturnValueOnce(new Promise((_, reject) => (failFirst = reject)))
      .mockResolvedValueOnce(callDetail({ id: 8, prompt: 'the second' }))
    const { wrapper } = await mountWithPlugins(AiCallDialog, {
      signedIn: 'admin',
      props: { callId: 7, modelValue: true },
    })
    await wrapper.setProps({ callId: 8 })
    await flushPromises()
    failFirst(offline())
    await flushPromises()

    expect(find('load-error-message')).toBeNull()
    expect(find('call-prompt')?.textContent).toBe('the second')
  })

  it('closes', async () => {
    vi.spyOn(usageApi, 'fetchUsageCall').mockResolvedValue(callDetail())
    const { wrapper } = await mountWithPlugins(AiCallDialog, {
      signedIn: 'admin',
      props: { callId: 7, modelValue: true },
    })
    await flushPromises()

    ;(find('call-close') as HTMLElement).click()
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })

  it('closes when the dialog is dismissed', async () => {
    vi.spyOn(usageApi, 'fetchUsageCall').mockResolvedValue(callDetail())
    const { wrapper } = await mountWithPlugins(AiCallDialog, {
      signedIn: 'admin',
      props: { callId: 7, modelValue: true },
    })
    await flushPromises()

    wrapper.findComponent(VDialog).vm.$emit('update:modelValue', false)
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })
})
