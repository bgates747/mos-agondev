# Headless parity evidence

`compare_boot.py` is a bounded differential test between the AgonDev-built MOS
and the pinned same-source ZDS Platform image. It launches each image in Fab's
CLI emulator with `--unlimited-cpu --zero` and requires their complete
normalized shell transcripts to be identical.

The test creates a fresh temporary hostfs tree for each invocation. Its four
fixed text files cover root and two-level directory traversal, directory
listing, relative and slash-qualified paths, and exact `TYPE` output including
CRLF, a missing final newline, repeated spaces, and punctuation. The
command corpus also covers `HELP` dispatch, `ECHO`,
`SET`/`SHOW`/`UNSET` process state, zeroed RTC display, credits, missing paths,
missing files, and unknown commands. Every command echo and every semantic
marker must be present; two equally truncated or inert transcripts cannot pass.
The fixture structure and file bytes are checked before, between, and after the
two runs, so the allegedly read-only corpus fails if either image changes it.

Run the evidence from the repository root after building the candidate:

```bash
make firmware-parity-check
```

The subprocess boundary rejects missing inputs, a non-executable emulator,
non-positive timeouts, timeout expiry, nonzero exit status, empty output, and
output beyond a one-MiB sanity ceiling.
Host unit tests exercise those failures without invoking Fab.

The separate `projects/contract-probe` target MOSlet provides bounded eZ80 formatter
varargs and read-only MOS API ABI evidence on both images; its README and
wrapper audit define the exact surface.

## Linked VDP protocol evidence

`verify_vdp_regressions.py` checks the bytes in the final linked candidate,
not a reimplementation compiled for the host. A deliberately small,
fail-closed eZ80 ADL interpreter starts at the linked `vdp_protocol` symbol and
executes the parser path used by the UART interrupt. Every oversized one-byte
length from 17 through 255 must enter discard state, retain and decrement the
exact announced length, leave the 16-byte packet buffer and handler state
untouched, return to idle on the final byte, and accept a following general
poll packet. The legal 16-byte boundary must fill exactly the buffer and also
accept a following poll. Encountering an opcode outside the audited path is a
hard failure.

Run the current candidate evidence after building the firmware:

```bash
make vdp-regression-check
```

This default gate reads only the candidate ELF and ROM. It checks the linked
startup handshake and every oversized length without requiring a particular
stock MOS/map pair.

The pinned ZDS image is not a valid positive comparison for this regression.
Its hash is the audited stock value
`d564243283972690933a4554296ad6202ca4ef54572279533a942960846bebae`, and its
map records `vdp_protocol.obj` as built on 2026-03-01. It predates the pinned
MOS source fix from 2026-07-28. The frozen baseline gate executes that image
and requires it to reproduce the old stale-length failure as an intentional
negative control:

```bash
make vdp-baseline-check
```

That target invokes the verifier with
`--check-reference-negative-control`. A refreshed ZDS image would require
refreshing this contract. The verifier pins both artifacts before interpreting
them: the ZDS map must also match
`d69e60bbce61a7b4b3eef318ba395f11c4e1a5b585755755113992dc94edcb86`.

The same verifier checks that the linked `_main` calls `_wait_ESP32` before
`_bootmsg`, and that `_wait_ESP32` initializes and repeatedly polls `_gp` with
a backward wait edge. Because that poll has no timeout, the banner required by
`verify_boot.py` is bounded evidence that the stock VDP answered the initial
general-poll handshake through the candidate's UART interrupt and protocol
parser. It is not evidence for all VDP packet types or graphical behavior.

The evidence remains intentionally narrow. Fab CLI stdin is not evidence for
the graphical keyboard editor. The tests do not exercise broader VDP packet
types and timing, UART error/timing behavior, RTC mutation/persistence,
writable FatFS operations, the complete MOS exported ABI, physical SD media,
or hardware. Those remain acceptance gaps under PORT-201/202/203 and the
applicable human gate for future emulator-coupled changes. The initial
graphical gate is recorded as complete in the research devlog.

The runtime host golden now covers every distinct format spelling inventoried
from maintained MOS (`%%`, integer/string/character conversions, all fixed and
dynamic widths, dynamic precision, and `%*lu`). `scan_formats.py` requires an
exact one-to-one set of golden markers, so a newly introduced spelling fails
verification until a boundary case is added. This proves the selected
nanoprintf behavior on the host configuration. The target contract repeats all
16 spellings at eZ80 boundary values; PORT-202 remains open for the broader
exported C/assembly ABI matrix.
