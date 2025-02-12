import sys
import json
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTabWidget, QLabel, QPushButton, 
                             QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
                             QTableWidget, QTableWidgetItem, QMessageBox, QFrame,
                             QScrollArea, QGridLayout, QGroupBox, QDateEdit, QCheckBox,
                             QFormLayout, QDialog, QSystemTrayIcon, QMenu)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor

def main():
    try:
        print("Starting application...")
        app = QApplication(sys.argv)
        print("Created QApplication")
        
        print("Creating main window...")
        window = LabInventoryGUI()
        print("Created main window")
        
        print("Showing window...")
        window.show()
        print("Window shown")
        
        print("Entering event loop...")
        sys.exit(app.exec())
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        raise

class QualityCheckDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quality Check Entry")
        # Set a fixed size for the dialog
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        self.setup_ui()
    
    def set_current_time(self):
        """Set the check time to current time"""
        current_time = datetime.now().strftime("%Y%m%d%H:%M:%S")
        self.check_time.setText(current_time)

    def handle_save(self):
        """Handle save button click without closing the dialog"""
        # Emit the accepted signal but don't close
        self.accepted.emit()
        # Clear fields after saving
        self.clear_fields()
        
    def clear_fields(self):
        """Clear all input fields"""
        self.set_current_time()  # Reset to current time
        self.fed.setChecked(False)
        self.feed_type.clear()
        self.water_changed.setChecked(False)
        self.vol_water_changed.setValue(0)
        self.num_dead.setValue(0)
        self.notes.clear()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        
        # Set wider spacing
        layout.setSpacing(10)
        form_layout.setSpacing(10)
        
        # Check time (auto-filled with current time)
        self.check_time = QLineEdit()
        current_time = datetime.now().strftime("%Y%m%d%H:%M:%S")
        self.check_time.setText(current_time)
        self.check_time.setPlaceholderText("YYYYMMDDhh:mm:ss")  # Show format
        self.check_time.setReadOnly(False)  # Make it editable
        form_layout.addRow("Check Time:", self.check_time)

        # Add a "Now" button to quickly set current time
        now_button = QPushButton("Set Current Time")
        now_button.clicked.connect(self.set_current_time)
        form_layout.addRow("", now_button)  # Add in new row
        
        # Feeding information
        self.fed = QCheckBox()
        form_layout.addRow("Fed:", self.fed)
        
        self.feed_type = QLineEdit()
        self.feed_type.setEnabled(False)  # Initially disabled
        self.feed_type.setPlaceholderText("e.g., paramecia, dry food")
        form_layout.addRow("Feed Type:", self.feed_type)
        
        # Connect fed checkbox to enable/disable feed type
        self.fed.stateChanged.connect(lambda state: self.feed_type.setEnabled(bool(state)))
        
        # Water change information
        self.water_changed = QCheckBox()
        form_layout.addRow("Water Changed:", self.water_changed)
        
        self.vol_water_changed = QSpinBox()
        self.vol_water_changed.setRange(0, 1000)
        self.vol_water_changed.setSuffix(" mL")
        self.vol_water_changed.setEnabled(False)  # Initially disabled
        form_layout.addRow("Volume Changed:", self.vol_water_changed)
        
        # Connect water changed checkbox to enable/disable volume
        self.water_changed.stateChanged.connect(lambda state: self.vol_water_changed.setEnabled(bool(state)))
        
        # Health information
        self.num_dead = QSpinBox()
        self.num_dead.setRange(0, 100)
        form_layout.addRow("Number Dead:", self.num_dead)
        
        # Notes field
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Any additional observations...")
        form_layout.addRow("Notes:", self.notes)
        
        # Add form to main layout
        layout.addLayout(form_layout)
        
        # Add buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.handle_save)  # Changed to custom handler
        
        button_layout.addWidget(save_button)
        layout.addLayout(button_layout)
        
    def get_data(self):
        """Return the quality check data as a dictionary"""
        return {
            "check_time": self.check_time.text(),
            "fed": self.fed.isChecked(),
            "feed_type": self.feed_type.text() if self.fed.isChecked() else None,
            "water_changed": self.water_changed.isChecked(),
            "vol_water_changed": self.vol_water_changed.value() if self.water_changed.isChecked() else None,
            "num_dead": self.num_dead.value(),
            "notes": self.notes.text() if self.notes.text() else None
        }

class LabInventoryGUI(QMainWindow):
    def __init__(self):
        print("Initializing LabInventoryGUI...")
        super().__init__()
        
        # Initialize data structures with proper nested structure
        self.data = {
            'agarose_bottles': {'agarose_bottles': {}},
            'agarose_solutions': {'agarose_solutions': {}},
            'fish_water_sources': {'fish_water_batches': {}},
            'fish_water_derivatives': {'fish_water_derivatives': {}},
            'poly_l_serine_bottles': {'poly_l_serine_bottles': {}},
            'poly_l_serine_derivatives': {'poly_l_serine_derivatives': {}}
        }
        self.data_dir = None
        
        # Create system tray icon
        self.setup_system_tray()
        
        try:
            print("Starting UI initialization...")
            self.init_ui()
            print("UI initialization complete")
        except Exception as e:
            print(f"Error in init_ui: {str(e)}")
            QMessageBox.critical(self, "Initialization Error", f"Error initializing UI: {str(e)}")
            raise

    def setup_system_tray(self):
        """Setup the system tray icon and menu"""
        # Create the system tray icon
        self.tray_icon = QSystemTrayIcon(self)
        
        # Create a simple icon - you can replace this with your own icon file
        icon = self.create_simple_icon()
        self.tray_icon.setIcon(icon)
        
        # Create the menu
        tray_menu = QMenu()
        
        # Add menu items
        show_action = tray_menu.addAction("Show")
        show_action.triggered.connect(self.show)
        
        hide_action = tray_menu.addAction("Hide")
        hide_action.triggered.connect(self.hide)
        
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(QApplication.quit)
        
        # Set the menu for the tray icon
        self.tray_icon.setContextMenu(tray_menu)
        
        # Show a message when the icon is first displayed
        self.tray_icon.showMessage(
            "Lab Inventory",
            "Application is running in the system tray",
            QSystemTrayIcon.Information,
            2000
        )
        
        # Show the icon
        self.tray_icon.show()
        
        # Connect double click to show/hide window
        self.tray_icon.activated.connect(self.tray_icon_activated)

    def create_simple_icon(self):
        """Create a simple colored square icon if no icon file is available"""
        # Create a pixmap
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        # Create a painter
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw a colored square with rounded corners
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(41, 128, 185))  # Nice blue color
        painter.drawRoundedRect(0, 0, 32, 32, 8, 8)
        
        # End painting
        painter.end()
        
        return QIcon(pixmap)

    def tray_icon_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.DoubleClick:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.raise_()  # Bring window to front
                self.activateWindow()

    def closeEvent(self, event):
        """Override close event to minimize to tray instead of closing"""
        if self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage(
                "Lab Inventory",
                "Application minimized to tray",
                QSystemTrayIcon.Information,
                2000
            )
            event.ignore()
        else:
            event.accept()
            
    def init_ui(self):
        """Initialize the user interface"""
        print("Setting window properties...")
        self.setWindowTitle("Lab Inventory Management System")
        self.setGeometry(100, 100, 1200, 800)
        
        # Load config first
        print("Loading config...")
        if not self.load_config():
            print("Config loading failed")
            return
        print("Config loaded successfully")
            
        # Then try to load data
        print("Loading data...")
        if not self.load_data():
            print("Data loading failed, using empty datasets")
            # Continue with empty data if load fails
            self.data = {
                'agarose_bottles': {'agarose_bottles': {}},
                'agarose_solutions': {'agarose_solutions': {}},
                'fish_water_sources': {'fish_water_batches': {}},
                'fish_water_derivatives': {'fish_water_derivatives': {}},
                'poly_l_serine_bottles': {'poly_l_serine_bottles': {}},
                'poly_l_serine_derivatives': {'poly_l_serine_derivatives': {}},
                'fish_dishes': {'fish_dishes': {}}
            }
        print("Data loaded or initialized")
        
        print("Creating main widget...")
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Create tab widget
        print("Creating tab widget...")
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Add tabs for different sections
        try:
            print("Creating agarose tab...")
            agarose_tab = self.create_agarose_tab()
            tabs.addTab(agarose_tab, "Agarose Solutions")
            
            print("Creating fish water tab...")
            fish_water_tab = self.create_fish_water_tab()
            tabs.addTab(fish_water_tab, "Fish Water")
            
            print("Creating poly-l-serine tab...")
            pls_tab = self.create_poly_l_serine_tab()
            tabs.addTab(pls_tab, "Poly-L-Serine")
            
            print("Creating fish dishes tab...")
            fish_dishes_tab = self.create_fish_dish_tab()
            tabs.addTab(fish_dishes_tab, "Fish Dishes")
            
            print("All tabs created successfully")
        except Exception as e:
            print(f"Error creating tabs: {str(e)}")
            QMessageBox.warning(self, "Tab Creation Error", f"Error creating tabs: {str(e)}")
            raise

    def load_config(self):
        """Load configuration settings"""
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                self.material_data_dir = Path(config['remote_material_data_directory'])
                self.dish_data_dir = Path(config['remote_dish_data_directory'])
        except FileNotFoundError:
            QMessageBox.critical(self, "Error", "config.json not found!")
            return False
        except KeyError:
            QMessageBox.critical(self, "Error", "Invalid config.json format!")
            return False
        except json.JSONDecodeError:
            QMessageBox.critical(self, "Error", "Invalid JSON in config.json!")
            return False
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Unexpected error loading config: {str(e)}")
            return False
                
        # Check if directories exist but don't try to create them
        if not self.material_data_dir.exists():
            QMessageBox.warning(
                self,
                "Warning",
                f"Remote materials directory {self.material_data_dir} does not exist. Will attempt to create when saving."
            )
        if not self.dish_data_dir.exists():
            QMessageBox.warning(
                self,
                "Warning",
                f"Remote dishes directory {self.dish_data_dir} does not exist. Will attempt to create when saving."
            )
        
        return True
        
    def validate_data_structure(self):
        """Validate the data structure has all required keys"""
        required_structure = {
            'agarose_bottles': ['agarose_bottles'],
            'agarose_solutions': ['agarose_solutions'],
            'fish_water_sources': ['fish_water_batches'],
            'fish_water_derivatives': ['fish_water_derivatives'],
            'poly_l_serine_bottles': ['poly_l_serine_bottles'],
            'poly_l_serine_derivatives': ['poly_l_serine_derivatives']
        }
        
        for key, subkeys in required_structure.items():
            if key not in self.data:
                print(f"Missing top-level key: {key}")
                self.data[key] = {}
            
            for subkey in subkeys:
                if subkey not in self.data[key]:
                    print(f"Missing subkey {subkey} in {key}")
                    self.data[key][subkey] = {}
                    
        return True

    def load_data(self):
        """Load all data files from remote directories"""
        success = True
        
        # Load material files
        material_files = {
            'agarose_bottles': 'agarose_bottles.json',
            'agarose_solutions': 'agarose_solutions.json',
            'fish_water_sources': 'fish_water_sources.json',
            'fish_water_derivatives': 'fish_water_derivatives.json',
            'poly_l_serine_bottles': 'poly-l-serine_bottles.json',
            'poly_l_serine_derivatives': 'poly-l-serine_derivatives.json'
        }
        
        if not self.material_data_dir:
            print("No material data directory configured")
            success = False
        else:
            success &= self._load_category_files(material_files, self.material_data_dir)
        
        # Load fish dishes
        try:
            self.data['fish_dishes'] = self.load_fish_dishes()
        except Exception as e:
            print(f"Error loading fish dishes: {str(e)}")
            self.data['fish_dishes'] = {'fish_dishes': {}}
            success = False
        
        # Validate and fix data structure
        print("Validating data structure...")
        self.validate_data_structure()
        
        return success

    def _load_category_files(self, file_dict, directory):
        """Helper function to load files from a specific directory"""
        success = True
        for key, filename in file_dict.items():
            file_path = directory / filename
            try:
                if file_path.exists():
                    print(f"Loading {filename}...")
                    with open(file_path, 'r') as f:
                        self.data[key] = json.load(f)
                else:
                    print(f"File {filename} not found, using empty dict")
                    self.data[key] = {}
            except Exception as e:
                print(f"Error loading {filename}: {str(e)}")
                QMessageBox.warning(
                    self,
                    "Data Loading Error",
                    f"Error loading {filename}: {str(e)}\nStarting with empty dataset."
                )
                self.data[key] = {}
                success = False
        
        return success
                
    def save_data(self):
        """Save all data back to JSON files in appropriate remote directories"""
        material_categories = {
            'agarose_bottles', 'agarose_solutions', 'fish_water_sources', 
            'fish_water_derivatives', 'poly_l_serine_bottles', 'poly_l_serine_derivatives'
        }
        dish_categories = {'fish_dishes'}
        
        success = True
        
        # Save material data
        if not self._save_category_data(material_categories, self.material_data_dir):
            success = False
            
        # Save dish data
        if not self._save_category_data(dish_categories, self.dish_data_dir):
            success = False
            
        return success

    def safe_get_nested(self, dict_obj, *keys, default=None):
        """Safely get nested dictionary values"""
        try:
            result = dict_obj
            for key in keys:
                result = result[key]
            return result if result is not None else default
        except (KeyError, TypeError):
            return default
    
    def create_agarose_tab(self):
        """Create the agarose solutions management tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Add new solution section
        form_layout = QHBoxLayout()
        
        # Bottle ID input
        bottle_layout = QVBoxLayout()
        bottle_layout.addWidget(QLabel("Agarose Bottle ID:"))
        self.agarose_bottle_id = QLineEdit()
        bottle_layout.addWidget(self.agarose_bottle_id)
        form_layout.addLayout(bottle_layout)
        
        # Concentration input
        conc_layout = QVBoxLayout()
        conc_layout.addWidget(QLabel("Concentration:"))
        self.concentration = QDoubleSpinBox()
        self.concentration.setRange(0, 1)
        self.concentration.setSingleStep(0.01)
        self.concentration.setValue(0.02)
        conc_layout.addWidget(self.concentration)
        form_layout.addLayout(conc_layout)
        
        # Volume input
        volume_layout = QVBoxLayout()
        volume_layout.addWidget(QLabel("Volume (mL):"))
        self.volume = QSpinBox()
        self.volume.setRange(0, 1000)
        self.volume.setValue(100)
        volume_layout.addWidget(self.volume)
        form_layout.addLayout(volume_layout)
        
        # Fish water batch selection
        fw_layout = QVBoxLayout()
        fw_layout.addWidget(QLabel("Fish Water Batch:"))
        self.fw_batch = QComboBox()
        self.update_fw_batches()
        fw_layout.addWidget(self.fw_batch)
        form_layout.addLayout(fw_layout)
        
        # Add solution button
        add_button = QPushButton("Add New Solution")
        add_button.clicked.connect(self.add_agarose_solution)
        form_layout.addWidget(add_button)
        
        layout.addLayout(form_layout)
        
        # Solutions table
        self.solutions_table = QTableWidget()
        self.solutions_table.setColumnCount(7)
        self.solutions_table.setHorizontalHeaderLabels([
            "Solution ID", "Date Prepared", "Concentration", "Volume (mL)",
            "Fish Water Batch", "Storage Location", "Expiration"
        ])
        layout.addWidget(self.solutions_table)
        
        self.update_solutions_table()
        return tab
    
    def create_fish_water_tab(self):
        """Create the fish water management tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Add new source batch section
        source_section = QWidget()
        source_layout = QVBoxLayout(source_section)
        
        # Source section header
        source_header = QLabel("Add New Source Batch")
        source_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        source_layout.addWidget(source_header)
        
        # Source batch form
        source_form = QHBoxLayout()
        
        # Batch ID input
        batch_id_layout = QVBoxLayout()
        batch_id_layout.addWidget(QLabel("Source Batch ID:"))
        self.source_batch_id = QLineEdit()
        self.source_batch_id.setPlaceholderText("FW_2025_XXXX")
        batch_id_layout.addWidget(self.source_batch_id)
        source_form.addLayout(batch_id_layout)
        
        # Preparation date input
        prep_date_layout = QVBoxLayout()
        prep_date_layout.addWidget(QLabel("Preparation Date:"))
        self.prep_date = QLineEdit()
        self.prep_date.setPlaceholderText("YYYY-MM-DD")
        prep_date_layout.addWidget(self.prep_date)
        source_form.addLayout(prep_date_layout)
        
        # Notes input
        notes_layout = QVBoxLayout()
        notes_layout.addWidget(QLabel("Notes (optional):"))
        self.source_notes = QLineEdit()
        self.source_notes.setPlaceholderText("Enter any notes...")
        notes_layout.addWidget(self.source_notes)
        source_form.addLayout(notes_layout)
        
        # Add source button
        add_source_button = QPushButton("Add Source Batch")
        add_source_button.clicked.connect(self.add_source_batch)
        source_form.addWidget(add_source_button)
        
        source_layout.addLayout(source_form)
        layout.addWidget(source_section)
        
        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Filtered water section header
        filtered_header = QLabel("Add New Filtered Batch")
        filtered_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(filtered_header)
        
        # Add filtered water section (existing code)
        form_layout = QHBoxLayout()
        
        # Source batch selection
        source_layout = QVBoxLayout()
        source_layout.addWidget(QLabel("Source Batch:"))
        self.fw_source_batch = QComboBox()
        self.update_fw_sources()
        source_layout.addWidget(self.fw_source_batch)
        form_layout.addLayout(source_layout)
        
        # Volume input
        volume_layout = QVBoxLayout()
        volume_layout.addWidget(QLabel("Volume (mL):"))
        self.fw_volume = QSpinBox()
        self.fw_volume.setRange(0, 1000)
        self.fw_volume.setValue(250)
        volume_layout.addWidget(self.fw_volume)
        form_layout.addLayout(volume_layout)
        
        # Filter size input
        filter_layout = QVBoxLayout()
        filter_layout.addWidget(QLabel("Filter Size (μm):"))
        self.filter_size = QSpinBox()
        self.filter_size.setRange(0, 100)
        self.filter_size.setValue(20)
        filter_layout.addWidget(self.filter_size)
        form_layout.addLayout(filter_layout)
        
        # Add batch button
        add_button = QPushButton("Add Filtered Batch")
        add_button.clicked.connect(self.add_filtered_water)
        form_layout.addWidget(add_button)
        
        layout.addLayout(form_layout)
        
        # Add separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator2)
        
        # Table section header
        table_header = QLabel("Fish Water Batches")
        table_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(table_header)
        
        # Batches table
        self.fw_table = QTableWidget()
        self.fw_table.setColumnCount(5)
        self.fw_table.setHorizontalHeaderLabels([
            "Batch ID", "Source Batch", "Date Prepared", 
            "Volume (mL)", "Storage Location"
        ])
        layout.addWidget(self.fw_table)
        
        self.update_fw_table()
        return tab
    
    def create_poly_l_serine_tab(self):
        """Create the poly-l-serine management tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Add new aliquot section
        form_layout = QHBoxLayout()
        
        # Bottle selection
        bottle_layout = QVBoxLayout()
        bottle_layout.addWidget(QLabel("Source Bottle:"))
        self.pls_bottle = QComboBox()
        self.update_pls_bottles()
        bottle_layout.addWidget(self.pls_bottle)
        form_layout.addLayout(bottle_layout)
        
        # Volume input
        volume_layout = QVBoxLayout()
        volume_layout.addWidget(QLabel("Volume (mL):"))
        self.pls_volume = QSpinBox()
        self.pls_volume.setRange(0, 100)
        self.pls_volume.setValue(50)
        volume_layout.addWidget(self.pls_volume)
        form_layout.addLayout(volume_layout)
        
        # Add aliquot button
        add_button = QPushButton("Add New Aliquot")
        add_button.clicked.connect(self.add_pls_aliquot)
        form_layout.addWidget(add_button)
        
        layout.addLayout(form_layout)
        
        # Aliquots table
        self.pls_table = QTableWidget()
        self.pls_table.setColumnCount(5)
        self.pls_table.setHorizontalHeaderLabels([
            "Aliquot ID", "Source Bottle", "Date Prepared",
            "Volume (mL)", "Storage Location"
        ])
        layout.addWidget(self.pls_table)
        
        self.update_pls_table()
        return tab
    
    def update_fw_batches(self):
        """Update fish water batch dropdown"""
        self.fw_batch.clear()
        batches = self.safe_get_nested(self.data, 'fish_water_sources', 'fish_water_batches', default={})
        for batch_id in batches:
            self.fw_batch.addItem(batch_id)
            
    def update_fw_sources(self):
        """Update fish water source batch dropdown"""
        self.fw_source_batch.clear()
        batches = self.safe_get_nested(self.data, 'fish_water_sources', 'fish_water_batches', default={})
        for batch_id in batches:
            self.fw_source_batch.addItem(batch_id)
            
    def update_pls_bottles(self):
        """Update poly-l-serine bottle dropdown"""
        self.pls_bottle.clear()
        bottles = self.safe_get_nested(self.data, 'poly_l_serine_bottles', 'poly_l_serine_bottles', default={})
        for bottle_id in bottles:
            self.pls_bottle.addItem(bottle_id)
    
    def update_solutions_table(self):
        """Update the agarose solutions table"""
        solutions = self.safe_get_nested(self.data, 'agarose_solutions', 'agarose_solutions', default={})
        self.solutions_table.setRowCount(len(solutions))
        
        for i, (sol_id, sol_data) in enumerate(solutions.items()):
            self.solutions_table.setItem(i, 0, QTableWidgetItem(sol_id))
            self.solutions_table.setItem(i, 1, QTableWidgetItem(str(self.safe_get_nested(sol_data, 'date_prepared', default=''))))
            self.solutions_table.setItem(i, 2, QTableWidgetItem(str(self.safe_get_nested(sol_data, 'concentration', default=''))))
            self.solutions_table.setItem(i, 3, QTableWidgetItem(str(self.safe_get_nested(sol_data, 'volume_prepared_mL', default=''))))
            self.solutions_table.setItem(i, 4, QTableWidgetItem(str(self.safe_get_nested(sol_data, 'fish_water_batch_id', default=''))))
            self.solutions_table.setItem(i, 5, QTableWidgetItem(str(self.safe_get_nested(sol_data, 'storage', 'location', default=''))))
            self.solutions_table.setItem(i, 6, QTableWidgetItem(str(self.safe_get_nested(sol_data, 'storage', 'expiration', default=''))))
    
    def update_fw_table(self):
        """Update the fish water table"""
        batches = self.safe_get_nested(self.data, 'fish_water_derivatives', 'fish_water_derivatives', default={})
        self.fw_table.setRowCount(len(batches))
        
        for i, (batch_id, batch_data) in enumerate(batches.items()):
            self.fw_table.setItem(i, 0, QTableWidgetItem(batch_id))
            self.fw_table.setItem(i, 1, QTableWidgetItem(str(self.safe_get_nested(batch_data, 'source_batch_id', default=''))))
            self.fw_table.setItem(i, 2, QTableWidgetItem(str(self.safe_get_nested(batch_data, 'date_prepared', default=''))))
            self.fw_table.setItem(i, 3, QTableWidgetItem(str(self.safe_get_nested(batch_data, 'volume_prepared_mL', default=''))))
            self.fw_table.setItem(i, 4, QTableWidgetItem(str(self.safe_get_nested(batch_data, 'storage', 'location', default=''))))
    
    def update_pls_table(self):
        """Update the poly-l-serine table"""
        aliquots = self.safe_get_nested(self.data, 'poly_l_serine_derivatives', 'poly_l_serine_derivatives', default={})
        self.pls_table.setRowCount(len(aliquots))
        
        for i, (aliquot_id, aliquot_data) in enumerate(aliquots.items()):
            self.pls_table.setItem(i, 0, QTableWidgetItem(aliquot_id))
            self.pls_table.setItem(i, 1, QTableWidgetItem(str(self.safe_get_nested(aliquot_data, 'source_bottle_id', default=''))))
            self.pls_table.setItem(i, 2, QTableWidgetItem(str(self.safe_get_nested(aliquot_data, 'date_prepared', default=''))))
            self.pls_table.setItem(i, 3, QTableWidgetItem(str(self.safe_get_nested(aliquot_data, 'volume_prepared', default=''))))
            self.pls_table.setItem(i, 4, QTableWidgetItem(str(self.safe_get_nested(aliquot_data, 'storage', 'location', default=''))))
    
    def add_agarose_solution(self):
        """Add a new agarose solution"""
        today = datetime.now().strftime("%Y%m%d")
        solution_id = f"AGSOL_{today}"
        
        # Check if solution ID already exists
        solutions = self.safe_get_nested(self.data, 'agarose_solutions', 'agarose_solutions', default={})
        if solution_id in solutions:
            # Find next available ID
            i = 1
            while f"{solution_id}_{i}" in solutions:
                i += 1
            solution_id = f"{solution_id}_{i}"
        
        new_solution = {
            "concentration": self.concentration.value(),
            "date_prepared": today,
            "prepared_by": "Lab Staff",  # Could add user input for this
            "agarose_bottle_id": self.agarose_bottle_id.text(),
            "fish_water_batch_id": self.fw_batch.currentText(),
            "volume_prepared_mL": self.volume.value(),
            "storage": {
                "location": "2E.260-6-3",  # Could add input for this
                "container": "incubator",
                "expiration": (datetime.now().replace(year=datetime.now().year + 1)
                             .strftime("%Y%m%d"))
            },
            "quality_checks": {
                "visual_inspection": "Clear, no particles"
            },
            "notes": None
        }
        
        if 'agarose_solutions' not in self.data:
            self.data['agarose_solutions'] = {'agarose_solutions': {}}
        
        self.data['agarose_solutions']['agarose_solutions'][solution_id] = new_solution
        self.save_data()
        self.update_solutions_table()
        
        # Clear inputs
        self.agarose_bottle_id.clear()
        self.volume.setValue(100)
        self.concentration.setValue(0.02)

    def create_fish_water_tab(self):
        """Create the fish water management tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Add new source batch section
        source_section = QWidget()
        source_layout = QVBoxLayout(source_section)
        
        # Source section header
        source_header = QLabel("Add New Source Batch")
        source_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        source_layout.addWidget(source_header)
        
        # Source batch form
        source_form = QHBoxLayout()
        
        # Batch ID input
        batch_id_layout = QVBoxLayout()
        batch_id_layout.addWidget(QLabel("Source Batch ID:"))
        self.source_batch_id = QLineEdit()
        self.source_batch_id.setPlaceholderText("FW_2025_XXXX")
        batch_id_layout.addWidget(self.source_batch_id)
        source_form.addLayout(batch_id_layout)
        
        # Preparation date input
        prep_date_layout = QVBoxLayout()
        prep_date_layout.addWidget(QLabel("Preparation Date:"))
        self.prep_date = QLineEdit()
        self.prep_date.setPlaceholderText("YYYY-MM-DD")
        prep_date_layout.addWidget(self.prep_date)
        source_form.addLayout(prep_date_layout)
        
        # Notes input
        notes_layout = QVBoxLayout()
        notes_layout.addWidget(QLabel("Notes (optional):"))
        self.source_notes = QLineEdit()
        self.source_notes.setPlaceholderText("Enter any notes...")
        notes_layout.addWidget(self.source_notes)
        source_form.addLayout(notes_layout)
        
        # Add source button
        add_source_button = QPushButton("Add Source Batch")
        add_source_button.clicked.connect(self.add_source_batch)
        source_form.addWidget(add_source_button)
        
        source_layout.addLayout(source_form)
        layout.addWidget(source_section)
        
        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Filtered water section header
        filtered_header = QLabel("Add New Filtered Batch")
        filtered_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(filtered_header)
        
        # Add filtered water section (existing code)
        form_layout = QHBoxLayout()
        
        # Source batch selection
        source_layout = QVBoxLayout()
        source_layout.addWidget(QLabel("Source Batch:"))
        self.fw_source_batch = QComboBox()
        self.update_fw_sources()
        source_layout.addWidget(self.fw_source_batch)
        form_layout.addLayout(source_layout)
        
        # Volume input
        volume_layout = QVBoxLayout()
        volume_layout.addWidget(QLabel("Volume (mL):"))
        self.fw_volume = QSpinBox()
        self.fw_volume.setRange(0, 1000)
        self.fw_volume.setValue(250)
        volume_layout.addWidget(self.fw_volume)
        form_layout.addLayout(volume_layout)
        
        # Filter size input
        filter_layout = QVBoxLayout()
        filter_layout.addWidget(QLabel("Filter Size (μm):"))
        self.filter_size = QSpinBox()
        self.filter_size.setRange(0, 100)
        self.filter_size.setValue(20)
        filter_layout.addWidget(self.filter_size)
        form_layout.addLayout(filter_layout)
        
        # Add batch button
        add_button = QPushButton("Add Filtered Batch")
        add_button.clicked.connect(self.add_filtered_water)
        form_layout.addWidget(add_button)
        
        layout.addLayout(form_layout)
        
        # Add separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator2)
        
        # Table section header
        table_header = QLabel("Fish Water Batches")
        table_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(table_header)
        
        # Batches table
        self.fw_table = QTableWidget()
        self.fw_table.setColumnCount(5)
        self.fw_table.setHorizontalHeaderLabels([
            "Batch ID", "Source Batch", "Date Prepared", 
            "Volume (mL)", "Storage Location"
        ])
        layout.addWidget(self.fw_table)
        
        self.update_fw_table()
        return tab

    def add_source_batch(self):
        """Add a new fish water source batch"""
        # Get input values
        batch_id = self.source_batch_id.text().strip()
        prep_date = self.prep_date.text().strip()
        notes = self.source_notes.text().strip() or None
        
        # Validate inputs
        if not batch_id:
            QMessageBox.warning(self, "Input Error", "Please enter a batch ID")
            return
            
        if not prep_date:
            QMessageBox.warning(self, "Input Error", "Please enter a preparation date")
            return
        
        # Validate date format
        try:
            datetime.strptime(prep_date, "%Y-%m-%d")
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Please enter date in YYYY-MM-DD format")
            return
        
        # Check if batch ID already exists
        existing_batches = self.safe_get_nested(self.data, 'fish_water_sources', 'fish_water_batches', default={})
        if batch_id in existing_batches:
            QMessageBox.warning(self, "Input Error", f"Batch ID {batch_id} already exists")
            return
        
        # Create new batch entry
        new_batch = {
            "source": "Janelia System",
            "preparation_date": prep_date,
            "notes": notes
        }
        
        # Ensure data structure exists
        if 'fish_water_sources' not in self.data:
            self.data['fish_water_sources'] = {'fish_water_batches': {}}
        
        # Add new batch
        self.data['fish_water_sources']['fish_water_batches'][batch_id] = new_batch
        
        # Save data and update UI
        if self.save_data():
            self.update_fw_sources()  # Update source batch dropdown
            QMessageBox.information(self, "Success", f"Added new source batch {batch_id}")
            
            # Clear inputs
            self.source_batch_id.clear()
            self.prep_date.clear()
            self.source_notes.clear()
        else:
            QMessageBox.warning(self, "Error", "Failed to save data")
        
    def add_filtered_water(self):
        """Add a new filtered water batch"""
        today = datetime.now().strftime("%Y%m%d")
        batch_id = f"FW_FILTERED_{today}"
        
        # Check if batch ID already exists
        batches = self.safe_get_nested(self.data, 'fish_water_derivatives', 'fish_water_derivatives', default={})
        if batch_id in batches:
            # Find next available ID
            i = 1
            while f"{batch_id}_{i}" in batches:
                i += 1
            batch_id = f"{batch_id}_{i}"
        
        new_batch = {
            "source_batch_id": self.fw_source_batch.currentText(),
            "type": "filtered",
            "date_prepared": today,
            "prepared_by": "Lab Staff",  # Could add user input for this
            "volume_prepared_mL": self.fw_volume.value(),
            "storage": {
                "location": "2E.260-7-B"  # Could add input for this
            },
            "processing": {
                "filter_type": "vacuum",
                "filter_size": f"{self.filter_size.value()}um"
            },
            "quality_checks": {
                "visual_inspection": "clear, no particles"
            },
            "notes": None
        }
        
        if 'fish_water_derivatives' not in self.data:
            self.data['fish_water_derivatives'] = {'fish_water_derivatives': {}}
        
        self.data['fish_water_derivatives']['fish_water_derivatives'][batch_id] = new_batch
        self.save_data()
        self.update_fw_table()
        
        # Clear inputs
        self.fw_volume.setValue(250)
        self.filter_size.setValue(20)
        
    def add_pls_aliquot(self):
        """Add a new poly-l-serine aliquot"""
        today = datetime.now().strftime("%Y%m%d")
        aliquot_id = f"PLS_ALIQUOT_{today}"
        
        # Check if aliquot ID already exists
        aliquots = self.safe_get_nested(self.data, 'poly_l_serine_derivatives', 'poly_l_serine_derivatives', default={})
        if aliquot_id in aliquots:
            # Find next available ID
            i = 1
            while f"{aliquot_id}_{i}" in aliquots:
                i += 1
            aliquot_id = f"{aliquot_id}_{i}"
        
        # Get expiration date from source bottle
        source_bottle = self.safe_get_nested(
            self.data, 'poly_l_serine_bottles', 'poly_l_serine_bottles', 
            self.pls_bottle.currentText(), default={}
        )
        expiration_date = self.safe_get_nested(source_bottle, 'expiration_date', default='')
        
        new_aliquot = {
            "source_bottle_id": self.pls_bottle.currentText(),
            "type": "aliquot",
            "date_prepared": today,
            "prepared_by": "Lab Staff",  # Could add user input for this
            "volume_prepared": self.pls_volume.value(),
            "storage": {
                "location": "2E.254",  # Could add input for this
                "container": "50mL tube",
                "expiration_date": expiration_date
            },
            "notes": None
        }
        
        if 'poly_l_serine_derivatives' not in self.data:
            self.data['poly_l_serine_derivatives'] = {'poly_l_serine_derivatives': {}}
        
        self.data['poly_l_serine_derivatives']['poly_l_serine_derivatives'][aliquot_id] = new_aliquot
        self.save_data()
        self.update_pls_table()
        
        # Clear inputs
        self.pls_volume.setValue(50)

    def create_fish_dish_tab(self):
        """Create the fish dish management tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Create scroll area for the form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Form section
        form_group = QGroupBox("New Dish Information")
        form_layout = QGridLayout()
        
        # Basic information section
        row = 0
        
        # Cross ID
        form_layout.addWidget(QLabel("Cross ID:"), row, 0)
        self.cross_id = QLineEdit()
        form_layout.addWidget(self.cross_id, row, 1)
        
        row += 1
        
        # Dish number
        form_layout.addWidget(QLabel("Dish Number:"), row, 0)
        self.dish_number = QSpinBox()
        self.dish_number.setMinimum(1)
        form_layout.addWidget(self.dish_number, row, 1)

        
        row += 1
        
        # Date of fertilization
        form_layout.addWidget(QLabel("Date of Fertilization:"), row, 0)
        self.dof = QDateEdit()
        self.dof.setDate(QDate.currentDate())
        self.dof.setCalendarPopup(True)
        form_layout.addWidget(self.dof, row, 1)
        
        # Genotype
        form_layout.addWidget(QLabel("Genotype:"), row, 2)
        self.genotype = QLineEdit()
        form_layout.addWidget(self.genotype, row, 3)
        
        row += 1
        
        # Sex
        form_layout.addWidget(QLabel("Sex:"), row, 0)
        self.sex = QComboBox()
        self.sex.addItems(["unknown", "M", "F"])
        form_layout.addWidget(self.sex, row, 1)
        
        # Species
        form_layout.addWidget(QLabel("Species:"), row, 2)
        self.species = QLineEdit()
        self.species.setText("Danio rerio")  # Default value
        form_layout.addWidget(self.species, row, 3)
        
        row += 1
        
        # Responsible person
        form_layout.addWidget(QLabel("Responsible:"), row, 0)
        self.responsible = QLineEdit()
        self.responsible.setText("Jeremy Delahanty")
        form_layout.addWidget(self.responsible, row, 1)
        
        # Parents section
        form_layout.addWidget(QLabel("Parents:"), row, 2)
        self.parents = QLineEdit()
        self.parents.setPlaceholderText("Comma-separated list")
        form_layout.addWidget(self.parents, row, 3)
        
        row += 1
        
        # Incubator Properties section
        form_layout.addWidget(QLabel("Temperature (°C):"), row, 0)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(18, 30)
        self.temperature.setValue(28.5)
        self.temperature.setSingleStep(0.5)
        form_layout.addWidget(self.temperature, row, 1)
        
        # Room
        form_layout.addWidget(QLabel("Room:"), row, 2)
        self.room = QLineEdit()
        self.room.setText("2E.282")  # Default value
        form_layout.addWidget(self.room, row, 3)
        
        row += 1
        
        # Light cycle
        form_layout.addWidget(QLabel("Light Duration:"), row, 0)
        self.light_duration = QLineEdit()
        self.light_duration.setText("14:00")  # Default value
        form_layout.addWidget(self.light_duration, row, 1)
        
        form_layout.addWidget(QLabel("Dawn/Dusk Time:"), row, 2)
        self.dawn_dusk = QLineEdit()
        self.dawn_dusk.setText("8:00")
        form_layout.addWidget(self.dawn_dusk, row, 3)
        
        row += 1
        
        # Whether a dish is in a beaker or not
        form_layout.addWidget(QLabel("In a beaker?"), row, 0)
        self.beaker_housing = QCheckBox()
        self.beaker_housing.setChecked(False)
        form_layout.addWidget(self.beaker_housing, row, 1)
        
        row += 1

        # Number of fish
        form_layout.addWidget(QLabel("Number of Fish:"), row, 0)
        self.fish_count = QSpinBox()
        self.fish_count.setRange(0, 1000)  # Set reasonable range
        self.fish_count.setValue(1)  # Default value
        form_layout.addWidget(self.fish_count, row, 1)
        
        # Add form to group box
        form_group.setLayout(form_layout)
        scroll_layout.addWidget(form_group)
        
        # Add buttons
        button_layout = QHBoxLayout()
        add_button = QPushButton("Add New Dish")
        add_button.clicked.connect(self.add_fish_dish)
        button_layout.addWidget(add_button)
        
        clear_button = QPushButton("Clear Form")
        clear_button.clicked.connect(self.clear_fish_dish_form)
        button_layout.addWidget(clear_button)
        
        scroll_layout.addLayout(button_layout)
        
        # Add scroll area to main layout
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # # Dishes table
        self.dishes_table = QTableWidget()
        self.dishes_table.setColumnCount(6)
        self.dishes_table.setHorizontalHeaderLabels([
            "Dish ID", "Date Created", "Genotype",
            "Responsible", "Status", "Location"
        ])
        layout.addWidget(self.dishes_table)

        # Connect double-click signal after creating the table
        self.dishes_table.cellDoubleClicked.connect(self.handle_dish_double_click)
        
        self.update_dishes_table()
        return tab

    def clear_fish_dish_form(self):
        """Clear all inputs in the fish dish form"""
        self.cross_id.clear()
        self.dish_number.setValue(1)
        self.dof.setDate(QDate.currentDate())
        self.genotype.clear()
        self.sex.setCurrentText("unknown")
        self.species.setText("Danio rerio")
        self.responsible.setText("Jeremy Delahanty")
        self.parents.clear()
        self.temperature.setValue(28.5)
        self.room.setText("2E.282")
        self.light_duration.setText("14:10")
        self.dawn_dusk.setText("8:00")
        self.beaker_housing.setChecked(False)
        self.fish_count.setValue(1)

    def setup_dish_table(self):
        """Setup the dish table with double-click handling"""
        # Set up table as before
        self.dishes_table.setColumnCount(6)
        self.dishes_table.setHorizontalHeaderLabels([
            "Dish ID", "Date Created", "Genotype",
            "Responsible", "Status", "Location"
        ])
        
        # Connect double-click signal
        self.dishes_table.cellDoubleClicked.connect(self.handle_dish_double_click)

    def handle_dish_double_click(self, row, column):
        """Handle double-click on a dish in the table"""
        try:
            # Get dish ID from the first column
            dish_id = self.dishes_table.item(row, 0).text()
            
            # Get the dish data
            dish_data = self.load_single_dish(dish_id)
            if not dish_data:
                QMessageBox.warning(self, "Error", f"Could not load dish {dish_id}")
                return
            
            # Show quality check dialog
            dialog = QualityCheckDialog(self)
            
            # Connect the accepted signal to handle saves
            dialog.accepted.connect(lambda: self.handle_quality_check_save(dish_id, dialog))
            
            # Show the dialog (non-modal)
            dialog.show()
        
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error updating dish: {str(e)}")

    def handle_quality_check_save(self, dish_id, dialog):
        """Handle saving of quality check data"""
        try:
            # Get quality check data
            check_data = dialog.get_data()
            
            # Update the dish data
            if self.update_dish_quality_check(dish_id, check_data):
                # Success message (optional - might be annoying with multiple saves)
                QMessageBox.information(self, "Success", "Quality check saved successfully")
            else:
                QMessageBox.warning(self, "Error", "Failed to save quality check")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error saving quality check: {str(e)}")

    def add_fish_dish(self):
        """Add a new fish dish"""
        try:
            # Get today's date
            today = datetime.now().strftime("%Y%m%d")
            
            # Generate dish ID
            dish_id = f"{self.cross_id.text()}_{self.dish_number.value()}"
            
            # Create the metadata structure
            metadata = {
                "cross_id": self.cross_id.text(),
                "dish_id": {
                    "dish_number": self.dish_number.value(),
                },
                "dof": self.dof.date().toString("yyyyMMdd"),
                "genotype": self.genotype.text(),
                "sex": self.sex.currentText(),
                "species": self.species.text(),
                "responsible": self.responsible.text(),
                "fish_count": self.fish_count.value(),
                "breeding": {
                    "parents": [p.strip() for p in self.parents.text().split(",") if p.strip()]
                },
                "enclosure": {
                    "temperature": self.temperature.value(),
                    "light_cycle": {
                        "light_duration": self.light_duration.text(),
                        "dawn_dusk": self.dawn_dusk.text()
                    },
                    "room": self.room.text(),
                    "in_beaker": self.beaker_housing.isChecked()
                }
            }
            
            # Create the new dish entry
            new_dish = {
                "dish_id": dish_id,
                "date_created": today,
                "metadata": metadata,
                "quality_checks": {
                    today: "Created and checked - normal"
                },
                "status": "active",
                "termination_date": None,
                "termination_reason": None
            }
            
            # Check if dish already exists
            dish_file = self.dish_data_dir / f"{dish_id}_{metadata['dof']}.json"
            if dish_file.exists():
                QMessageBox.warning(self, "Error", f"Dish {dish_id} already exists!")
                return
            
            # Save the individual dish file
            if self.save_fish_dish(new_dish):
                # Update the in-memory data structure
                if 'fish_dishes' not in self.data:
                    self.data['fish_dishes'] = {'fish_dishes': {}}
                self.data['fish_dishes']['fish_dishes'][dish_id] = new_dish
                
                self.update_dishes_table()
                self.clear_fish_dish_form()
                QMessageBox.information(self, "Success", f"Added new dish: {dish_id}")
            else:
                QMessageBox.warning(self, "Error", "Failed to save dish")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error adding dish: {str(e)}")

    def save_fish_dish(self, dish_data):
        """Save a single fish dish to its own file"""
        if not self.dish_data_dir:
            QMessageBox.critical(self, "Save Error", "No dish data directory configured!")
            return False
            
        try:
            # Create dishes directory if it doesn't exist
            self.dish_data_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename from dish_id and dof
            dish_id = dish_data['dish_id']
            dof = dish_data['metadata']['dof']
            filename = f"{dish_id}_{dof}.json"
            file_path = self.dish_data_dir / filename
            
            # Save dish to file
            with open(file_path, 'w') as f:
                json.dump(dish_data, f, indent=2)
                
            return True
                
        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Error saving dish: {str(e)}"
            )
            return False

    def load_fish_dishes(self):
        """Load all fish dishes from the directory"""
        if not self.dish_data_dir:
            return {'fish_dishes': {}}
            
        dishes = {}
        try:
            # Load each dish file in the directory
            for dish_file in self.dish_data_dir.glob("*.json"):
                with open(dish_file, 'r') as f:
                    dish_data = json.load(f)
                    dish_id = dish_data['dish_id']
                    dishes[dish_id] = dish_data
                    
            return {'fish_dishes': dishes}
            
        except Exception as e:
            print(f"Error loading dishes: {str(e)}")
            return {'fish_dishes': {}}

    def load_single_dish(self, dish_id):
        """Load a single dish file"""
        try:
            # Find the dish file
            dish_files = list(self.dish_data_dir.glob(f"{dish_id}_*.json"))
            if not dish_files:
                return None
                
            # Load the dish data
            with open(dish_files[0], 'r') as f:
                return json.load(f)
                
        except Exception as e:
            print(f"Error loading dish {dish_id}: {str(e)}")
            return None

    def update_dish_quality_check(self, dish_id, check_data):
        """Update the quality checks for a dish"""
        try:
            # Load current dish data
            dish_data = self.load_single_dish(dish_id)
            if not dish_data:
                return False
                
            # Add new quality check
            check_time = check_data['check_time']
            dish_data['quality_checks'][check_time] = check_data
            
            # Save updated dish data
            dof = dish_data['metadata']['dof']
            file_path = self.dish_data_dir / f"{dish_id}_{dof}.json"
            
            with open(file_path, 'w') as f:
                json.dump(dish_data, f, indent=2)
                
            # Update in-memory data
            self.data['fish_dishes']['fish_dishes'][dish_id] = dish_data
            
            return True
        
        except Exception as e:
            print(f"Error updating dish {dish_id}: {str(e)}")
            return False

    def update_dishes_table(self):
        """Update the fish dishes table"""
        dishes = self.safe_get_nested(self.data, 'fish_dishes', 'fish_dishes', default={})
        self.dishes_table.setRowCount(len(dishes))
        
        for i, (dish_id, dish_data) in enumerate(dishes.items()):
            self.dishes_table.setItem(i, 0, QTableWidgetItem(dish_id))

            self.dishes_table.setItem(i, 1, QTableWidgetItem(
                str(self.safe_get_nested(dish_data, 'date_created', default=''))
            ))
            self.dishes_table.setItem(i, 2, QTableWidgetItem(
                str(self.safe_get_nested(dish_data, 'metadata', 'genotype', default=''))
            ))
            self.dishes_table.setItem(i, 3, QTableWidgetItem(
                str(self.safe_get_nested(dish_data, 'metadata', 'responsible', default=''))
            ))
            self.dishes_table.setItem(i, 4, QTableWidgetItem(
                str(self.safe_get_nested(dish_data, 'status', default=''))
            ))
            self.dishes_table.setItem(i, 5, QTableWidgetItem(
                str(self.safe_get_nested(dish_data, 'metadata', 'enclosure', 'room', default=''))
            ))

def main():
    app = QApplication(sys.argv)
    window = LabInventoryGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
