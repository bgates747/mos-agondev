# Native MOS foundation validation

The source and shared build helpers now have reproducible local commits. The
native ROM still matches its stock AgonDev control exactly, and bounded
headless boot, shell and two-cold-boot API comparisons pass against official
MOS. Human graphical shell checks passed, but the initial API review failed
because of incorrect staging/instructions and a same-boot failure shared with
official MOS. Corrected file/persistence checks pass unattended on both images;
the Author need not repeat them manually. Physical
qualification and downstream adoption remain open; no firmware was installed
on hardware.

## Candidate inputs and publication

1. Source mechanical conversion: `a5fa859367998b05a8e4d17364d18d6b12b9607c`.
2. Readable native source/direct build: `92662538a5766ae1e3d5b47e7dd78829a4dfe1c5`.
3. Shared helper/policy promotion: `6cbaf08b7dc4155a1428a83ad9dcb99ae8cbf847`.
4. Infrastructure path-only correction: `7b584ae`; source, compiler, runtime
   and helper code are unchanged by that follow-up.

These commits are local. Private GitHub source main still contains official
history only; this tranche did not push or create a qualified release tag.
Oryx received verified local Git bundles and separate generated artifacts, not
an unrecorded overlay of another owner's working checkout. The source tree was
clean at the measured build; its receipt identifies the exact native commit.

The selected toolchain/runtime is unchanged from the
[first tranche](build-005-2026-10-15.md): Clang 15.0.7, LLVM
`c76386c0083e6a6236ff774275227e2389f85538`, Binutils 2.45 and the pinned
restricted runtime. No UART addition, qsort API experiment, EMOS change,
post-release VDP fix or API-001 implementation entered this stock control.

## Offline and linked-byte evidence

The fresh root baseline-check passed at 102,055 bytes / SHA-256
`f891721bbb2a0bc2845dbb13edbeb449365a315f11be48500d8e65e2ab1aebb4`.
All 512 defined public symbols and all 16 C object files match the previous
translated stock control. All consumed input hashes remain unchanged, with
35 target-step provenance records. Runtime closure, formatter golden checks,
i48 helper equivalence and linker/image guards pass through the normal helper.

Actual linked handshake structure and legal packet framing pass. The inherited
stock oversized-packet stale-length defect reproduces as an explicit negative
control. It is not relabeled corrected or silently fixed to pass a newer
candidate's regression suite. A later behavior correction needs separate scope.

The full infrastructure unit discovery ran 154 tests: one known backward-JR
objdump display failure remains, and the optional pinned-Fab UART-model class
was skipped. The native migration/profile/comparison tests are included in that
run. Six native-source checks pass on both Pi and Oryx. Three generated-launcher
tests pass with a harmless stub: managed selection, forbidden overrides and
changed MOS/map/runtime/VDP/startup inputs. No GUI was started for those tests.

The initial full run also caught stale path coordinates in guidance, a disposed
task and a portable evidence export. These were corrected without weakening
the test. The original frozen first-tranche summary remains byte-identical at
SHA-256 `e968118001cc48ff49ff51e68af0b64447612bd389b5a7b84f8bad571506dc58`;
the repository export explicitly records its path-coordinate normalization.

## Headless runtime and review fixture

Oryx has a dedicated project-local Fab 1.2.5 checkout at official commit
`c22876d1f7ad903537c308cf65afd6553b37cdb8`, with pinned submodules. It was
built through the upstream top-level Makefile; existing peer runtimes and
reference checkouts were not modified. Its locally built stock Platform VDP
and host SDL are pinned in the review profile. Dynamic-library resolution was
checked without starting a graphical emulator.

Passing headless checks use the actual native image and official v3.0.2
reference (`d564243283972690933a4554296ad6202ca4ef54572279533a942960846bebae`):

1. Boot banner, directory-backed hostfs and a directory command.
2. Matching safe-shell transcript, including command help, variables, nested
   paths/file contents and intentional invalid-command/path handling.
3. A freshly built formatter/C/RST API probe, including the existing SDK wrapper
   fixes, 32-bit sparse-file operations and two-cold-boot write persistence.
   Candidate and reference each pass create/verify and restore the fixture;
   normalized contract output agrees.

The CLI uses a fake VDP and does not establish physical UART timing, baud/CTS
reserve or graphical native-VDP behavior. The latter remains the human gate in
[the source-owned review instructions](../../agon-mos-agondev/docs/qualification.md).
The generated wrapper is a real executable, its raw runtime is a separate
`.bin` link, and MOS/map/runtime/VDP/SDL/startup identities fail closed. The
original manual API fixture was staged at guest `/native-api`; that layout was
subsequently found invalid for this probe, as recorded below. No containing
project tree is mapped back into its nested SD overlay. The agent never starts
the graphical profile.

## Initial human review failure and corrected fixture

The Author's screenshots confirm the selected candidate identity, Fab 1.2.5,
stock Platform VDP 2.16.0, help, directory listing and fixture-file reading.
They also report genuine API failures, so the human review is not accepted.

1. The probe hard-codes `/seek.txt`, `/lines.txt`, `/nested/alpha.txt` and other
   root paths, and expects the current directory to be `/`. Staging its files
   under `/native-api` and instructing `cd native-api` was a preparation error.
   It explains the observed path/directory/file failures without changing MOS.
2. The second same-boot invocation reports `api-extractnumber-u24-output`.
   Headless replay from a correct root reproduces first-run PASS / second-run
   failure under both official and native MOS, with byte-identical matched
   outputs. Both normal and zero-initialized RAM, with and without `.bin` in
   command names, show the same result. The root cause is not proven; the
   scratchpad-state lead and exact reproducer are retained as
   `MOS-EXTRACTNUMBER-001` in [upstream findings](../docs/upstream-findings.md).
3. The original automatic API test used separate cold boots. Asking the Author
   to run twice in one boot unintentionally broadened that test. The corrected
   manual test uses a fresh root fixture and one invocation per cold boot;
   it does not fix or waive the repeated-run finding.

The new stopped profile is `.emulator/contract-review-20261016/` in the native
Oryx checkout, generated through the same pinned canonical setup snapshot. It
has its own wrapper, root SD tree and input manifest, using the unchanged MOS,
probe, official runtime and stock native VDP. The generated default tool-tree
is retained outside its guest SD mount to keep directory enumeration bounded.
The original failed profile and its user-created persistence file are preserved.

Four fresh CLI cold boots against the **actual corrected SD tree** pass:
native CREATE/VERIFY and official CREATE/VERIFY. Each pair restores the exact
initial snapshot; normalized transcripts match and all 13 launch input hashes
verify. This check took 10.19 s including SSH/command setup. Three launcher
guard tests use a harmless stub, not the GUI. The corrected graphical review
is not claimed for this new diagnostic profile. File testing is agent-run,
as directed below; explicit acceptance is still required before commit/push.

Additional durable evidence in the existing validation workspace:
`diagnose_manual_probe.py`, `manual-probe-diagnostics-20261016.json`,
`stage_contract_review.py`, `corrected-contract-profile.json`,
`check_contract_review.py` and `corrected-contract-cold-boots-20261016/`.
Raw replay logs remain under the Oryx profile's
`manual-probe-diagnostics-20261016/`; the matrix has 16 cases, with eight
root-fixture cases providing the repeated-run comparison. The nested CLI cases
also expose command-feeding limitations and are not counted as passing probes.
The initial validation summary/inventory remain unchanged as historical cuts.

## Unattended file test result

The Author directed the agent to test the files instead of requiring a manual
probe/reboot protocol. The fresh unattended run passes native CREATE/VERIFY and
official CREATE/VERIFY in 10.22 s including SSH/command setup. It covers reads,
writes, copy, rename, delete, directory operations, large-file seek/tell and
exact payload persistence. Each firmware pair restores the initial fixture;
matched transcripts are identical and all 13 launch inputs verify. No graphical
emulator was started, firmware changed, or manual API rerun requested.

Latest result/logs: `../worktrees/mos-build-005-validation/unattended-file-checks-20261016/`;
command receipt: `../worktrees/mos-build-005-validation/unattended-file-checks-command/`.
The same outputs remain under the native Oryx checkout's
`.emulator/unattended-file-checks-20261016/`. The repeated same-boot
number-extraction failure remains separately recorded, not relabeled fixed.

## Evidence location and durations

Persistent scripts, complete command outputs, failed diagnostic attempts,
comparison JSON, target artifacts and returned Oryx records are under
`../worktrees/mos-build-005-validation/`, relative to this project root.
The source keeps its fresh build under `.build/validation-20261016/`; Oryx
keeps its profile under the source root's ignored `.emulator/`.
Portable summary: `evidence/build-005-validation-summary.json`.

Recorded host command durations: native build/check 12.42 s; Oryx official
runtime build 58.78 s; complete headless qualification 72.50 s, dominated by
the two approximately 30 s shell transcripts. Individual boot/API runs were
about 2.1–2.5 s. The probe build took 0.29 s. These are monotonic command
durations, not target CPU-cycle measurements or calibrated cross-machine timing.
Setup, transport and individual steps remain separate in receipts.

## Review boundary

B005-06 now has additional offline/runtime evidence, but human/physical gaps
remain. B005-07 has immutable candidate inputs, not an accepted qualified
handoff. The selected first-pass B005-09 helpers are committed; further tool
selection and the review fixture's promotion remain open. B005-08 EMOS adoption
and B005-10 final downstream workflow transition were not performed.

Qualification documents, evidence and emulator-coupled work remain uncommitted
pending the Author's human review and explicit commit approval. No hardware,
bench service, installed firmware, EMOS/UART source, API allocation or production
release was changed. API-001 remains a later coordinated implementation task.
