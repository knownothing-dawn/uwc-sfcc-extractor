# Security policy

## Supported versions

Security fixes are applied to the latest published release candidate or stable
release. Older versions may not receive backports.

## Reporting a vulnerability

Do not open a public issue containing an undisclosed vulnerability, a private
paper, credentials, or personal data.

Use GitHub's private vulnerability reporting feature from the repository's
Security page. Repository maintainers should enable that feature immediately
after publishing the repository. Include the affected version, impact, minimal
reproduction and any suggested mitigation.

For ordinary correctness problems that do not expose data or create a security
boundary failure, use the public bug-report form.

This project processes untrusted PDFs and writes local files. Run it with the
least filesystem access needed for the current paper and review output paths
before use in automated environments.
