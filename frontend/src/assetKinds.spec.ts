import { Camera, MonitorSmartphone, Router } from '@lucide/vue'

import { kindIcon } from '@/assetKinds'

describe('kindIcon', () => {
  it('has a picture for each kind', () => {
    expect(kindIcon('router')).toBe(Router)
    expect(kindIcon('camera')).toBe(Camera)
  })

  it('has the picture of an unknown device for a kind it does not know, or none', () => {
    expect(kindIcon('toaster')).toBe(MonitorSmartphone)
    expect(kindIcon(null)).toBe(MonitorSmartphone)
    expect(kindIcon(undefined)).toBe(MonitorSmartphone)
  })
})
