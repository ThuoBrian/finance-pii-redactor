# Security policy

This tool handles personal data, so a redaction that misses something counts
as a security issue, not just a bug.

## What to report

- A name, ID, or bank or payment detail that stays readable in a redacted file
  when it should have been replaced.
- A way for a redacted file to reveal the original, for example through
  metadata, hidden text, or an embedded object.
- Real personal data committed anywhere in this repository or its history.
- Any vulnerability in the app or its dependencies.

## How to report

**Don't open a public issue, and don't attach real documents or real names.**
Describe the problem with made-up data, or send a file that reproduces it with
invented content.

Email the maintainer at bthuo@poverty-action.org. If you work at
IPA and the report involves real data being exposed, also contact
support@poverty-action.org.

## Supported versions

Only the latest commit on `main` is supported. Fixes are not backported.
