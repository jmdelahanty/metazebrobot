#!/usr/bin/env python3
"""
Cleanup script to fix placeholder cross records and invalid dish records.
This script will identify and fix records that are causing validation errors.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

def cleanup_database(database_path: str):
    """Clean up placeholder records in the database."""
    
    print(f"Cleaning up database: {database_path}")
    
    # Backup database first
    backup_path = f"{database_path}.cleanup_backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    import shutil
    shutil.copy2(database_path, backup_path)
    print(f"Created backup: {backup_path}")
    
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Find and fix placeholder crosses
        print("\n=== Cleaning Placeholder Crosses ===")
        cursor.execute("SELECT cross_id, data FROM crosses")
        crosses_to_fix = []
        crosses_to_delete = []
        
        for row in cursor.fetchall():
            cross_id = row['cross_id']
            try:
                cross_data = json.loads(row['data'])
                
                if cross_data.get('placeholder'):
                    # This is a placeholder record
                    created_from_dish = cross_data.get('created_from_dish')
                    print(f"Found placeholder cross: {cross_id} (from dish: {created_from_dish})")
                    
                    # Try to get dish info to fill in missing cross data
                    cursor.execute("SELECT data FROM dishes WHERE dish_id = ?", (created_from_dish,))
                    dish_row = cursor.fetchone()
                    
                    if dish_row:
                        dish_data = json.loads(dish_row['data'])
                        
                        # Create a proper cross record from dish data
                        fixed_cross = {
                            'cross_id': cross_id,
                            'request_date': dish_data.get('date_created', '20250101'),
                            'responsible_requestor': dish_data.get('responsible', 'Unknown'),
                            'line_strain': dish_data.get('genotype', 'Unknown'),
                            'parents': [
                                {
                                    'identifier': parent,
                                    'sex': 'unknown',
                                    'genotype': None
                                } for parent in dish_data.get('breeding', {}).get('parents', ['Unknown_Parent1', 'Unknown_Parent2'])
                            ],
                            'requested_groups': 1,
                            'groups_produced': 1,
                            'cross_type': 'Standard',  # Default to Standard
                            'cross_status': 'Completed',  # Since dishes exist
                            'notes': f'Auto-generated from dish {created_from_dish} during cleanup',
                            'transgenic_details': None
                        }
                        
                        # Ensure we have exactly 2 parents
                        if len(fixed_cross['parents']) < 2:
                            fixed_cross['parents'].extend([
                                {'identifier': f'Unknown_Parent{i}', 'sex': 'unknown', 'genotype': None}
                                for i in range(len(fixed_cross['parents']) + 1, 3)
                            ])
                        elif len(fixed_cross['parents']) > 2:
                            fixed_cross['parents'] = fixed_cross['parents'][:2]
                        
                        crosses_to_fix.append((cross_id, fixed_cross))
                    else:
                        # No dish found, delete this placeholder
                        crosses_to_delete.append(cross_id)
                
            except json.JSONDecodeError:
                print(f"Invalid JSON in cross {cross_id}, will delete")
                crosses_to_delete.append(cross_id)
        
        # Fix placeholder crosses
        for cross_id, fixed_cross in crosses_to_fix:
            cursor.execute("""
            UPDATE crosses SET 
                request_date = ?,
                responsible_requestor = ?,
                line_strain = ?,
                cross_type = ?,
                cross_status = ?,
                data = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE cross_id = ?
            """, (
                fixed_cross['request_date'],
                fixed_cross['responsible_requestor'],
                fixed_cross['line_strain'],
                fixed_cross['cross_type'],
                fixed_cross['cross_status'],
                json.dumps(fixed_cross),
                cross_id
            ))
            print(f"Fixed placeholder cross: {cross_id}")
        
        # Delete orphaned placeholder crosses
        for cross_id in crosses_to_delete:
            cursor.execute("DELETE FROM crosses WHERE cross_id = ?", (cross_id,))
            print(f"Deleted orphaned placeholder cross: {cross_id}")
        
        print(f"Fixed {len(crosses_to_fix)} placeholder crosses")
        print(f"Deleted {len(crosses_to_delete)} orphaned placeholder crosses")
        
        # Find and fix invalid dishes
        print("\n=== Cleaning Invalid Dishes ===")
        cursor.execute("SELECT dish_id, data FROM dishes")
        dishes_to_fix = []
        dishes_to_delete = []
        
        for row in cursor.fetchall():
            dish_id = row['dish_id']
            try:
                dish_data = json.loads(row['data'])
                
                # Check for required fields
                required_fields = ['cross_id', 'dof', 'genotype', 'responsible', 'fish_count', 'breeding', 'enclosure']
                missing_fields = [field for field in required_fields if field not in dish_data]
                
                if missing_fields:
                    print(f"Dish {dish_id} missing fields: {missing_fields}")
                    
                    # Try to fix by adding default values
                    if 'cross_id' not in dish_data:
                        # Extract cross_id from dish_id if possible
                        parts = dish_id.split('_')
                        if len(parts) >= 2:
                            dish_data['cross_id'] = parts[0]
                        else:
                            dish_data['cross_id'] = 'UNKNOWN'
                    
                    if 'dof' not in dish_data:
                        dish_data['dof'] = dish_data.get('date_created', '20250101')
                    
                    if 'genotype' not in dish_data:
                        dish_data['genotype'] = 'Unknown'
                    
                    if 'responsible' not in dish_data:
                        dish_data['responsible'] = 'Unknown'
                    
                    if 'fish_count' not in dish_data:
                        dish_data['fish_count'] = 0
                    
                    if 'breeding' not in dish_data:
                        dish_data['breeding'] = {'parents': []}
                    
                    if 'enclosure' not in dish_data:
                        dish_data['enclosure'] = {
                            'temperature': 28.5,
                            'light_cycle': {
                                'light_duration': '14:10',
                                'dawn_dusk': '8:00'
                            },
                            'room': '2E.282',
                            'in_beaker': False
                        }
                    
                    dishes_to_fix.append((dish_id, dish_data))
            
            except json.JSONDecodeError:
                print(f"Invalid JSON in dish {dish_id}, will delete")
                dishes_to_delete.append(dish_id)
        
        # Fix dishes
        for dish_id, fixed_dish in dishes_to_fix:
            cursor.execute("""
            UPDATE dishes SET 
                cross_id = ?,
                dof = ?,
                genotype = ?,
                responsible = ?,
                fish_count = ?,
                data = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE dish_id = ?
            """, (
                fixed_dish['cross_id'],
                fixed_dish['dof'],
                fixed_dish['genotype'],
                fixed_dish['responsible'],
                fixed_dish['fish_count'],
                json.dumps(fixed_dish),
                dish_id
            ))
            print(f"Fixed dish: {dish_id}")
        
        # Delete invalid dishes
        for dish_id in dishes_to_delete:
            # Also delete related quality checks
            cursor.execute("DELETE FROM quality_checks WHERE dish_id = ?", (dish_id,))
            cursor.execute("DELETE FROM dishes WHERE dish_id = ?", (dish_id,))
            print(f"Deleted invalid dish: {dish_id}")
        
        print(f"Fixed {len(dishes_to_fix)} dishes")
        print(f"Deleted {len(dishes_to_delete)} invalid dishes")
        
        # Commit all changes
        conn.commit()
        print(f"\n✅ Database cleanup completed successfully!")
        print(f"Backup saved at: {backup_path}")
        
        # Show summary
        cursor.execute("SELECT COUNT(*) FROM crosses")
        cross_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM dishes")
        dish_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM quality_checks")
        qc_count = cursor.fetchone()[0]
        
        print(f"\nFinal counts:")
        print(f"  Crosses: {cross_count}")
        print(f"  Dishes: {dish_count}")
        print(f"  Quality Checks: {qc_count}")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error during cleanup: {e}")
        raise
    finally:
        conn.close()

def main():
    """Main function."""
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python cleanup_database.py <path_to_database>")
        print("Example: python cleanup_database.py /groups/ahrens/ahrenslab/jeremy/zebrobot/zebrobot.db")
        sys.exit(1)
    
    database_path = sys.argv[1]
    
    if not Path(database_path).exists():
        print(f"Error: Database file {database_path} does not exist")
        sys.exit(1)
    
    cleanup_database(database_path)

if __name__ == "__main__":
    main()