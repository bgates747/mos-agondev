# nanoprintf source input

`nanoprintf.h` is vendored from the pinned AgonDev checkout at
`src/lib/libc/nanoprintf.h`. Its SHA-256 is recorded and checked by
`runtime_policy.json` and `audit_runtime.py`.

Keeping this single header in the port repository makes the firmware formatter
reproducible from the installed AgonDev release; no undeclared sibling source
checkout is required at build time.
