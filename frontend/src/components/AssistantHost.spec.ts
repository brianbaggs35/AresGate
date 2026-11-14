import { VBottomSheet, VNavigationDrawer } from 'vuetify/components'

import AssistantHost from '@/components/AssistantHost.vue'
import { useAssistantStore } from '@/stores/assistant'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open(width: number, route = '/') {
  const mounted = await mountWithPlugins(AssistantHost, {
    signedIn: 'admin',
    withApp: true,
    width,
    route,
  })
  await mounted.router.isReady()
  const assistant = useAssistantStore()
  assistant.open = true
  await flushPromises()
  return { ...mounted, assistant }
}

describe('AssistantHost', () => {
  it('is a drawer at the side of a wide screen', async () => {
    const { wrapper } = await open(1280)
    expect(wrapper.find('[data-test="assistant-drawer"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="assistant-panel"]').exists()).toBe(true)
    wrapper.findComponent(VNavigationDrawer).vm.$emit('update:modelValue', false)
    expect(useAssistantStore().open).toBe(false)
  })

  it('has no panel in the page until it is opened, so nothing of it is read or found', async () => {
    const { wrapper, assistant } = await open(1280)
    assistant.open = false
    await flushPromises()
    expect(wrapper.find('[data-test="assistant-panel"]').exists()).toBe(false)
  })

  it('is a drawer that covers the page on a screen with no room beside it', async () => {
    const { wrapper } = await open(900)
    expect(wrapper.find('[data-test="assistant-drawer"]').classes()).toContain(
      'v-navigation-drawer--temporary',
    )
  })

  it('is a sheet from the bottom on a phone', async () => {
    const { wrapper } = await open(400)
    expect(wrapper.find('[data-test="assistant-drawer"]').exists()).toBe(false)
    const sheet = document.body.querySelector('.host__sheet')
    expect(sheet).not.toBeNull()
    expect(sheet?.querySelector('[data-test="assistant-panel"]')).not.toBeNull()
    // Pressing outside it, or swiping it away, closes it.
    wrapper.findComponent(VBottomSheet).vm.$emit('update:modelValue', false)
    expect(useAssistantStore().open).toBe(false)
    wrapper.unmount()
  })

  it('draws nothing of the panel in a sheet that is closed, on a phone', async () => {
    const { assistant, wrapper } = await open(400)
    assistant.open = false
    await flushPromises()
    expect(document.body.querySelector('[data-test="assistant-panel"]')).toBeNull()
    wrapper.unmount()
  })

  it('goes away on the Assistant page, which is the conversation', async () => {
    const { assistant, router } = await open(1280)
    await router.push('/assistant')
    await flushPromises()
    expect(assistant.open).toBe(false)

    // Leaving it leaves the panel as it was.
    assistant.open = true
    await router.push('/')
    await flushPromises()
    expect(assistant.open).toBe(true)
  })
})
