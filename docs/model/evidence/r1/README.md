# Historical R1 evidence

These logs and counts describe the R1 model and sources listed in
[REPORT-before-r2.md](../r2/REPORT-before-r2.md). They do not prove current
release-order safety: R2 found that R1 discharged hold obligations with the
implementation's own clamped timestamp key.

R1's source snapshots, raw logs, commands, model hashes and historical report
remain unchanged. The R1 environment/policy/config bytes formerly at the top
level are preserved in `../r2/*-before-r2.*`. `PreFixControl.tla` at the top
level is also historical R1 source and is unchanged. It must be paired with
`ControlEnvironment-before-r2.tla.txt`, renamed `ControlEnvironment.tla` in a
separate scratch directory, and the historical config. The old R1 runner copied
then-current top-level files; running that runner against R2 top-level files
would not reproduce the old proof. No historical check was rerun in R2.

The earlier reconciliation and `historical/` proofs were already historical;
R2 does not promote any of their claims to current safety evidence.
