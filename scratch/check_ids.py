import sqlite3
import pandas as pd
import os

db_path = 'data/jobs.db'
csv_path = 'data/jobs_tracker.csv'

if not os.path.exists(db_path):
    print("DB does not exist")
    exit()
if not os.path.exists(csv_path):
    print("CSV does not exist")
    exit()

conn = sqlite3.connect(db_path)
db_ids = set(r[0] for r in conn.execute('SELECT id FROM jobs'))
conn.close()

df = pd.read_csv(csv_path)
csv_ids = set(df['Job ID'].astype(str))

diff = csv_ids - db_ids
print(f"Total in CSV: {len(csv_ids)}")
print(f"Total in DB: {len(db_ids)}")
print(f"Diff count (CSV - DB): {len(diff)}")
if diff:
    print("Sample missing IDs:", list(diff)[:5])
