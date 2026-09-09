# TEST-001 — Isolated Fab UART1 test peer

Status: complete; Author accepted graphical review and authorized source freeze.

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
