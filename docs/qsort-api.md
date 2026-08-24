# MOS `qsort()` C-function API

The `dev/sort` branch exposes the C runtime's existing `qsort()` through MOS
3.0's indirect C-function interface. It does not add a conventional `RST 08h`
register API, and it does not change `DIR`, `LS`, FatFS enumeration, or any
application unless that application explicitly requests and calls the new
function.

## Interface

Request function number `0x12` from `mos_getfunction` (`RST 08h`, API `0x50`)
with flags `C=0`. In ADL mode, a successful request returns `A=0` and a
24-bit function pointer in `HLU` with this prototype:

```c
void qsort(void *base, size_t count, size_t size,
           int (*compare)(const void *, const void *));
```

An AgonDev application can use a small assembly getter such as the one tested
in `projects/contract-probe/src/mos_getqsort.asm`, declare the returned type in
C, and fall back when it receives `NULL`:

```c
typedef void (*mos_qsort_fn)(void *, size_t, size_t,
                             int (*)(const void *, const void *));
extern mos_qsort_fn mos_getqsort(void);

mos_qsort_fn sort = mos_getqsort();
if (entry_count > 1) {
    if (sort != NULL) {
        sort(entries, entry_count, sizeof(entries[0]), compare_entries);
    } else {
        application_sort(entries, entry_count);
    }
}
```

The function and comparator use the eZ80 C calling convention. Assembly
callers must push the four arguments in reverse order, with each argument in a
three-byte stack slot, then call the returned pointer. `size_t`, pointers, and
the comparator's `int` result are 24-bit values in the supported ABI.

Programs must check the `mos_getfunction` result instead of assuming the slot
exists. MOS v3.0.2 and older reject function number `0x12`; firmware containing
this extension returns the pointer. A program can retain its own sorter as a
compatibility fallback.

The comparator executes in the application's address space while MOS's
`qsort()` is active. Its code and referenced data must remain valid for the
whole call. It must implement a consistent ordering and return a value less
than, equal to, or greater than zero. As with standard C `qsort()`, equal
elements are not guaranteed to retain their original order.

The exported routine is whichever runtime `qsort()` implementation was linked
into that MOS build. AgonDev and ZDS firmware can therefore differ in
algorithm, performance, and working-memory behavior even though they share the
same public signature and calling convention.

The first-pass API deliberately promises no more than the current firmware
implementation has demonstrated. Callers must supply non-null array and
comparator pointers, a nonzero element count, and a nonzero element size. In
particular, the pinned AgonDev implementation computes `(count - 1) * size`
before entering its partition loop and divides by `size`, so it does not safely
guard zero values. Applications should skip the call for empty and one-entry
arrays. That implementation performs bytewise in-place swaps, returns no error
status, allocates no heap memory, and uses a fixed internal stack of 16
partition pairs (96 bytes with 24-bit pointers) without an overflow check.
Very large or adversarial arrays are outside the qualified first-pass scope;
representative application directory sizes must be benchmarked and tested.

## Directory sorting policy

`qsort()` does not know about filenames, dates, directories, sizes, ascending
order, or descending order. Applications keep those choices in comparator
callbacks. A directory application can therefore provide comparators such as:

```c
typedef struct {
    char *name;
    unsigned short fat_date;
    unsigned char attributes;
} DirectoryEntry;

static int by_name(const void *left, const void *right) {
    const DirectoryEntry *a = left;
    const DirectoryEntry *b = right;
    return strcmp(a->name, b->name);
}

static int by_date(const void *left, const void *right) {
    const DirectoryEntry *a = left;
    const DirectoryEntry *b = right;
    return (a->fat_date > b->fat_date) - (a->fat_date < b->fat_date);
}
```

Directories-first behavior, reverse ordering, and secondary tie-breakers also
belong in the comparator. The first API deliberately does not standardize a
directory-entry structure or MOS sort flags; doing so would couple MOS to
application ownership, allocation, filename representation, and policy.

Applications still enumerate entries with `f_opendir()`/`f_readdir()` and
store them in their own array. Calling this API only replaces the array-sorting
step. FatFS enumeration remains unsorted.

## Evidence and scope

The target contract probe retrieves slot `0x12`, sorts application-owned
records by both filename and FAT date, and proves that application comparator
callbacks ran. It also verifies that the pinned v3.0.2 reference reports the
extension unavailable. The firmware image grows by three bytes because MOS
already links `qsort()` for its `DIR`/`LS` command; the change adds only one
`DW24` function-table entry.

This proves the ABI and bounded callback round trips in the emulator. It does
not establish that `qsort()` will outperform an application's specialized
sort. Applications should benchmark execution time, code size saved, working
memory, and required ordering on representative directories before replacing
an existing sorter.
