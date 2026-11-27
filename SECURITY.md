# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Report it privately through GitHub: open the **Security** tab of this
repository and choose **Report a vulnerability**. Include what you found,
how to reproduce it and what you think the impact is.

You will get an acknowledgement within a few days. Rolda is pre-release and
maintained by a small team, so fixes are made on a best-effort basis, and
we will tell you what we plan to do.

## Supported versions

Only the latest commit on `main` is supported. There is no stable release
yet.

## Security model

- Trace content is untrusted. It can contain prompt injection and hostile
  text. Rolda stores and returns it as data, never runs it, and gives it to
  the judge only inside delimited blocks, with a validated answer.
- Prompt and response capture is off by default and is not part of the
  data model.
- The API needs a bearer token and does not start without one. It is bound
  to `127.0.0.1` by default. Use TLS in front of it.
- The OTLP receiver and the databases have no network authentication. The
  Compose file binds their ports to `127.0.0.1`. Do not expose them.
- Webhook URLs and API keys are secrets. Rolda reads them from the
  environment and does not log them.

Known limitations are listed in [docs/STATUS.md](docs/STATUS.md).
