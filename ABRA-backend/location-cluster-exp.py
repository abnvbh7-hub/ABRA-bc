from database import pool
import pandas as pd
import numpy as np
import datetime
from sklearn.cluster import DBSCAN

def get_data(day=None):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            if day:
                cur.execute("SELECT id, timestamp, latitude, longitude, speed, battery_level, is_charging, network_type, wifi_count FROM abradb WHERE day = %s AND latitude IS NOT NULL AND longitude IS NOT NULL ORDER BY timestamp ASC", (day,))
            else:
                cur.execute("SELECT id, timestamp, latitude, longitude, speed, battery_level, is_charging, network_type, wifi_count FROM abradb WHERE latitude IS NOT NULL AND longitude IS NOT NULL ORDER BY timestamp ASC LIMIT 5000")
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            return pd.DataFrame(rows, columns=columns)

df = get_data(day=datetime.date(2026, 9, 28))
print(f"Total points: {len(df)}")

if not df.empty:
    coords = np.radians(df[['latitude', 'longitude']].values)
    kms_per_radian = 6371.0088
    eps_km = 0.05  # 50 meters
    epsilon = eps_km / kms_per_radian

    db = DBSCAN(eps=epsilon, min_samples=5, metric='haversine', algorithm='ball_tree')
    db.fit(coords)

    df['cluster'] = db.labels_
    print("Cluster counts:")
    print(df['cluster'].value_counts())

    for cluster_id in sorted(df['cluster'].unique()):
        cluster_df = df[df['cluster'] == cluster_id]
        if cluster_id == -1:
            print(f"Noise points: {len(cluster_df)}")
        else:
            center_lat = cluster_df['latitude'].mean()
            center_lon = cluster_df['longitude'].mean()
            min_time = cluster_df['timestamp'].min()
            max_time = cluster_df['timestamp'].max()
            duration_minutes = (max_time - min_time).total_seconds() / 60 if pd.notnull(min_time) and pd.notnull(max_time) else 0
            print(f"Cluster {cluster_id}: {len(cluster_df)} points | Center: ({center_lat:.5f}, {center_lon:.5f}) | Avg Speed: {cluster_df['speed'].mean():.1f} | Duration: {duration_minutes:.1f} mins")

import os
os._exit(0)

