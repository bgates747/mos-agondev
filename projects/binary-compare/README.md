# Firmware comparison

This project compares the AgonDev-built MOS image with the newest official
upstream release using scripts, maps, symbols, object files, compiler output,
and eZ80 ADL disassembly. It deliberately does not ask a maintainer to inspect
two entire ROMs by hand.

The pinned reference is the official Platform MOS `v3.0.2` release at commit
`8336409351ee5314e02801a7b72a4f1bb5282519`, published 2026-03-01. Its release
contains `MOS.bin`, `MOS.hex`, and—especially usefully—the matching ZDS II
`MOS.map`. `reference/v3.0.2.json` records the official URLs, byte sizes, and
SHA-256 values. The map identifies ZDS II eZ80Acclaim 5.3.5 Build 23020901,
IEEE 695 linker 6.25, module/segment extents, external symbols, and absolute
linker constants; its command list also supplies the compiler, assembler, and
linker options retained in sanitized report metadata. No matching ZDS listing,
object, or source-annotated disassembly is published with that release.

Release assets are downloaded into ignored `projects/binary-compare/artifacts/`;
they are never silently accepted. Every use checks the recorded size and hash.
The networked fetch also asks GitHub's latest-release and tag APIs to prove that
the manifest still names the newest publication and exact source commit.
To fetch them and run the reviewed comparison from the repository root:

```bash
make binary-reference
make binary-compare
```

The first command needs network access once. An already downloaded release can
instead be imported without network access:

```bash
.venv/bin/python projects/binary-compare/fetch_reference.py \
  --source-dir PATH_TO_OFFICIAL_RELEASE_ASSETS
make binary-compare
```

## What the automation retains

`collect_candidate.py` captures the linked ELF, binary, GNU map, linked symbol
table, relocations, sections, disassembly, every object symbol table and
relocated disassembly, the restricted runtime archive, frontend-generated
GNU-as units, and Clang-emitted assembly for all 16 C units. It also records
the prepared-source provenance and an exact diff inventory between maintained
MOS source and the disposable build worktree. Generated paths are sanitized
and the manifest covers every retained file; missing, extra, changed, or
symlinked artifacts fail closed.

`analyze.py` then:

1. parses ZDS and GNU module ranges, including ZDS `User Defined` linker
   constants;
2. pairs exact-name symbols and records address deltas and function ordering;
3. maps matching ZDS source modules to AgonDev input sections;
4. partitions every matched executable handwritten-assembly module at trusted
   shared symbols, including module-start and module-end gaps;
5. compares bytes first, then conservatively covers differences with recognized
   little-endian address relocations or normalizes disassembly operands only
   when both sides resolve to the same shared symbol, symbol-relative offset,
   or equal module-relative offset; and
6. emits `report.json`, `report.md`, and a bounded `review-queue.json`.

It also retains `reference.disassembly.txt`, a complete raw eZ80 ADL
disassembly of the ZDS image. It is an inspection aid, not a source-boundary
oracle; embedded tables may decode as instructions, so automated conclusions
use trusted map ranges and conservative byte coverage instead.

Equal numeric constants are not rewritten merely because they look like
addresses. Differing values which cannot be paired are not normalized.
Instruction lengths, layouts, constants, and control flow therefore remain
visible. Raw-binary statistics are reported but are not used as a semantic
test: different C compilers and section layouts make same-offset byte counts
mostly noise.

The classifications are evidence labels, not proofs of whole-program semantic
equivalence:

- `exact` means the bounded bytes are identical;
- `relocation-only` means every changed byte or instruction operand is covered
  by a recognized paired address relationship;
- `reordered` is reported for exact-name external symbols whose relative order
  changed, without claiming their bodies are equivalent;
- `explained-source-divergence` requires a maintained-source change relative to
  the official release;
- `compiler-codegen-different` deliberately makes no static semantic claim and
  sends the C/data module to the medium-priority review inventory; and
- `unexplained` is high-priority and makes evidence verification fail.

`semantically-equivalent` is intentionally not emitted by the current static
analyzer: different compiler output is only promoted out of the queue when a
separate behavioral or ABI regression establishes the relevant contract. This
is safer than guessing equivalence from similar-looking disassembly.

For C, the scripts still do substantially more than a module-size diff. They
inventory every safe exact-name external anchor, use the next ZDS external
anchor or module end as the explicit reference bound, use the ELF symbol size
as the candidate bound, and attempt the same conservative comparison. The map
does not publish ZDS private/static function sizes, so the boundary basis is
retained with every result and no external-anchor range is called a function
when that cannot be proved.

## Reviewed v3.0.2 result

The initial comparison is recorded in
`evidence/binary-compare-v3.0.2.json`. The 108,490-byte official ZDS image and
102,059-byte AgonDev candidate have only a five-byte common prefix, confirming
that a naive whole-image diff is not useful. The ZDS map nevertheless yields
506 external definitions and 468 exact-name pairs.

All 8,049 matched executable bytes from the official handwritten assembly are
covered by 51 complete slices. Twenty-three slices are byte-identical, 27 are
relocation-only, and one is the four-byte post-v3.0.2 oversized-VDP discard fix
which is both a recorded source divergence and an independently executed regression.
There are no unexplained handwritten-assembly slices. The corresponding
AgonDev assembly is 8,053 bytes because of that fix. The SD `TEXT` constant
table is independently byte-identical.

In concise terms, the maintained handwritten assembly is therefore
effectively byte-for-byte identical after accounting for relocation and that
known bug fix. The bulk of the remaining whole-image differences comes from
different Zilog versus AgonDev/Clang C code generation, replacement runtime
libraries, and the resulting section and symbol layout. Those C differences
are regression-test inputs, not static proof that the generated programs are
semantically equivalent.

The ZDS map inventory has 128 module/segment ranges: 40 maintained-source ROM
ranges are compared, 11 are RAM/data address-space records, 76 belong to ZDS
runtime libraries replaced by the audited AgonDev runtime, and one is ZDS's
one-byte `zsldevinitdummy` source object with no candidate counterpart. Nothing
is silently dropped from the reference inventory.

Four of 29 multi-symbol modules changed external-symbol order: three MOS C
modules, where different compiler ordering is expected but not assumed
equivalent, and one ZDS runtime-library module outside the maintained source
module comparison. The remaining 24 review entries are bounded C code or data
modules plus the explained VDP change. Existing boot/shell parity, formatter,
ABI, linker, VDP, and target-contract tests provide behavioral coverage; the
queue is the input for further PORT-201 and PORT-202 expansion rather than a
request for an unbounded manual disassembly pass.

The report also contains 248 individual C external-anchor comparisons. None
has an identical bounded instruction stream across the two compilers, so all
remain honestly labeled `compiler-codegen-different`; their complete inventory
digest is part of the reviewed evidence.

`verify_report.py` hashes the complete range classification inventory and
compares the reviewed facts with the committed evidence. It refuses drift and
prints the explicit review command rather than updating evidence automatically:

```bash
make binary-compare
# inspect projects/binary-compare/artifacts/report/report.md and review-queue.json
make binary-compare-record   # only after intentional human review
```

Changing the evidence is not a way to make a failed comparison pass. It is the
record of a review decision and should be committed with the source or build
change that explains every new high-priority difference.
