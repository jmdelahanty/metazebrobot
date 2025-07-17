#!/usr/bin/env python3
"""
Simple query interface for the Zebrobot NoSQL database.
Provides common queries and allows custom SQL queries.
"""

import sqlite3
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

class ZebrobotQueryInterface:
    def __init__(self, database_path: str = "zebrobot.db"):
        """Initialize the query interface."""
        self.db_path = database_path
        self.conn = None
        
    def connect(self):
        """Connect to the database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row  # Enable dict-like access to rows
        
    def disconnect(self):
        """Disconnect from the database."""
        if self.conn:
            self.conn.close()
            
    def __enter__(self):
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        
    def query(self, sql: str, params: tuple = ()) -> List[Dict]:
        """Execute a SQL query and return results as list of dictionaries."""
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        columns = [description[0] for description in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        return results
    
    def get_active_dishes(self) -> List[Dict]:
        """Get all active dishes with summary information."""
        return self.query("""
        SELECT 
            dish_id,
            cross_id,
            genotype,
            responsible,
            fish_count,
            dof,
            date_created,
            (SELECT COUNT(*) FROM quality_checks qc WHERE qc.dish_id = dishes.dish_id) as check_count,
            (SELECT MAX(check_time) FROM quality_checks qc WHERE qc.dish_id = dishes.dish_id) as last_check
        FROM dishes 
        WHERE status = 'active'
        ORDER BY date_created DESC
        """)
    
    def get_dishes_needing_attention(self, days_since_check: int = 2) -> List[Dict]:
        """Get dishes that haven't been checked recently."""
        return self.query("""
        SELECT 
            d.dish_id,
            d.cross_id,
            d.genotype,
            d.responsible,
            d.fish_count,
            MAX(qc.check_time) as last_check,
            julianday('now') - julianday(MAX(qc.check_time)) as days_since_check
        FROM dishes d
        LEFT JOIN quality_checks qc ON d.dish_id = qc.dish_id
        WHERE d.status = 'active'
        GROUP BY d.dish_id
        HAVING days_since_check > ? OR last_check IS NULL
        ORDER BY days_since_check DESC
        """, (days_since_check,))
    
    def get_dish_details(self, dish_id: str) -> Optional[Dict]:
        """Get complete details for a specific dish."""
        dishes = self.query("SELECT * FROM dishes WHERE dish_id = ?", (dish_id,))
        if not dishes:
            return None
            
        dish = dishes[0]
        # Parse the JSON data
        dish['data'] = json.loads(dish['data'])
        
        # Get quality checks
        checks = self.query("""
        SELECT * FROM quality_checks 
        WHERE dish_id = ? 
        ORDER BY check_time DESC
        """, (dish_id,))
        
        dish['quality_checks'] = checks
        return dish
    
    def get_cross_details(self, cross_id: str) -> Optional[Dict]:
        """Get complete details for a specific cross and its dishes."""
        crosses = self.query("SELECT * FROM crosses WHERE cross_id = ?", (cross_id,))
        if not crosses:
            return None
            
        cross = crosses[0]
        cross['data'] = json.loads(cross['data'])
        
        # Get all dishes for this cross
        dishes = self.query("""
        SELECT dish_id, status, fish_count, dof, 
               (SELECT COUNT(*) FROM quality_checks qc WHERE qc.dish_id = dishes.dish_id) as check_count
        FROM dishes 
        WHERE cross_id = ?
        ORDER BY dish_number
        """, (cross_id,))
        
        cross['dishes'] = dishes
        return cross
    
    def get_feeding_schedule(self, days_ahead: int = 7) -> List[Dict]:
        """Get dishes that need feeding in the next N days."""
        return self.query("""
        SELECT 
            d.dish_id,
            d.cross_id,
            d.genotype,
            d.responsible,
            MAX(qc.check_time) as last_fed,
            julianday('now') - julianday(MAX(qc.check_time)) as days_since_fed
        FROM dishes d
        LEFT JOIN quality_checks qc ON d.dish_id = qc.dish_id AND qc.fed = 1
        WHERE d.status = 'active'
        GROUP BY d.dish_id
        HAVING days_since_fed >= 1 OR last_fed IS NULL
        ORDER BY days_since_fed DESC
        """)
    
    def get_mortality_report(self) -> List[Dict]:
        """Get mortality statistics by dish."""
        return self.query("""
        SELECT 
            d.dish_id,
            d.cross_id,
            d.genotype,
            d.fish_count as initial_count,
            COALESCE(SUM(qc.num_dead), 0) as total_deaths,
            d.fish_count - COALESCE(SUM(qc.num_dead), 0) as current_count,
            ROUND(COALESCE(SUM(qc.num_dead), 0) * 100.0 / d.fish_count, 2) as mortality_rate
        FROM dishes d
        LEFT JOIN quality_checks qc ON d.dish_id = qc.dish_id
        WHERE d.status = 'active'
        GROUP BY d.dish_id
        ORDER BY mortality_rate DESC
        """)
    
    def get_materials_summary(self) -> Dict[str, int]:
        """Get count of materials by type."""
        results = self.query("""
        SELECT material_type, COUNT(*) as count
        FROM materials
        GROUP BY material_type
        ORDER BY material_type
        """)
        return {row['material_type']: row['count'] for row in results}
    
    def search_dishes(self, genotype: str = None, responsible: str = None, 
                     cross_id: str = None) -> List[Dict]:
        """Search dishes by various criteria."""
        where_clauses = ["status = 'active'"]
        params = []
        
        if genotype:
            where_clauses.append("genotype LIKE ?")
            params.append(f"%{genotype}%")
            
        if responsible:
            where_clauses.append("responsible LIKE ?")
            params.append(f"%{responsible}%")
            
        if cross_id:
            where_clauses.append("cross_id = ?")
            params.append(cross_id)
        
        sql = f"""
        SELECT dish_id, cross_id, genotype, responsible, fish_count, dof, status
        FROM dishes
        WHERE {' AND '.join(where_clauses)}
        ORDER BY date_created DESC
        """
        
        return self.query(sql, tuple(params))
    
    def add_quality_check(self, dish_id: str, fed: bool = False, feed_type: str = None,
                         water_changed: bool = False, vol_water_changed: int = None,
                         num_dead: int = 0, notes: str = None) -> bool:
        """Add a new quality check record."""
        check_time = datetime.now().strftime("%Y%m%dT%H:%M:%S")
        
        check_data = {
            "check_time": check_time,
            "fed": fed,
            "feed_type": feed_type,
            "water_changed": water_changed,
            "vol_water_changed": vol_water_changed,
            "num_dead": num_dead,
            "notes": notes
        }
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
            INSERT INTO quality_checks 
            (dish_id, check_time, fed, feed_type, water_changed, 
             vol_water_changed, num_dead, notes, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dish_id, check_time, fed, feed_type, water_changed,
                vol_water_changed, num_dead, notes, json.dumps(check_data)
            ))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error adding quality check: {e}")
            return False
    
    def export_to_csv(self, table_name: str, output_file: str):
        """Export a table to CSV format."""
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", self.conn)
            df.to_csv(output_file, index=False)
            print(f"Exported {table_name} to {output_file}")
        except Exception as e:
            print(f"Error exporting to CSV: {e}")

def print_table(data: List[Dict], title: str = None):
    """Pretty print tabular data."""
    if not data:
        print("No data found.")
        return
        
    if title:
        print(f"\n{title}")
        print("=" * len(title))
    
    # Convert to pandas DataFrame for nice formatting
    df = pd.DataFrame(data)
    print(df.to_string(index=False))
    print()

def main():
    """Interactive command-line interface."""
    print("Zebrobot Database Query Interface")
    print("=" * 40)
    
    with ZebrobotQueryInterface() as db:
        while True:
            print("\nAvailable commands:")
            print("1. List active dishes")
            print("2. Show dishes needing attention")
            print("3. Get dish details")
            print("4. Get cross details")
            print("5. Show feeding schedule")
            print("6. Mortality report")
            print("7. Materials summary")
            print("8. Search dishes")
            print("9. Add quality check")
            print("10. Custom SQL query")
            print("0. Exit")
            
            choice = input("\nEnter your choice (0-10): ").strip()
            
            try:
                if choice == "0":
                    break
                elif choice == "1":
                    data = db.get_active_dishes()
                    print_table(data, "Active Dishes")
                elif choice == "2":
                    days = input("Days since last check (default 2): ").strip()
                    days = int(days) if days else 2
                    data = db.get_dishes_needing_attention(days)
                    print_table(data, f"Dishes Not Checked in {days} Days")
                elif choice == "3":
                    dish_id = input("Enter dish ID: ").strip()
                    details = db.get_dish_details(dish_id)
                    if details:
                        print(f"\nDish Details: {dish_id}")
                        print("-" * 30)
                        for key, value in details.items():
                            if key not in ['data', 'quality_checks']:
                                print(f"{key}: {value}")
                        print(f"\nQuality Checks ({len(details['quality_checks'])}):")
                        print_table(details['quality_checks'][:10])  # Show last 10
                    else:
                        print(f"Dish {dish_id} not found.")
                elif choice == "4":
                    cross_id = input("Enter cross ID: ").strip()
                    details = db.get_cross_details(cross_id)
                    if details:
                        print(f"\nCross Details: {cross_id}")
                        print("-" * 30)
                        for key, value in details.items():
                            if key not in ['data', 'dishes']:
                                print(f"{key}: {value}")
                        print("\nDishes:")
                        print_table(details['dishes'])
                    else:
                        print(f"Cross {cross_id} not found.")
                elif choice == "5":
                    data = db.get_feeding_schedule()
                    print_table(data, "Feeding Schedule")
                elif choice == "6":
                    data = db.get_mortality_report()
                    print_table(data, "Mortality Report")
                elif choice == "7":
                    summary = db.get_materials_summary()
                    print("\nMaterials Summary:")
                    print("-" * 20)
                    for material_type, count in summary.items():
                        print(f"{material_type}: {count}")
                elif choice == "8":
                    genotype = input("Genotype (optional): ").strip() or None
                    responsible = input("Responsible person (optional): ").strip() or None
                    cross_id = input("Cross ID (optional): ").strip() or None
                    data = db.search_dishes(genotype, responsible, cross_id)
                    print_table(data, "Search Results")
                elif choice == "9":
                    dish_id = input("Dish ID: ").strip()
                    fed = input("Fed (y/n): ").strip().lower() == 'y'
                    feed_type = input("Feed type (if fed): ").strip() or None
                    water_changed = input("Water changed (y/n): ").strip().lower() == 'y'
                    vol_water_changed = input("Volume changed (mL): ").strip()
                    vol_water_changed = int(vol_water_changed) if vol_water_changed else None
                    num_dead = int(input("Number dead (default 0): ").strip() or "0")
                    notes = input("Notes (optional): ").strip() or None
                    
                    success = db.add_quality_check(
                        dish_id, fed, feed_type, water_changed, 
                        vol_water_changed, num_dead, notes
                    )
                    print("✅ Quality check added!" if success else "❌ Failed to add quality check")
                elif choice == "10":
                    sql = input("Enter SQL query: ").strip()
                    if sql:
                        data = db.query(sql)
                        print_table(data, "Query Results")
                else:
                    print("Invalid choice. Please try again.")
                    
            except Exception as e:
                print(f"Error: {e}")
            
            input("\nPress Enter to continue...")

if __name__ == "__main__":
    main()