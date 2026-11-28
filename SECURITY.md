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
  data model. A span's error message is stored in the incident and returned
  by alerts and the API without redaction. Evals and the judge never get it.
- The API needs a bearer token and does not start without one. It is bound
  to `127.0.0.1` by default. Use TLS in front of it.
- The databases have no network authentication, and the OTLP receiver has
  none unless you turn on the bearer token (always on in Kubernetes). The
  Compose file binds their ports to `127.0.0.1`. Do not expose them. The token
  is sent in clear text unless TLS protects the connection.
- Webhook URLs and API keys are secrets. Rolda reads them from the
  environment and does not log them.

Known limitations are listed in [docs/STATUS.md](docs/STATUS.md).

## Supply chain hardening

- CI has no secrets, runs with read-only permissions and uses no
  `pull_request_target` or `workflow_run` trigger. Actions are pinned to
  full commit SHAs, and GitHub enforces that.
- Python dependencies are locked with hashes (`uv.lock`) and installed with
  `--locked`. Container images are pinned by digest.
- CI runs `zizmor` on the workflows and `pip-audit` on the locked
  dependencies. A weekly job repeats the audit.
- Dependabot proposes updates with a 7 day cooldown, so a freshly published
  release is not adopted at once.
- Maintainers use two-factor authentication and short-lived, narrowly
  scoped tokens.

## If you suspect a compromise

The wfx-loot campaign of November 2026 used stolen account tokens to push
secret-stealing workflows. If something similar happens here:

1. Look for unexpected branches (for example `wfx-docs`), pull requests,
   workflow files and workflow runs, and for gaps in run numbers.
2. Revoke the personal access tokens, SSH keys and OAuth apps of every
   account that could write to the repository, then rotate any secret those
   workflows could reach. This project keeps no secrets in CI.
3. Check cloud trust policies and federated credentials, not only keys.
4. Report it through the private channel described above.
