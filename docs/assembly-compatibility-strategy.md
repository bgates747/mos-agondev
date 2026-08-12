# Assembly Compatibility Strategy

Status: strict compatibility frontend accepted for ongoing use
Decision owner: project author, delegating the initial technical choice to Codex

## 1. Purpose and maintenance principle

The assembly port should preserve as much as practicable of the vocabulary and
structure familiar to current `agon-mos` maintainers. In particular, the port
must not require maintainers to globalize labels that are presently local under
ZDS `SCOPE`. Anonymous forward/backward labels and macro-local labels should
remain available as idioms, even where the compatibility layer maps them to
different GNU assembler syntax.

This is not solely a convenience issue. Local labels communicate ownership and
limit accidental coupling. Replacing them with hand-maintained global names
would enlarge the visible namespace, create collision risk, add review noise,
and impose a permanent maintenance tax unrelated to firmware behavior.

The author advised taking the most conservative approach and deferred the
initial technical choice to Codex. The resulting strict Python compatibility
frontend retains ZDS-oriented maintained source and emits generated GNU-as
input. It has passed the translation, diagnostic, object, and full-corpus gates
described below and is accepted as normal build infrastructure.

## 2. Two distinct kinds of tooling

The project distinguishes two tool categories because they have different
lifetime and compatibility obligations.

### 2.1 Initial port-preparation tools

Migration tools perform bounded transformations used to establish the port.
Examples include inventory generation, one-time header changes, linker-script
construction, source comparisons, or converting constructs that the project
chooses not to retain. Their output may become maintained source after review.
Such tools need reproducibility and auditability, but do not necessarily become
part of every future build.

### 2.2 Ongoing assembly compatibility frontend

An ongoing preprocessor is part of the supported source language and normal
build. Maintainers continue writing agreed ZDS-like constructs; generated GAS
source remains ignored build output. This tool must therefore be deterministic,
strict, documented, fast, stable across includes, and covered by semantic tests.
It must provide useful source locations and must fail rather than guess about
unsupported or ambiguous syntax.

Local-label scoping is ongoing compatibility behavior. The implementation also
retains the audited MOS forms of numeric literals, macros, data directives,
conditionals, section declarations, includes, and public structure definitions.
Three conditional branches whose range depended on ZDS relaxation remain
explicit one-time preparation edits; not every incompatibility is forced
through the frontend.

## 3. Options considered

### 3.1 Strict ZDS-to-GAS source frontend — accepted implementation

Maintain ZDS-oriented source and generate GNU-as source during the build. A
two-pass parser identifies scope and macro boundaries, builds a local-symbol
table, validates every definition and reference, then renders deterministic
assembler input plus a source/mapping manifest.

The implemented label mappings are:

| Maintained-source construct | Generated GNU-as form |
|---|---|
| anonymous `$$:` | deterministic generated `.Lzds_...` identity |
| anonymous `$F` / `$B` | nearest generated forward/backward identity |
| named `$loop` inside `SCOPE` | deterministic `.Lzds_<file>_<scope>_loop` |
| suffix local `loop?` inside `SCOPE` | deterministic scope-private `.Lzds_...` identity |
| macro-local `$$loop` | expansion-private `.L...\@` identity |
| ordinary public/private label | unchanged |

The frontend resolves nearest forward/backward identities explicitly and emits
GNU `.L` symbols, which remain local and normally disappear from the linked
symbol table. This avoids reserving or colliding with any numeric label that a
maintainer may use natively. Generated spellings are implementation details,
not maintained names.

The installed AgonDev GNU assembler was directly tested with repeated numeric
labels and directional references as an initial mechanism. The frontend emits
unique `.L` identities instead, avoiding collisions with native numeric labels.
GAS was also tested with repeated macro expansions; `\@`-derived identities
resolved independently and did not expose macro-local symbols in the object
symbol table.

Advantages include conservative source preservation, one normal object per
source file, deterministic ordering, ordinary linker behavior, and a bounded
implementation that does not fork Binutils. The cost is that the frontend
becomes maintained build infrastructure and must understand enough lexical
context to avoid rewriting comments, strings, macro arguments, or unrelated
uses of `$`.

### 3.2 Direct one-time conversion to GNU local idioms

Convert anonymous labels to numeric labels, macro locals to `LOCAL` or `\@`, and
named scoped labels to hand-maintained `.L` names. This removes an ongoing
preprocessor and uses only native GAS source afterward.

It is viable for anonymous and macro-local labels, because the replacement
idioms remain genuinely local. It is not acceptable as the default treatment
of named ZDS scopes: maintainers would still have to choose and preserve unique
spellings, recreating much of the manual globalization burden. This option may
still be used selectively where maintainers prefer native GAS syntax.

### 3.3 Wrap each ZDS scope in an immediately expanded GNU macro

Generate a `.macro` for each scope, declare its local symbols with GNU
`.altmacro`/`LOCAL`, and immediately expand it. Public labels inside the macro
remain visible while its local names receive assembler-generated identities.

This delegates uniqueness to GAS and avoids explicit mangled names. A direct
probe confirmed that it works for simple code. The risk is semantic context:
arbitrary source inside a macro can interact differently with escaping, token
concatenation, nested macro definitions, conditional assembly, diagnostics,
and argument substitution. It is an interesting fallback or scoped optimization
but is too magical for the universal first implementation.

### 3.4 Extend the AgonDev GNU assembler

Add first-class `SCOPE` semantics and ZDS-local symbol lookup to the AgonDev
Binutils fork. This gives the best source experience and could eventually make
the compatibility feature useful beyond MOS.

It is also the largest maintenance commitment: parser and symbol-table changes,
macro/include behavior, diagnostics, listings, relocations, tests, toolchain
distribution, and possible upstream coordination. It remains a reasonable
future direction if the Python frontend proves broadly valuable but difficult
to maintain. It is not justified as the first experiment.

### 3.5 Split scopes into separate object files

Generate one assembly unit per ZDS scope so identical local spellings live in
separate assembler symbol tables, then reconstruct source order in the link.
This is the technique the author previously used while porting BBC BASIC V3.
It works, but required binary comparison against a reference to recover and
verify ordering.

For MOS it would complicate section ordering, shared macros/constants,
inter-scope references, code/data interleaving, diagnostics, and linker inputs.
It also moves a source-language problem into linker orchestration. Because the
project already has a substantial fixed-layout linker contract, adding this
coupling is undesirable. This remains a last-resort technique for a genuinely
isolated source region, not a general strategy.

### 3.6 Adopt another assembler or compatibility assembler

A separate assembler could theoretically accept ZDS syntax and emit ELF or
objects suitable for the GNU link. This would avoid maintaining the frontend
inside this repository if a sufficiently compatible implementation existed.

The practical risks are eZ80 ADL opcode coverage, object format and relocation
compatibility, C ABI symbol conventions, section control, active maintenance,
and introducing another toolchain pin. No currently audited candidate has been
shown to satisfy the MOS contract, so this is a research alternative rather
than the initial plan.

## 4. Selected frontend behavior

The accepted implementation is `projects/mos-port/tools/zds2gas.py`. It runs
lexical analysis and rendering as separate passes, distinguishing code,
comments, quoted strings, labels, expressions, macro definitions and calls,
includes, and directives. It fails on ambiguous dollar syntax and unresolved,
duplicate, or case-mismatched local symbols instead of guessing. Diagnostics
from the frontend cite the original source path and line with a stable error
code.

`INCLUDE` is a textual operation before analysis. A `SCOPE` begun in an include
therefore affects following included or caller text just as it did under ZDS.
An included `END` returns to its caller, while the root `END` terminates the
translation unit. Lookup accepts an exact name or one unique case-insensitive
match to preserve the historical Windows behavior. Ambiguous case-folded names,
absolute paths, symlinked files, unresolved paths, and targets outside the
allow-listed source or toolchain roots are rejected. The manifest records every
include edge, every contributing file and hash, and every generated-to-original
line mapping.

Generated files are disposable and always newline-terminated. Their header
names the frontend schema, translation unit, prepared source identity, and hash
of the expanded input. The source identity is the actual `agon-mos` `HEAD`,
with `+tracked-dirty` when tracked source differed from that commit at
preparation time. Untracked files do not affect it because the prepared tree
copies only Git-tracked files.

Preparation writes `.mos-agondev-worktree.json` into the ignored worktree. Its
schema records the source `HEAD`, tracked-dirty boolean, and a sorted inventory
of every prepared tracked path with SHA-256 and executable bits. Before any
tree translation, the frontend validates the sidecar and the complete prepared
tree against one another, including the absence of undeclared files and
symlinks. Missing, malformed, or stale provenance is an error. The generated
manifest records the effective identity and the validated sidecar hash; the
frozen research baseline is not a normal generation dependency. Generated
files must never be edited manually.

The audited source-language surface includes:

- `$name` and `name?` locals with case-exact scope lookup;
- nearest-definition `$$:`, `$F`, and `$B` anonymous labels using unique GNU
  `.L` identities rather than a reserved numeric label;
- expansion-private `$$name` macro locals and case-sensitive macro names and
  parameters;
- immutable `EQU`/`.set` handling, with identical duplicates elided and
  conflicting definitions rejected;
- the MOS numeric literals, sections, conditional directives, data widths,
  reserves, macro token concatenation, and wide-register copy forms exercised
  by the pinned source; and
- `.STRUCT`/`.ENDSTRUCT` definitions containing literal-sized `DS` members and
  previously defined `.TAG` types. These emit absolute member/size symbols and
  allocate no storage.

Native GNU constructs such as numeric `1f`/`1b` labels and `.L` symbols remain
available where they do not conflict with an explicitly translated form. This
allows incremental adoption without globalizing maintained ZDS locals.

The assembly recipe invokes `projects/mos-port/tools/assemble_zds.py` instead
of calling GAS directly. Before execution, this wrapper validates the manifest
schema, normalized relative names, duplicate outputs, regular-file and symlink
constraints, output hash, line-map length, and original source locations. It
then appends the validated generated source to the requested assembler command.
Exact GAS references to that generated path are rewritten through the manifest,
including references to flattened include lines. The assembler's exit status
and stdout are preserved; unrelated, malformed, binary, or honestly unmapped
stderr remains byte-for-byte unchanged.

The boundary is deliberate. Nested macros or structures, `SCOPE` and scoped
`$name`/`name?` locals inside macros, forward or recursive `.TAG` references,
nonliteral structure sizes, and structure storage directives other than `DS`
and prior `.TAG` are unsupported. Conditional bodies are transformed lexically
and evaluated by GAS, so mutually exclusive branches must still use distinct
definition names. Other unaudited ZDS syntax remains unsupported until it gains
positive, negative, object, and corpus tests.

## 5. Validation strategy and decision gate

The acceptance suite includes lexical and source-location unit tests, exact
positive and negative golden fixtures, nested include/case/`END` tests,
conditionals, repeated anonymous labels, multiple forward references, backward
loops, adjacent scopes, repeated macro expansion, and mixed public/local
references. Object checks cover emitted bytes, section behavior, public symbol
binding, undefined-symbol relocation, local-symbol visibility, resolved branch
targets, and disassembly. A standalone object test validates the public
`mos_api.inc` structure offsets even though that include is not consumed by the
15 firmware assembly roots.

Wrapper tests cover valid root and included-source remapping, a real AgonDev GAS
failure, optional columns and line endings, non-UTF-8 continuation data,
unmapped and malformed diagnostics, exit/stdout preservation, stale hashes,
schema errors, traversal, duplicate outputs, external generated sources, and
symlinks. The deterministic corpus test independently translates the tree twice
and assembles every generated root. Preparation/frontend tests additionally
cover clean and tracked-dirty identities, deterministic metadata, missing or
malformed sidecars, content and executable-mode drift, extra files, and
symlinks in prepared input.

The decision gate passed: all 15 build-critical assembly roots translate and
assemble without maintained-source globalization; generated output and
provenance are deterministic; GAS diagnostics map to original paths and lines;
and object evidence verifies labels, relocations, control flow, and layout. The
same objects link into the verified 102,059-byte AgonDev MOS firmware image.
The strict frontend is therefore accepted for ongoing use on its audited
language surface.

Binary comparison with a same-source ZDS build remains useful future evidence,
but is not used to infer source order or to broaden the accepted syntax. Three
out-of-range conditional branches remain reviewed one-time source-preparation
edits because GAS does not perform ZDS's silent branch relaxation. Physical
hardware qualification and behavioral emulator expansion are separate from the
assembly-language compatibility decision.
