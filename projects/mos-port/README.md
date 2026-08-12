# MOS C compile probe

This directory is deliberately not a complete MOS port. It answers whether
AgonDev can generate objects for the current MOS C source after a minimal,
explicit compatibility experiment.

`scripts/prepare_mos_worktree.py` copies only Git-tracked files from the
read-only upstream checkout into ignored `worktree/`, then applies five
validated edits. The compatibility headers model Zilog types and hardware
register lvalues with AgonDev address-space I/O.

From the repository root:

```bash
.venv/bin/python scripts/prepare_mos_worktree.py
make c-probe
```

All 16 C translation units compile. FatFS `ff.c` has a local `-Os` override
because this AgonDev version exhausts registers for that file at `-Oz`. No
assembly is compiled and no link is attempted; success here must not be
described as a working MOS image.
