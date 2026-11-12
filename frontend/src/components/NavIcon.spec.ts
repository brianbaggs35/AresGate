import NavIcon from '@/components/NavIcon.vue'
import { navItems } from '@/navigation'
import { useReviewStore } from '@/stores/review'
import { mountWithPlugins } from '@/test/mount'

const item = (route: string) =>
  navItems.find((each) => each.route === route) as (typeof navItems)[number]

async function open(route: string, waiting: number) {
  return mountWithPlugins(NavIcon, {
    props: { item: item(route) },
    withApp: true,
    beforeMount: () => {
      useReviewStore().set(waiting)
    },
  })
}

describe('NavIcon', () => {
  it('carries the number that wait on the review place, in words as well', async () => {
    const { wrapper } = await open('review', 3)

    expect(wrapper.find('[data-test="nav-badge"]').text()).toContain('3')
    expect(wrapper.find('[data-test="nav-badge-spoken"]').text()).toBe(', 3 waiting')
  })

  it('stops counting at 99', async () => {
    const { wrapper } = await open('review', 240)

    expect(wrapper.find('[data-test="nav-badge"]').text()).toContain('99+')
  })

  it('has no number when nothing waits, or on another place', async () => {
    expect((await open('review', 0)).wrapper.find('[data-test="nav-badge-spoken"]').exists()).toBe(
      false,
    )
    expect(
      (await open('incidents', 5)).wrapper.find('[data-test="nav-badge-spoken"]').exists(),
    ).toBe(false)
  })
})
