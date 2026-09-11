"""Exercise the generated Rust adapter against a deliberately unread socket."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_uart_peer',ROOT/'scripts/prepare_uart_peer.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class Backpressure(unittest.TestCase):
    def test_full_socket_withdraws_cts_and_preserves_every_byte(self):
        stub='''mod agon_ez80_emulator {
            pub trait SerialLink {
                fn send(&mut self, byte:u8); fn recv(&mut self)->Option<u8>;
                fn read_clear_to_send(&mut self)->bool; fn owns_cts_pin(&self)->bool;
            }
        }\n'''
        check=r'''
        #[test] fn saturated_socket() {
            let (socket,mut receiver)=UnixStream::pair().unwrap();
            socket.set_nonblocking(true).unwrap(); receiver.set_nonblocking(true).unwrap();
            let mut peer=Peer {socket,pending:VecDeque::new()};
            let mut sent=Vec::new();
            while peer.read_clear_to_send() {
                assert!(sent.len()<2_000_000,"socket never saturated");
                let byte=(sent.len()%251) as u8;sent.push(byte);peer.send(byte);
            }
            assert_eq!(peer.pending.len(),1);
            assert!(!peer.read_clear_to_send());
            let mut got=Vec::new();let deadline=std::time::Instant::now()+std::time::Duration::from_secs(3);
            while got.len()<sent.len() {
                assert!(std::time::Instant::now()<deadline,"drain timeout");
                peer.read_clear_to_send();
                let mut data=[0;4096];
                match receiver.read(&mut data) {
                    Ok(n)=>got.extend_from_slice(&data[..n]),
                    Err(e) if e.kind()==ErrorKind::WouldBlock=>std::thread::yield_now(),
                    other=>panic!("unexpected read: {:?}",other),
                }
            }
            assert_eq!(sent,got);assert!(peer.read_clear_to_send());
            receiver.write_all(&[42]).unwrap();assert_eq!(peer.recv(),Some(42));
        }
        '''
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'peer.rs';exe=Path(tmp)/'peer-test'
            src.write_text(stub+module.PEER+check)
            subprocess.run(['rustc','--test',str(src),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True,capture_output=True,timeout=10)
