CREATE TABLE crosses (
            cross_id TEXT PRIMARY KEY,
            request_date TEXT,
            responsible_requestor TEXT,
            line_strain TEXT,
            cross_type TEXT,
            cross_status TEXT,
            data JSON,  -- Full JSON data
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        , agg_total_initially_produced INTEGER, agg_total_positive_final INTEGER, agg_yield_percentage REAL, agg_date_aggregated TEXT, requested_groups INTEGER, groups_produced INTEGER, notes TEXT, parents TEXT);
CREATE TABLE dishes (
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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, screening_final_positive_count INTEGER, screening_date_finalized TEXT, species TEXT DEFAULT 'Danio rerio', sex TEXT DEFAULT 'unknown', parent_dish_id TEXT, dish_population_type TEXT, notes TEXT, room TEXT, enclosure_temperature REAL, enclosure_in_beaker BOOLEAN, enclosure_vol_water_total INTEGER, enclosure_light_duration TEXT, enclosure_dawn_dusk TEXT, breeding_parents TEXT, termination_date TEXT, termination_reason TEXT,
            FOREIGN KEY (cross_id) REFERENCES crosses (cross_id)
        );
CREATE TABLE quality_checks (
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
        );
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_type TEXT,  -- agarose_bottles, fish_water_sources, etc.
            material_id TEXT,
            data JSON,  -- Full material data
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(material_type, material_id)
        );
CREATE INDEX idx_dishes_cross_id ON dishes(cross_id);
CREATE INDEX idx_dishes_status ON dishes(status);
CREATE INDEX idx_quality_checks_dish_id ON quality_checks(dish_id);
CREATE INDEX idx_quality_checks_check_time ON quality_checks(check_time);
CREATE INDEX idx_materials_type ON materials(material_type);
CREATE VIEW active_dishes AS
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
/* active_dishes(dish_id,cross_id,genotype,responsible,fish_count,dof,date_created,check_count,last_check) */;
CREATE VIEW recent_quality_checks AS
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
/* recent_quality_checks(id,dish_id,check_time,fed,feed_type,water_changed,vol_water_changed,num_dead,notes,data,created_at,cross_id,genotype,responsible) */;
CREATE UNIQUE INDEX idx_quality_checks_unique
                    ON quality_checks(dish_id, check_time)
                ;
CREATE TABLE screening_steps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dish_id TEXT NOT NULL,
                        screening_datetime TEXT NOT NULL,
                        dpf_screened INTEGER,
                        indicator_screened TEXT,
                        criteria TEXT,
                        count_screened_this_step INTEGER,
                        number_positive INTEGER,
                        tricaine_used BOOLEAN DEFAULT FALSE,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, number_removed_pigmented INTEGER, number_removed_negative INTEGER, number_removed_other INTEGER,
                        FOREIGN KEY (dish_id) REFERENCES dishes(dish_id),
                        UNIQUE(dish_id, screening_datetime)
                    );
CREATE INDEX idx_screening_steps_dish_id
                    ON screening_steps(dish_id)
                ;
CREATE TABLE transgenic_indicators (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cross_id TEXT NOT NULL,
                        modification_type TEXT DEFAULT 'tg',
                        promoter_driver TEXT,
                        reporter_effector TEXT NOT NULL,
                        color TEXT,
                        expected_expression TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (cross_id) REFERENCES crosses(cross_id)
                    );
CREATE INDEX idx_transgenic_indicators_cross_id
                    ON transgenic_indicators(cross_id)
                ;
CREATE INDEX idx_dishes_genotype ON dishes(genotype);
CREATE INDEX idx_dishes_responsible ON dishes(responsible);
CREATE INDEX idx_dishes_dof ON dishes(dof);
CREATE INDEX idx_dishes_date_created ON dishes(date_created);
CREATE INDEX idx_crosses_cross_type ON crosses(cross_type);
CREATE INDEX idx_crosses_cross_status ON crosses(cross_status);
CREATE INDEX idx_crosses_responsible_requestor ON crosses(responsible_requestor);
CREATE TABLE fish_subjects (
  fish_id TEXT PRIMARY KEY,
  dish_id TEXT NOT NULL,
  subject_label TEXT,
  sex TEXT,
  genotype TEXT,
  species TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  notes TEXT,
  FOREIGN KEY (dish_id) REFERENCES dishes(dish_id)
);
CREATE TABLE experiment_sessions (
  session_uuid TEXT PRIMARY KEY,
  run_at_utc TEXT,
  rig_id TEXT,
  arena_id TEXT,
  protocol_name TEXT,
  h5_path TEXT
);
CREATE TABLE fish_runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  fish_id TEXT NOT NULL,
  session_uuid TEXT NOT NULL,
  notes TEXT,
  FOREIGN KEY (fish_id) REFERENCES fish_subjects(fish_id) ON DELETE CASCADE,
  FOREIGN KEY (session_uuid) REFERENCES experiment_sessions(session_uuid) ON DELETE CASCADE,
  UNIQUE (fish_id, session_uuid)
);
CREATE INDEX idx_fish_subjects_dish_id ON fish_subjects(dish_id);
CREATE INDEX idx_fish_runs_fish_id ON fish_runs(fish_id);
CREATE INDEX idx_fish_runs_session_uuid ON fish_runs(session_uuid);
