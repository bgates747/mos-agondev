# TEST-001 — Isolated Fab UART1 test peer

Status: Complete; runtime adaptation and output-identical host-library portability correction verified.

Fab 1.2.3 (`fbb7d7ca887a06966ca8a62ed22272409a5ab640`) emulates UART1
registers but omits its receive interrupt from `AgonMachine::do_interrupts`.
Its CLI provides no UART1 peer; its graphical serial-device adapter depends
on host modem-control ioctls, which a Unix pseudo-terminal cannot supply.

This bounded test dependency copies tracked reference sources to a new output
directory, applies checked local adaptations and builds a separate runtime.
The reference checkout and the author's independently developed Fab fork remain
untouched. No change to production MOS or guest memory supplies test packets.

1. [x] Raise UART1 RX interrupt 0x1a only when IER permits it and a byte is pending.
2. [x] Add an explicit Unix-socket byte peer to both frontends. Retain ordinary
   UART behavior when the option is absent; connection failure must not fall back.
3. [x] Record reference, adaptations and executable hashes. Exercise real
   resident UART1 code using the consuming project's fixture and run existing
   ordinary boot/absent-peer checks. Obtain human emulator review before commit.

This peer supplies bytes and constant CTS-ready, not electrical timing, FIFO
overflow or RTS backpressure qualification. P4/browser and hardware evidence
remain owned by the consumer. Remove the interrupt adaptation when the selected
official runtime implements it; remove the peer adaptation when a supported
equivalent permits the same controlled tests.


The graphical frontend also initializes Port C high for its joystick inputs.
Its inherited GPIO read ORs in UART CTS, so a ready serial peer cannot lower
PC3. The explicit test peer now owns that input bit while the guest configures
it as input. Other serial adapters, absent-peer and joystick behavior remain
unchanged. This is a model of the test peer driving CTS, not guest register
injection or an EMOS bypass of its CTS check.

Validation includes paired CLI target behavior, stock/EMOS ordinary SD/clock
boot, absent-peer admission timeout and a missing socket exiting with status 2
instead of silent fallback. Target fixtures and expectations remain in EMOS.
The adapter and generated executable hashes are recorded with each runtime.
Physical flow control is not inferred from the constant-ready peer.

The final paired graphical execution passes all eleven EMOS fixture stages
and returns to the mainboard MOS prompt with the same firmware as the CLI.
The Author subsequently accepted the graphical result and authorized its source
freeze. The checked reference adaptation does not alter guest firmware.

Recurring usage and limits are maintained in [UART peer emulator](../uart-peer-emulator.md).

## Host-library portability correction

The next consumer firmware qualification found that the helper assumed a
home-relative host-library directory, violating the repository's existing
portable-path check. No firmware or UART behavior failed. Keep that check
unchanged: expose an optional `--library-dir PATH` instead, inheriting the
caller environment when omitted. Record the selected directory only in the
generated machine-local runtime manifest.

1. [x] Pass the existing generic test suite with the portability guard intact.
2. [x] Rebuild the isolated runtime with the prior host-library selection,
   compare generated runtime source and execute the consuming paired fixture.
3. [x] Verify that prior Author graphical evidence applies to the resulting
   runtime before freezing the correction. Every generated source, Cargo lock
   and both executable hashes match the previously reviewed runtime exactly.
   The Author authorized freezing and continuing the consuming hardware-test
   preparation. No new emulator behavior is introduced.

All 134 generic tests pass with the portability guard unchanged. Rebuilding with the explicit prior library directory produces no changed runtime-file hashes. The generated manifest records the new helper hash and explicit directory; old manifests are preserved. The existing consuming graphical PASS therefore tests the exact resulting runtime executables.

## Large-upload socket backpressure — 2026-09-11

The Extender graphics timing consumer exposed a local adapter defect: the
nonblocking Unix socket filled while its native VDP peer processed a bitmap,
and `write_all` exited the emulator with status 2 on `WouldBlock`. The guest
firmware did not crash. The earlier constant-ready adapter cannot qualify this
larger workload.

The maintained generator now retains a bounded sixteen-byte pending queue and
withdraws its modeled CTS until the host socket drains. It preserves ordered
bytes, fails explicit peer disconnects/overflow, and never blocks the guest
CPU. No official emulator source is edited. The generated Rust unit test fills
a real Unix socket, verifies CTS withdrawal, then drains and compares every
byte before checking reverse delivery. That test passes. Consuming paired
graphics and Author visual review remain required before source freeze.

The consuming paired graphics review completed 256 intervals and 17 independent
presentation checks. All 135 generic tests pass. On 2026-09-11 the Author
supplied the completed graphical screen and MOS prompt and authorized hardware
deployment, accepting this runtime correction for source freeze. One later
bounded native completion timeout remains recorded by the consumer; it is not
silently retried or classified as a physical-board defect.
