"""Compile ZDS-style UART lvalues and inspect actual eZ80 I/O instructions."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UartRegisterTests(unittest.TestCase):
    def test_uart1_accesses_are_volatile_port_instructions(self):
        toolchain = ROOT / 'toolchains/agondev'
        compiler = toolchain / 'bin/ez80-none-elf-clang'
        if not compiler.exists():
            self.skipTest('AgonDev toolchain is not configured')
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'uart.c'
            output = source.with_suffix('.s')
            source.write_text('#include "ez80.h"\n'
                              'unsigned char status(void) { return UART1_LSR; }\n'
                              'unsigned char receive(void) { return UART1_RBR; }\n'
                              'void transmit(unsigned char c) { UART1_THR = c; }\n')
            subprocess.run([str(compiler), '-target', 'ez80-none-elf', '-march=ez80',
                            '-mllvm', '-z80-gas-style', '-ffreestanding', '-Oz',
                            '-I' + str(ROOT / 'projects/mos-port/include'),
                            '-nostdinc', '-isystem', str(toolchain / 'include'),
                            '-S', str(source), '-o', str(output)], check=True,
                           capture_output=True, text=True)
            assembly = output.read_text()
            self.assertRegex(assembly, r'in0\s+a,\s*\(213\)')
            self.assertRegex(assembly, r'in0\s+a,\s*\(208\)')
            self.assertRegex(assembly, r'out0\s*\(208\),\s*a')


if __name__ == '__main__':
    unittest.main()
