# Assembly Compatibility Strategy

Status: initial approach selected for experiment
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

The author advises taking the most conservative approach and has deferred the
choice of the initial experiment to Codex. The selected first attempt is a
strict Python compatibility preprocessor that retains ZDS-oriented maintained
source and emits generated GNU-as input. This is provisional until its
translation and diagnostic behavior pass the gates described below.

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

Local-label scoping is a strong candidate for ongoing compatibility support.
Whether other ZDS forms—numeric literals, macros, data directives, conditionals,
or section declarations—remain frontend features or receive one-time source
conversion should be decided construct by construct. There is no requirement
that every incompatibility use the same mechanism.

## 3. Options considered

### 3.1 Strict ZDS-to-GAS source preprocessor — selected initial attempt

Maintain ZDS-oriented source and generate GNU-as source during the build. A
two-pass parser identifies scope and macro boundaries, builds a local-symbol
table, validates every definition and reference, then renders deterministic
assembler input plus a source/mapping manifest.

The proposed initial label mappings are:

| Maintained-source construct | Generated GNU-as form |
|---|---|
| anonymous `$$:` | a reusable numeric label such as `99:` |
| anonymous `$F` / `$B` | `99f` / `99b` |
| named `$loop` inside `SCOPE` | deterministic `.Lzds_<file>_<scope>_loop` |
| macro-local `$$loop` | GNU macro `LOCAL` or `.L...\@` |
| ordinary public/private label | unchanged |

GNU numeric labels are specifically designed for repeated definitions and
nearest forward/backward resolution, so they preserve the anonymous-label
idiom without inventing globally unique names. GNU `.L` symbols remain local
and normally disappear from the linked symbol table. The generated mangled
spellings are implementation details, not maintained names.

The installed AgonDev GNU assembler was directly tested with repeated `99:`
definitions and `99f`/`99b` references. It was also tested with two expansions
of a macro using both `LOCAL` and `\@`-derived labels; the expansions resolved
independently and did not expose the macro-local symbols in the object symbol
table.

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

The initial frontend should preserve input line count wherever practical and
emit line directives or a sidecar mapping when exact preservation is impossible.
Generated files should contain a header naming the input commit and frontend
version and should never be edited manually.

It should recognize tokens rather than run unrestricted regular-expression
replacement. At minimum it must distinguish code, labels, expressions,
comments, quoted strings, macro definitions, macro invocations, includes, and
conditional regions sufficiently to make local-symbol transformation safe.

The frontend should reject malformed or ambiguous input, including a named
local outside a scope, duplicate named locals within a scope, unresolved local
references, nested or otherwise unsupported scopes, ambiguous macro-local
syntax, and local-label forms it has not explicitly implemented. Its diagnostic
should cite the original file, line, construct, and scope.

Source names need not be forced to remain ZDS syntax forever. The supported
language may deliberately allow both the familiar form and native GNU idioms:
numeric `1f`/`1b` labels, `.L` labels, and GNU macro-local constructs should
pass through. This lets maintainers use anonymous-label idioms naturally and
adopt GAS features incrementally without a flag day.

## 5. Validation strategy and decision gate

The frontend should have lexical unit tests, golden source-to-source fixtures,
negative diagnostic fixtures, assembler/object tests, and subsystem tests drawn
from real MOS sources. Tests must include repeated anonymous labels, multiple
forward references, backward loops, reused named locals across adjacent scopes,
macro expansion at multiple call sites, includes, conditional assembly, and
mixed public/local references.

Object-level checks should compare sections, symbol binding, relocations,
branch targets, and disassembly. Where a same-source ZDS object or firmware
binary is available, binary comparison is valuable evidence, especially for
instruction selection and section order; it is validation rather than the
mechanism used to recover ordering.

The initial approach is accepted for continued use only if representative MOS
subsystems assemble without maintained-source globalization, diagnostics map
cleanly back to source, generated output is deterministic, and object-level
evidence shows preserved control flow and layout. If those criteria fail, the
next choices are selective native-GAS conversion for simple idioms, a limited
macro-wrapper technique, or reassessment of an assembler extension. The
separate-object approach remains available only for isolated cases where its
ordering cost is explicitly justified.

Implementation work for this decision remains exclusively under `PORT-101` in
the authoritative `TODO.md`.
