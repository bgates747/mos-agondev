# BUILD-002 — UART1 data/status register lvalues

Status: complete; target and EMOS visual checks passed, commit approved.

EMOS INTEG-004 exercises UART1 polling in C. The compatibility header mapped
its configuration registers but left RBR, THR and LSR as AgonDev numeric port
addresses. ZDS source expects volatile byte lvalues. Add those three mappings
using the existing address-space IO convention and address assertions (D0,
D0, D5). This is generic header compatibility; product behavior stays in EMOS.

1. [x] Add the three register mappings without changing existing mappings.
2. [x] Verify generated target instructions read/write peripheral ports.
3. [x] Author explicitly approved the reviewed changes and commit. The EMOS v0.3.0 draft
   screenshot confirms SD/CLOCK PASS, expected UART timeout and prompt return.

The first target build rejected assignment to numeric THR; an unmapped LSR
read would instead silently read a constant. Check both reads and writes.
Reference: installed read-only AgonDev ez80f92.h peripheral definitions.
