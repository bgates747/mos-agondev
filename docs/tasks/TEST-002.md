# TEST-002 — Opt-in UART1 transmit-interrupt model

Status: Machine checks complete. Author explicitly authorized categorized
commits and remote publication on 2026-09-14 to preserve the work. Human
emulator validation remains pending; publication is not release qualification.

The Extender BENCH-001 resident-service check exposes a missing dependency in
TEST-001's isolated native runtime: UART1 TX demand is absent. A stationary
consumer trace measures61 valid144-byte packets taking128.786–136.941ms each
to assemble at the host. The physical consumer already passed its own driving
and recovery tests. This task owns the generic emulator-model correction;
consumer policy, game physics and physical qualification remain in their owners.

## Bounded plan

1. [x] T002-01: Inspect native UART1 dispatch/IIR, maintained peer generator,
   ownership and eZ80F92/F93 PS015317-0120 pp105–107,113–115. Freeze the scope
   below before implementation; keep reference and prior generated runtimes.
2. [x] T002-02: Add an explicit generator option for UART1 RX/TX pending and
   read-only IIR priority/status. Derive TX-empty from actual FIFO state and
   IER bit1, complete from FIFO/shift cooldown and IER bit4. Preserve RX priority,
   FIFO status bits, guest interrupt masking, byte cooldowns, CTS and UART0.
   Default generator output retains the reviewed RX-only model.
3. [x] T002-03: Test actual adapted Rust UART behavior with disabled/enabled
   IRQs, empty/refilled/drained FIFO, RX priority, IIR read stability, completion
   versus holding-empty, divisor cooldown, ordered bytes and independent UART
   instances. Test exact source-drift rejection and default-output preservation.
   Run the existing socket backpressure test and relevant generic checks.
4. [x] T002-04: Build a fresh opt-in isolated runtime with exact source/output
   hashes and consume it through the generated profile launcher. The consuming
   project owns the repeated fixed application case and reports its limits.
5. [x] T002-05: Record outcomes and reusable usage; leave all emulator-coupled
   changes uncommitted/unpushed for Author validation and approval.

## Contract and research boundaries

Reference Fab1.2.3 commitfbb7d7ca887a06966ca8a62ed22272409a5ab640 stays read-only.
`scripts/prepare_uart_peer.py` is the maintained owner of copied adaptations;
never hand-edit generated files. Its existing byte-socket/CTS adaptation is
retained. This option changes only the selected UART1 interrupt/status path.
UART0, receive/transmit cooldown arithmetic, FIFO capacities, peer framing,
guest registers/firmware, VDP and scheduling remain untouched.

The datasheet defines IER bit0 RX, bit1 holding/FIFO-empty and bit4 complete.
IIR has active-low bit0; RX code4 outranks complete code10, which outranks
holding-empty code2. FIFO-enabled status sets bits7:6. Reading this status must
not clear an interrupt-enable bit; guest THR writes and IER masking control
the selected transmit source. No undocumented interrupt-clear latch is invented.
FIFO reset, RX error/timeout/modem interrupts, electrical baud/framing, RTS,
all UART modes and a complete hardware model are not claimed by this slice.

Default generated source must remain byte-identical. Opt-in output manifests
record the model selection and maintained correction-source hash. Consumers
must preserve earlier failing evidence and identify the model in new results;
a pass is not evidence that the old runtime worked. Do not change the model
to satisfy an application assertion that contradicts the documented UART.

## Machine evidence, 2026-09-13

All 138 generic unit tests pass, including the existing bounded socket/CTS
test and the new tests compiling the actual adapted Rust UART. Its five Rust
cases exercise register state and byte timing independently of the game.
Default source output matches all seven files produced by generator commit
`2b7884ceb7b2cfa803f87e03ebe39ebe10d97723`. Exact IIR source drift is rejected.
The opt-in runtime builds from the pinned read-only Fab reference. Its host
executable SHA256 is
`875e73f4f452c7005e41a9e230b0d961289d58841dffd8d8a6c3a1ee64725911`;
manifest SHA256 is
`446caa45878bf2eca812f73dd7f08669ca0cb78bbdd80750d61b5ecb384b874a`.
These hashes identify this machine's build, not a cross-host reproducibility
promise. Four inherited build warnings remain outside this change's scope.

The consuming Extender BENCH-001 HEADLESS-CLOSEOUT.md owns complete evidence.
Its stationary 10-second trace changes from 61 packets with median134.260ms
host assembly/source-frame gap3 to 175 packets with median2.180ms/gap1. The
same Rally, EMOS and controller then pass two fixed40-second runs, with no
freshness-limit relaxation or CPU-unlimited option. The final run has660
manual road observations, four clean laps,12 passes, zero contacts/kerb/grass,
later guest key-release confirmation and ordinary application exit. Generated
profile input hashes and final inventory verify. No physical firmware or bench
state changed for this correction. Earlier model failures remain preserved.

This fulfills the bounded machine checks, not human validation or publication.
Keep TEST-002 in TODO.md pending that review. Usage and exclusions are in
[uart-peer-emulator.md](../uart-peer-emulator.md); no generated source is
maintained or committed as an implementation.

## Publication authorization — 2026-09-14

The Author explicitly requested discrete commits and pushes for both projects
after being informed of this pending emulator work and its validation gate.
That instruction authorizes publishing the candidate without asserting new
human validation. The three focused Python tests (including actual adapted
Rust UART cases) pass again with the local Fab reference. Historical statements
above describe the earlier hold. Human validation remains the open task.
