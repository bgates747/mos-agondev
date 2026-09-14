"""Actual adapted UART register/FIFO behavior, independent of consumer gameplay."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('prepare_uart_peer_irq', ROOT/'scripts/prepare_uart_peer.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
BASE_GENERATOR = '2b7884ceb7b2cfa803f87e03ebe39ebe10d97723'
INPUTS = ('agon-ez80-emulator/src/agon_machine.rs', 'agon-ez80-emulator/src/uart.rs',
          'src/main.rs', 'src/parse_args.rs', 'agon-cli-emulator/src/main.rs',
          'agon-cli-emulator/src/parse_args.rs')

RUST_TESTS = r'''
use std::cell::RefCell;
use std::collections::VecDeque;
use std::rc::Rc;
struct Link { tx: Rc<RefCell<Vec<u8>>>, rx: Rc<RefCell<VecDeque<u8>>> }
impl uart::SerialLink for Link {
    fn send(&mut self, byte:u8) { self.tx.borrow_mut().push(byte); }
    fn recv(&mut self)->Option<u8> { self.rx.borrow_mut().pop_front() }
    fn read_clear_to_send(&mut self)->bool { true }
}
fn fixture()->(uart::Uart, Rc<RefCell<Vec<u8>>>, Rc<RefCell<VecDeque<u8>>>) {
    let tx=Rc::new(RefCell::new(Vec::new()));
    let rx=Rc::new(RefCell::new(VecDeque::new()));
    (uart::Uart::new(Box::new(Link{tx:tx.clone(),rx:rx.clone()})),tx,rx)
}
#[test] fn disabled_and_read_only_enable() {
    let (mut u,_,_)=fixture();
    assert_eq!(u.uart1_interrupt_identification(),1);
    u.ier=2;
    for _ in 0..5 { assert_eq!(u.uart1_interrupt_identification(),2); assert_eq!(u.ier,2); }
    u.ier=0; assert_eq!(u.uart1_interrupt_identification(),1);
    u.write_fctl(1); assert_eq!(u.uart1_interrupt_identification(),0xc1);
}
#[test] fn holding_empty_is_not_transmit_complete() {
    let (mut u,tx,_)=fixture(); u.ier=0x12; u.brg_div=2;
    assert_eq!(u.uart1_interrupt_identification(),0x0a);
    u.send_byte(7); assert_eq!(u.uart1_interrupt_identification(),1);
    u.apply_ticks(1); assert_eq!(*tx.borrow(),vec![7]);
    assert_eq!(u.read_lsr() & 0x60,0x20);
    assert_eq!(u.uart1_interrupt_identification(),2);
    u.ier=0x10; assert_eq!(u.uart1_interrupt_identification(),1);
    u.apply_ticks(319); assert_eq!(u.uart1_interrupt_identification(),1);
    u.apply_ticks(1); assert_eq!(u.uart1_interrupt_identification(),0x0a);
    assert_eq!(u.read_lsr() & 0x60,0x60);
    u.send_byte(8); assert_eq!(u.uart1_interrupt_identification(),1);
}
#[test] fn rx_priority_and_enable_masking() {
    let (mut u,_,rx)=fixture();u.write_fctl(1);u.ier=0x13;
    rx.borrow_mut().push_back(91);u.apply_ticks(0);
    assert_eq!(u.uart1_interrupt_identification(),0xc4);
    assert_eq!(u.ier,0x13);assert_eq!(u.receive_byte(),91);
    assert_eq!(u.uart1_interrupt_identification(),0xca);
    u.ier=2; assert_eq!(u.uart1_interrupt_identification(),0xc2);
    u.ier=1; assert_eq!(u.uart1_interrupt_identification(),0xc1);
}
#[test] fn fifo_drain_order_and_divisor_clock_unchanged() {
    let (mut u,tx,_)=fixture();u.write_fctl(1);u.brg_div=4;u.ier=2;
    for n in 0..16 {u.send_byte(n);}
    assert_eq!(u.uart1_interrupt_identification(),0xc1);
    u.apply_ticks(1);assert_eq!(*tx.borrow(),vec![0]);
    u.apply_ticks(639);assert_eq!(*tx.borrow(),vec![0]);
    for n in 1..16 {
        u.apply_ticks(if n==1 {1} else {640});
        assert_eq!(tx.borrow().len(),n as usize+1);
        assert_eq!(u.uart1_interrupt_identification(),if n==15 {0xc2} else {0xc1});
    }
    assert_eq!(*tx.borrow(),(0..16).collect::<Vec<u8>>());
    u.send_byte(32);assert_eq!(u.uart1_interrupt_identification(),0xc1);
    u.apply_ticks(640);assert_eq!(tx.borrow().last(),Some(&32));
    assert_eq!(u.uart1_interrupt_identification(),0xc2);
}
#[test] fn uart_instances_do_not_share_demand() {
    let (mut a,_,_)=fixture();let (mut b,_,_)=fixture();
    a.ier=2;b.ier=1;
    assert_eq!(a.uart1_interrupt_identification(),2);
    assert_eq!(b.uart1_interrupt_identification(),1);
    a.send_byte(1);assert_eq!(a.uart1_interrupt_identification(),1);
    b.ier=0x10;assert_eq!(b.uart1_interrupt_identification(),10);
}
'''


class UartPeerInterruptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = Path(os.environ.get('FAB_ROOT', ROOT/'fab-agon-emulator'))
        if not cls.reference.exists():
            raise unittest.SkipTest('Set FAB_ROOT to the pinned read-only Fab reference')
        commit = subprocess.check_output(['git', '-C', str(cls.reference), 'rev-parse', 'HEAD'], text=True).strip()
        if commit != MODULE.REFERENCE:
            raise RuntimeError('UART model tests require the pinned reference')

    def source_tree(self, directory):
        directory.mkdir()
        for name in INPUTS:
            path = directory/name;path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output(['git', '-C', str(self.reference),
                                                       'show', MODULE.REFERENCE+':'+name]))
        return directory

    def test_actual_adapted_uart_registers_and_byte_clock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.source_tree(Path(temporary)/'source')
            MODULE.adapt(root, uart1_tx_interrupts=True)
            source = root/'irq-test.rs';exe = root/'irq-test'
            source.write_text('#[path="agon-ez80-emulator/src/uart.rs"] mod uart;\n'+RUST_TESTS)
            subprocess.run(['rustc', '--test', str(source), '-o', str(exe)],
                           check=True, capture_output=True, text=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=10)
            self.assertIn('5 passed; 0 failed', result.stdout)
            machine = (root/INPUTS[0]).read_text()
            self.assertIn('if self.uart1.uart1_interrupt_identification() & 1 == 0', machine)
            self.assertIn('0xd2 => self.uart1.uart1_interrupt_identification(),', machine)
            self.assertNotIn('self.uart1.ier = self.uart1.ier & 0b11111101', machine)

    def test_default_source_matches_frozen_reviewed_generator(self):
        frozen = subprocess.check_output(['git', '-C', str(ROOT), 'show',
                                           BASE_GENERATOR+':scripts/prepare_uart_peer.py'], text=True)
        namespace = {'__name__': 'frozen_generator', '__file__': str(ROOT/'scripts/prepare_uart_peer.py')}
        exec(compile(frozen, 'frozen_uart_generator', 'exec'), namespace)
        with tempfile.TemporaryDirectory() as temporary:
            a = self.source_tree(Path(temporary)/'frozen')
            b = self.source_tree(Path(temporary)/'current')
            namespace['adapt'](a);MODULE.adapt(b)
            for name in (*INPUTS, 'test_serial_peer.rs'):
                self.assertEqual((a/name).read_bytes(), (b/name).read_bytes(), name)

    def test_iir_source_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.source_tree(Path(temporary)/'source')
            p = root/INPUTS[0]
            p.write_text(p.read_text().replace('// UART1_IIR', '// changed UART1_IIR'))
            with self.assertRaisesRegex(ValueError, 'Reference drift'):
                MODULE.adapt(root, uart1_tx_interrupts=True)


if __name__ == '__main__':
    unittest.main()
