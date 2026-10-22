/**
 * Everything the tests mount, so each test can unmount what it left behind. It imports nothing
 * from the app, so the setup file can use it without loading modules a spec may want to mock.
 */
const mounted: { unmount: () => void; element: Node | null }[] = []

export function track(wrapper: { unmount: () => void; element: Node | null }) {
  mounted.push(wrapper)
}

/** Unmounts whatever a test left mounted, so its dialogs and timers don't leak into the next. */
export function unmountAll() {
  for (const wrapper of mounted.splice(0)) {
    if (wrapper.element?.isConnected) wrapper.unmount()
  }
}
