#!/usr/bin/env python3
"""
Migration script to move JSON files to a NoSQL-style SQLite database.
This script will read your existing JSON structure and create a single database file.
"""

import json
import sqlite3
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

class ZebrobotMigrator:
    def __init__(self, source_directory: str, database_path: str = "zebrobot.db"):
        """
        Initialize the migrator.
        
        Args:
            source_directory: Path to your current zebrobot directory
            database_path: Path where the new database will be created
        """
        self.source_dir = Path(source_directory)
        self.db_path = database_path
        self.conn = None
        
    def connect_database(self):
        """Create database connection and setup tables."""
        self.conn = sqlite3.connect(self.db_path)
        # Temporarily disable foreign key constraints during migration
        self.conn.execute("PRAGMA foreign_keys = OFF")
        
        # Create tables for different data types
        self.create_tables()
        
    def enable_foreign_keys(self):
        """Re-enable foreign key constraints after migration."""
        self.conn.execute("PRAGMA foreign_keys = ON")
        
    def create_tables(self):
        """Create database tables with JSON columns for flexible storage."""
        cursor = self.conn.cursor()
        
        # Crosses table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS crosses (
            cross_id TEXT PRIMARY KEY,
            request_date TEXT,
            responsible_requestor TEXT,
            line_strain TEXT,
            cross_type TEXT,
            cross_status TEXT,
            data JSON,  -- Full JSON data
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Dishes table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS dishes (
            dish_id TEXT PRIMARY KEY,
            cross_id TEXT,
            date_created TEXT,
            dof TEXT,  -- Date of fertilization
            genotype TEXT,
            responsible TEXT,
            status TEXT DEFAULT 'active',
            fish_count INTEGER,
            data JSON,  -- Full JSON data
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cross_id) REFERENCES crosses (cross_id)
        )
        """)
        
        # Quality checks table (extracted from dishes for easier querying)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS quality_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_id TEXT,
            check_time TEXT,
            fed BOOLEAN,
            feed_type TEXT,
            water_changed BOOLEAN,
            vol_water_changed INTEGER,
            num_dead INTEGER,
            notes TEXT,
            data JSON,  -- Full check data
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (dish_id) REFERENCES dishes (dish_id)
        )
        """)
        
        # Materials table (for your existing materials data)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_type TEXT,  -- agarose_bottles, fish_water_sources, etc.
            material_id TEXT,
            data JSON,  -- Full material data
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(material_type, material_id)
        )
        """)
        
        # Create indexes for better performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dishes_cross_id ON dishes(cross_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dishes_status ON dishes(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_quality_checks_dish_id ON quality_checks(dish_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_quality_checks_check_time ON quality_checks(check_time)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_materials_type ON materials(material_type)")
        
        self.conn.commit()
        
    def migrate_crosses(self):
        """Migrate cross data from JSON files."""
        crosses_dir = self.source_dir / "crosses"
        if not crosses_dir.exists():
            print("No crosses directory found, skipping...")
            return
            
        cursor = self.conn.cursor()
        migrated_count = 0
        
        for cross_file in crosses_dir.glob("*.json"):
            if cross_file.name.endswith(".bak"):
                continue  # Skip backup files
                
            try:
                with open(cross_file, 'r') as f:
                    cross_data = json.load(f)
                
                cursor.execute("""
                INSERT OR REPLACE INTO crosses 
                (cross_id, request_date, responsible_requestor, line_strain, 
                 cross_type, cross_status, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    cross_data.get('cross_id'),
                    cross_data.get('request_date'),
                    cross_data.get('responsible_requestor'),
                    cross_data.get('line_strain'),
                    cross_data.get('cross_type'),
                    cross_data.get('cross_status'),
                    json.dumps(cross_data)
                ))
                migrated_count += 1
                
            except Exception as e:
                print(f"Error migrating cross {cross_file}: {e}")
        
        self.conn.commit()
        print(f"Migrated {migrated_count} crosses")
        
    def migrate_dishes(self):
        """Migrate dish data from JSON files."""
        dishes_dir = self.source_dir / "dishes"
        if not dishes_dir.exists():
            print("No dishes directory found, skipping...")
            return
            
        cursor = self.conn.cursor()
        migrated_dishes = 0
        migrated_checks = 0
        missing_crosses = set()
        
        for dish_file in dishes_dir.glob("*.json"):
            if dish_file.name.endswith(".bak"):
                continue  # Skip backup files
                
            try:
                with open(dish_file, 'r') as f:
                    dish_data = json.load(f)
                
                cross_id = dish_data.get('cross_id')
                
                # Check if cross exists, create placeholder if not
                if cross_id:
                    cursor.execute("SELECT 1 FROM crosses WHERE cross_id = ?", (cross_id,))
                    if not cursor.fetchone():
                        # Create a placeholder cross record
                        cursor.execute("""
                        INSERT OR IGNORE INTO crosses 
                        (cross_id, request_date, responsible_requestor, line_strain, 
                         cross_type, cross_status, data)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            cross_id,
                            dish_data.get('date_created', 'unknown'),
                            dish_data.get('responsible', 'unknown'),
                            dish_data.get('genotype', 'unknown'),
                            'unknown',
                            'unknown',
                            json.dumps({"placeholder": True, "created_from_dish": dish_data.get('dish_id')})
                        ))
                        missing_crosses.add(cross_id)
                
                # Insert dish data
                cursor.execute("""
                INSERT OR REPLACE INTO dishes 
                (dish_id, cross_id, date_created, dof, genotype, responsible, 
                 status, fish_count, data, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    dish_data.get('dish_id'),
                    cross_id,
                    dish_data.get('date_created'),
                    dish_data.get('dof'),
                    dish_data.get('genotype'),
                    dish_data.get('responsible'),
                    dish_data.get('status', 'active'),
                    dish_data.get('fish_count'),
                    json.dumps(dish_data)
                ))
                migrated_dishes += 1
                
                # Extract and insert quality checks
                quality_checks = dish_data.get('quality_checks', {})
                for check_time, check_data in quality_checks.items():
                    cursor.execute("""
                    INSERT OR REPLACE INTO quality_checks 
                    (dish_id, check_time, fed, feed_type, water_changed, 
                     vol_water_changed, num_dead, notes, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        dish_data.get('dish_id'),
                        check_time,
                        check_data.get('fed'),
                        check_data.get('feed_type'),
                        check_data.get('water_changed'),
                        check_data.get('vol_water_changed'),
                        check_data.get('num_dead'),
                        check_data.get('notes'),
                        json.dumps(check_data)
                    ))
                    migrated_checks += 1
                
            except Exception as e:
                print(f"Error migrating dish {dish_file}: {e}")
        
        self.conn.commit()
        print(f"Migrated {migrated_dishes} dishes and {migrated_checks} quality checks")
        
        if missing_crosses:
            print(f"⚠️ Created placeholder records for {len(missing_crosses)} missing crosses:")
            for cross_id in sorted(missing_crosses):
                print(f"   - {cross_id}")
            print("   You may want to add proper cross information for these later.")
        
    def migrate_materials(self):
        """Migrate materials data from JSON files."""
        materials_dir = self.source_dir / "materials"
        if not materials_dir.exists():
            print("No materials directory found, skipping...")
            return
            
        cursor = self.conn.cursor()
        migrated_count = 0
        
        for material_file in materials_dir.glob("*.json"):
            if material_file.name.endswith(".bak"):
                continue  # Skip backup files
                
            try:
                # Determine material type from filename
                material_type = material_file.stem
                
                with open(material_file, 'r') as f:
                    materials_data = json.load(f)
                
                # Handle nested structure (like agarose_solutions -> agarose_solutions)
                if isinstance(materials_data, dict) and len(materials_data) == 1:
                    # If there's a nested structure, extract the inner dict
                    inner_key = list(materials_data.keys())[0]
                    if inner_key == material_type or inner_key.replace('_', '-') == material_type:
                        materials_data = materials_data[inner_key]
                
                # Insert each material item
                if isinstance(materials_data, dict):
                    for material_id, material_data in materials_data.items():
                        cursor.execute("""
                        INSERT OR REPLACE INTO materials 
                        (material_type, material_id, data, updated_at)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        """, (
                            material_type,
                            material_id,
                            json.dumps(material_data)
                        ))
                        migrated_count += 1
                
            except Exception as e:
                print(f"Error migrating material {material_file}: {e}")
        
        self.conn.commit()
        print(f"Migrated {migrated_count} material items")
        
    def create_views(self):
        """Create useful views for common queries."""
        cursor = self.conn.cursor()
        
        # Active dishes view
        cursor.execute("""
        CREATE VIEW IF NOT EXISTS active_dishes AS
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
        
        # Recent quality checks view
        cursor.execute("""
        CREATE VIEW IF NOT EXISTS recent_quality_checks AS
        SELECT 
            qc.*,
            d.cross_id,
            d.genotype,
            d.responsible
        FROM quality_checks qc
        JOIN dishes d ON qc.dish_id = d.dish_id
        WHERE d.status = 'active'
        ORDER BY qc.check_time DESC
        LIMIT 50
        """)
        
        self.conn.commit()
        print("Created database views")
        
    def run_migration(self):
        """Run the complete migration process."""
        print(f"Starting migration from {self.source_dir} to {self.db_path}")
        
        # Backup existing database if it exists
        if os.path.exists(self.db_path):
            backup_path = f"{self.db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(self.db_path, backup_path)
            print(f"Backed up existing database to {backup_path}")
        
        self.connect_database()
        
        try:
            self.migrate_crosses()
            self.migrate_dishes()
            self.migrate_materials()
            self.create_views()
            
            # Re-enable foreign key constraints
            self.enable_foreign_keys()
            
            print(f"\n✅ Migration completed successfully!")
            print(f"Database created at: {self.db_path}")
            print("\nYou can now query your data using SQL!")
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            raise
        finally:
            if self.conn:
                self.conn.close()

def main():
    """Main function to run the migration."""
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python migrate_to_nosql.py <path_to_zebrobot_directory>")
        print("Example: python migrate_to_nosql.py /groups/ahrens/ahrenslab/jeremy/zebrobot")
        sys.exit(1)
    
    source_directory = sys.argv[1]
    
    if not os.path.exists(source_directory):
        print(f"Error: Directory {source_directory} does not exist")
        sys.exit(1)
    
    migrator = ZebrobotMigrator(source_directory)
    migrator.run_migration()
    
    # Show some example queries
    print("\n" + "="*50)
    print("EXAMPLE QUERIES")
    print("="*50)
    print("1. View all active dishes:")
    print("   SELECT * FROM active_dishes;")
    print()
    print("2. Get recent quality checks:")
    print("   SELECT * FROM recent_quality_checks;")
    print()
    print("3. Find dishes that haven't been checked in 2 days:")
    print("   SELECT dish_id, last_check FROM active_dishes")
    print("   WHERE last_check < date('now', '-2 days');")
    print()
    print("4. Get all dishes for a specific cross:")
    print("   SELECT * FROM dishes WHERE cross_id = '15180';")
    print()
    print("5. Count fish deaths by dish:")
    print("   SELECT dish_id, SUM(num_dead) as total_deaths")
    print("   FROM quality_checks GROUP BY dish_id;")

if __name__ == "__main__":
    main()