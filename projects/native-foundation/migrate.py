#!/usr/bin/env python3
"""One-time, pinned MOS migration; never invoked by native firmware builds.

Convert each original file independently so includes and macros remain readable.
The legacy frontend remains the semantic authority for the initial dialect edit.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_COMMIT = '8336409351ee5314e02801a7b72a4f1bb5282519'

def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

ZDS = load('native_migration_zds', ROOT/'projects/mos-port/tools/zds2gas.py')
PREPARE = load('native_migration_prepare', ROOT/'scripts/prepare_mos_worktree.py')

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def readable_identifier(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9_]', '_', name.strip('$?')).strip('_') or 'local'

def scope_anchors(text: str) -> dict[int, str]:
    scopes = {0: 'file'}
    current = 0
    waiting = False
    for line in text.splitlines():
        code, _ = ZDS.split_comment(line)
        if ZDS.SCOPE_RE.match(code):
            current += 1
            waiting = True
        match = re.match(r'^\s*([A-Za-z_][\w?]*):', code)
        if match and (waiting or current == 0 and scopes[0] == 'file'):
            scopes[current] = readable_identifier(match[1])
            waiting = False
    return scopes

def make_readable(result, source: str, macros: dict) -> tuple[str, list[dict], list[int]]:
    anchors = scope_anchors(source)
    replacements = {m.gas_name: readable_identifier(m.source_name) for m in macros.values()}
    native_macro_names = set(replacements.values())
    mappings = []
    used = set()
    for record in result.analysis.mappings:
        old = record['generated']
        if record['kind'] == 'named-local':
            anchor = anchors.get(record.get('scope', 0), 'file')
            new = f'.L{anchor}_{readable_identifier(record["source"])}'
        elif record['kind'] == 'macro-local':
            new = f'.L{record["macro"]}_{readable_identifier(record["source"])}\\@'
        elif record['kind'] == 'anonymous':
            # Numeric labels outside macros cannot be intercepted by a macro's
            # anonymous label: macro-local anonymous targets retain unique \@.
            if record.get('macro'):
                new = f'.L{record["macro"]}_anonymous_{record["line"]}\\@'
            else:
                new = '1'
        else:
            continue
        if new != '1':
            candidate = new
            suffix = 2
            while candidate in used:
                candidate = new.replace('\\@', '')+f'_{suffix}'+('\\@' if '\\@' in new else '')
                suffix += 1
            new = candidate
            used.add(new)
        replacements[old] = new
        mappings.append({**record, 'native': new})
    pattern = re.compile('|'.join(re.escape(k) for k in sorted(replacements, key=len, reverse=True)))
    anonymous = {r['generated']: r['line'] for r in result.analysis.mappings
                 if r['kind']=='anonymous' and not r.get('macro')}
    lines = []
    line_map = []
    for number, physical in enumerate(result.text.splitlines()[5:]):
        original_line = result.output_locations[number+5].line
        code, comment = ZDS.split_comment(physical)
        def replace(segment):
            def token(match):
                name = match[0]
                if name in anonymous:
                    target = anonymous[name]
                    if original_line == target and segment.lstrip().startswith(name+':'):
                        return '1'
                    return '1f' if target > original_line else '1b'
                return replacements[name]
            return pattern.sub(token, segment)
        code = ZDS.map_unquoted(code, replace)
        code = re.sub(r'^(\s*)XDEF\b', r'\1.global', code, flags=re.I)
        code = re.sub(r'^(\s*)XREF\b', r'\1.extern', code, flags=re.I)
        code = re.sub(r'(?i); zds2gas: SCOPE', '; private labels in this routine', code)
        if code.strip() == '; zds2gas: END': continue
        code=code.replace('; zds2gas: DEFINE', '; Upstream placement: DEFINE')
        code=code.replace('; zds2gas:', '; Upstream layout:')
        code=re.sub(r'\.ASSUME\s+ADL\s*=\s*1', '.assume adl=1',code,flags=re.I)
        # All comments and operand spelling are retained. Only instruction
        # mnemonics become lowercase; macro names keep upstream spelling.
        code = re.sub(r'^(\s*(?:[\w.]+:\s*)?)([A-Za-z][A-Za-z0-9.]*)(?=\s|$)',
                      lambda m:m[1]+(m[2] if m[2] in native_macro_names else m[2].lower()), code)
        lines.append((code+comment).rstrip())
        line_map.append(original_line)
    return '\n'.join(lines)+'\n', mappings, line_map

def migrate(upstream: Path, destination: Path, readable: bool) -> dict:
    upstream = upstream.resolve(strict=True)
    head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=upstream,text=True).strip()
    if head != UPSTREAM_COMMIT:
        raise ValueError('migration input must be exact official v3.0.2')
    if subprocess.check_output(['git','status','--porcelain'],cwd=upstream):
        raise ValueError('migration input must be clean')
    destination = destination.absolute()
    if destination.exists(): raise ValueError('refusing existing migration destination')
    # Reuse only the exact, fail-closed, already-qualified initial C/branch edits.
    PREPARE.prepare_worktree(destination.parent, upstream, destination)
    records = ZDS.source_records(destination)
    macros = ZDS.discover_macros([(name,text) for name,_,text in records])
    manifest = {'schema':1,'upstream_commit':head,'mode':'readable' if readable else 'mechanical',
                'files':[], 'symbols':[]}
    for name,path,text in records:
        result = ZDS.translate(name,text,macros,input_identity=head)
        if readable:
            body, mappings, line_map = make_readable(result,text,macros)
        else:
            body='\n'.join(result.text.splitlines()[5:])+'\n'
            mappings=[{**m,'native':m['generated']} for m in result.analysis.mappings]
            line_map=result.output_to_source[5:]
        relaxed={
            'src/mos_api.asm':r'JP\s+NC,\s*\$F',
            'src/sd.asm':r'JP\s+NZ,\s*\$out3',
            'src/vdp_protocol.asm':r'JP\s+Z,\s*vdp_protocol_state3',
        }
        if name in relaxed:
            original_lines=text.splitlines()
            native_lines=body.splitlines()
            changed=0
            for index,origin in enumerate(line_map):
                if origin and re.search(relaxed[name],original_lines[origin-1],re.I):
                    native_lines[index]+=(' ' if ';' in native_lines[index] else ' ; ')
                    native_lines[index]+='[DEV-006: ZDS relaxes this long JR; GNU requires explicit JP.]'
                    changed+=1
            if changed != 1:
                raise ValueError(f'expected one documented long branch in {name}, found {changed}')
            body='\n'.join(native_lines)+'\n'
        # Guard project includes: original ZDS corpus deliberately includes
        # equs both directly and through macros. Flattening formerly deduped it.
        if path.suffix=='.inc':
            guard='AGON_MOS_'+readable_identifier(name).upper()
            body='; DEV-009: guard repeated includes; SDK hardware aliases are checked by the build.\n'+f'.ifndef {guard}\n.set {guard},1\n'+body+'\n.endif\n'
            line_map=[None,None,None,*line_map,None,None]
        # ez80f92.inc uses mutable .set hardware constants. Permit its identical
        # redeclarations, while project-only constants remain immutable.
        if name=='src/equs.inc':
            hardware = {'PA_DR','PA_DDR','PA_ALT1','PA_ALT2','PB_DR','PB_DDR','PB_ALT1','PB_ALT2',
                'PC_DR','PC_DDR','PC_ALT1','PC_ALT2','PD_DR','PD_DDR','PD_ALT1','PD_ALT2',
                'TMR0_CTL','TMR0_RR_H','TMR0_RR_L','TMR0_DR_L','TMR0_DR_H',
                'UART0_IVECT','UART1_IVECT'}
            body=re.sub(r'\.equiv (\w+),',lambda m:('.equ ' if m[1] in hardware else '.equiv ')+m[1]+',',body)
        header=f'; Native AgonDev source derived from official MOS v3.0.2: {name}\n'
        header+='; Upstream ancestry and changes: docs/upstream-origin.md and docs/deviations.md.\n'
        data=(header+body).encode()
        line_map=[None,None,*line_map]
        if len(line_map) != len(data.decode().splitlines()):
            raise ValueError(f'line mapping does not match emitted source: {name}')
        path.write_bytes(data)
        manifest['files'].append({'upstream_path':name,'native_path':name,
            'upstream_sha256':sha((upstream/name).read_bytes()),'native_sha256':sha(data),
            'upstream_line_map':line_map,
            'transformations':result.transformations})
        manifest['symbols'].extend({'path':name,**m} for m in mappings)
    manifest['macros']=[{'path':m.source,'upstream':m.source_name,
        'native':readable_identifier(m.source_name) if readable else m.gas_name,
        'upstream_line':m.line} for m in macros.values()]
    # Metadata attests generated prepared source, not maintained native source;
    # it must not masquerade as current native provenance.
    (destination/PREPARE.PREPARATION_METADATA).unlink()
    (destination/'migration-map.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--readable',action='store_true')
    args=parser.parse_args()
    result=migrate(args.upstream,args.destination,args.readable)
    print('Converted',len(result['files']),'assembly/include files; mode',result['mode'])

if __name__=='__main__':main()
