#!/usr/bin/env python3
"""Build an isolated Fab 1.2.3 UART1 test runtime; never edit the reference.

TEST-001: upstream has UART1 registers but omits its RX interrupt. The explicit
socket peer models ordered bytes and host-socket CTS backpressure only. It is not a hardware UART
or timing qualification. Delete these adaptations once upstream provides both.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

REFERENCE = 'fbb7d7ca887a06966ca8a62ed22272409a5ab640'
PEER = r'''// Generated TEST-001 byte peer. See prepare_uart_peer.py for scope.
use agon_ez80_emulator::SerialLink;
use std::io::{Read, Write, ErrorKind};
use std::os::unix::net::UnixStream;
use std::collections::VecDeque;
pub struct Peer { socket: UnixStream, pending: VecDeque<u8> }
fn fail(message: &str, error: impl std::fmt::Debug) -> ! {
    eprintln!("{}: {:?}", message, error);
    std::process::exit(2); // A worker-thread panic could leave the UI alive.
}
pub fn connect(path: Option<&str>) -> Option<Box<dyn SerialLink>> {
    path.map(|path| {
        let socket = UnixStream::connect(path).unwrap_or_else(|e| fail("UART1 test peer connection failed", e));
        socket.set_nonblocking(true).unwrap_or_else(|e| fail("UART1 test peer nonblocking setup failed", e));
        eprintln!("TEST UART1 byte peer active (host backpressure; no physical timing proof)");
        Box::new(Peer { socket, pending: VecDeque::with_capacity(16) }) as Box<dyn SerialLink>
    })
}
impl Peer {
    // A nonblocking socket can fill while the consumer processes an upload.
    // Retain at most sixteen in-flight bytes and withdraw CTS until drained.
    // Never block the guest CPU or discard/reorder a byte on WouldBlock.
    fn flush(&mut self) {
        while let Some(byte) = self.pending.front().copied() {
            match self.socket.write(&[byte]) {
                Ok(1) => { self.pending.pop_front(); }
                Err(e) if e.kind() == ErrorKind::WouldBlock => return,
                Err(e) if e.kind() == ErrorKind::Interrupted => continue,
                other => fail("UART1 test peer write failed", other),
            }
        }
    }
}
impl SerialLink for Peer {
    fn send(&mut self, byte: u8) {
        self.flush();
        if self.pending.len() == 16 { fail("UART1 test peer overflow: guest ignored CTS", self.pending.len()); }
        self.pending.push_back(byte);
        self.flush();
    }
    fn recv(&mut self) -> Option<u8> {
        self.flush();
        let mut byte = [0];
        match self.socket.read(&mut byte) {
            Ok(1) => Some(byte[0]),
            Err(e) if e.kind() == ErrorKind::WouldBlock || e.kind() == ErrorKind::Interrupted => None,
            other => fail("UART1 test peer disconnected or failed", other),
        }
    }
    fn read_clear_to_send(&mut self) -> bool { self.flush(); self.pending.is_empty() }
    fn owns_cts_pin(&self) -> bool { true }
}
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


UART1_IRQ_METHOD = '''
// TEST-002 optional UART1 status/demand binding; PS015317-0120 pp105-115.
// Keep the inherited byte-clock/FIFO implementation. UART0 never calls this
// method. IIR is read-only: reading it must not erase an IER enable bit.
// RX errors/timeouts and modem edges are not represented by this model.
impl Uart {
    pub fn uart1_interrupt_identification(&self) -> u8 {
        let fifo_status = if self.fctl & FCTL_FIFOEN != 0 { 0xc0 } else { 0 };
        let source = if self.ier & 1 != 0 && self.rx_buf.is_some() {
            0x04 // receiver-ready has higher priority than either transmitter
        } else if self.ier & 0x10 != 0 && self.tx_fifo.is_empty() && self.transmit_cooldown == 0 {
            0x0a // complete: both holding FIFO and shift register are empty
        } else if self.ier & 2 != 0 && self.tx_fifo.is_empty() {
            0x02 // holding-empty may be true while the final byte is shifting
        } else {
            0x01 // active-low interrupt status: no enabled source
        };
        fifo_status | source
    }
}
'''


def adapt(root, uart1_tx_interrupts=False):
    def replace(file, old, new):
        path = root / file
        source = path.read_text()
        if source.count(old) != 1:
            raise ValueError('Reference drift at '+file+': '+old[:70])
        path.write_text(source.replace(old, new))

    replace('agon-ez80-emulator/src/agon_machine.rs',
            '            if self.i2c.is_interrupt_due() {',
            '''            // TEST-001: the upstream model omits UART1 RX interrupts.
            if self.uart1.is_rx_interrupt_enabled() && self.uart1.rx_byte_ready() {
                Environment::new(&mut cpu.state, self).interrupt(0x1a);
                return;
            }

            if self.i2c.is_interrupt_due() {''')
    # Graphical Fab initializes every Port C input high for its joysticks.
    # Upstream ORs CTS into that input, so an active serial peer cannot pull
    # PC3 low. Only this explicit peer owns PC3; absent-peer/joystick behavior
    # is unchanged. Respect a guest-configured output rather than hiding it.
    replace('agon-ez80-emulator/src/uart.rs',
            '    fn read_clear_to_send(&mut self) -> bool;',
            '    fn read_clear_to_send(&mut self) -> bool;\n'
            '    fn owns_cts_pin(&self) -> bool { false }')
    replace('agon-ez80-emulator/src/uart.rs', '    pub fn read_modem_status_register(&mut self) -> u8 {',
            '    pub fn owns_cts_pin(&self) -> bool { self.link.owns_cts_pin() }\n\n'
            '    pub fn read_modem_status_register(&mut self) -> u8 {')
    replace('agon-ez80-emulator/src/agon_machine.rs', '                self.gpios.c.get_dr() | uart1_cts',
            '''                if self.uart1.owns_cts_pin() && self.gpios.c.get_ddr() & 8 != 0 {
                    (self.gpios.c.get_dr() & !8) | uart1_cts
                } else {
                    self.gpios.c.get_dr() | uart1_cts
                }''')
    (root/'test_serial_peer.rs').write_text(PEER)
    for prefix, relative in [('src', '../'), ('agon-cli-emulator/src', '../../')]:
        replace(prefix+'/main.rs', 'mod parse_args;',
                f'#[path = "{relative}test_serial_peer.rs"]\nmod test_serial_peer;\nmod parse_args;')
        replace(prefix+'/parse_args.rs', '    pub ram_size: u32,',
                '    pub uart1_peer: Option<String>,\n    pub ram_size: u32,')
        replace(prefix+'/parse_args.rs', '        ram_size: pargs',
                '        uart1_peer: pargs.opt_value_from_str("--uart1-peer")?,\n        ram_size: pargs')
        replace(prefix+'/parse_args.rs', '  --mos PATH',
                '  --uart1-peer PATH     TEST ONLY: Unix-socket byte peer, host CTS backpressure\n  --mos PATH')
    replace('agon-cli-emulator/src/main.rs', 'uart1_link: Box::new(DummySerialLink {}),',
            'uart1_link: test_serial_peer::connect(args.uart1_peer.as_deref())\n'
            '                    .unwrap_or_else(|| Box::new(DummySerialLink {})),')
    replace('src/main.rs', 'uart1_link: uart1_serial.unwrap_or(uart1_dummy),',
            'uart1_link: test_serial_peer::connect(args.uart1_peer.as_deref())\n'
            '                        .or(uart1_serial).unwrap_or(uart1_dummy),')
    replace('src/parse_args.rs', '    let remaining = pargs.finish();',
            '''    if args.uart1_peer.is_some() && args.uart1_device.is_some() {
        panic!("Select a UART1 test peer OR physical serial device, not both");
    }
    let remaining = pargs.finish();''')

    if uart1_tx_interrupts:
        # Explicit opt-in: preserve every byte of the reviewed default runtime.
        # This supplies a documented missing peripheral event, not guest state,
        # synthetic VBlank/RX events or a faster serial clock.
        replace('agon-ez80-emulator/src/agon_machine.rs',
                '''            // TEST-001: the upstream model omits UART1 RX interrupts.
            if self.uart1.is_rx_interrupt_enabled() && self.uart1.rx_byte_ready() {''',
                '''            // TEST-002: enabled UART1 RX/TX sources own vector0x1a.
            if self.uart1.uart1_interrupt_identification() & 1 == 0 {''')
        replace('agon-ez80-emulator/src/agon_machine.rs',
                '''            0xd2 => {
                // UART1_IIR
                if self.uart1.ier & 0x02 != 0 {
                    self.uart1.ier = self.uart1.ier & 0b11111101;
                    0x02
                } else {
                    0x04
                }
            }''',
                '''            // TEST-002: read-only UART1 priority/status, including FIFO bits.
            0xd2 => self.uart1.uart1_interrupt_identification(),''')
        uart = root/'agon-ez80-emulator/src/uart.rs'
        uart.write_text(uart.read_text()+UART1_IRQ_METHOD)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fab-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--uart1-tx-interrupts', action='store_true',
                        help='TEST-002 opt-in UART1 RX/TX demand and read-only IIR; no physical timing claim')
    parser.add_argument('--library-dir', type=Path,
                        help='Optional directory for non-system host libraries; otherwise inherit the build environment')
    args = parser.parse_args()
    libraries = args.library_dir.resolve(strict=True) if args.library_dir else None
    if libraries is not None and not libraries.is_dir():
        parser.error('--library-dir must name a directory')
    reference = args.fab_root.resolve(strict=True)
    root = args.output.absolute()
    if subprocess.check_output(['git', '-C', str(reference), 'rev-parse', 'HEAD'], text=True).strip() != REFERENCE:
        parser.error('This adaptation requires the recorded Fab 1.2.3 reference')
    root.mkdir(parents=True)  # Never overwrite an earlier runtime.
    archive = subprocess.check_output(['git', '-C', str(reference), 'archive', REFERENCE])
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(root, filter='data')
    adapt(root, uart1_tx_interrupts=args.uart1_tx_interrupts)
    env = os.environ.copy()
    if libraries is not None:
        for name in ('LIBRARY_PATH', 'LD_LIBRARY_PATH'):
            env[name] = str(libraries) + os.pathsep + env.get(name, '')
    with (root/'build.log').open('w') as log:
        # Fab's tagged lock needs Cargo's local metadata normalization. Resolve
        # offline and retain the exact resulting lock hash with this runtime.
        subprocess.run(['cargo', 'build', '--offline', '--release', '-p',
                        'agon-cli-emulator', '-p', 'fab-agon-emulator'],
                       cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    files = ['test_serial_peer.rs', 'agon-ez80-emulator/src/agon_machine.rs',
             'agon-ez80-emulator/src/uart.rs',
             'src/main.rs', 'src/parse_args.rs', 'agon-cli-emulator/src/main.rs',
             'agon-cli-emulator/src/parse_args.rs', 'Cargo.lock',
             'target/release/agon-cli-emulator', 'target/release/fab-agon-emulator']
    (root/'runtime-inputs.json').write_text(json.dumps({
        'reference_commit': REFERENCE, 'adapter_sha256': digest(Path(__file__)),
        'host_library_directory': str(libraries) if libraries else None,
        'uart1_tx_interrupts': args.uart1_tx_interrupts,
        'files': {name: digest(root/name) for name in files},
        'scope': ('UART1 RX/TX IRQ and read-only IIR; ' if args.uart1_tx_interrupts else 'UART1 RX IRQ; ')
                 + 'ordered byte peer; host-socket CTS backpressure; no physical timing or RTS proof',
    }, indent=2)+'\n')
    print('UART1 test runtime built: '+str(root))


if __name__ == '__main__':
    main()
