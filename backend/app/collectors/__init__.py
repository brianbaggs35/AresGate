"""The collectors: regular jobs that read from the integrations, run by the worker (a process of
its own, next to the API) and answered for on the status page.

``base`` says what a collector is, ``registry`` lists them, ``scheduler`` runs them and
``health`` says how each one is doing."""
