import type { Cve, CvePage, DeviceIntel, DeviceIntelPage } from '@/api/threatCatalog'

/** A critical CVE that CISA lists as exploited in the wild. */
export const EXPLOITED_CVE: Cve = {
  cve_id: 'CVE-2024-3400',
  state: 'found',
  checked_at: '2026-11-14T08:00:00Z',
  status: 'Analyzed',
  published_at: '2024-04-12T08:15:06Z',
  modified_at: '2026-10-02T10:00:00Z',
  cvss_version: '3.1',
  score: 10,
  rating: 'critical',
  vector: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H',
  description:
    'A command injection in the GlobalProtect feature of PAN-OS lets an attacker run code.',
  weaknesses: ['CWE-77', 'CWE-20'],
  exploited: true,
  exploited_on: '2024-04-12',
  action_due: '2024-04-19',
  required_action: 'Apply the mitigations the vendor lists.',
  kev_name: 'Palo Alto Networks PAN-OS Command Injection Vulnerability',
  link: 'https://nvd.nist.gov/vuln/detail/CVE-2024-3400',
}

/** A medium CVE nobody is known to exploit. */
export const MEDIUM_CVE: Cve = {
  ...EXPLOITED_CVE,
  cve_id: 'CVE-2023-1234',
  checked_at: '2026-11-13T08:00:00Z',
  score: 5.4,
  rating: 'medium',
  vector: null,
  description: null,
  weaknesses: [],
  exploited: false,
  exploited_on: null,
  action_due: null,
  required_action: null,
  kev_name: null,
  link: 'https://nvd.nist.gov/vuln/detail/CVE-2023-1234',
}

/** A CVE NVD has no record of yet. */
export const UNKNOWN_CVE: Cve = {
  ...MEDIUM_CVE,
  cve_id: 'CVE-2026-9999',
  state: 'unknown',
  status: null,
  published_at: null,
  modified_at: null,
  cvss_version: null,
  score: null,
  rating: 'unrated',
  link: 'https://nvd.nist.gov/vuln/detail/CVE-2026-9999',
}

/** What NVD answered about three CVEs, newest asked first. */
export function cvePage(overrides: Partial<CvePage> = {}): CvePage {
  return {
    notice: 'This product uses data from the NVD API but is not endorsed or certified by the NVD.',
    total: 3,
    counts: { critical: 1, high: 0, medium: 1, low: 0, unrated: 1, exploited: 1 },
    items: [EXPLOITED_CVE, MEDIUM_CVE, UNKNOWN_CVE],
    ...overrides,
  }
}

/** A device Fingerbank recognised. */
export const CAMERA: DeviceIntel = {
  device_id: 7,
  mac: '3c:5a:b4:00:00:01',
  hostname: 'driveway-cam',
  vendor: 'Google, Inc.',
  address: '192.168.1.50',
  state: 'identified',
  reason: 'asset',
  name: 'Nest Cam',
  path: 'Hardware Manufacturer/Google/Camera',
  manufacturer: 'Google',
  operating_system: 'Linux OS',
  score: 87,
  checked_at: '2026-11-14T08:00:00Z',
  last_seen_at: '2026-11-15T08:00:00Z',
}

/** A device whose hardware address is one it made up, so Fingerbank was not asked. */
export const PRIVATE_PHONE: DeviceIntel = {
  ...CAMERA,
  device_id: 8,
  mac: 'da:a1:19:00:00:02',
  hostname: null,
  vendor: null,
  address: null,
  state: 'private',
  reason: 'incident',
  name: null,
  path: null,
  manufacturer: null,
  operating_system: null,
  score: null,
}

/** What Fingerbank made of three devices, the most recently asked first. */
export function deviceIntelPage(overrides: Partial<DeviceIntelPage> = {}): DeviceIntelPage {
  return {
    total: 3,
    counts: { identified: 1, unknown: 1, private: 1 },
    items: [
      CAMERA,
      {
        ...CAMERA,
        device_id: 9,
        hostname: null,
        address: null,
        state: 'unknown',
        name: null,
        path: null,
        manufacturer: null,
        operating_system: null,
        score: null,
        vendor: null,
        mac: '00:11:22:00:00:03',
      },
      PRIVATE_PHONE,
    ],
    ...overrides,
  }
}
