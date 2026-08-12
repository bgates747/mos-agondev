# Authoritative TODO

This is the project's only actionable task list. IDs are stable; completed,
rejected, or superseded work is recorded in the current development log and
removed from this file.

## Parity and release evidence

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
- [ ] **PORT-207** — Perform a whole-project prior-art audit of
  [`tomm/rainbow-mos`](https://github.com/tomm/rainbow-mos), pinned to the
  reviewed commit. Compare its lineage and supported MOS version; direct
  GNU/AgonDev source-port strategy; assembly dialect changes; startup and
  linker layout; compiler flags and `ff.c` register-allocation workaround;
  libc, formatter, and runtime selection; API and ABI choices; RAM/ROM size and
  performance work; emulator/hardware evidence; and maintenance tradeoffs with
  this project's corpus-preserving MOS 3 frontend. Record which techniques are
  already shared, worth adopting, unsuitable, or require follow-up tests, and
  add durable credit and license attribution before incorporating any code.
