# Production firmware linker area

The minimal linker proof lives in `projects/toolchain-probe/ld/firmware.ld`.
This directory is reserved for the production MOS linker script once its full
startup, reset/vector, RAM jump-table, hardware-constant, and symbol contracts
are implemented and tested.

The missing production work is tracked only by `PORT-102` in the root TODO.
