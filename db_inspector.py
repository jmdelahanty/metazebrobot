import sqlite3
import json
from pathlib import Path

# --- Configuration ---
# Update this path if your database is not in the same directory as the script.
DATABASE_PATH = Path("zebrobot.db")

# Number of sample rows to display for each table
SAMPLE_ROW_COUNT = 2

def get_table_schema(cursor, table_name):
    """Fetches the schema for a given table."""
    cursor.execute(f"PRAGMA table_info({table_name});")
    return cursor.fetchall()

def get_sample_data(cursor, table_name, limit):
    """Fetches a limited number of rows from a table."""
    cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit};")
    return cursor.fetchall()

def print_table_info(conn, table_name):
    """Prints the schema and sample data for a table."""
    print(f"\n{'='*10} Table: {table_name.upper()} {'='*10}")
    cursor = conn.cursor()

    # --- Print Schema ---
    print("\n## Schema:")
    schema = get_table_schema(cursor, table_name)
    if not schema:
        print(f"Could not retrieve schema for table '{table_name}'.")
        return

    for column in schema:
        col_id, name, col_type, notnull, default_val, pk = column
        print(f"  - {name} ({col_type}){' (Primary Key)' if pk else ''}")

    # --- Print Sample Data ---
    print(f"\n## Sample Data ({SAMPLE_ROW_COUNT} rows):")
    try:
        samples = get_sample_data(cursor, table_name, SAMPLE_ROW_COUNT)
        if not samples:
            print("  No data found in this table.")
            return

        for i, row in enumerate(samples):
            print(f"\n--- Sample Row {i+1} ---")
            for col_name, value in zip([desc[0] for desc in cursor.description], row):
                if isinstance(value, str) and value.strip().startswith('{'):
                    # Pretty-print JSON data for readability
                    try:
                        parsed_json = json.loads(value)
                        print(f"  {col_name}:")
                        print(json.dumps(parsed_json, indent=2))
                    except json.JSONDecodeError:
                        print(f"  {col_name}: {value} (Invalid JSON)")
                else:
                    print(f"  {col_name}: {value}")

    except sqlite3.Error as e:
        print(f"  An error occurred while fetching sample data: {e}")


def main():
    """Main function to connect to the database and inspect it."""
    if not DATABASE_PATH.exists():
        print(f"Error: Database file not found at '{DATABASE_PATH}'.")
        print("Please make sure the database file is in the correct path.")
        return

    print(f"Connecting to database: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # Get list of all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [table[0] for table in cursor.fetchall()]

        print(f"Found tables: {', '.join(tables)}")

        for table_name in tables:
            print_table_info(conn, table_name)

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            print(f"\nDatabase connection closed.")


def integrity_checks():
    """Run database integrity and weakness checks."""
    if not DATABASE_PATH.exists():
        print(f"Error: Database not found at '{DATABASE_PATH}'.")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("\n" + "=" * 50)
    print("DATABASE INTEGRITY & WEAKNESS ANALYSIS")
    print("=" * 50)

    # Row counts
    print("\n--- Row Counts ---")
    for table in ['crosses', 'dishes', 'quality_checks', 'materials']:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table}: {cursor.fetchone()[0]}")

    # Indexes
    print("\n--- Indexes ---")
    cursor.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
    for idx in cursor.fetchall():
        print(f"  {idx[0]} on {idx[1]}")

    # Foreign key status
    print("\n--- Foreign Key Status ---")
    cursor.execute("PRAGMA foreign_keys")
    print(f"  Foreign keys enabled at runtime: {cursor.fetchone()[0]}")

    # Integrity checks
    print("\n--- Referential Integrity ---")

    cursor.execute("""
        SELECT COUNT(*) FROM dishes d
        WHERE d.cross_id IS NOT NULL
        AND d.cross_id NOT IN (SELECT cross_id FROM crosses)
    """)
    print(f"  Orphaned dishes (cross_id not in crosses): {cursor.fetchone()[0]}")

    cursor.execute("SELECT COUNT(*) FROM dishes WHERE cross_id IS NULL")
    print(f"  Dishes with NULL cross_id: {cursor.fetchone()[0]}")

    cursor.execute("""
        SELECT COUNT(*) FROM quality_checks qc
        WHERE qc.dish_id NOT IN (SELECT dish_id FROM dishes)
    """)
    print(f"  Orphaned quality_checks: {cursor.fetchone()[0]}")

    cursor.execute("SELECT COUNT(*) FROM crosses WHERE data LIKE '%placeholder%'")
    print(f"  Placeholder cross records: {cursor.fetchone()[0]}")

    # JSON consistency
    print("\n--- JSON/Column Consistency (sample of 10) ---")
    cursor.execute("SELECT dish_id, cross_id, status, data FROM dishes LIMIT 10")
    mismatches = 0
    for row in cursor.fetchall():
        data = json.loads(row[3])
        if data.get('cross_id') != row[1]:
            print(f"  MISMATCH dish {row[0]}: cross_id col={row[1]} vs json={data.get('cross_id')}")
            mismatches += 1
        if data.get('status') != row[2]:
            print(f"  MISMATCH dish {row[0]}: status col={row[2]} vs json={data.get('status')}")
            mismatches += 1
    print(f"  Column/JSON mismatches found: {mismatches}")

    # Quality check duplication
    print("\n--- Duplicate Quality Checks ---")
    cursor.execute("""
        SELECT dish_id, check_time, COUNT(*) as cnt
        FROM quality_checks
        GROUP BY dish_id, check_time
        HAVING cnt > 1
    """)
    dups = cursor.fetchall()
    print(f"  Duplicate (same dish+time): {len(dups)}")

    # NULL analysis
    print("\n--- NULL Value Analysis ---")
    for table in ['crosses', 'dishes']:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = cursor.fetchall()
        for col in cols:
            col_name = col[1]
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {col_name} IS NULL")
            null_count = cursor.fetchone()[0]
            if null_count > 0:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                total = cursor.fetchone()[0]
                print(f"  {table}.{col_name}: {null_count}/{total} NULL")

    conn.close()


def check_screening_migration():
    """Check the screening_steps migration status."""
    if not DATABASE_PATH.exists():
        print(f"Error: Database not found at '{DATABASE_PATH}'.")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("\n" + "=" * 50)
    print("SCREENING STEPS MIGRATION STATUS")
    print("=" * 50)

    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='screening_steps'")
    if not cursor.fetchone():
        print("  screening_steps table does NOT exist")
        conn.close()
        return

    # Count rows
    cursor.execute("SELECT COUNT(*) FROM screening_steps")
    print(f"\n  Total screening_steps rows: {cursor.fetchone()[0]}")

    # Sample data
    cursor.execute("SELECT * FROM screening_steps LIMIT 3")
    rows = cursor.fetchall()
    if rows:
        cols = [d[0] for d in cursor.description]
        print(f"\n  Sample data (columns: {cols}):")
        for row in rows:
            print(f"    {dict(zip(cols, row))}")

    # Check dishes with screening data
    cursor.execute("""
        SELECT dish_id, screening_final_positive_count, screening_date_finalized
        FROM dishes
        WHERE screening_final_positive_count IS NOT NULL
        LIMIT 5
    """)
    rows = cursor.fetchall()
    print(f"\n  Dishes with screening_final_positive_count: {len(rows)}")
    for row in rows:
        print(f"    {row}")

    conn.close()


def check_transgenic_migration():
    """Check the transgenic_indicators migration status."""
    if not DATABASE_PATH.exists():
        print(f"Error: Database not found at '{DATABASE_PATH}'.")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("\n" + "=" * 50)
    print("TRANSGENIC INDICATORS MIGRATION STATUS")
    print("=" * 50)

    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transgenic_indicators'")
    if not cursor.fetchone():
        print("  transgenic_indicators table does NOT exist")
        conn.close()
        return

    # Count rows
    cursor.execute("SELECT COUNT(*) FROM transgenic_indicators")
    print(f"\n  Total transgenic_indicators rows: {cursor.fetchone()[0]}")

    # Sample data
    cursor.execute("SELECT * FROM transgenic_indicators LIMIT 5")
    rows = cursor.fetchall()
    if rows:
        cols = [d[0] for d in cursor.description]
        print(f"\n  Sample data:")
        for row in rows:
            print(f"    {dict(zip(cols, row))}")

    # Check crosses with aggregate data
    cursor.execute("""
        SELECT cross_id, agg_total_initially_produced, agg_total_positive_final, agg_yield_percentage
        FROM crosses
        WHERE agg_total_initially_produced IS NOT NULL
        LIMIT 5
    """)
    rows = cursor.fetchall()
    print(f"\n  Crosses with aggregate data: {len(rows)}")
    for row in rows:
        print(f"    {row}")

    conn.close()


def check_dishes_flattening():
    """Check the dishes flattening migration status."""
    if not DATABASE_PATH.exists():
        print(f"Error: Database not found at '{DATABASE_PATH}'.")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("\n" + "=" * 50)
    print("DISHES FLATTENING MIGRATION STATUS")
    print("=" * 50)

    # Check which columns exist
    cursor.execute("PRAGMA table_info(dishes)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    print(f"\n  Total columns in dishes table: {len(columns)}")

    # New flattened columns to check
    new_columns = [
        'species', 'sex', 'parent_dish_id', 'dish_population_type', 'notes', 'room',
        'enclosure_temperature', 'enclosure_in_beaker', 'enclosure_vol_water_total',
        'enclosure_light_duration', 'enclosure_dawn_dusk', 'breeding_parents'
    ]

    print("\n  Flattened columns status:")
    for col in new_columns:
        if col in columns:
            # Count non-null values
            cursor.execute(f"SELECT COUNT(*) FROM dishes WHERE {col} IS NOT NULL")
            non_null = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM dishes")
            total = cursor.fetchone()[0]
            print(f"    {col}: {non_null}/{total} populated")
        else:
            print(f"    {col}: NOT PRESENT")

    # Sample data with enclosure fields
    print("\n  Sample dish with enclosure data:")
    cursor.execute("""
        SELECT dish_id, species, sex, room, enclosure_temperature,
               enclosure_vol_water_total, enclosure_light_duration
        FROM dishes
        WHERE enclosure_temperature IS NOT NULL
        LIMIT 3
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            print(f"    {dict(zip([d[0] for d in cursor.description], row))}")
    else:
        cursor.execute("""
            SELECT dish_id, species, sex, room, enclosure_temperature
            FROM dishes LIMIT 3
        """)
        rows = cursor.fetchall()
        for row in rows:
            print(f"    {dict(zip([d[0] for d in cursor.description], row))}")

    conn.close()


def check_crosses_flattening():
    """Check the crosses flattening migration status."""
    if not DATABASE_PATH.exists():
        print(f"Error: Database not found at '{DATABASE_PATH}'.")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("\n" + "=" * 50)
    print("CROSSES FLATTENING MIGRATION STATUS")
    print("=" * 50)

    # Check which columns exist
    cursor.execute("PRAGMA table_info(crosses)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    print(f"\n  Total columns in crosses table: {len(columns)}")

    # New flattened columns to check
    new_columns = ['requested_groups', 'groups_produced', 'notes', 'parents']

    print("\n  Flattened columns status:")
    for col in new_columns:
        if col in columns:
            cursor.execute(f"SELECT COUNT(*) FROM crosses WHERE {col} IS NOT NULL")
            non_null = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM crosses")
            total = cursor.fetchone()[0]
            print(f"    {col}: {non_null}/{total} populated")
        else:
            print(f"    {col}: NOT PRESENT")

    # Sample data
    print("\n  Sample cross with flattened data:")
    cursor.execute("""
        SELECT cross_id, cross_type, cross_status, requested_groups,
               groups_produced, parents
        FROM crosses
        WHERE requested_groups IS NOT NULL
        LIMIT 3
    """)
    rows = cursor.fetchall()
    if rows:
        for row in rows:
            data = dict(zip([d[0] for d in cursor.description], row))
            if data.get('parents'):
                data['parents'] = json.loads(data['parents'])
            print(f"    {data}")
    else:
        cursor.execute("""
            SELECT cross_id, cross_type, cross_status
            FROM crosses LIMIT 3
        """)
        rows = cursor.fetchall()
        for row in rows:
            print(f"    {dict(zip([d[0] for d in cursor.description], row))}")

    conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--integrity":
        integrity_checks()
    elif len(sys.argv) > 1 and sys.argv[1] == "--screening":
        check_screening_migration()
    elif len(sys.argv) > 1 and sys.argv[1] == "--transgenic":
        check_transgenic_migration()
    elif len(sys.argv) > 1 and sys.argv[1] == "--dishes":
        check_dishes_flattening()
    elif len(sys.argv) > 1 and sys.argv[1] == "--crosses":
        check_crosses_flattening()
    else:
        main()
        integrity_checks()