/** The services that well-known ports stand for, by transport. A port with no entry here is shown
 * as its number alone, since a number says no more than it is. */
const SERVICES: Record<string, string> = {
  '20': 'FTP data',
  '21': 'FTP',
  '22': 'SSH',
  '23': 'Telnet',
  '25': 'SMTP mail',
  '53': 'DNS',
  '67': 'DHCP',
  '68': 'DHCP',
  '80': 'HTTP',
  '110': 'POP3 mail',
  '123': 'NTP time',
  '137': 'NetBIOS',
  '139': 'NetBIOS',
  '143': 'IMAP mail',
  '161': 'SNMP',
  '389': 'LDAP',
  '443': 'HTTPS',
  '445': 'SMB file sharing',
  '465': 'SMTPS mail',
  '514': 'Syslog',
  '587': 'Mail submission',
  '853': 'DNS over TLS',
  '993': 'IMAPS mail',
  '995': 'POP3S mail',
  '1194': 'OpenVPN',
  '1433': 'SQL Server',
  '1883': 'MQTT',
  '3306': 'MySQL',
  '3389': 'Remote Desktop',
  '5060': 'SIP',
  '5353': 'mDNS',
  '5432': 'PostgreSQL',
  '5900': 'VNC',
  '8080': 'HTTP alternate',
  '8443': 'HTTPS alternate',
  '8883': 'MQTT over TLS',
  '51820': 'WireGuard',
}

/** The service a port is known for, or null if it has no well-known one. */
export function serviceOf(port: number): string | null {
  return SERVICES[String(port)] ?? null
}

/** A port as it is shown: its number, its transport, and the service it stands for. */
export function describePort(port: number, protocol: string | null): string {
  const service = serviceOf(port)
  const base = protocol ? `${port}/${protocol}` : String(port)
  return service ? `${base} ${service}` : base
}
