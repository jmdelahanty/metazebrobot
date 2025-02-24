import sys
import random
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QLabel, QGridLayout)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QPixmap, QIcon, QColor, QPainter

class BugSquashGame(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lab Bug Squash")
        self.setFixedSize(600, 500)
        
        # Game state
        self.score = 0
        self.time_left = 30  # 30 seconds game
        self.game_active = False
        self.bugs = {}  # To track active bugs {button_id: bug_type}
        self.bug_timer = QTimer()
        self.bug_timer.timeout.connect(self.spawn_bug)
        self.game_timer = QTimer()
        self.game_timer.timeout.connect(self.update_timer)
        
        # Bug types and their point values
        self.bug_types = {
            'bacteria': 10,   # Common, worth fewer points
            'fungus': 20,     # Less common, worth more
            'virus': 30       # Rare, worth the most
        }
        
        # Penalties for missing (clicking empty)
        self.penalty = -5
        
        # Setup UI
        self.init_ui()
        
    def init_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # Info panel
        info_panel = QHBoxLayout()
        
        # Score display
        self.score_label = QLabel("Score: 0")
        self.score_label.setFont(QFont("Arial", 16, QFont.Bold))
        info_panel.addWidget(self.score_label)
        
        # Timer display
        self.timer_label = QLabel("Time: 30s")
        self.timer_label.setFont(QFont("Arial", 16, QFont.Bold))
        info_panel.addWidget(self.timer_label)
        
        main_layout.addLayout(info_panel)
        
        # Game grid - where the bugs will appear
        game_widget = QWidget()
        game_widget.setStyleSheet("background-color: #f0f8ff;")  # Light blue like a clean lab surface
        game_layout = QGridLayout(game_widget)
        game_layout.setSpacing(5)
        
        # Create a 5x5 grid of buttons where bugs can appear
        self.buttons = []
        for row in range(5):
            for col in range(5):
                button = QPushButton()
                button.setFixedSize(100, 70)
                button.setIcon(QIcon())  # Empty icon initially
                button.setIconSize(QSize(60, 60))
                button.setStyleSheet("background-color: transparent; border: none;")
                button.clicked.connect(lambda checked, r=row, c=col: self.squash_bug(r, c))
                button.setEnabled(False)  # Disabled until game starts
                game_layout.addWidget(button, row, col)
                self.buttons.append((row, col, button))
        
        main_layout.addWidget(game_widget)
        
        # Control panel
        control_panel = QHBoxLayout()
        
        # Start button
        self.start_button = QPushButton("Start Game")
        self.start_button.setFont(QFont("Arial", 14))
        self.start_button.clicked.connect(self.start_game)
        control_panel.addWidget(self.start_button)
        
        main_layout.addLayout(control_panel)
        
        # Add game instructions
        instructions = QLabel("Click the contaminations when they appear! Bacteria: 10pts, Fungus: 20pts, Virus: 30pts. Missing costs 5pts.")
        instructions.setWordWrap(True)
        instructions.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(instructions)
    
    def start_game(self):
        # Reset game state
        self.score = 0
        self.time_left = 30
        self.bugs = {}
        self.game_active = True
        
        # Update UI
        self.score_label.setText("Score: 0")
        self.timer_label.setText("Time: 30s")
        self.start_button.setEnabled(False)
        self.start_button.setText("Game In Progress")
        
        # Enable all buttons
        for row, col, button in self.buttons:
            button.setEnabled(True)
            button.setIcon(QIcon())  # Clear any icons
        
        # Start timers
        self.bug_timer.start(1200)  # New bug every 1.2 seconds
        self.game_timer.start(1000)  # Update timer every second
    
    def update_timer(self):
        self.time_left -= 1
        self.timer_label.setText(f"Time: {self.time_left}s")
        
        if self.time_left <= 0:
            self.end_game()
    
    def end_game(self):
        # Stop the game
        self.game_active = False
        self.bug_timer.stop()
        self.game_timer.stop()
        
        # Disable all buttons
        for row, col, button in self.buttons:
            button.setEnabled(False)
            button.setIcon(QIcon())  # Clear any icons
        
        # Reset start button
        self.start_button.setEnabled(True)
        self.start_button.setText(f"Game Over! Score: {self.score} - Play Again?")
    
    def spawn_bug(self):
        if not self.game_active:
            return
        
        # Randomly choose a location
        available_buttons = [(r, c, b) for r, c, b in self.buttons if (r, c) not in self.bugs]
        if not available_buttons:
            return  # No space available
        
        row, col, button = random.choice(available_buttons)
        
        # Choose bug type based on rarity
        bug_roll = random.random()
        if bug_roll < 0.6:  # 60% chance for bacteria
            bug_type = 'bacteria'
            button.setStyleSheet("background-color: #d3f0ea; border-radius: 10px;")
        elif bug_roll < 0.9:  # 30% chance for fungus
            bug_type = 'fungus'
            button.setStyleSheet("background-color: #f5e5b7; border-radius: 10px;")
        else:  # 10% chance for virus
            bug_type = 'virus'
            button.setStyleSheet("background-color: #f7c1c1; border-radius: 10px;")
        
        # Store the bug
        self.bugs[(row, col)] = bug_type
        
        # Set a timer to make the bug disappear if not clicked
        QTimer.singleShot(2000, lambda r=row, c=col: self.remove_bug(r, c))
    
    def remove_bug(self, row, col):
        if (row, col) in self.bugs:
            del self.bugs[(row, col)]
            
            # Find the button for this position
            for r, c, button in self.buttons:
                if r == row and c == col:
                    button.setStyleSheet("background-color: transparent; border: none;")
                    break
    
    def squash_bug(self, row, col):
        if not self.game_active:
            return
            
        # Check if there's a bug at this position
        if (row, col) in self.bugs:
            bug_type = self.bugs[(row, col)]
            points = self.bug_types[bug_type]
            self.score += points
            
            # Remove the bug
            self.remove_bug(row, col)
            
            # Provide visual feedback for the squash
            for r, c, button in self.buttons:
                if r == row and c == col:
                    button.setStyleSheet("background-color: #e1ffd6; border: none;")  # Green flash for success
                    QTimer.singleShot(200, lambda b=button: b.setStyleSheet("background-color: transparent; border: none;"))
                    break
        else:
            # Penalty for missing
            self.score += self.penalty
            
            # Visual feedback for miss
            for r, c, button in self.buttons:
                if r == row and c == col:
                    button.setStyleSheet("background-color: #ffe1e1; border: none;")  # Red flash for miss
                    QTimer.singleShot(200, lambda b=button: b.setStyleSheet("background-color: transparent; border: none;"))
                    break
        
        # Update score display
        self.score_label.setText(f"Score: {self.score}")

def launch_game():
    app = QApplication(sys.argv)
    game = BugSquashGame()
    game.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    launch_game()