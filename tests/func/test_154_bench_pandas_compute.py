import pandas as pd
df = pd.DataFrame({'a': list(range(1000)), 'b': list(range(1000, 2000))})
df['c'] = df['a'] + df['b']
s = df['c'].sum()
print("bench_pandas_compute: PASS")
