# Security Policy

## Supported versions

Cascade is a portfolio project. Security fixes land on `main` and in the most
recent tagged release.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's
[private vulnerability reporting](https://github.com/Talif787/cascade/security/advisories/new)
rather than opening a public issue. Include a description, reproduction steps,
and the affected version or commit. Expect an acknowledgement within a few days.

## Supply-chain guarantees

Release images are built, pushed, and signed by the `release` workflow on every
`v*` tag:

- Images are signed keyless with cosign using GitHub OIDC (no long-lived keys).
- A CycloneDX/SPDX SBOM is generated with syft and attached as a cosign attestation.
- Build provenance is attached via the builder's SLSA provenance output.
- Images are scanned with Trivy for CRITICAL and HIGH findings.

Verify a release image before deploying:

```bash
cosign verify \
  --certificate-identity-regexp "https://github.com/Talif787/cascade/.github/workflows/release.yml@.*" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/talif787/cascade@sha256:<digest>
```

## Runtime hardening

The container runs as a non-root user with a read-only root filesystem, all
Linux capabilities dropped, no privilege escalation, and the RuntimeDefault
seccomp profile. The Helm chart adds a default-deny NetworkPolicy, a
PodDisruptionBudget, and disables service-account token automounting.
