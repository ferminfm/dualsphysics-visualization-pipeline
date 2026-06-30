# Human Decision Checklist

Before any public visibility change:

- [ ] Review the draft PR diff: https://github.com/ferminfm/visualbasilisk/pull/1
- [ ] Confirm `PUBLIC_VISIBILITY_GATE_REPORT.md` is acceptable.
- [ ] Confirm the repository should become public, remain private, or receive another hardening pass.
- [ ] Confirm no private local paths or generated solver artifacts are present.
- [ ] Confirm synthetic-only fixture policy remains acceptable.
- [ ] Confirm public wording does not imply validation, production CFD,
      atomisation prediction, pressure-nozzle modeling, fit readiness, or public readiness.
- [ ] If making public, issue a separate explicit command for repository visibility change.
- [ ] Do not deploy the site or publish a release from this gate.
