#!/usr/bin/env python3
"""Compare native firmware/public symbols against its pinned translated control."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def public_symbols(nm,elf):
    output=subprocess.check_output([str(nm),'--defined-only','-g',str(elf)],text=True)
    result={}
    for line in output.splitlines():
        if not line.strip():
            continue
        words=line.split()
        if len(words)!=3 or len(words[1])!=1 or words[2] in result:
            raise ValueError(f'malformed/duplicate public symbol record: {line}')
        result[words[2]]={'address':int(words[0],16),'kind':words[1]}
    if not result:
        raise ValueError('public symbol table is empty')
    return result

def compare(native,reference,nm):
    native=native.resolve(strict=True);reference=reference.resolve(strict=True)
    symbols=public_symbols(nm,native/'MOS.elf')
    old=public_symbols(nm,reference/'MOS.elf')
    result={'schema':1,'binary_equal':(native/'MOS.bin').read_bytes()==(reference/'MOS.bin').read_bytes(),
        'native_binary_sha256':sha(native/'MOS.bin'),'reference_binary_sha256':sha(reference/'MOS.bin'),
        'bytes':(native/'MOS.bin').stat().st_size,'public_symbols_equal':symbols==old,
        'public_symbol_count':len(symbols),
        'symbol_differences':{name:{'native':symbols.get(name),'reference':old.get(name)}
            for name in sorted(symbols.keys()|old.keys()) if symbols.get(name)!=old.get(name)},
        'native_elf_sha256':sha(native/'MOS.elf'),'reference_elf_sha256':sha(reference/'MOS.elf'),
        'emulator_qualified':False,'hardware_qualified':False}
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-bin-dir',type=Path,required=True)
    parser.add_argument('--reference-bin-dir',type=Path,required=True)
    parser.add_argument('--nm',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=compare(args.native_bin_dir,args.reference_bin_dir,args.nm)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    raise SystemExit(not(report['binary_equal'] and report['public_symbols_equal']))

if __name__=='__main__':main()
