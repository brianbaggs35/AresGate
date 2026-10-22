# Certificates

Put your certificate here to have nginx use it instead of the generated self-signed one:

- `fullchain.pem`: the certificate followed by its intermediates
- `privkey.pem`: the private key

Both files are ignored by git. After renewing them, run `make restart`.
