"""Native source migration and direct-build profile contracts, without an emulator."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module

MIGRATE=load('test_native_migrate',ROOT/'projects/native-foundation/migrate.py')
BUILD=load('test_native_build',ROOT/'projects/native-foundation/build.py')
COMPARE=load('test_native_compare',ROOT/'projects/native-foundation/compare.py')

class NativeMigrationTests(unittest.TestCase):
    def readable(self,source):
        macros=MIGRATE.ZDS.discover_macros([('src/test.asm',source)])
        result=MIGRATE.ZDS.translate('src/test.asm',source,macros)
        return MIGRATE.make_readable(result,source,macros)

    def test_public_label_case_and_private_scope(self):
        source='XDEF PublicEntry\nSCOPE\nPublicEntry:\n jr $done\n$done: ret\nEND\n'
        native,mappings,origins=self.readable(source)
        self.assertIn('PublicEntry:',native)
        self.assertNotIn('publicentry:',native)
        self.assertIn('.global PublicEntry',native)
        self.assertIn('.LPublicEntry_done',native)
        self.assertNotIn('.Lzds_',native)
        self.assertEqual(len(native.splitlines()),len(origins))

    def test_anonymous_forward_and_backward_labels(self):
        native,_,_=self.readable('entry: jr $F\n$$: nop\njr $B\nEND\n')
        self.assertIn('jr 1f',native)
        self.assertIn('1: nop',native)
        self.assertIn('jr 1b',native)

    def test_macro_locals_keep_invocation_uniqueness(self):
        native,_,_=self.readable('WAIT MACRO\n$$again: nop\njr $$again\nENDMACRO\nWAIT\nWAIT\nEND\n')
        self.assertIn('.macro WAIT',native)
        self.assertIn('.LWAIT_again\\@:',native)
        self.assertIn('jr .LWAIT_again\\@',native)
        self.assertNotIn('zds_WAIT',native)

    def test_illegal_macro_question_mark_becomes_readable_name(self):
        native,_,_=self.readable('TIMER_EXP? MACRO TIMER\nld a,TIMER\nENDMACRO\nTIMER_EXP? 1\nEND\n')
        self.assertIn('.macro TIMER_EXP TIMER',native)
        self.assertIn('TIMER_EXP 1',native)
        self.assertNotIn('TIMER_EXP?',native)

    def test_strings_and_comments_are_not_symbol_rewritten(self):
        native,_,_=self.readable('WAIT MACRO\nnop\nENDMACRO\nDB "zds_WAIT XDEF" ; Original attribution\nWAIT\nEND\n')
        self.assertIn('"zds_WAIT XDEF" ; Original attribution',native)

    def test_two_procedures_retain_distinct_private_labels(self):
        native,_,_=self.readable('SCOPE\nFirst:\njr $out\n$out: ret\nSCOPE\nSecond:\njr $out\n$out: ret\nEND\n')
        self.assertIn('.LFirst_out',native)
        self.assertIn('.LSecond_out',native)

class NativeProfileTests(unittest.TestCase):
    def fixture(self,root):
        (root/'src').mkdir()
        (root/'main.c').write_text('int main(void) {return 0;}\n')
        (root/'src/unit.asm').write_text('.text\nret\n')
        config={'schema':1,'upstream_commit':MIGRATE.UPSTREAM_COMMIT,
            'c_sources':['main.c'],'asm_sources':['src/unit.asm'],
            'c_optimization':'-Oz','c_overrides':{},'cppflags':[],
            'firmware_link_checks':[],'reference_binary':{'bytes':1,'sha256':'0'*64}}
        (root/'build.json').write_text(json.dumps(config))
        return config

    def test_explicit_source_and_optimization_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=self.fixture(root)
            self.assertEqual(BUILD.profile(root),config)

    def test_unknown_profile_field_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=self.fixture(root);config['translate']=True
            (root/'build.json').write_text(json.dumps(config))
            with self.assertRaises(ValueError):BUILD.profile(root)

    def test_duplicate_or_escaping_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=self.fixture(root)
            for names in (['main.c','main.c'],['../main.c']):
                config['c_sources']=names
                (root/'build.json').write_text(json.dumps(config))
                with self.assertRaises(ValueError):BUILD.profile(root)

    def test_unselected_override_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=self.fixture(root);config['c_overrides']={'missing.c':'-Os'}
            (root/'build.json').write_text(json.dumps(config))
            with self.assertRaises(ValueError):BUILD.profile(root)

    def test_missing_product_checker_is_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=self.fixture(root);config['firmware_link_checks']=['check.py']
            (root/'build.json').write_text(json.dumps(config))
            with self.assertRaises(ValueError):BUILD.profile(root)

    def test_source_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            (root/'linked.c').symlink_to(root/'main.c')
            with self.assertRaises(ValueError):BUILD.source_path(root,'linked.c','.c')

    def test_sanitizer_covers_dictionary_path_keys(self):
        builder=object.__new__(BUILD.Builder)
        builder.roots=[('SOURCE',Path('/private/source'))]
        self.assertEqual(builder.sanitized({'/private/source/main.c':'/private/source/src'}),
            {'${SOURCE}/main.c':'${SOURCE}/src'})

    def test_differing_sdk_alias_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);native=root/'native.inc';sdk=root/'sdk.inc'
            native.write_text('.equ UART0_IVECT, 0x18\n')
            sdk.write_text('.set UART0_IVECT, 0x19\n')
            with self.assertRaises(ValueError):BUILD.verify_register_aliases(native,sdk)
            sdk.write_text('.set UART0_IVECT, 0x18\n')
            self.assertEqual(BUILD.verify_register_aliases(native,sdk),['UART0_IVECT'])

    def test_every_product_checker_runs_against_selected_source_and_elf(self):
        builder=Mock();builder.tool.side_effect=lambda n:Path('/tools')/n
        BUILD.product_checks(builder,{'firmware_link_checks':['one.py','two.py']},Path('/source'),Path('/build/MOS.elf'))
        self.assertEqual(builder.command.call_count,2)
        for call in builder.command.call_args_list:
            command=call.args[1]
            self.assertEqual(command[command.index('--source')+1],Path('/source'))
            self.assertEqual(command[command.index('--elf')+1],Path('/build/MOS.elf'))

    def test_failed_product_checker_cannot_be_ignored(self):
        builder=Mock();builder.tool.side_effect=lambda n:Path('/tools')/n
        builder.command.side_effect=RuntimeError('failed checker')
        with self.assertRaises(RuntimeError):
            BUILD.product_checks(builder,{'firmware_link_checks':['one.py','two.py']},Path('/source'),Path('/build/MOS.elf'))
        self.assertEqual(builder.command.call_count,1)

class NativeComparisonTests(unittest.TestCase):
    def fixture(self,root):
        native=root/'native';reference=root/'reference'
        for directory in (native,reference):
            directory.mkdir()
            (directory/'MOS.bin').write_bytes(b'firmware')
            (directory/'MOS.elf').write_bytes(b'elf')
        return native,reference

    def test_identical_bytes_and_public_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            native,reference=self.fixture(Path(tmp))
            with patch.object(COMPARE,'public_symbols',return_value={'entry':{'address':8,'kind':'T'}}):
                result=COMPARE.compare(native,reference,Path('/tools/nm'))
            self.assertTrue(result['binary_equal'])
            self.assertTrue(result['public_symbols_equal'])
            self.assertFalse(result['hardware_qualified'])

    def test_binary_and_public_symbol_changes_are_independently_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            native,reference=self.fixture(Path(tmp))
            for same_bytes in (False,True):
                (native/'MOS.bin').write_bytes(b'firmware' if same_bytes else b'changed')
                with patch.object(COMPARE,'public_symbols',side_effect=[
                    {'entry':{'address':8,'kind':'T'}},{'entry':{'address':9,'kind':'T'}}]):
                    result=COMPARE.compare(native,reference,Path('/tools/nm'))
                self.assertEqual(result['binary_equal'],same_bytes)
                self.assertFalse(result['public_symbols_equal'])
                self.assertIn('entry',result['symbol_differences'])

    def test_empty_malformed_and_duplicate_symbol_tables_are_rejected(self):
        for output in ('','not-a-symbol\n','8 T entry\n9 T entry\n'):
            with patch.object(COMPARE.subprocess,'check_output',return_value=output):
                with self.assertRaises(ValueError):
                    COMPARE.public_symbols(Path('/tools/nm'),Path('/build/MOS.elf'))

if __name__=='__main__':unittest.main()
