#!/usr/bin/env python3
"""Generate/check the native foundation's canonical extension bindings."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def validate(data: dict, table: list[str]) -> None:
    if data.get('schema') != 1 or type(data.get('api_revision')) is not int or data['api_revision'] < 1:
        raise ValueError('unsupported reservation schema/revision')
    if not isinstance(data.get('reservations'), list):
        raise ValueError('reservations must be a list')
    slots, symbols = set(), set()
    for row in data['reservations']:
        if row.get('namespace') != 'mos_getfunction':
            raise ValueError('only the explicitly audited mos_getfunction namespace is supported')
        value = row.get('value')
        if type(value) is not int or not 0 <= value <= 255:
            raise ValueError('identifier must be an unsigned byte')
        key = (row['namespace'], value)
        if key in slots:
            raise ValueError('duplicate namespace/identifier')
        slots.add(key)
        if row.get('status') not in ('reserved', 'experimental', 'accepted', 'retired'):
            raise ValueError('invalid reservation status')
        if not row.get('owner') or not row.get('purpose'):
            raise ValueError('owner and purpose required')
        for field in ('asm_symbol', 'c_symbol'):
            symbol = row.get(field)
            if symbol is not None:
                if not isinstance(symbol, str) or not re.fullmatch(r'[A-Za-z_]\w*', symbol) or symbol in symbols:
                    raise ValueError('invalid or duplicate binding symbol')
                symbols.add(symbol)
        if (row.get('asm_symbol') is None) != (row.get('c_symbol') is None):
            raise ValueError('assembly and C bindings must be supplied together')
        if row['status'] == 'retired' and row.get('asm_symbol') is not None:
            raise ValueError('retired allocations must not export callable-feature constants')
        if value < len(table) and table[value] != row.get('implementation_symbol'):
            raise ValueError(f'getfunction 0x{value:02X} collides with {table[value]}')


def table_entries(text: str) -> list[str]:
    block = text.split('mos_function_block_start:', 1)[1].split('.equiv mos_function_block_size', 1)[0]
    entries = re.findall(r'^\s*d24\s+([^;\s]+)', block, re.M)
    if not entries:
        raise ValueError('missing/unsupported native getfunction table')
    return entries


def bindings(data: dict, digest: str) -> dict[str, str]:
    asm = ['; Generated from api/reservations.json; do not edit independently.',
           '; Reservations declare identifiers, not firmware feature availability.',
           '.ifndef AGON_MOS_API_RESERVATIONS_INC', '.set AGON_MOS_API_RESERVATIONS_INC,1',
           f'.equiv mos_extension_api_revision, {data["api_revision"]}']
    c = ['/* Generated from api/reservations.json; do not edit independently. */',
         '#ifndef AGON_MOS_API_RESERVATIONS_H', '#define AGON_MOS_API_RESERVATIONS_H',
         f'#define MOS_EXTENSION_API_REVISION {data["api_revision"]}u',
         f'#define MOS_EXTENSION_API_SHA256 "{digest}"']
    for row in data['reservations']:
        if row['asm_symbol'] is not None:
            asm += [f'; mos_getfunction: {row["owner"]}; {row["status"]}; not an RST08 call number.',
                    f'.equiv {row["asm_symbol"]}, 0x{row["value"]:02X}']
            c += [f'/* mos_getfunction index; {row["owner"]}; {row["status"]}; runtime discovery required. */',
                  f'#define {row["c_symbol"]} 0x{row["value"]:02X}u']
    asm += ['.endif', '']
    c += ['#endif', '']
    return {'src/mos_api_reservations.inc': '\n'.join(asm),
            'api/include/mos_api_reservations.h': '\n'.join(c)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    root = a.source_root.resolve(strict=True)
    registry = root / 'api/reservations.json'
    raw = registry.read_bytes()
    data = json.loads(raw)
    validate(data, table_entries((root / 'src/mos_api.asm').read_text()))
    canonical = (root / 'src/mos_api.inc').read_text()
    if canonical.count('.include "mos_api_reservations.inc"') != 1:
        raise SystemExit('canonical assembly interface must include the shared reservations exactly once')
    for name, text in bindings(data, hashlib.sha256(raw).hexdigest()).items():
        path = root / name
        if path.is_symlink():
            raise SystemExit('refusing symlink binding output: ' + name)
        if a.check:
            if not path.is_file() or path.read_text() != text:
                raise SystemExit('stale canonical binding: ' + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    print('Canonical API reservations and assembly/C bindings agree.')


if __name__ == '__main__':
    main()
