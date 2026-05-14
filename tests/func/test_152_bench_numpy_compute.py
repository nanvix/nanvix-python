import numpy as np
a = np.arange(10000, dtype=np.float64)
b = np.sin(a) + np.cos(a)
r = np.dot(a, b)
print("bench_numpy_compute: PASS")
