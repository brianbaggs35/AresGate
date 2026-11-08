import ModeCards, { type Purpose } from '@/components/ModeCards.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(modelValue: Purpose = 'threats') {
  return mountWithPlugins(ModeCards, { props: { modelValue } })
}

describe('ModeCards', () => {
  it('asks what the channel is for, with a card for each answer', async () => {
    const { wrapper } = await show()

    expect(wrapper.find('legend').text()).toBe('What is this channel for?')
    expect(wrapper.findAll('label').map((card) => card.find('.purpose__title').text())).toEqual([
      'Real attacks only Recommended',
      'Everything serious',
      'Custom',
    ])
  })

  it('recommends real attacks only, and nothing else', async () => {
    const { wrapper } = await show()

    expect(wrapper.findAll('.v-chip')).toHaveLength(1)
    expect(wrapper.find('[data-test="purpose-threats"] .v-chip').text()).toBe('Recommended')
  })

  it('marks the chosen card, and checks its radio button', async () => {
    const { wrapper } = await show('serious')

    expect(wrapper.find('[data-test="purpose-serious"]').classes()).toContain('purpose--chosen')
    expect(wrapper.find('[data-test="purpose-threats"]').classes()).not.toContain('purpose--chosen')
    const radios = wrapper.findAll<HTMLInputElement>('input[type="radio"]')
    expect(radios.map((radio) => radio.element.checked)).toEqual([false, true, false])
  })

  it('shares one name between the radio buttons, so that the arrow keys move between them', async () => {
    const { wrapper } = await show()

    const names = new Set(wrapper.findAll('input').map((radio) => radio.attributes('name')))
    expect(names.size).toBe(1)
  })

  it('says which card was chosen', async () => {
    const { wrapper } = await show('threats')

    await wrapper.find('[data-test="purpose-custom"] input').setValue(true)

    expect(wrapper.emitted('update:modelValue')).toEqual([['custom']])
  })
})
