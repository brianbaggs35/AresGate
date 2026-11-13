"""Step-by-step instructions for connecting each integration, shown in a window on its page.

Each guide is written from the product's own pages and source, which are listed with it, so that
the menu names, privileges and values are the ones the product uses. Where a step could not be
read from them, it says so in ``inferred`` and the page shows that note beside it, rather than
passing a guess off as documentation. None of it has been tried against every release of the
products: the connection test is what tells whether a step worked."""

from pydantic import BaseModel, ConfigDict

# Said the same way in every guide, and by the guides that mention the same menu.
ADDRESS = "Address, for example"
INDEXER = "Indexer management"
PASTE_KEY = "Paste it into API key on the card."
COPY_KEY = "Copy the API key"


class Source(BaseModel):
    """A page of the product's documentation, or of its source, that a guide was written from."""

    model_config = ConfigDict(frozen=True)

    title: str
    url: str


class Fill(BaseModel):
    """An exact value to pick or enter: what it is for, and what to put."""

    model_config = ConfigDict(frozen=True)

    label: str
    value: str


class Step(BaseModel):
    model_config = ConfigDict(frozen=True)

    # A few words: what this step gets done.
    title: str
    detail: str
    # The menus to go through, in order.
    menu: tuple[str, ...] = ()
    fills: tuple[Fill, ...] = ()
    # Something to run in a shell, shown as it is to be copied.
    command: str = ""
    # Which of AresGate's fields what this step produced goes into.
    result: str = ""
    # What is easy to get wrong.
    watch: str = ""
    # What was worked out rather than read, and why.
    inferred: str = ""


class Part(BaseModel):
    """The steps for one connection of the integration (its Wazuh manager, say, or its indexer)."""

    model_config = ConfigDict(frozen=True)

    title: str
    # The key of the connection whose form these steps fill in.
    connection: str
    intro: str
    steps: tuple[Step, ...]
    # Left out when the integration doesn't use it, as the connection is.
    optional: bool = False


class Guide(BaseModel):
    model_config = ConfigDict(frozen=True)

    parts: tuple[Part, ...]
    sources: tuple[Source, ...]


OPNSENSE = Guide(
    parts=(
        Part(
            title="Make a key for AresGate",
            connection="api",
            intro=(
                "AresGate calls OPNsense's REST API with an API key and its secret. OPNsense gives "
                "a key the permissions of the user it belongs to, so make a user for AresGate and "
                "give it only what AresGate reads."
            ),
            steps=(
                Step(
                    title="Add a user for AresGate",
                    detail=(
                        "Make a user that only AresGate uses, so its key can be removed without "
                        "touching anyone else's. In the list of users, click the + sign at the "
                        "bottom right of the form."
                    ),
                    menu=("System", "Access", "Users"),
                    fills=(
                        Fill(label="Username", value="aresgate"),
                        Fill(
                            label="Password",
                            value="A long random one. AresGate signs in with the key, not this.",
                        ),
                    ),
                    watch=(
                        "OPNsense recommends a separate key for each application, so don't use "
                        "the key of an existing user."
                    ),
                ),
                Step(
                    title="Give it what AresGate reads",
                    detail=(
                        "OPNsense checks the API against the same privileges as its web pages. "
                        "Add these to the user under Effective Privileges, or to a group that the "
                        "user is in, under Assigned Privileges (System, Access, Groups). Add only "
                        "the ones for the services you run."
                    ),
                    menu=("System", "Access", "Users"),
                    fills=(
                        Fill(label="Health and resources", value="Lobby: Dashboard"),
                        Fill(label="CPU use", value="Diagnostics: System Activity"),
                        Fill(label="Interface traffic", value="Diagnostics: Netstat"),
                        Fill(label="ARP table", value="Diagnostics: ARP Table"),
                        Fill(label="Firewall log", value="Diagnostics: Logs: Firewall: Live View"),
                        Fill(label="Gateways", value="System: Gateways"),
                        Fill(label="Suricata alerts", value="Services: Intrusion Detection"),
                        Fill(label="Kea DHCP leases", value="Services: DHCP: Kea(v4)"),
                        Fill(
                            label="Dnsmasq DHCP leases",
                            value="Services: Dnsmasq DNS/DHCP: Settings",
                        ),
                        Fill(label="CrowdSec plugin", value="CrowdSec"),
                        Fill(label="Wazuh agent plugin", value="Services: Wazuh Agent"),
                    ),
                    watch=(
                        "System, Access, Privileges lists who has each privilege. A privilege "
                        "that is missing makes that one call fail in the connection test, not the "
                        "whole connection."
                    ),
                    inferred=(
                        "OPNsense's documentation doesn't list the privileges an API client "
                        "needs. These are the ones whose rules, in OPNsense's own source (its ACL "
                        "files), match the calls AresGate makes. Names can differ a little "
                        "between releases. The Wazuh agent plugin's rules name wazuh_agent "
                        "while AresGate asks for wazuhagent, so that privilege alone may not "
                        "be enough."
                    ),
                ),
                Step(
                    title="Create the API key",
                    detail=(
                        "Open the user again and create an API key for it: the + sign in the API "
                        "section of the user's page, or the key button for the user in the list "
                        "on newer releases. OPNsense downloads apikey.txt at once, with a line "
                        "key=... and a line secret=..."
                    ),
                    menu=("System", "Access", "Users"),
                    result=(
                        "Paste the key= value into API key and the secret= value into API "
                        "secret on the card below."
                    ),
                    watch=(
                        "The secret is shown once and OPNsense doesn't keep it. If the file is "
                        "lost, make a new key."
                    ),
                    inferred=(
                        "Two pages of OPNsense's documentation put this button in different "
                        "places, which fits a page that changed between releases. Use the one "
                        "yours shows."
                    ),
                ),
                Step(
                    title="Enter the address and connect",
                    detail=(
                        "Enter the address you open OPNsense at, starting with https://. Connect "
                        "saves it and tests it. The test finds which services are installed "
                        "(Suricata, CrowdSec, OpenVPN, WireGuard and more) and lists them under "
                        "Services, where you can switch off any you don't want read."
                    ),
                    fills=(Fill(label=ADDRESS, value="https://192.168.1.1"),),
                    watch=(
                        "OPNsense makes a certificate for itself until you replace it. Under "
                        "Certificate on the card, click Look up the certificate, compare its "
                        "fingerprint with the one in System, Trust, Certificates, and trust it. "
                        "If the test fails over the certificate, Review the certificate does the "
                        "same."
                    ),
                ),
            ),
        ),
        Part(
            title="Zenarmor",
            connection="zenarmor",
            optional=True,
            intro=(
                "Only if you use Zenarmor. Its API is separate from OPNsense's: it has an address "
                "and keys of its own, made in Zenconsole."
            ),
            steps=(
                Step(
                    title="Turn the API on",
                    detail=(
                        "Select the firewall in Zenconsole, open Settings, then API, and switch "
                        "the API from Disabled to Enabled with the button at the top right of "
                        "the pane."
                    ),
                    menu=("Zenconsole", "Settings", "API"),
                ),
                Step(
                    title="Generate a key",
                    detail=(
                        "Click +Generate API Key, enter a user name and click Generate. The key "
                        "shows in the API Keys pane."
                    ),
                    menu=("Zenconsole", "Settings", "API"),
                    fills=(Fill(label="User name", value="aresgate"),),
                    result="Enter the user name as API user and the key as API key on the card.",
                    watch=(
                        "Zenarmor's page says a new key has to be activated from the command line "
                        "on the firewall before it works, and doesn't show the command there. "
                        "Follow its API Key Management page."
                    ),
                ),
                Step(
                    title="Enter the address",
                    detail=(
                        "The firewall's address with the port Zenarmor's API listens on. HTTPS is "
                        "required, and the key is sent as the user name of HTTP basic "
                        "authentication."
                    ),
                    fills=(Fill(label=ADDRESS, value="https://192.168.1.1:8090"),),
                    inferred=(
                        "Zenarmor's pages give no fixed port; their examples use 8090. Use the "
                        "port your firewall shows."
                    ),
                ),
            ),
        ),
    ),
    sources=(
        Source(
            title="OPNsense: using the API and API keys",
            url="https://docs.opnsense.org/development/how-tos/api.html",
        ),
        Source(
            title="OPNsense: the API and its privileges",
            url="https://docs.opnsense.org/development/api.html",
        ),
        Source(
            title="OPNsense: local users and groups",
            url="https://docs.opnsense.org/manual/how-tos/user-local.html",
        ),
        Source(
            title="OPNsense source: privileges and the API paths they allow",
            url="https://github.com/opnsense/core/tree/master/src/opnsense/mvc/app/models/OPNsense",
        ),
        Source(
            title="OPNsense plugins source: CrowdSec and Wazuh agent privileges",
            url="https://github.com/opnsense/plugins/tree/master/security",
        ),
        Source(
            title="Zenarmor: enable or disable the API",
            url="https://www.zenarmor.com/docs/developers/zenarmor-enable-disable-api",
        ),
        Source(
            title="Zenarmor: API key management",
            url="https://www.zenarmor.com/docs/developers/zenarmor-api-key-management",
        ),
        Source(
            title="Zenarmor: RESTful API calls",
            url="https://www.zenarmor.com/docs/developers/zenarmor-restful-api",
        ),
    ),
)

NTOPNG = Guide(
    parts=(
        Part(
            title="Make a user and its token",
            connection="api",
            intro=(
                "AresGate reads the hosts, the interface's traffic and the alerts through "
                "ntopng's REST API. It needs a user of its own in ntopng, and that user's "
                "authentication token."
            ),
            steps=(
                Step(
                    title="Open user management",
                    detail=(
                        "Sign in to ntopng as an administrator. Manage Users is in the gear menu "
                        "in the top toolbar."
                    ),
                    menu=("Settings (the gear in the top bar)", "Manage Users"),
                ),
                Step(
                    title="Add a user for AresGate",
                    detail="Click Add New User and fill in the form.",
                    menu=("Manage Users", "Add New User"),
                    fills=(
                        Fill(
                            label="Username",
                            value=(
                                "aresgate (letters, digits and . _ - @, at most 32; ntopng keeps "
                                "it in lower case)"
                            ),
                        ),
                        Fill(label="Full name", value="AresGate"),
                        Fill(
                            label="Password",
                            value="A long random one. AresGate signs in with the token, not this.",
                        ),
                        Fill(
                            label="User Role",
                            value=(
                                "Non Privileged User (Administrator also works, but gives "
                                "AresGate more than it needs)"
                            ),
                        ),
                        Fill(label="Allow Alerts", value="On"),
                        Fill(label="Allowed Interface", value="Any Interface"),
                        Fill(label="Allowed Networks", value="0.0.0.0/0,::/0"),
                        Fill(
                            label="Allow Historical Flows, Allow PCAP Download",
                            value="Off. AresGate doesn't use them.",
                        ),
                    ),
                    watch=(
                        "Allowed Networks limits which hosts and traffic the user can see, so a "
                        "shorter list hides hosts from AresGate. It doesn't limit alerts."
                    ),
                    inferred=(
                        "ntopng's guide doesn't say what a read-only client needs. The role and "
                        "the flags come from ntopng's own user form and source. If the test "
                        "shows missing hosts or alerts, widen this user or use Administrator."
                    ),
                ),
                Step(
                    title="Generate the user's token",
                    detail=(
                        "Sign in to ntopng as the new user, open the settings, go to User and "
                        "click Edit. Choose User Authentication Token and click Generate Token."
                    ),
                    menu=(
                        "Settings",
                        "User",
                        "Edit",
                        "User Authentication Token",
                        "Generate Token",
                    ),
                    command=(
                        "curl -u admin:PASSWORD -H 'Content-Type: application/json' "
                        '-d \'{"username": "aresgate"}\' '
                        "http://NTOPNG:3000/lua/rest/v2/create/ntopng/api_token.lua"
                    ),
                    result=(
                        "Paste the token into Authentication token on the card, with Sign in "
                        "with set to Authentication token."
                    ),
                    watch=(
                        "The command is another way for an administrator to make the token, from "
                        "a shell; the answer holds it as api_token. Replace the capitals. A wrong "
                        "login gets no error, only a redirect to the login page."
                    ),
                ),
                Step(
                    title="Connect and choose the interfaces",
                    detail=(
                        "Enter ntopng's address, with the port of its web interface (3000 unless "
                        "you changed it). Then press Fetch interfaces: it lists the interfaces "
                        "ntopng watches, with their ID and what each has seen, and you choose each "
                        "one AresGate reads. ntopng numbers its interfaces itself, not always from "
                        "0, so go by the names. Choose none and AresGate reads every one except "
                        "the loopback (lo or lo0), which only carries the machine's traffic to "
                        "itself. Username and password, instead of the token, use HTTP basic "
                        "authentication."
                    ),
                    fills=(
                        Fill(label=ADDRESS, value="http://192.168.1.2:3000"),
                        Fill(label="Sign in with", value="Authentication token"),
                    ),
                    watch=(
                        "A login ntopng refuses is answered with a redirect to its login page, "
                        "not an error, so a wrong token shows up as a redirect."
                    ),
                ),
            ),
        ),
    ),
    sources=(
        Source(
            title="ntopng: authentication and tokens",
            url="https://www.ntop.org/guides/ntopng/authentication.html#token-based-authentication",
        ),
        Source(
            title="ntopng: the web interface's settings",
            url="https://www.ntop.org/guides/ntopng/web_gui/settings.html",
        ),
        Source(
            title="ntopng: REST API version 2",
            url="https://www.ntop.org/guides/ntopng/api/rest/api_v2.html",
        ),
        Source(
            title="ntopng source: add a user",
            url="https://github.com/ntop/ntopng/blob/dev/scripts/lua/rest/v2/add/ntopng/user.lua",
        ),
        Source(
            title="ntopng source: create an API token",
            url=(
                "https://github.com/ntop/ntopng/blob/dev/scripts/lua/rest/v2/create/ntopng/"
                "api_token.lua"
            ),
        ),
        Source(
            title="ntopng source: the labels of the user form",
            url="https://github.com/ntop/ntopng/blob/dev/scripts/locales/en.lua",
        ),
    ),
)

WAZUH = Guide(
    parts=(
        Part(
            title="Manager API: the agents",
            connection="manager",
            intro=(
                "AresGate signs in to the manager's API (HTTPS, port 55000) with a user name and "
                "password, and asks which agents are reporting. Give it a user that may only read "
                "agents, not the administrator."
            ),
            steps=(
                Step(
                    title="Open Security",
                    detail=(
                        "Sign in to the Wazuh dashboard as an administrator and open the Security "
                        "section of Server management."
                    ),
                    menu=("Server management", "Security"),
                ),
                Step(
                    title="Create the API user",
                    detail=(
                        "Create a user for AresGate with a user name and a password. The API does "
                        "the same with POST /security/users."
                    ),
                    fills=(
                        Fill(label="Username", value="aresgate"),
                        Fill(label="Password", value="A long random one."),
                    ),
                    inferred=(
                        "Wazuh's pages describe the API call. The dashboard's Users tab is beside "
                        "the Roles mapping tab in the same section, but no page found walks "
                        "through it."
                    ),
                ),
                Step(
                    title="Give it the read-only agents role",
                    detail=(
                        "Give the user the agents_readonly role, which Wazuh describes as a read "
                        "only role for agents related functionalities. Don't use administrator, "
                        "or the default wazuh account, whose password Wazuh says to change after "
                        "installing."
                    ),
                    fills=(Fill(label="Role", value="agents_readonly"),),
                    watch=(
                        "A user with no role can sign in, and the API then lists no agents to "
                        "it, not even the manager, instead of refusing. The connection test says "
                        "so, and the Agents collector reports the same, but a user that is "
                        "missing its role looks like a working one until then."
                    ),
                    inferred=(
                        "The pages found don't show which button links a role to a user. The "
                        "role itself is in Wazuh's source. Linking it through the API, with POST "
                        "/security/users/{user_id}/roles?role_ids=... (GET /security/roles lists "
                        "the role ids), was tried on a Wazuh 4.14.1 manager: the user then "
                        "listed the manager's agent. The dashboard's buttons were not tried."
                    ),
                ),
                Step(
                    title="Enter the address and the sign-in",
                    detail=(
                        "Enter the manager's address with port 55000, and the user name and "
                        "password from above. The API answers with its own certificate, which "
                        "Wazuh's pages call self-signed by default. Under Certificate on the "
                        "card, click Look up the certificate, compare its fingerprint with the "
                        "one on the Wazuh server (below) and trust it. If the test fails over "
                        "the certificate, Review the certificate does the same."
                    ),
                    fills=(Fill(label=ADDRESS, value="https://192.168.1.3:55000"),),
                    command=(
                        "openssl x509 -in /var/ossec/api/configuration/ssl/server.crt "
                        "-noout -fingerprint -sha256"
                    ),
                    watch=(
                        "A Let's Encrypt certificate on the Wazuh dashboard is not used here. "
                        "Wazuh's page on Let's Encrypt covers the dashboard only, so the "
                        "choice The certificates this computer trusts fails on the API unless "
                        "you also put a public certificate on it (the cert and key settings "
                        "under https in api.yaml)."
                    ),
                    inferred=(
                        "The command is plain OpenSSL, run on the file the API's configuration "
                        "page names as its default certificate (server.crt in the ssl folder). "
                        "No Wazuh page shows it, and the file is somewhere else if you changed "
                        "api.yaml."
                    ),
                ),
            ),
        ),
        Part(
            title="Indexer: the alerts",
            connection="indexer",
            intro=(
                "The alerts are read from the Wazuh indexer (HTTPS, port 9200) with a user name "
                "and password, from the wazuh-alerts-* indices. Make a user that can only read "
                "those, rather than using admin."
            ),
            steps=(
                Step(
                    title="Create an internal user",
                    detail="Click Create internal user, enter a user name and a password, and "
                    "click Create.",
                    menu=(INDEXER, "Security", "Internal users"),
                    fills=(
                        Fill(label="Username", value="aresgate"),
                        Fill(label="Password", value="A long random one."),
                    ),
                ),
                Step(
                    title="Create a read-only role",
                    detail=(
                        "Click Create role and give it a name, such as aresgate_alerts. Add one "
                        "index permission: the index pattern wazuh-alerts-* with the read "
                        "permission. Leave Cluster permissions empty: AresGate only searches "
                        "the alerts."
                    ),
                    menu=(INDEXER, "Security", "Roles"),
                    fills=(
                        Fill(label="Index", value="wazuh-alerts-*"),
                        Fill(label="Index permissions", value="read"),
                    ),
                    watch=(
                        "Wazuh's example of a read-only role reads every index (*) and adds the "
                        "cluster permission cluster_composite_ops_ro and a Dashboard tenant. "
                        "That works too, but it gives more than AresGate uses. Either way the "
                        "user can't ask the indexer's root page, which needs the cluster "
                        "permission cluster:monitor/main (part of cluster_monitor). AresGate "
                        "doesn't ask it."
                    ),
                    inferred=(
                        "Wazuh's page shows the example role, not this narrower one. That a "
                        "user with only read on wazuh-alerts-* can search those indices, "
                        "including when none exist yet, and gets 403 for the root page, was "
                        "tried on OpenSearch 2.19.1 with its security plugin, which the Wazuh "
                        "indexer is built on. It was not tried on Wazuh's own build."
                    ),
                ),
                Step(
                    title="Map the user to the role",
                    detail=(
                        "Open the role, go to the Mapped users tab, click Manage mapping, add the "
                        "user and click Map."
                    ),
                    menu=(INDEXER, "Security", "Roles", "Mapped users"),
                    watch=(
                        "A user who isn't mapped to a role can sign in and is then refused every "
                        "search: the test says the user has no permission for "
                        "indices:data/read/search. A wrong user name or password is a different "
                        "message, a refused sign-in (HTTP 401)."
                    ),
                ),
                Step(
                    title="Enter the address and the sign-in",
                    detail=(
                        "Enter the indexer's address with port 9200, and the user name and "
                        "password of this user. Wazuh's certificate tool makes the indexer's "
                        "certificate and the authority that signed it, root-ca.pem. This card "
                        "has its own Certificate setting. Under Certificate on the card, click "
                        "Look up the certificate and trust it, or choose A certificate "
                        "authority I paste and paste the contents of root-ca.pem."
                    ),
                    fills=(Fill(label=ADDRESS, value="https://192.168.1.3:9200"),),
                    watch=(
                        "A Let's Encrypt certificate on the Wazuh dashboard is not used here. "
                        "Wazuh's page on Let's Encrypt covers the dashboard only, so the "
                        "choice The certificates this computer trusts fails on the indexer "
                        "unless you also replaced its certificate. Paste root-ca.pem, never "
                        "root-ca.key."
                    ),
                    inferred=(
                        "The certificate tool's script gives each certificate the addresses and "
                        "names it was run with, so if the test says the certificate is for "
                        "other names, use one of those in the address. Wazuh's pages don't say "
                        "so, and where root-ca.pem was kept depends on how Wazuh was installed."
                    ),
                ),
            ),
        ),
    ),
    sources=(
        Source(
            title="Wazuh: getting started with the server API",
            url="https://documentation.wazuh.com/current/user-manual/api/getting-started.html",
        ),
        Source(
            title="Wazuh: configuring the API's role based access control",
            url="https://documentation.wazuh.com/current/user-manual/api/rbac/configuration.html",
        ),
        Source(
            title="Wazuh: creating and mapping internal users",
            url="https://documentation.wazuh.com/current/user-manual/user-administration/rbac.html",
        ),
        Source(
            title="Wazuh: configuring third-party certificates (the dashboard only)",
            url=(
                "https://documentation.wazuh.com/current/user-manual/wazuh-dashboard/"
                "configuring-third-party-certs/index.html"
            ),
        ),
        Source(
            title="Wazuh: the API's configuration file, with its https settings",
            url="https://documentation.wazuh.com/current/user-manual/api/configuration.html",
        ),
        Source(
            title="Wazuh: certificate deployment, with root-ca.pem",
            url=(
                "https://documentation.wazuh.com/current/user-manual/wazuh-indexer-cluster/"
                "certificate-deployment.html"
            ),
        ),
        Source(
            title="Wazuh source: the certificate tool",
            url="https://packages.wazuh.com/4.14/wazuh-certs-tool.sh",
        ),
        Source(
            title="Wazuh source: the default roles",
            url=(
                "https://github.com/wazuh/wazuh/blob/v4.14.1/framework/wazuh/rbac/default/"
                "roles.yaml"
            ),
        ),
        Source(
            title="OpenSearch: permissions (cluster:monitor/main and the index permissions)",
            url="https://docs.opensearch.org/latest/security/access-control/permissions/",
        ),
        Source(
            title="OpenSearch: default action groups (read, cluster_monitor)",
            url="https://docs.opensearch.org/latest/security/access-control/default-action-groups/",
        ),
    ),
)

CROWDSEC = Guide(
    parts=(
        Part(
            title="Add a bouncer",
            connection="lapi",
            intro=(
                "AresGate reads the decisions CrowdSec has made through its local API, with a "
                "bouncer's API key. CrowdSec says a bouncer's key can only read decisions."
            ),
            steps=(
                Step(
                    title="Add a bouncer for AresGate",
                    detail=(
                        "On the machine where CrowdSec runs, add a bouncer. CrowdSec prints an "
                        "API key: keep it."
                    ),
                    command="sudo cscli bouncers add aresgate",
                    result="Paste the key into API key on the card.",
                    watch=(
                        "Copy the key when it is printed. CrowdSec's page says to keep it and "
                        "shows no way to read it again."
                    ),
                    inferred=(
                        "If the key is lost, deleting the bouncer (cscli bouncers delete "
                        "aresgate) and adding it again makes a new one. That is how cscli works, "
                        "not something the page says."
                    ),
                ),
                Step(
                    title="Make the local API reachable",
                    detail=(
                        "The local API listens where api.server.listen_uri says, as host:port. "
                        "CrowdSec's examples use 127.0.0.1:8080, which only the same machine can "
                        "reach. For AresGate to reach it, make it listen on an address of the "
                        "machine on your network, and restart CrowdSec."
                    ),
                    fills=(
                        Fill(label="File", value="/etc/crowdsec/config.yaml"),
                        Fill(label="Setting", value="api.server.listen_uri"),
                        Fill(label="Value, for example", value="192.168.1.4:8080"),
                    ),
                    inferred=(
                        "The configuration page names the setting and its host:port form but "
                        "gives no default. Restarting CrowdSec after the change is the usual "
                        "step, not something that page says."
                    ),
                ),
                Step(
                    title="Enter the address and connect",
                    detail=(
                        "Enter the address with its port. The local API speaks plain HTTP unless "
                        "api.server.tls (cert_file and key_file) is set up. AresGate accepts "
                        "http:// here, but anyone on the network path can read the key, so keep "
                        "it to a network you trust."
                    ),
                    fills=(Fill(label=ADDRESS, value="http://192.168.1.4:8080"),),
                ),
            ),
        ),
    ),
    sources=(
        Source(
            title="CrowdSec: authentication to the local API",
            url="https://docs.crowdsec.net/docs/local_api/authentication/",
        ),
        Source(
            title="CrowdSec: configuration",
            url="https://docs.crowdsec.net/docs/configuration/crowdsec_configuration/",
        ),
    ),
)


VIRUSTOTAL = Guide(
    parts=(
        Part(
            title="Get an API key",
            connection="api",
            intro=(
                "AresGate asks VirusTotal about the internet addresses in an incident, with the "
                "API key from your account. VirusTotal says that key carries all of your "
                "privileges."
            ),
            steps=(
                Step(
                    title=COPY_KEY,
                    detail="Sign in to VirusTotal. Your API key is in your account's user menu.",
                    menu=("User menu",),
                    result=PASTE_KEY,
                    watch=(
                        "Keep the key to AresGate alone. Anyone who holds it can act as your "
                        "account there."
                    ),
                ),
                Step(
                    title="Choose the access level",
                    detail=(
                        "Choose Free public API, or Premium API if your plan is premium. The two "
                        "have different limits, which the card shows beside the choice."
                    ),
                    result="Set Access level on the card.",
                    watch=(
                        "The free public API must not be used in commercial products or services, "
                        "or in business workflows. Choose it only where those rules allow."
                    ),
                    inferred=(
                        "VirusTotal's pages don't say how to tell from a key which plan it is on, "
                        "so AresGate doesn't detect the access level: you choose it."
                    ),
                ),
            ),
        ),
    ),
    sources=(
        Source(
            title="VirusTotal API: overview",
            url="https://docs.virustotal.com/reference/overview",
        ),
        Source(
            title="VirusTotal API: authentication",
            url="https://docs.virustotal.com/reference/authentication",
        ),
        Source(
            title="VirusTotal API: public and premium limits",
            url="https://docs.virustotal.com/reference/public-vs-premium-api",
        ),
    ),
)


OTX = Guide(
    parts=(
        Part(
            title="Get an OTX key",
            connection="api",
            intro=(
                "AresGate asks AlienVault OTX which threat reports from its community name the "
                "internet addresses in an incident, with the OTX key from your account. The key "
                "is free."
            ),
            steps=(
                Step(
                    title="Copy the OTX key",
                    detail=(
                        "Sign in to AlienVault OTX, or create a free account. Your OTX key is on "
                        "your account's settings page."
                    ),
                    menu=("Settings",),
                    result=PASTE_KEY,
                    watch=(
                        "Keep the key to AresGate alone. Anyone who holds it can act as your "
                        "account there."
                    ),
                ),
                Step(
                    title="Choose the lookup pace",
                    detail=(
                        "Gentle, balanced or fast sets how often AresGate asks about a new address."
                    ),
                    result="Set Lookup pace on the card.",
                    watch=(
                        "Every address asked about is shared with OTX, so only addresses on the "
                        "internet are sent, never your own."
                    ),
                    inferred=(
                        "OTX's pages don't give a limit on requests, so AresGate chose the pace "
                        "for each setting itself, and stops for five minutes if OTX answers 429."
                    ),
                ),
            ),
        ),
    ),
    sources=(
        Source(
            title="OTX API: DirectConnect",
            url="https://otx.alienvault.com/assets/static/external_api.html",
        ),
    ),
)


GREYNOISE = Guide(
    parts=(
        Part(
            title="Get a GreyNoise key",
            connection="api",
            intro=(
                "AresGate asks GreyNoise whether an address on the internet is one of the many "
                "that scan every address, or belongs to a common business service. It works "
                "with a free account, with a subscription, and, for 10 lookups a day, with no "
                "account at all."
            ),
            steps=(
                Step(
                    title="Choose how to ask",
                    detail=(
                        "With no account, GreyNoise's Community API answers up to 10 lookups a "
                        "day and needs no key. A free account's key allows 50 searches a week. "
                        "A Standard, Advanced or Elite subscription also gives the tags and the "
                        "actor GreyNoise attaches to an address."
                    ),
                    result="Set Account, and Plan if there is an account, on the card.",
                    watch=(
                        "Only an account made with a business email is given an API key: "
                        "GreyNoise says accounts made with free email addresses, such as Gmail "
                        "or iCloud, have no key-level access. If yours is one, choose No account."
                    ),
                ),
                Step(
                    title=COPY_KEY,
                    detail=(
                        "Sign in to the GreyNoise Visualizer, or sign up. Open the account menu "
                        "at the bottom of the left sidebar and choose API Key under Workspace."
                    ),
                    menu=("Account menu", "Workspace", "API Key"),
                    result=PASTE_KEY,
                    watch=(
                        "The page shows the week's searches used so far. The Visualizer and "
                        "AresGate share them, and AresGate keeps 10 of the 50 for you. Keep the "
                        "key to AresGate alone."
                    ),
                ),
            ),
        ),
    ),
    sources=(
        Source(
            title="GreyNoise: Using the Community API",
            url="https://docs.greynoise.io/docs/using-the-greynoise-community-api",
        ),
        Source(
            title="GreyNoise: Using the v3 API",
            url="https://docs.greynoise.io/docs/using-the-greynoise-api",
        ),
        Source(
            title="GreyNoise: Setting up an account",
            url="https://docs.greynoise.io/docs/setting-up-an-account",
        ),
        Source(title="GreyNoise: Plans", url="https://www.greynoise.io/plans"),
    ),
)


NVD = Guide(
    parts=(
        Part(
            title="Get an NVD API key",
            connection="api",
            intro=(
                "AresGate asks the National Vulnerability Database about the CVEs that incidents "
                "name, to learn how severe each is and whether CISA has seen it exploited. NVD "
                "answers without a key, though slowly: with a free key it answers ten times as "
                "fast, which is the better choice."
            ),
            steps=(
                Step(
                    title="Request a key",
                    detail=(
                        "On NVD's Request an API Key page, give an organization name (Personal "
                        "Use is one of the choices), an email address and the type of "
                        "organization, then agree to the Terms of Use at the end of the page and "
                        "submit. NVD emails a single-use link."
                    ),
                    result="Choose Ask with an API key on the card.",
                    watch=(
                        "The link works once and expires after seven days. NVD can't show the "
                        "key again or tell you whether one was requested, so a lost key means a "
                        "new request, and asking again with the same email address cancels the "
                        "key from before as soon as the new link is opened."
                    ),
                ),
                Step(
                    title="Copy the key",
                    detail=(
                        "Open the link in the email. The page shows the key once: copy it "
                        "before closing it."
                    ),
                    result=PASTE_KEY,
                    watch=(
                        "A key is for one person or application. Don't share it, and keep it to "
                        "AresGate alone."
                    ),
                ),
                Step(
                    title="Or ask without a key",
                    detail=(
                        "Without a key NVD allows 5 requests in 30 seconds, and AresGate asks "
                        "about one CVE every ten seconds. A new CVE can wait a little for its "
                        "answer, which is rarely a problem."
                    ),
                    result="Choose Ask without a key on the card.",
                ),
            ),
        ),
    ),
    sources=(
        Source(title="NVD: Start Here", url="https://nvd.nist.gov/developers/start-here"),
        Source(
            title="NVD: Vulnerability APIs", url="https://nvd.nist.gov/developers/vulnerabilities"
        ),
        Source(
            title="NVD: Request an API Key",
            url="https://nvd.nist.gov/developers/request-an-api-key",
        ),
    ),
)


FINGERBANK = Guide(
    parts=(
        Part(
            title="Get a Fingerbank key",
            connection="api",
            intro=(
                "AresGate asks Fingerbank what each device on your network is, with the API key "
                "from your Fingerbank account. The free key is enough."
            ),
            steps=(
                Step(
                    title=COPY_KEY,
                    detail=(
                        "Create a free account on Fingerbank's website, or sign in. Your API key "
                        "is on your account page."
                    ),
                    menu=("My Account",),
                    result=PASTE_KEY,
                    watch=(
                        "Use one key for AresGate alone. Fingerbank blocks a client that uses "
                        "more than one key from the same internet address."
                    ),
                ),
                Step(
                    title="Choose whose devices are identified",
                    detail=(
                        "Your own devices are always identified, the ones that connected "
                        "most recently first. Choose whether the devices in incidents and "
                        "threats are identified too."
                    ),
                    result="Set Devices in incidents and threats on the card.",
                    watch=(
                        "What is sent is the device's hardware address and nothing else, and "
                        "never one the device made up for itself. Fingerbank keeps what it is "
                        "sent to improve its matching."
                    ),
                    inferred=(
                        "The Fingerbank pages this was written from give no figure for the free "
                        "key's requests an hour. AresGate keeps to 600 an hour, which the free "
                        "plan is understood to allow, and treats a 429 as a request to wait, not "
                        "as an error. The API's own cap is 250 requests a minute for every key."
                    ),
                ),
            ),
        ),
    ),
    sources=(
        Source(
            title="Fingerbank API v2: interrogate",
            url="https://api.fingerbank.org/api_doc/2/combinations/interrogate.html",
        ),
        Source(
            title="Fingerbank: how to use the API",
            url="https://www.fingerbank.org/usage/",
        ),
        Source(
            title="Fingerbank: fair usage policy",
            url="https://www.fingerbank.org/fair-usage-policy",
        ),
        Source(
            title="Fingerbank: terms and privacy",
            url="https://www.fingerbank.org/privacy",
        ),
    ),
)
