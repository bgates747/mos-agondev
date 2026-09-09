# Controlled UART1 emulator peer

`scripts/prepare_uart_peer.py` builds an isolated Fab 1.2.3 source copy for
controlled UART1 byte tests. Invoke it with `--help` for required reference,
output and host-library arguments. It requires the exact reviewed reference
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
and constant CTS-ready, not baud, FIFO overflow, RTS timing or physical peer
qualification. Product packet semantics and assertions belong to the consumer.

Remove the receive-interrupt workaround when the selected official runtime
implements it; retire the socket/CTS adaptation when a supported equivalent
provides the controlled tests. [TEST-001](tasks/TEST-001.md) retains the original
review and validation history.
