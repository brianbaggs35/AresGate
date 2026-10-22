import QrCode from '@/components/QrCode.vue'
import { mountWithPlugins } from '@/test/mount'

async function draw(text: string) {
  const { wrapper } = await mountWithPlugins(QrCode, {
    props: { text, label: 'QR code for the test' },
  })
  const svg = wrapper.find('svg')
  const [width = 0, height = 0] = (svg.attributes('viewBox') ?? '').split(' ').slice(2).map(Number)
  return { svg, width, height, path: wrapper.find('path').attributes('d') ?? '' }
}

describe('QrCode', () => {
  it('is a picture with a name, for someone who can’t see it', async () => {
    const { svg } = await draw('otpauth://totp/AresGate:admin?secret=JBSWY3DPEHPK3PXP')
    expect(svg.attributes('role')).toBe('img')
    expect(svg.attributes('aria-label')).toBe('QR code for the test')
  })

  it('is square, with a margin of four squares around the code', async () => {
    const { width, height } = await draw('otpauth://totp/AresGate:admin?secret=JBSWY3DPEHPK3PXP')
    expect(width).toBe(height)
    // A version 1 code is 21 squares across, and each version after it adds 4.
    expect((width - 8 - 21) % 4).toBe(0)
  })

  it('starts with the finder pattern in the top left corner: seven dark squares', async () => {
    const { path } = await draw('otpauth://totp/AresGate:admin?secret=JBSWY3DPEHPK3PXP')
    expect(path.startsWith('M4 4h7v1h-7z')).toBe(true)
  })

  it('is bigger for more to say', async () => {
    const short = await draw('a')
    const long = await draw('x'.repeat(200))
    expect(long.width).toBeGreaterThan(short.width)
  })

  it('is black on white whatever the theme, which is what scanners read', async () => {
    const { svg } = await draw('a')
    expect(svg.find('rect').attributes('fill')).toBe('#fff')
    expect(svg.find('path').attributes('fill')).toBe('#000')
  })
})
