import psycopg2
import json
from datetime import datetime

# Railway Postgres connection
conn = psycopg2.connect(
    host="caboose.proxy.rlwy.net",
    port=23311,
    database="railway",
    user="postgres",
    password="nuqHaToEwGLKjqdTvdtGhIzGQxujjQIy"
)

conn.autocommit = False
cur = conn.cursor()

try:
    print("=== MIGRATION: Backfill health_connect_daily raw_data ===\n")
    
    # Find all records that need backfilling (missing 'date' in raw_data)
    cur.execute("""
        SELECT id, device_id, date, collected_at, raw_data
        FROM health_connect_daily
        WHERE raw_data->>'date' IS NULL
    """)
    
    rows_to_fix = cur.fetchall()
    print(f"Found {len(rows_to_fix)} records to backfill\n")
    
    if len(rows_to_fix) == 0:
        print("No records need backfilling. Exiting.")
        cur.close()
        conn.close()
        exit(0)
    
    updated_count = 0
    
    for row in rows_to_fix:
        record_id, device_id, date, collected_at, raw_data = row
        
        # Skip if raw_data is None
        if raw_data is None:
            print(f"  Skipping {record_id} - raw_data is null")
            continue
        
        # Build the backfilled raw_data
        # date from the row
        date_str = date.strftime('%Y-%m-%d') if isinstance(date, datetime) else str(date)
        
        # source reconstructed
        source = {
            "device_id": device_id,
            "collected_at": collected_at.isoformat() if isinstance(collected_at, datetime) else str(collected_at)
        }
        
        # Create updated raw_data with new fields
        updated_raw = dict(raw_data)
        updated_raw['date'] = date_str
        updated_raw['source'] = source
        updated_raw['schema_version'] = 1
        
        # total_calories_burned - we don't have historical data, so add as null if missing
        if 'total_calories_burned' not in updated_raw:
            updated_raw['total_calories_burned'] = None
        
        # Update the record
        cur.execute(
            "UPDATE health_connect_daily SET raw_data = %s WHERE id = %s",
            (json.dumps(updated_raw), record_id)
        )
        
        updated_count += 1
        
        if updated_count % 10 == 0:
            print(f"  Processed {updated_count}/{len(rows_to_fix)}...")
    
    # Commit the transaction
    conn.commit()
    
    print(f"\n✅ Successfully backfilled {updated_count} records")
    
    # Verify the fix
    print("\n=== VERIFICATION ===")
    cur.execute("""
        SELECT date, raw_data
        FROM health_connect_daily
        ORDER BY date
        LIMIT 3
    """)
    
    for row in cur.fetchall():
        date, raw = row
        keys = list(raw.keys()) if raw else []
        print(f"  {date}: keys = {sorted(keys)}")

except Exception as e:
    conn.rollback()
    print(f"\n❌ Error during migration: {e}")
    raise

finally:
    cur.close()
    conn.close()
    print("\nMigration complete.")
