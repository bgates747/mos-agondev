"""Reservation namespaces, collisions and shared binding consistency."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('api_reservations', ROOT / 'scripts/generate_api_reservations.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class ReservationTests(unittest.TestCase):
    def fixture(self):
        return {'schema': 1, 'api_revision': 1, 'reservations': [{
            'namespace': 'mos_getfunction', 'value': 19, 'owner': 'agon-mos',
            'purpose': 'UART discovery', 'status': 'experimental',
            'asm_symbol': 'mos_function_uart0_async', 'c_symbol': 'MOS_FUNCTION_UART0_ASYNC',
            'implementation_symbol': 'uart0_async_getapi'}]}

    def test_matching_bindings(self):
        data = self.fixture(); api.validate(data, ['official'] * 18)
        outputs = api.bindings(data, 'a' * 64)
        self.assertIn('.equiv mos_function_uart0_async, 0x13', outputs['src/mos_api_reservations.inc'])
        self.assertIn('#define MOS_FUNCTION_UART0_ASYNC 0x13u', outputs['api/include/mos_api_reservations.h'])

    def test_native_table_is_required(self):
        self.assertEqual(api.table_entries('mos_function_block_start:\n d24 first ; 0\n d24 0\n.equiv mos_function_block_size,2'), ['first', '0'])
        with self.assertRaises(ValueError):
            api.table_entries('mos_function_block_start:\n unsupported format\n.equiv mos_function_block_size,0')

    def test_duplicate_and_wrong_namespace_rejected(self):
        data = self.fixture(); data['reservations'].append(copy.deepcopy(data['reservations'][0]))
        with self.assertRaises(ValueError): api.validate(data, [])
        data = self.fixture(); data['reservations'][0]['namespace'] = 'rst08'
        with self.assertRaises(ValueError): api.validate(data, [])

    def test_upstream_collision_rejected(self):
        with self.assertRaisesRegex(ValueError, 'collides'):
            api.validate(self.fixture(), ['official'] * 20)
        api.validate(self.fixture(), ['official'] * 19 + ['uart0_async_getapi'])

    def test_retired_values_not_exported(self):
        data = self.fixture(); row = data['reservations'][0]
        row.update(status='retired', asm_symbol=None, c_symbol=None, implementation_symbol='0')
        api.validate(data, [])
        self.assertNotIn('UART0_ASYNC', api.bindings(data, 'a' * 64)['api/include/mos_api_reservations.h'])

    def test_out_of_range_and_incomplete_bindings_rejected(self):
        for value in (-1, 256, True, '19'):
            data = self.fixture(); data['reservations'][0]['value'] = value
            with self.assertRaises(ValueError): api.validate(data, [])
        data = self.fixture(); data['reservations'][0]['c_symbol'] = None
        with self.assertRaises(ValueError): api.validate(data, [])


if __name__ == '__main__': unittest.main()
