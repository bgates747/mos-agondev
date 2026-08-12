# Assembly port area

The accepted ongoing compatibility frontend lives at
`projects/mos-port/tools/zds2gas.py`.
Maintainers continue to use the audited ZDS idioms in the prepared source tree;
the normal build writes 15 disposable GNU-as translation units and a
deterministic mapping manifest to `projects/mos-port/generated/`.

The frontend textually expands `INCLUDE` files, so `SCOPE` continues across
include boundaries and an included `END` returns to its caller. Include lookup
accepts a unique case-insensitive match, matching the historical Windows build,
but rejects ambiguous case-folded names. It preserves named `$local` and
`local?` labels without globalizing maintained source, resolves `$$`/`$F`/`$B`
to collision-proof generated `.L` identities, and gives every macro expansion
private `$$name` labels via `\@`. It also handles the audited MOS
directive, macro, numeric-literal, section, and register-copy subset. The public
`mos_api.inc` structure surface is translated to absolute member offsets and
sizes: `DS` and previously defined `.TAG` members are supported between
`.STRUCT`/`.ENDSTRUCT`, without allocating storage. That public include is not
used by the 15 firmware roots, so its layout is verified in a standalone object
test. Unknown or ambiguous dollar syntax, case-mismatched local/macro names,
and conflicting immutable `EQU` definitions are errors with original source
locations. The manifest records every expanded source location and SHA-256.

Every generated unit starts with the pinned `agon-mos` commit, frontend schema,
translation-unit name, and expanded-input hash. The pinned baseline is an
explicit generation dependency. The normal object recipe invokes
`projects/mos-port/tools/assemble_zds.py`, which rejects stale output, unsafe or duplicate
manifest names, invalid line maps, non-UTF-8 generated source, and symlinked
manifest or generated files before running GNU as. It rewrites exact GNU-as
diagnostics through the manifest, including errors originating in flattened
include files, while preserving assembler stdout, exit status, malformed or
unrelated stderr, and diagnostics for generated lines that cannot be mapped
honestly. Relative includes such as startup's `../src/equs.inc` are accepted
only when their resolved target remains under an allow-listed source or
toolchain root.

The supported language boundary is intentionally narrower than all of ZDS.
Nested macros and structures, `SCOPE` or scoped `$name`/`name?` labels inside a
macro, forward or recursive `.TAG` references, and structure members other than
literal-sized `DS` and prior `.TAG` types are rejected. Conditional directives
are passed to GAS and transformed lexically, so definitions in mutually
exclusive branches must still have distinct maintained-source names. Absolute,
outside-root, symlinked, unresolved, and ambiguously cased includes are also
rejected.

Run `make asm-probe` at repository root. All 15 build-critical assembly units
must translate and assemble. Run the focused acceptance suite with
`.venv/bin/python -B -m unittest tests.test_zds2gas tests.test_assemble_zds -v`.
It covers lexical behavior, nested includes, conditionals, positive and negative
goldens, object bytes, structure offsets, symbol binding, relocation,
disassembly, real-GAS diagnostic remapping, process semantics, path safety, and
the deterministic full corpus. Generated files are not maintained source and
must not be edited.

Three out-of-range conditional branches that ZDS silently relaxed are explicit
one-time preparation edits in `scripts/prepare_mos_worktree.py`. Keeping those
source-level decisions outside the ongoing frontend prevents it from silently
changing instruction selection.
