import { createPasskey, getPasskey, PasskeyError, passkeysSupported } from '@/webauthn'

const creation = {
  challenge: 'AAAA',
  rp: { name: 'AresGate' },
} as PublicKeyCredentialCreationOptionsJSON
const request = { challenge: 'AAAA' } as PublicKeyCredentialRequestOptionsJSON
const json = { id: 'AAAA', rawId: 'AAAA', type: 'public-key' }

/** What the browser's WebAuthn API is, made of stand-ins: jsdom has none of it. */
class FakeCredential {
  toJSON = () => json
}

function install(credentials: Partial<CredentialsContainer> | undefined) {
  vi.stubGlobal(
    'PublicKeyCredential',
    Object.assign(FakeCredential, {
      parseCreationOptionsFromJSON: vi.fn((options: unknown) => ({ parsed: options })),
      parseRequestOptionsFromJSON: vi.fn((options: unknown) => ({ parsed: options })),
    }),
  )
  Object.defineProperty(navigator, 'credentials', { value: credentials, configurable: true })
}

function refuse(name: string) {
  return new DOMException('refused', name)
}

describe('webauthn', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    Reflect.deleteProperty(navigator, 'credentials')
  })

  describe('passkeysSupported', () => {
    it('is true in a browser with the WebAuthn API and its JSON helpers', () => {
      install({ create: vi.fn() })
      expect(passkeysSupported()).toBe(true)
    })

    it('is false without the API', () => {
      expect(passkeysSupported()).toBe(false)
    })

    it('is false in a browser without the JSON helpers', () => {
      vi.stubGlobal('PublicKeyCredential', {})
      expect(passkeysSupported()).toBe(false)
      vi.stubGlobal('PublicKeyCredential', { parseCreationOptionsFromJSON: () => ({}) })
      expect(passkeysSupported()).toBe(false)
    })

    it('is false on a page without credentials, such as one that is not served over HTTPS', () => {
      install(undefined)
      Reflect.deleteProperty(navigator, 'credentials')
      expect(passkeysSupported()).toBe(false)
    })
  })

  describe('createPasskey', () => {
    it("asks the device to make one from the API's options, and returns it as JSON", async () => {
      const create = vi.fn().mockResolvedValue(new FakeCredential())
      install({ create })
      await expect(createPasskey(creation)).resolves.toEqual(json)
      expect(create).toHaveBeenCalledWith({ publicKey: { parsed: creation } })
    })

    it.each([
      ['NotAllowedError', 'Making the passkey was cancelled or timed out. Try again.'],
      ['InvalidStateError', 'This device already has a passkey for your account.'],
      ['SecurityError', "A passkey can't be used at this address."],
      ['NotSupportedError', "This device can't make a passkey that it unlocks itself."],
      ['AbortError', "Your browser couldn't make a passkey."],
    ])('explains %s', async (name, message) => {
      install({ create: vi.fn().mockRejectedValue(refuse(name)) })
      await expect(createPasskey(creation)).rejects.toThrow(message)
    })

    it('explains anything else that goes wrong', async () => {
      install({ create: vi.fn().mockRejectedValue(new Error('odd')) })
      await expect(createPasskey(creation)).rejects.toThrow("Your browser couldn't make a passkey.")
    })

    it('says so when the browser gives back nothing', async () => {
      install({ create: vi.fn().mockResolvedValue(null) })
      await expect(createPasskey(creation)).rejects.toThrow(
        new PasskeyError('No passkey was made.'),
      )
    })
  })

  describe('getPasskey', () => {
    it("asks the device to sign with one of its passkeys, from the API's options", async () => {
      const get = vi.fn().mockResolvedValue(new FakeCredential())
      install({ get })
      await expect(getPasskey(request)).resolves.toEqual(json)
      expect(get).toHaveBeenCalledWith({ publicKey: { parsed: request } })
    })

    it('explains a cancelled prompt', async () => {
      install({ get: vi.fn().mockRejectedValue(refuse('NotAllowedError')) })
      await expect(getPasskey(request)).rejects.toThrow(
        'Using the passkey was cancelled or timed out. Try again.',
      )
    })

    it('explains anything else that goes wrong', async () => {
      install({ get: vi.fn().mockRejectedValue(new Error('odd')) })
      await expect(getPasskey(request)).rejects.toThrow("Your browser couldn't use a passkey.")
    })

    it('says so when the browser gives back nothing', async () => {
      install({ get: vi.fn().mockResolvedValue(null) })
      await expect(getPasskey(request)).rejects.toThrow('No passkey was used.')
    })
  })
})
