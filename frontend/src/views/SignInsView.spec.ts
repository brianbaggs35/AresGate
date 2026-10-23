import * as accountApi from '@/api/account'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import SignInsView from '@/views/SignInsView.vue'

describe('SignInsView', () => {
  it('is the list of where the account is signed in', async () => {
    vi.spyOn(accountApi, 'fetchSignIns').mockResolvedValue([])
    const { wrapper } = await mountWithPlugins(SignInsView, {
      route: '/settings/sign-ins',
      signedIn: 'admin',
    })
    await flushPromises()
    expect(wrapper.find('[data-test="sign-ins-card"]').exists()).toBe(true)
  })
})
