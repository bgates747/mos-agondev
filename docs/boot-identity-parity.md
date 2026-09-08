# BUILD-001 — Explicit product boot identity in shell parity

Status: complete and accepted, 2026-09-07. Automated checks and the Author's
graphical emulator review pass; the Author explicitly authorized the checkpoint
commit alongside EMOS QUAL-002.

An ordinary MOS derivative may print its identity immediately after the MOS
lineage banner. The source profile can now set `PARITY_EXPECTED_BOOT_LINE`;
the root gate passes it as the comparator's `--expected-boot-line` argument.
The value must be a single shell-safe literal line (no single quotes).

The comparator requires that exact line at normalized position 1 and exactly
once in the candidate, absent from the stock reference. It then compares the
remaining transcript unchanged, including all existing command, HELP, state
and filesystem checks. With the option unset, the strict stock comparison is
unchanged. Generic tools contain no EMOS identity or product vocabulary.

Validation: 11 focused comparator tests, including missing, changed, repeated,
misplaced and unsolicited output; the complete configured EMOS build gate
also exercises the real candidate/reference transcripts. The passing generic
suite now has 133 tests. Firmware, profiles and graphical review belong to
the source owner's [QUAL-002](../../agon-emos/docs/tasks/QUAL-002.md).

The Author's 2026-09-07 screenshot shows the exact reviewed EMOS identity,
passing ordinary smoke and prompt return. It closes the graphical behavior
check. The Author subsequently accepted that pass and authorized the checkpoint
commit. Physical deployment remains outside this generic build change.
