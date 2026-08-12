# Authoritative TODO

This is the project's only actionable task list. IDs are stable; completed,
rejected, or superseded work is recorded in the current development log and
removed from this file.

## Parity and release evidence

- [ ] **PORT-206** — Compare the AgonDev firmware with the most recent official
  upstream MOS release at the binary and instruction levels, then turn
  unexplained differences into focused regression evidence. The analysis must
  be automation-first and reproducible: scripts, not manual whole-image review,
  must perform artifact inventory, map/disassembly parsing, symbol pairing,
  address normalization, range classification, and report generation. Each
  automated conclusion must retain its evidence and a confidence/reason code;
  uncertain cases must fail closed into a bounded manual-review queue rather
  than being silently treated as equivalent. This task must:
  1. identify the newest published release rather than assuming upstream
     `HEAD`, record its tag/version, Platform/Console8 variant, source commit,
     ZDS II build version and options when discoverable, and pin the exact
     `MOS.bin` plus every matching map, listing, symbol, or debug artifact;
  2. retain an equivalently inspectable AgonDev build: ELF, binary, GNU map,
     symbols, relocations, per-object and linked disassembly, generated GNU-as
     units, and compiler-emitted assembly for the C translation units;
  3. disassemble the ZDS image as eZ80 ADL and recover function/data boundaries
     from its matching artifacts where available, otherwise using vectors, API
     tables, strings, constants, source patterns, and reviewed anchors;
  4. build a reproducible symbol/function correspondence and normalize expected
     address noise, including absolute pointers, PC-relative displacements,
     section or function ordering, padding, and alignment, without masking
     changed constants, layouts, control flow, or instruction semantics;
  5. classify ranges as exact, relocation-only, reordered, semantically
     equivalent code generation, explained source/release divergence, or
     genuinely unexplained, retaining machine-readable results and a durable
     human report; require deterministic reruns and regression fixtures for the
     parsers and normalizers; and
  6. promote useful findings into exact tests for handwritten assembly, fixed
     vectors/tables, startup and interrupt behavior, ABI-sensitive C paths,
     linker layout, and any unexplained behavioral difference. Raw whole-image
     equality is evidence where achievable, not a blanket success criterion
     across different C compilers.
  Establishing the official public reference and its provenance contributes to
  PORT-205. The resulting difference inventory should guide the next PORT-201
  and PORT-202 expansions before broad, untargeted parity work. Manual
  disassembly review should be limited to the script-produced uncertain or
  unexplained queue and should feed new classification rules or regression
  tests whenever the result can be generalized safely.
- [ ] **PORT-201** — Extend emulator parity beyond the accepted boot, shell,
  graphical keyboard/editor, blocking VDP general-poll handshake, and
  oversized-packet regressions to broader VDP packets and timing, writable FatFS,
  RTC mutation/persistence, and UART error/timing behavior; compare with a
  same-source ZDS reference image where possible.
- [ ] **PORT-202** — Complete the exported MOS C/assembly ABI matrix beyond the
  bounded 42-wrapper target contract probe: cover remaining public entry
  points, high-byte return widening, callbacks, and write/hardware paths, and
  characterize the candidate-only `mos_extractnumber` sensitivity seen when
  its otherwise-passing call was embedded in the probe's large stack frame.
  Every maintained `printf`/`sprintf` spelling already has host and target
  boundary evidence.
- [ ] **PORT-203** — After emulator parity, define recovery procedures and run
  staged physical-hardware validation before treating the port as releasable.
- [ ] **PORT-204** — Coordinate upstream fixes for the three pinned AgonDev
  libmos wrapper defects and Fab's 24-bit hostfs object-size write recorded in
  `docs/upstream-findings.md`; upgrade the affected pins, remove local wrapper
  shims, and rerun the ABI/large-file regressions.
- [ ] **PORT-205** — Make every frozen-study input publicly reproducible:
  publish or upstream the recorded `agon-mos` VDP-discard commit, and publish
  the exact path-dependent Fab artifacts or replace their byte hashes with a
  transparent reproducible-artifact policy. Then rerun `make baseline-check`
  from only documented public inputs.
