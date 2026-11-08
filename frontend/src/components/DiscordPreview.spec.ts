import type { DiscordMessage } from '@/api/alerts'
import DiscordPreview from '@/components/DiscordPreview.vue'
import { sample } from '@/test/alerts'
import { mountWithPlugins } from '@/test/mount'

async function show(message: DiscordMessage = sample().payload) {
  return mountWithPlugins(DiscordPreview, { props: { message } })
}

describe('DiscordPreview', () => {
  it('shows who sent the message and its title, words and footer', async () => {
    const { wrapper } = await show()

    expect(wrapper.find('[data-test="discord-name"]').text()).toBe('AresGate')
    expect(wrapper.find('[data-test="discord-title"]').text()).toBe(
      'Attack in progress: High-severity scanning from 93.184.216.34',
    )
    expect(wrapper.find('[data-test="discord-description"]').text()).toContain(
      'AresGate is 88% sure this is a real attack',
    )
    expect(wrapper.find('[data-test="discord-footer"]').text()).toBe('AresGate · sample alert')
  })

  it('draws the colour bar from the colour of the message', async () => {
    const { wrapper } = await show()

    expect(wrapper.find('[data-test="discord-embed"]').attributes('style')).toContain(
      'border-inline-start-color: rgb(239, 68, 68)',
    )
  })

  it('draws the fields, the wide ones across the whole width', async () => {
    const { wrapper } = await show()

    const fields = wrapper.findAll('.discord__field')
    expect(fields.map((field) => field.find('dt').text())).toEqual([
      'How far it got',
      'How sure',
      'Seen from',
    ])
    expect(fields[0]!.classes()).toContain('discord__field--wide')
    expect(fields[1]!.classes()).not.toContain('discord__field--wide')
    expect(fields[2]!.find('code').text()).toBe('93.184.216.34')
  })

  it('leaves out the fields and the footer a message does not have', async () => {
    const message = sample().payload
    const [embed] = message.embeds
    delete embed!.fields
    delete embed!.footer
    const { wrapper } = await show(message)

    expect(wrapper.find('[data-test="discord-fields"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="discord-footer"]').exists()).toBe(false)
  })

  it('leaves out the fields of a message whose list of them is empty', async () => {
    const message = sample({ fields: [] }).payload
    const { wrapper } = await show(message)

    expect(wrapper.find('[data-test="discord-fields"]').exists()).toBe(false)
  })

  it('has a name for a screen reader, and takes no one anywhere', async () => {
    const { wrapper } = await show()

    expect(wrapper.find('[data-test="discord-preview"]').attributes('aria-labelledby')).toBeTruthy()
    expect(wrapper.text()).toContain('How the message looks in Discord')
    expect(wrapper.find('a').exists()).toBe(false)
  })
})
