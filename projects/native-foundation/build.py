#!/usr/bin/env python3
"""Build maintained native MOS source directly, without preparation/translation.

Source inventories and product checks are explicit profile inputs. Existing
restricted-runtime, target-step and linker verifiers remain the shared authority.
Every invocation uses a fresh build directory and retains failures for diagnosis.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time

INFRA = Path(__file__).resolve().parents[2]
PORT = INFRA/'projects/mos-port'

def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_path(root, name, suffix=None):
    if not isinstance(name,str):raise ValueError('source name must be text')
    relative=PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or relative.as_posix()!=name:
        raise ValueError(f'unsafe source path: {name}')
    path=root/name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f'missing/nonregular/escaping source: {name}')
    if suffix and path.suffix!=suffix:raise ValueError(f'wrong source suffix: {name}')
    return path

def verify_register_aliases(source, vendor):
    """Keep overlapping native and SDK hardware declarations demonstrably equal."""
    pattern=r'^\s*\.(?:equiv|equ|set)\s+(\w+)\s*,\s*([^;\n]+)'
    def constants(text):
        result={}
        for name,value in re.findall(pattern,text,re.M):
            try:result[name]=int(value.strip(),0)
            except ValueError:continue
        return result
    native=constants(source.read_text())
    sdk=constants(vendor.read_text())
    common=native.keys()&sdk.keys()
    mismatches={name:(native[name],sdk[name]) for name in common if native[name]!=sdk[name]}
    if mismatches:raise ValueError(f'conflicting native/SDK register aliases: {mismatches}')
    return sorted(common)

def profile(root):
    data=json.loads(source_path(root,'build.json').read_text())
    allowed={'schema','upstream_commit','c_sources','asm_sources','c_optimization',
             'c_overrides','cppflags','firmware_link_checks','reference_binary'}
    if set(data)!=allowed or data['schema']!=1:raise ValueError('unsupported native profile schema/fields')
    if not re.fullmatch(r'[0-9a-f]{40}',data['upstream_commit']):raise ValueError('invalid upstream identity')
    for key,suffix in [('c_sources','.c'),('asm_sources','.asm')]:
        names=data[key]
        if not isinstance(names,list) or not names or len(set(names))!=len(names):
            raise ValueError(f'empty/duplicate source inventory: {key}')
        for name in names:source_path(root,name,suffix)
    if data['c_optimization'] not in ('-Oz','-Os','-O0','-O1','-O2','-O3'):
        raise ValueError('unsupported optimization selection')
    if not set(data['c_overrides']).issubset(data['c_sources']):raise ValueError('override for unselected source')
    if any(v not in ('-Oz','-Os','-O0','-O1','-O2','-O3') for v in data['c_overrides'].values()):
        raise ValueError('unsupported source optimization override')
    if not isinstance(data['cppflags'],list) or any(not isinstance(v,str) or not re.fullmatch(r'-D[A-Za-z_]\w*(?:=[\w.+-]+)?',v) for v in data['cppflags']):
        raise ValueError('cppflags must be explicit simple -D definitions')
    if not isinstance(data['firmware_link_checks'],list) or len(set(data['firmware_link_checks']))!=len(data['firmware_link_checks']):
        raise ValueError('invalid/duplicate product checker inventory')
    reference=data['reference_binary']
    if (set(reference)!= {'bytes','sha256'} or type(reference['bytes']) is not int or not 0<reference['bytes']<=0x20000
        or not re.fullmatch(r'[0-9a-f]{64}',reference['sha256'])):
        raise ValueError('invalid reference binary pin')
    for name in data['firmware_link_checks']:source_path(root,name,'.py')
    return data

class Builder:
    def __init__(self,root,toolchain,output):
        self.root=root
        self.toolchain=toolchain
        self.bin=toolchain/'bin'
        self.output=output
        self.records=output/'provenance'
        self.logdir=output/'logs'
        self.logdir.mkdir(parents=True)
        self.roots=[('BUILD_TOOL',INFRA),('SOURCE',root),('BUILD',output),
                    ('TOOLCHAIN',toolchain),('PYTHON_ENV',Path(sys.prefix)),
                    ('PROVENANCE',self.records)]
        self.producers={}
        self.steps=[]
        self.common_inputs=[p for top in ('src','src_startup','src_fatfs','src_umm_malloc')
            for p in (root/top).rglob('*') if p.is_file() and p.suffix in ('.inc','.h')]
        self.common_inputs += [p for directory in (PORT/'include',toolchain/'include',PORT/'runtime/vendor/nanoprintf')
            for p in directory.rglob('*') if p.is_file()]
        self.command('initialize-provenance',[sys.executable,PORT/'tools/record_target_step.py',
            '--initialize',self.records])

    def sanitized(self,value):
        if isinstance(value,dict):return {self.sanitized(k):self.sanitized(v) for k,v in value.items()}
        if isinstance(value,list):return [self.sanitized(v) for v in value]
        if isinstance(value,str):
            for name,path in sorted(self.roots,key=lambda p:len(str(p[1])),reverse=True):
                value=value.replace(str(path),'${'+name+'}')
        return value

    def command(self,name,command):
        start=time.monotonic()
        run=subprocess.run([str(v) for v in command],cwd=self.root,text=True,capture_output=True)
        receipt=self.sanitized({'command':[str(v) for v in command],
            'returncode':run.returncode,'elapsed_seconds':time.monotonic()-start,
            'stdout':run.stdout,'stderr':run.stderr})
        (self.logdir/(name+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
        self.steps.append({'name':name,'returncode':run.returncode,'elapsed_seconds':receipt['elapsed_seconds']})
        if run.returncode:
            print(run.stdout+run.stderr,file=sys.stderr)
            raise RuntimeError(f'{name} failed: {run.returncode}; retained {self.output}')
        return run.stdout

    def target(self,name,kind,source,output,command,inputs=(),secondary=(),link_inputs=()):
        output.parent.mkdir(parents=True,exist_ok=True)
        record=self.records/(name+'.json')
        depfile=output.with_suffix('.d')
        args=[sys.executable,'-B',PORT/'tools/record_target_step.py','--kind',kind,
              '--record',record,'--cwd',self.root,'--source',source,
              '--output',output,'--depfile',depfile]
        for label,path in self.roots:args+=['--root',label+'='+str(path)]
        for item in dict.fromkeys([self.root/'build.json',Path(__file__).resolve(),*self.common_inputs,*inputs]):
            args+=['--input',item]
        for item in secondary:args+=['--secondary-output',item]
        if kind=='c-compile':
            args+=['--nested-executable',self.bin/'ez80-none-elf-as',
                   '--driver-selected-executable',self.bin/'ez80-none-elf-as']
        for item in link_inputs:
            args+=['--link-input',item]
            if item in self.producers:args+=['--producer',item,self.producers[item]]
        self.command(name.replace('/','-'),[*args,'--',*command])
        self.producers[output]=record

    def tool(self,name):return self.bin/('ez80-none-elf-'+name)

def product_checks(builder,config,root,elf):
    for number,name in enumerate(config['firmware_link_checks']):
        builder.command('product-check-'+str(number),[sys.executable,root/name,
            '--source',root,'--elf',elf,'--nm',builder.tool('nm'),
            '--objdump',builder.tool('objdump')])

def build(root,toolchain,output,reference=None):
    config=profile(root)
    policy=json.loads((PORT/'runtime/runtime_policy.json').read_text())
    if digest(toolchain/'lib/libagon.a')!=policy['archive_sha256']:
        raise ValueError('unqualified libagon.a selection')
    version=subprocess.check_output([str(toolchain/'bin/ez80-none-elf-clang'),'--version'],text=True)
    if 'c76386c0083e6a6236ff774275227e2389f85538' not in version:
        raise ValueError('unqualified compiler selection')
    aliases=verify_register_aliases(root/'src/equs.inc',toolchain/'include/ez80f92.inc')
    output.mkdir(parents=True,exist_ok=False)
    b=Builder(root,toolchain,output)
    start=time.monotonic()
    inputs=[root/'build.json',Path(__file__).resolve(),PORT/'ld/mos.ld',
        PORT/'include/ez80.h',PORT/'runtime/runtime_policy.json',toolchain/'lib/libagon.a',PORT/'runtime/formatter/firmware_printf.c',
        PORT/'runtime/helpers/i48_required.asm',PORT/'runtime/vendor/nanoprintf/nanoprintf.h']
    inputs += [root/p for p in config['c_sources']+config['asm_sources']]
    inputs += [root/p for p in config['firmware_link_checks']]
    inputs += [p for top in ('src','src_startup','src_fatfs','src_umm_malloc') for p in (root/top).rglob('*') if p.is_file() and p.suffix in ('.inc','.h')]
    inputs += b.common_inputs
    inputs += [PORT/p for p in ('tools/record_target_step.py','tools/profile_assembly.py',
        'runtime/build_runtime_archive.py','runtime/audit_runtime.py','runtime/scan_formats.py',
        'runtime/formatter/host_golden.c','runtime/verify_i48_helpers.py','hostfs_descriptor.asm','verify_firmware.py')]
    inputs += [b.tool(name) for name in ('clang','as','ld','ar','objcopy','nm','readelf','objdump','size')]
    before={str(p):digest(p) for p in inputs}
    (output/'inputs.json').write_text(json.dumps(b.sanitized(before),indent=2)+'\n')
    cflags=['-target','ez80-none-elf','-march=ez80','-mllvm','-z80-gas-style',
        '-mllvm','-z80-print-zero-offset','-std=gnu17','-Wall','-Wextra',
        '-Werror=return-type',config['c_optimization'],'-ffreestanding',
        '-fno-threadsafe-statics','-fno-integrated-as','-B'+str(b.bin),'-Wa,-march=ez80+full']
    includes=['-I'+str(PORT/'include'),*['-I'+str(root/p) for p in ('src','src_fatfs','src_startup','src_umm_malloc')],
        '-nostdinc','-isystem',str(toolchain/'include'),'-DAGONDEV','-D_EZ80','-D_EZ80F92','-DNDEBUG',*config['cppflags']]
    c_objects=[]
    for name in config['c_sources']:
        obj=output/'obj'/Path(name).with_suffix('.o')
        flags=cflags+([config['c_overrides'][name]] if name in config['c_overrides'] else [])
        b.target('compile/'+str(Path(name).with_suffix('')),'c-compile',root/name,obj,
            [b.tool('clang'),*includes,*flags,'-MD','-MF',obj.with_suffix('.d'),'-c',root/name,'-o',obj])
        c_objects.append(obj)
    asm_objects=[]
    for name in config['asm_sources']:
        obj=output/'obj/asm'/Path(name).with_suffix('.o')
        b.target('assemble/'+str(Path(name).with_suffix('')),'direct-assembly',root/name,obj,
            [b.tool('as'),'--MD',obj.with_suffix('.d'),'-march=ez80+full+adl',
             '-I',root/'src','-I',root/'src_startup','-I',toolchain/'include',root/name,'-o',obj])
        asm_objects.append(obj)
    runtime=output/'runtime'
    runtime.mkdir()
    printf=runtime/'firmware_printf.o'
    runtimeflags=['-target','ez80-none-elf','-march=ez80','-mllvm','-z80-gas-style',
        '-mllvm','-z80-print-zero-offset','-std=gnu17','-Wall','-Wextra','-Oz',
        '-ffreestanding','-fno-builtin','-fno-threadsafe-statics','-Wa,-march=ez80+full',
        '-fno-integrated-as','-B'+str(b.bin),'-nostdinc','-isystem',str(toolchain/'include'),
        '-iquote'+str(PORT/'runtime/vendor/nanoprintf')]
    b.target('compile/runtime/firmware_printf','c-compile',PORT/'runtime/formatter/firmware_printf.c',printf,
        [b.tool('clang'),*runtimeflags,'-MD','-MF',printf.with_suffix('.d'),'-c',PORT/'runtime/formatter/firmware_printf.c','-o',printf])
    i48=runtime/'i48_required.o'
    b.target('assemble/runtime/i48_required','direct-assembly',PORT/'runtime/helpers/i48_required.asm',i48,
        [b.tool('as'),'--MD',i48.with_suffix('.d'),'-march=ez80+full',PORT/'runtime/helpers/i48_required.asm','-o',i48])
    b.command('i48-equivalence',[sys.executable,PORT/'runtime/verify_i48_helpers.py',
        '--ar',b.tool('ar'),'--nm',b.tool('nm'),'--objdump',b.tool('objdump'),
        '--archive',toolchain/'lib/libagon.a','--local',i48])
    archive=runtime/'libmos_runtime.a'
    archive_builder=load('native_archive',PORT/'runtime/build_runtime_archive.py')
    members=archive_builder.build(b.tool('ar'),toolchain/'lib/libagon.a',[printf,i48],archive,policy)
    (runtime/'archive.json').write_text(json.dumps({'source_sha256':policy['archive_sha256'],
        'ar_sha256':digest(b.tool('ar')),'builder_sha256':digest(PORT/'runtime/build_runtime_archive.py'),
        'local_objects':{p.name:digest(p) for p in (printf,i48)},'members':members,
        'member_sha256':{p.name:digest(p) for p in (runtime/'runtime-members').iterdir()},
        'output_sha256':digest(archive)},indent=2)+'\n')
    probe=runtime/'c-runtime-linked.o'
    b.command('runtime-link-probe',[b.tool('ld'),'-r','-o',probe,*c_objects,archive])
    audit=load('native_runtime_audit',PORT/'runtime/audit_runtime.py')
    extras=[str(Path(n).with_suffix('.o')) for n in config['c_sources'] if str(Path(n).with_suffix('.o')) not in policy['c_objects']]
    audit_report,errors=audit.audit(b.tool('nm'),b.tool('readelf'),b.tool('ar'),b.tool('size'),
        output/'obj',toolchain/'lib/libagon.a',PORT/'runtime/vendor/nanoprintf/nanoprintf.h',
        root,[printf,i48],probe,archive,policy,extras,config['asm_sources'],
        [str(Path(n).with_suffix('.o')) for n in config['asm_sources']])
    (runtime/'audit.json').write_text(json.dumps(b.sanitized({'errors':errors,**audit_report}),indent=2)+'\n')
    if errors:raise ValueError('runtime audit: '+str(errors))
    b.command('format-scan',[sys.executable,PORT/'runtime/scan_formats.py','--source',root,'--json'])
    golden=runtime/'host-golden'
    b.command('host-formatter-compile',['cc','-std=c17','-Wall','-Wextra','-Werror','-fno-builtin',
        '-iquote'+str(PORT/'runtime/vendor/nanoprintf'),PORT/'runtime/formatter/host_golden.c','-o',golden])
    b.command('host-formatter-run',[golden])
    descriptor=output/'obj/hostfs_descriptor.o'
    b.target('assemble/hostfs_descriptor','direct-assembly',PORT/'hostfs_descriptor.asm',descriptor,
        [b.tool('as'),'--MD',descriptor.with_suffix('.d'),'-march=ez80+full+adl',PORT/'hostfs_descriptor.asm','-o',descriptor])
    binary_dir=output/'bin';binary_dir.mkdir()
    elf=binary_dir/'MOS.elf'
    objects=[*asm_objects,*c_objects,descriptor,archive]
    b.target('link/firmware','final-link',PORT/'ld/mos.ld',elf,
        [b.tool('ld'),'--orphan-handling=error','-T',PORT/'ld/mos.ld','-Map',binary_dir/'MOS.map',
         '--dependency-file',elf.with_suffix('.d'),'-o',elf,*objects],
        secondary=[binary_dir/'MOS.map'],link_inputs=objects)
    for fmt,suffix in [('binary','bin'),('ihex','hex')]:
        b.command('objcopy-'+suffix,[b.tool('objcopy'),'-O',fmt,elf,binary_dir/('MOS.'+suffix)])
    b.command('verify-firmware',[sys.executable,PORT/'verify_firmware.py',elf,binary_dir/'MOS.bin','--toolbin',b.bin])
    product_checks(b,config,root,elf)
    after={str(p):digest(p) for p in inputs}
    if before!=after:raise ValueError('source/infrastructure changed during build')
    image=binary_dir/'MOS.bin'
    if reference:
        pin=config['reference_binary']
        if digest(reference)!=pin['sha256'] or reference.stat().st_size!=pin['bytes']:
            raise ValueError('reference binary does not match pinned migration control')
        if image.read_bytes()!=reference.read_bytes():raise ValueError('native image differs from migration reference')
    result={'schema':1,'status':'pass','rom_bytes':image.stat().st_size,'sha256':digest(image),
        'reference_equal':True if reference else None,'emulator_qualified':False,'hardware_qualified':False,
        'elapsed_seconds':time.monotonic()-start,'steps':b.steps,
        'verified_register_aliases':aliases,'inputs_sha256':digest(output/'inputs.json')}
    if (root/'.git').exists():
        result['source_identity']={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            'dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=root))}
    else:result['source_identity']={'head':None,'mode':'isolated-migration-control'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result|{'output':str(output)},indent=2))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--toolchain',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--reference-bin',type=Path)
    args=parser.parse_args()
    root=args.source_root.resolve(strict=True)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output=args.output.absolute() if args.output else root/'.build'/stamp
    if output.exists() or output.is_symlink():raise ValueError('fresh output directory required')
    build(root,args.toolchain.resolve(strict=True),output,args.reference_bin)

if __name__=='__main__':main()
