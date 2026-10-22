# Certificates

nginx serves the certificate in this folder instead of a generated self-signed one:

- `fullchain.pem`: the certificate followed by its intermediates
- `privkey.pem`: the private key

`make cert` fills this folder with a Let's Encrypt certificate for `ARESGATE_SERVER_NAME`, and
`make cert-renew` replaces it before it expires (DOCS/quick-start.md). To bring your own, put
both files here. Both files are ignored by git.

After a certificate here changes, run `make cert-reload` so AresGate uses it without
restarting. A restart (`make restart`) also does.
