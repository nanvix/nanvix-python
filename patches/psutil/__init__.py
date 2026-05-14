"""Nanvix psutil shim — static system info stubs.

Reports static values for CPU, memory, and disk on the Nanvix
microkernel.  No actual OS probing.
"""

__version__ = "5.9.8"

# CPU
ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
HIGH_PRIORITY_CLASS = 0x00000080
IDLE_PRIORITY_CLASS = 0x00000040
NORMAL_PRIORITY_CLASS = 0x00000020
REALTIME_PRIORITY_CLASS = 0x00000100


def cpu_count(logical=True):
    return 1


def cpu_percent(interval=None, percpu=False):
    if percpu:
        return [0.0]
    return 0.0


def cpu_freq(percpu=False):
    class _Freq:
        current = 1000.0
        min = 1000.0
        max = 1000.0
    if percpu:
        return [_Freq()]
    return _Freq()


def cpu_times(percpu=False):
    class _Times:
        user = 0.0
        system = 0.0
        idle = 0.0
    if percpu:
        return [_Times()]
    return _Times()


# Memory
def virtual_memory():
    class _VMem:
        total = 512 * 1024 * 1024
        available = 256 * 1024 * 1024
        percent = 50.0
        used = 256 * 1024 * 1024
        free = 256 * 1024 * 1024
    return _VMem()


def swap_memory():
    class _Swap:
        total = 0
        used = 0
        free = 0
        percent = 0.0
        sin = 0
        sout = 0
    return _Swap()


# Disk
def disk_usage(path="/"):
    class _Disk:
        total = 1024 * 1024 * 1024
        used = 0
        free = 1024 * 1024 * 1024
        percent = 0.0
    return _Disk()


def disk_partitions(all=False):
    return []


# Network
def net_connections(kind="inet"):
    return []


def net_if_addrs():
    return {}


def net_io_counters(pernic=False):
    class _NetIO:
        bytes_sent = 0
        bytes_recv = 0
        packets_sent = 0
        packets_recv = 0
    if pernic:
        return {}
    return _NetIO()


# Process
class Process:
    def __init__(self, pid=None):
        self.pid = pid or 1
        self._name = "nanvix"

    def name(self):
        return self._name

    def status(self):
        return "running"

    def cpu_percent(self, interval=None):
        return 0.0

    def memory_info(self):
        class _MemInfo:
            rss = 0
            vms = 0
        return _MemInfo()

    def memory_percent(self):
        return 0.0

    def is_running(self):
        return True

    def cmdline(self):
        return [self._name]


def process_iter(attrs=None, ad_value=None):
    return iter([])


def pid_exists(pid):
    return pid == 1


def pids():
    return [1]


# Boot
def boot_time():
    return 0.0


# Platform
LINUX = True
WINDOWS = False
MACOS = False
