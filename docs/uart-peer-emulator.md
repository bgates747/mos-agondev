# Controlled UART1 emulator peer

`scripts/prepare_uart_peer.py` builds an isolated Fab 1.2.3 source copy for
controlled UART1 byte tests. Invoke it with `--help` for required reference,
and output arguments. Use `--library-dir PATH` for non-system host libraries;
otherwise the caller's existing build environment is inherited. The helper
does not infer a library location from the user's home directory.
It requires the exact reviewed reference
commit `fbb7d7ca887a06966ca8a62ed22272409a5ab640` and a new output directory.
The reference checkout is read-only. The output manifest records adapter,
adapted sources, resolved Cargo lock and executable hashes.

The generated CLI and graphical runtimes accept `--uart1-peer SOCKET`.
A consuming test harness supplies a listening Unix stream socket and sends
ordinary UART bytes. Connection failure is fatal; there is no fallback peer.
Without this explicit option, existing frontend serial behavior is retained.
Graphical profiles must still use the canonical generated local launcher;
this runtime does not waive profile verification or human review.

The adaptation adds the missing UART1 receive interrupt and gives the explicit
peer control of PC3 CTS when the guest configures that pin as an input. This
avoids the graphical joystick-high input masking a ready peer. It preserves
the guest ISR, driver, parser and firmware effects. It supplies ordered bytes
and CTS backpressure when its nonblocking host socket fills, not baud, real
UART FIFO overflow, RTS timing or physical peer
qualification. Product packet semantics and assertions belong to the consumer.

The peer retains at most sixteen pending transmit bytes, retries on socket
read/CTS activity, and withdraws CTS until those bytes drain. It never blocks
the guest CPU waiting for host I/O or discards a byte on `WouldBlock`. A guest
which ignores CTS and exhausts this bound fails explicitly. This corrects the
earlier adapter's process exit on large graphics uploads; it is test transport
behavior, not a production UART or renderer change.

Remove the receive-interrupt workaround when the selected official runtime
implements it; retire the socket/CTS adaptation when a supported equivalent
provides the controlled tests. [TEST-001](tasks/TEST-001.md) retains the original
review and validation history.

## Optional UART1 transmit interrupts

Pass `--uart1-tx-interrupts` only when the consumer explicitly requires and
records this model. The default adapted source remains byte-identical to the
reviewed RX-only generator. For a new isolated output, with `FAB_ROOT` already
set to the pinned reference:

```bash
.venv/bin/python scripts/prepare_uart_peer.py \
  --fab-root "$FAB_ROOT" --output .emulator/uart-peer-txirq \
  --uart1-tx-interrupts
```

Add `--library-dir PATH` when this host requires non-system SDL libraries.
Rust/Cargo and the reference runtime's host build dependencies are required.
The consumer must then use its canonical profile generator with this runtime,
pin `runtime-inputs.json` and the executable, and launch via that profile's
`./fab-agon-emulator` wrapper. Never patch the generated sources or run the
raw linked executable as a substitute for the generated profile entry point.

This option binds UART1 interrupt vector0x1A and IIR reads to actual enabled
RX/TX state. RX-ready outranks transmit-complete, which outranks holding/FIFO-
empty. Completion additionally requires the inherited shift-register cooldown
to be zero. IIR reports active-low pending and FIFO status bits without
clearing IER enable bits. THR writes and IER masking change transmit demand.
The definitions follow eZ80F92/F93 PS015317-0120, pp105–107 and113–115.

UART0, byte cooldown arithmetic, FIFO capacities and host-socket CTS remain
unchanged. This is still not a full peripheral model: error/timeout/modem
interrupts, FIFO reset semantics, all operating modes, electrical framing,
physical baud and RTS timing are outside this correction. Independent tests
compile the adapted Rust UART and exercise the register/FIFO transitions;
consumer packet semantics and physical qualification remain elsewhere.

The manifest records `uart1_tx_interrupts` and adapter/source/executable hashes.
Consumers should reject a mismatch between the selected fixture and that
manifest, and preserve earlier RX-only failures as separate evidence. The
Extender consumer's passing fixed integration is summarized in
[TEST-002](tasks/TEST-002.md). It is not evidence that a physical game sped up.
Human emulator validation and explicit commit approval remain open.
