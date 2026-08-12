# Assembly port area

The accepted ongoing compatibility frontend lives at
`projects/mos-port/tools/zds2gas.py`.
Maintainers continue to use the audited ZDS idioms in maintained MOS source;
preparation preserves them in the disposable copied tree, and the normal build
writes 15 disposable GNU-as translation units plus a deterministic mapping
manifest to `projects/mos-port/generated/`.

This is a corpus-driven compatibility frontend, not a complete implementation
of the ZDS II assembly language. Its behavior was derived from constructs found
in the maintained MOS tree and a small set of separately exercised public
include forms; no exhaustive exploration of all ZDS II syntax, directives,
expression rules, macro facilities, or assembler behavior has been performed.
Passing the full corpus proves only the declared audited surface below.

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

Every generated unit starts with the prepared source identity, frontend schema,
translation-unit name, and expanded-input hash. The identity is the actual
source `HEAD`, suffixed with `+tracked-dirty` when tracked source differed from
that commit during preparation; untracked source is deliberately excluded
because preparation copies only Git-tracked files.

`scripts/prepare_mos_worktree.py` writes
`worktree/.mos-agondev-worktree.json` with that source state plus the exact
prepared-file inventory, SHA-256 hashes, and executable bits. Tree translation
validates the sidecar against the complete input tree and fails closed when it
is missing, malformed, or stale. The frozen research baseline is not a normal
generation input. The normal object recipe invokes
`projects/mos-port/tools/assemble_zds.py`, which rejects stale output, unsafe or duplicate
manifest names, invalid line maps, non-UTF-8 generated source, and symlinked
manifest or generated files before running GNU as. It rewrites exact GNU-as
diagnostics through the manifest, including errors originating in flattened
include files, while preserving assembler stdout, exit status, malformed or
unrelated stderr, and diagnostics for generated lines that cannot be mapped
honestly. Relative includes such as startup's `../src/equs.inc` are accepted
only when their resolved target remains under an allow-listed source or
toolchain root.

Every direct C, assembly, runtime, and firmware aggregate first runs the phony
`provenance-check` target, so an incremental build cannot bypass complete-tree
validation merely because generated assembly is newer than a changed or extra
prepared input. The repository-root `firmware-check` additionally verifies the
prepared copy directly against its configured maintained-source worktree.

The supported language boundary is intentionally narrower than all of ZDS.
Nested macros and structures, `SCOPE` or scoped `$name`/`name?` labels inside a
macro, forward or recursive `.TAG` references, and structure members other than
literal-sized `DS` and prior `.TAG` types are rejected. Conditional directives
are passed to GAS and transformed lexically, so definitions in mutually
exclusive branches must still have distinct maintained-source names. Absolute,
outside-root, symlinked, unresolved, and ambiguously cased includes are also
rejected.

When maintained MOS introduces a construct outside this boundary, preserve the
ZDS-oriented source and make the compatibility decision explicitly:

1. establish the intended ZDS behavior with a minimal source fixture and, when
   available, ZDS object or binary evidence;
2. classify it as an ongoing language feature or a reviewed one-time
   preparation edit;
3. for an ongoing feature, add strict parsing plus positive and negative source
   tests, original-source diagnostics, and object/relocation/disassembly tests
   wherever semantics reach emitted code;
4. add or update real-corpus coverage and run every assembly root; and
5. reject ambiguous or unverified variants rather than guessing or passing
   them through to GAS accidentally.

Supporting one spelling or operand shape does not imply support for the rest of
the similarly named ZDS directive or macro family. Document each intentionally
accepted expansion of the boundary in this file and in
`docs/assembly-compatibility-strategy.md`.

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
