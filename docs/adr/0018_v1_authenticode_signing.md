# ADR 0018: v1.0.0 Authenticode signing policy

Status: Accepted as a fail-closed release gate policy

## Decision

Windows executable release artifacts must be Authenticode signed before public release. The required executable artifacts are `dist/ygo-effect-dsl.exe` and `dist/ygo-effect-dsl-desktop.exe`; the portable ZIP is release eligible only when the executable payloads inside it have valid signatures and the ZIP checksum is linked to the same build provenance.

Release verification must use `Get-AuthenticodeSignature` or an equivalent Windows trust verifier, must record the signer subject, certificate thumbprint, SHA-256 checksum, verification command, commit, workflow run URL, and timestamp status for each signed executable, and must reject unsigned or tampered artifacts.

## Signer Identity

The signer identity must match the release approval record. The certificate must have code signing extended key usage, a recorded certificate thumbprint, and an explicit approval trail before it can satisfy the v1.0.0 production distribution gate.

The repository, runtime artifacts, normal CI logs, and package contents must not store signing credentials. Signing material may be provided through GitHub Actions secrets or an approved external signing service. The project must not store signing credentials in source control or package output.

## Timestamp Policy

Every signed executable must carry an RFC 3161 timestamp from a release-approved timestamp authority. A valid signature without a valid timestamp is not enough for v1.0.0 public release because certificate expiry or revocation would make post-release verification ambiguous.

## Failure Cases

Unsigned artifacts must be rejected as not release eligible. Tampered artifacts must be rejected after signature verification or checksum comparison. A signed executable whose SHA-256 checksum is not linked to the same commit and workflow run as the portable ZIP is also not release eligible.

## Current Release State

The current CI path intentionally records unsigned Authenticode verification output for the built executables and marks those artifacts as not release eligible. This proves the verifier is fail-closed without introducing repository signing credentials. The production distribution gate remains blocked until signed artifact evidence with valid timestamp and checksum provenance exists.
