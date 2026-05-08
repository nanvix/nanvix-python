# Testing

## Smoke Test

[`tests/smoke_test_l2.py`](../tests/smoke_test_l2.py) validates core
CPython built-in modules: `sys`, `os`, `json`, `collections`, `math`,
`io`, `zlib`, `bz2`, `hashlib`, `sqlite3`, `ctypes`, `pyexpat`, and
`xml.etree`.

## Functional Tests

Individual test files in [`tests/func/`](../tests/func/) each
cover one package. Tests are numbered `test_001_packaging.py` through
`test_105_libffi.py` and run sequentially on `nanvixd.elf`.

> **Note:** Tests for C extension packages (numpy, cymem, kiwisolver,
> murmurhash, preshed, srsly, cffi) have been temporarily removed.

### Running Tests

```bash
./z test
```

### Running a Subset

Use `TEST_START` and `TEST_END` to restrict the range:

```bash
# Run only tests 1 through 10
TEST_START=1 TEST_END=10 ./z test
```

### Per-test Timeout

Each test is capped at `TIMEOUT_SECONDS` (default: 300). Override it
for slow environments:

```bash
TIMEOUT_SECONDS=600 ./z test
```

## Hello-world Benchmark

Run the built-in benchmark to measure end-to-end hello-world execution:

```bash
./z benchmark
```

The benchmark prints the timing in stdout:

```text
Execution time: X.XXXs
```
