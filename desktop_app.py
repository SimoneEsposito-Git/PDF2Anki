import os
import sys
import threading
import zipfile
from pathlib import Path
import tempfile
from datetime import datetime
import subprocess  # For detecting Mac system theme
import shutil  # Explicitly import shutil for file operations

from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout,
                           QPushButton, QFileDialog, QSlider, QCheckBox, QProgressBar,
                           QWidget, QScrollArea, QSpinBox, QGroupBox, QMessageBox,
                           QSizePolicy, QFrame, QStyleFactory, QToolButton, QComboBox,
                           QInputDialog, QLineEdit, QDialog)  # Added QInputDialog, QLineEdit, QDialog
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QSize
from PyQt5.QtGui import QFont, QIcon, QDragEnterEvent, QDropEvent

# Import the functions from anki.py
from anki import read_pdf, split_content, process_chunk, create_anki_deck, save_to_csv, generate_qa_pairs
import concurrent.futures
import genanki

# Define stylesheets for light and dark modes

def get_mac_system_theme():
    """Detect if macOS is using dark mode"""
    try:
        cmd = "defaults read -g AppleInterfaceStyle"
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
        return result.stdout.strip() == "Dark"
    except:
        # Default to light mode if detection fails
        return False

class WorkerSignals(QThread):
    '''
    Define signals available from a running worker thread.
    '''
    progress = pyqtSignal(float)
    status = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

class FlashcardGeneratorThread(QThread):
    '''
    Worker thread for generating flashcards without blocking the UI
    '''
    def __init__(self, pdf_files, chunk_size, overlap, max_workers, include_csv, language, individual_decks):
        super().__init__()
        self.pdf_files = pdf_files
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.max_workers = max_workers
        self.include_csv = include_csv
        self.language = language
        self.individual_decks = individual_decks  # Add individual_decks parameter
        self.signals = WorkerSignals()

    def run(self):
        try:
            # Create a temporary directory that will be persistent until we're done with it
            temp_dir = tempfile.mkdtemp()
            
            try:
                all_files = []
                all_qa_pairs = []  # Store all Q&A pairs for combined deck
                individual_deck_files = []  # Track individual deck files for potential bundling
                
                # Process each uploaded file
                for i, pdf_file in enumerate(self.pdf_files):
                    file_progress = (i / len(self.pdf_files)) * 0.9  # Reserve 10% for final packaging
                    
                    # Update status
                    self.signals.status.emit(f"Processing file {i+1}/{len(self.pdf_files)}: {os.path.basename(pdf_file)}")
                    self.signals.progress.emit(file_progress)
                    
                    # Process the PDF
                    self.signals.status.emit(f"Reading PDF: {os.path.basename(pdf_file)}")
                    pages = read_pdf(pdf_file)
                    
                    self.signals.status.emit(f"Splitting content into chunks...")
                    chunks = split_content(pages, chunk_size=self.chunk_size, overlap=self.overlap)
                    
                    file_qa_pairs = []
                    
                    # Process chunks in parallel
                    self.signals.status.emit(f"Processing chunks in parallel...")
                    with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                        chunk_data = [(chunk, i, len(chunks), self.language) for i, chunk in enumerate(chunks)]
                        
                        # Execute processing and update progress
                        completed = 0
                        futures = {executor.submit(process_chunk, chunk_info): chunk_info for chunk_info in chunk_data}
                        
                        for future in concurrent.futures.as_completed(futures):
                            try:
                                chunk_info = futures[future]
                                qa_pairs = future.result()
                                file_qa_pairs.extend(qa_pairs)
                                
                                completed += 1
                                chunk_progress = file_progress + (completed / len(chunks)) * (1/len(self.pdf_files)) * 0.8
                                self.signals.progress.emit(chunk_progress)
                                self.signals.status.emit(f"Processed chunk {completed}/{len(chunks)} for {os.path.basename(pdf_file)}")
                            except Exception as e:
                                self.signals.error.emit(f"Error processing chunk: {str(e)}")
                    
                    # If creating individual decks, generate a deck now
                    if self.individual_decks:
                        # Generate file names
                        base_name = Path(pdf_file).stem
                        deck_name = f"{base_name} {self.language} Flashcards"
                        apkg_path = os.path.join(temp_dir, f"{base_name}_flashcards.apkg")
                        
                        # Create the Anki deck
                        self.signals.status.emit(f"Creating Anki deck for {os.path.basename(pdf_file)}...")
                        deck = create_anki_deck(file_qa_pairs, deck_name)
                        
                        # Save the Anki deck
                        genanki.Package(deck).write_to_file(apkg_path)
                        
                        # Save to CSV if selected
                        csv_path = None
                        if self.include_csv:
                            csv_path = os.path.join(temp_dir, f"{base_name}_flashcards.csv")
                            save_to_csv(file_qa_pairs, csv_path)
                        
                        # Add to individual deck files list for potential bundling
                        individual_deck_files.append({
                            'apkg': apkg_path,
                            'csv': csv_path if self.include_csv else None,
                            'base_name': base_name
                        })
                    
                    # Always collect Q&A pairs for potential combined deck
                    all_qa_pairs.extend(file_qa_pairs)
                
                # If creating individual decks and we have multiple files, create a zip bundle
                if self.individual_decks and len(self.pdf_files) > 1:
                    # Create a zip file containing all individual decks
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    zip_filename = f"All_Decks_{timestamp}.zip"
                    zip_path = os.path.join(temp_dir, zip_filename)
                    
                    self.signals.status.emit("Creating zip bundle of all individual decks...")
                    
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        # Add each individual deck file to the zip
                        for deck_info in individual_deck_files:
                            # Add the APKG file
                            apkg_filename = os.path.basename(deck_info['apkg'])
                            zipf.write(deck_info['apkg'], apkg_filename)
                            
                            # Add the CSV file if it exists
                            if deck_info['csv']:
                                csv_filename = os.path.basename(deck_info['csv'])
                                zipf.write(deck_info['csv'], csv_filename)
                    
                    # Add ONLY the zip file to the list of files to return
                    all_files.append({
                        'path': zip_path,
                        'type': 'zip'
                    })
                    
                    # No longer add individual files for separate download option
                else:
                    # If not bundling, just add individual files
                    if self.individual_decks:
                        for deck_info in individual_deck_files:
                            all_files.append({
                                'path': deck_info['apkg'],
                                'type': 'apkg'
                            })
                            
                            if deck_info['csv']:
                                all_files.append({
                                    'path': deck_info['csv'],
                                    'type': 'csv'
                                })
                
                # If not creating individual decks, create a combined deck
                if not self.individual_decks or len(self.pdf_files) == 1:
                    # Create a combined name for all PDFs
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    combined_name = f"Combined_{timestamp}"
                    deck_name = f"Combined {self.language} Flashcards"
                    apkg_path = os.path.join(temp_dir, f"{combined_name}_flashcards.apkg")
                    
                    # Create the Anki deck
                    self.signals.status.emit(f"Creating combined Anki deck...")
                    deck = create_anki_deck(all_qa_pairs, deck_name)
                    
                    # Save the Anki deck
                    genanki.Package(deck).write_to_file(apkg_path)
                    
                    # Save to CSV if selected
                    csv_path = None
                    if self.include_csv:
                        csv_path = os.path.join(temp_dir, f"{combined_name}_flashcards.csv")
                        save_to_csv(all_qa_pairs, csv_path)
                    
                    # Add to the list of generated files
                    all_files.append({
                        'path': apkg_path,
                        'type': 'apkg'
                    })
                    
                    if self.include_csv and csv_path:
                        all_files.append({
                            'path': csv_path,
                            'type': 'csv'
                        })
                
                # Signal completion with the list of generated files
                self.signals.progress.emit(1.0)
                self.signals.status.emit("Generation complete! Saving files...")
                self.signals.finished.emit(all_files)
                
            except Exception as e:
                self.signals.error.emit(f"Error during processing: {str(e)}")
                # Clean up the temp directory on error
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except Exception as e:
            self.signals.error.emit(f"Error: {str(e)}")

class DropFileLabel(QLabel):
    dropped = pyqtSignal(list)
    
    def __init__(self, text):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(100)
        self.setObjectName("DropFileLabel")  # Set object name for styling
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        file_paths = []
        for url in urls:
            path = url.toLocalFile()
            if path.lower().endswith('.pdf'):
                file_paths.append(path)
        
        if file_paths:
            self.dropped.emit(file_paths)

# Add this function to check the OpenAI API key
def is_openai_api_key_valid(api_key):
    """Test if the provided OpenAI API key is valid"""
    if not api_key or api_key.strip() == "" or api_key == "your_api_key_here":
        return False
    
    # Basic format check (not a full validation)
    if not api_key.startswith(('sk-', 'org-')):
        return False
    
    # Optionally, you could do a minimal API call to verify the key works
    # But we'll skip that to avoid unnecessary API usage
    
    return True

class ApiKeyDialog(QDialog):
    """Dialog for entering OpenAI API key"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OpenAI API Key Required")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Explanation
        msg = QLabel(
            "An OpenAI API key is required to generate flashcards. "
            "Please enter your API key below.\n\n"
            "You can create a key at: https://platform.openai.com/api-keys"
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)
        
        # API key input
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("sk-...")
        self.key_input.setEchoMode(QLineEdit.Password)  # Hide the key by default
        layout.addWidget(self.key_input)
        
        # Show/hide password checkbox
        show_key = QCheckBox("Show API key")
        show_key.stateChanged.connect(self.toggle_key_visibility)
        layout.addWidget(show_key)
        
        # Remember checkbox
        self.remember = QCheckBox("Remember API key for future sessions")
        self.remember.setChecked(True)
        layout.addWidget(self.remember)
        
        # Buttons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def toggle_key_visibility(self, state):
        self.key_input.setEchoMode(QLineEdit.Normal if state else QLineEdit.Password)
    
    def get_api_key(self):
        return self.key_input.text().strip()
    
    def should_remember(self):
        return self.remember.isChecked()

class FlashcardGenerator(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.pdf_files = []
        # Detect system theme
        self.is_dark_mode = get_mac_system_theme()
        self.style_dark = ""
        self.style_light = ""
        
        # Check for OpenAI API key before setting up UI
        self.check_api_key()
        
        self.initUI()
    
    def check_api_key(self):
        """Check if OpenAI API key exists and is valid"""
        api_key = os.environ.get("OPENAI_API_KEY", "")
        
        if not is_openai_api_key_valid(api_key):
            dialog = ApiKeyDialog(self)
            result = dialog.exec_()
            
            if result == QDialog.Accepted:
                new_key = dialog.get_api_key()
                if is_openai_api_key_valid(new_key):
                    # Set for current session
                    os.environ["OPENAI_API_KEY"] = new_key
                    
                    # If user wants to remember
                    if dialog.should_remember():
                        self.save_api_key(new_key)
                else:
                    QMessageBox.warning(
                        self, 
                        "Invalid API Key", 
                        "The API key format appears to be invalid. The app may not work correctly."
                    )
            else:
                # User canceled - show warning
                QMessageBox.warning(
                    self, 
                    "API Key Required", 
                    "An OpenAI API key is required to use this application. "
                    "The app may not function correctly without a valid key."
                )
    
    def save_api_key(self, api_key):
        """Save API key for future sessions"""
        try:
            # For macOS - save to .zshrc or .bash_profile
            if sys.platform == "darwin":
                home = os.path.expanduser("~")
                shell_profile = os.path.join(home, ".zshrc" if os.path.exists(os.path.join(home, ".zshrc")) else ".bash_profile")
                
                with open(shell_profile, "a") as f:
                    f.write(f'\n# Added by PDF to Anki Flashcards app\nexport OPENAI_API_KEY="{api_key}"\n')
                
                QMessageBox.information(
                    self,
                    "API Key Saved",
                    f"API key has been added to {shell_profile}.\n"
                    "You may need to restart your terminal or computer for the changes to take effect."
                )
            
            # For Windows
            elif sys.platform == "win32":
                # Use the built-in Windows API to set environment variables
                import subprocess
                subprocess.run(f'setx OPENAI_API_KEY "{api_key}"', shell=True)
                
                QMessageBox.information(
                    self,
                    "API Key Saved",
                    "API key has been saved to Windows environment variables.\n"
                    "You may need to restart your computer for the changes to take effect in other applications."
                )
        
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error Saving API Key",
                f"Could not save API key: {str(e)}\n\n"
                "The key will only be used for the current session."
            )
    
    def initUI(self):
        self.setWindowTitle('PDF to Anki Flashcards')
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        
        with open("style/dark_style.qss", "r") as file:
            self.style_dark = file.read()
        with open("style/light_style.qss", "r") as file:
            self.style_light = file.read()
        
        # Main layout
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Header layout with title and theme switcher
        header_layout = QHBoxLayout()
        
        # Title
        title_label = QLabel('PDF to Anki Flashcards')
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label, 1)  # Stretch factor 1
        
        # Theme switcher button
        self.theme_button = QToolButton()
        self.theme_button.setText("☀️" if self.is_dark_mode else "🌙")
        self.theme_button.setToolTip("Switch to light mode" if self.is_dark_mode else "Switch to dark mode")
        self.theme_button.clicked.connect(self.toggle_theme)
        header_layout.addWidget(self.theme_button, 0)  # No stretch
        
        main_layout.addLayout(header_layout)
        
        # Description
        desc_label = QLabel('Upload PDF files to automatically generate Anki flashcards.\n'
                           'The application will extract text from PDFs and use AI to create question-answer pairs in your chosen language.')
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)
        
        # Horizontal separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(line)
        
        # File drop area
        self.drop_label = DropFileLabel('Drag and drop PDF files here\nor click to select files')
        self.drop_label.dropped.connect(self.add_pdf_files)
        self.drop_label.mousePressEvent = lambda e: self.open_file_dialog()  # Add click event
        main_layout.addWidget(self.drop_label)
        
        # Selected files display
        self.files_label = QLabel('No files selected')
        self.files_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.files_label)
        
        # Configuration group
        config_group = QGroupBox('Configuration')
        config_layout = QVBoxLayout()
        
        # Language selection
        language_layout = QHBoxLayout()
        language_layout.addWidget(QLabel('Target Language:'))
        self.language_combo = QComboBox()
        
        # Add common languages
        languages = [
            "Arabic", "Bengali", "Chinese", "Dutch", "English", "French", "German", "Hindi", 
            "Italian", "Japanese", "Korean", "Portuguese", "Russian", "Spanish", "Swedish", "Turkish"
        ]
        for language in sorted(languages):
            self.language_combo.addItem(language)
            
        # Default to German
        self.language_combo.setCurrentText("German")
        language_layout.addWidget(self.language_combo)
        config_layout.addLayout(language_layout)
        
        # Chunk size as user-friendly slider (1-10)
        chunk_layout = QHBoxLayout()
        chunk_layout.addWidget(QLabel('Content Chunk Size:'))
        self.chunk_size_slider = QSlider(Qt.Horizontal)
        self.chunk_size_slider.setMinimum(1)
        self.chunk_size_slider.setMaximum(10)
        self.chunk_size_slider.setValue(5)  # Default middle value
        self.chunk_size_slider.setTickPosition(QSlider.TicksBelow)
        self.chunk_size_slider.setTickInterval(1)
        chunk_layout.addWidget(self.chunk_size_slider)
        
        # Display text instead of numbers
        self.chunk_size_label = QLabel('Standard')
        self.chunk_size_slider.valueChanged.connect(self.update_chunk_size_label)
        chunk_layout.addWidget(self.chunk_size_label)
        config_layout.addLayout(chunk_layout)
        
        # Add explanation for chunk size
        chunk_explanation = QLabel('Smaller chunks give better quality flashcards but take longer to process.\nLarger chunks process faster but may produce less focused flashcards.')
        chunk_explanation.setWordWrap(True)
        chunk_explanation.setStyleSheet("font-size: 11px; color: #666666;")
        config_layout.addWidget(chunk_explanation)
        
        # Advanced settings in a collapsible group
        self.advanced_group = QGroupBox('Advanced Settings')
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)  # Start collapsed
        advanced_layout = QVBoxLayout()
        
        # Overlap
        overlap_layout = QHBoxLayout()
        overlap_layout.addWidget(QLabel('Overlap:'))
        self.overlap_slider = QSlider(Qt.Horizontal)
        self.overlap_slider.setMinimum(100)
        self.overlap_slider.setMaximum(1000)
        self.overlap_slider.setValue(500)  # Default value
        self.overlap_slider.setTickPosition(QSlider.TicksBelow)
        self.overlap_slider.setTickInterval(100)
        overlap_layout.addWidget(self.overlap_slider)
        
        self.overlap_value = QLabel('500')
        self.overlap_slider.valueChanged.connect(lambda v: self.overlap_value.setText(str(v)))
        overlap_layout.addWidget(self.overlap_value)
        advanced_layout.addLayout(overlap_layout)
        
        # Overlap explanation
        overlap_explanation = QLabel('Controls how much text overlaps between chunks to maintain context.')
        overlap_explanation.setWordWrap(True)
        overlap_explanation.setStyleSheet("font-size: 11px; color: #666666;")
        advanced_layout.addWidget(overlap_explanation)
        
        # Workers
        workers_layout = QHBoxLayout()
        workers_layout.addWidget(QLabel('Parallel Workers:'))
        self.workers_spin = QSpinBox()
        self.workers_spin.setMinimum(1)
        self.workers_spin.setMaximum(10)
        self.workers_spin.setValue(4)  # Default value
        workers_layout.addWidget(self.workers_spin)
        advanced_layout.addLayout(workers_layout)
        
        # Workers explanation
        workers_explanation = QLabel('Number of simultaneous processing tasks. Higher values may be faster but use more system resources.')
        workers_explanation.setWordWrap(True)
        workers_explanation.setStyleSheet("font-size: 11px; color: #666666;")
        advanced_layout.addWidget(workers_explanation)
        
        # CSV checkbox
        self.csv_checkbox = QCheckBox('Include CSV Export')
        self.csv_checkbox.setChecked(False)  # Default to unchecked
        advanced_layout.addWidget(self.csv_checkbox)
        
        # CSV explanation
        csv_explanation = QLabel('Also export flashcards as a CSV file (can be imported into spreadsheet software).')
        csv_explanation.setWordWrap(True)
        csv_explanation.setStyleSheet("font-size: 11px; color: #666666;")
        advanced_layout.addWidget(csv_explanation)
        
        # Add individual decks checkbox
        self.individual_decks_checkbox = QCheckBox('Generate individual decks')
        self.individual_decks_checkbox.setChecked(False)  # Default to unchecked
        self.individual_decks_checkbox.setToolTip('Generate separate deck for each PDF file instead of a single combined deck')
        advanced_layout.addWidget(self.individual_decks_checkbox)
        
        # Individual decks explanation
        individual_decks_explanation = QLabel('When uploading multiple PDFs, creates separate deck for each file instead of combining them.')
        individual_decks_explanation.setWordWrap(True)
        individual_decks_explanation.setStyleSheet("font-size: 11px; color: #666666;")
        advanced_layout.addWidget(individual_decks_explanation)
        
        self.advanced_group.setLayout(advanced_layout)
        config_layout.addWidget(self.advanced_group)
        
        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)
        
        # Generate button
        self.generate_btn = QPushButton('Generate Flashcards')
        self.generate_btn.setMinimumHeight(50)
        self.generate_btn.clicked.connect(self.start_generation)
        self.generate_btn.setEnabled(False)  # Disabled until files are selected
        main_layout.addWidget(self.generate_btn)
        
        # Progress bar and status
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel('')
        self.status_label.setVisible(False)
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)
        
        # Set the central widget
        self.setCentralWidget(main_widget)
        
        # Apply the appropriate theme
        self.apply_theme()
    
    def toggle_theme(self):
        """Toggle between light and dark mode"""
        self.is_dark_mode = not self.is_dark_mode
        self.theme_button.setText("☀️" if self.is_dark_mode else "🌙")
        self.theme_button.setToolTip("Switch to light mode" if self.is_dark_mode else "Switch to dark mode")
        self.apply_theme()
    
    def apply_theme(self):
        """Apply the current theme to the application"""
        stylesheet = self.style_dark if self.is_dark_mode else self.style_light
        self.setStyleSheet(stylesheet)
    
    def open_file_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, 'Select PDF Files', '', 'PDF Files (*.pdf)'
        )
        if files:
            self.add_pdf_files(files)
    
    def add_pdf_files(self, file_paths):
        self.pdf_files = file_paths
        
        # Update label
        if len(self.pdf_files) == 1:
            self.files_label.setText(f'1 file selected: {os.path.basename(self.pdf_files[0])}')
        else:
            self.files_label.setText(f'{len(self.pdf_files)} files selected')
        
        # Enable generate button
        self.generate_btn.setEnabled(True)
    
    def update_chunk_size_label(self, value):
        """Convert slider value (1-10) to human-readable description"""
        labels = {
            1: "Very Small",
            2: "Small",
            3: "Medium-Small",
            4: "Medium",
            5: "Standard",
            6: "Medium-Large",
            7: "Large",
            8: "Very Large",
            9: "Extra Large",
            10: "Maximum"
        }
        self.chunk_size_label.setText(labels[value])
    
    def start_generation(self):
        if not self.pdf_files:
            QMessageBox.warning(self, 'No Files', 'Please select at least one PDF file.')
            return
        
        # Disable UI components during processing
        self.generate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setVisible(True)
        self.status_label.setText('Starting flashcard generation...')
        
        # Get configuration
        # Convert user-friendly chunk size (1-10) to actual chunk size
        user_chunk_size = self.chunk_size_slider.value()
        # Map the 1-10 values to actual chunk sizes (roughly exponential)
        chunk_size_map = {
            1: 1000,   # Very small chunks
            2: 1500,
            3: 2000,
            4: 2250,
            5: 2500,   # Default/medium
            6: 3000,
            7: 3500,
            8: 4000,
            9: 4500,
            10: 5000   # Very large chunks
        }
        chunk_size = chunk_size_map[user_chunk_size]
        
        overlap = self.overlap_slider.value()
        max_workers = self.workers_spin.value()
        include_csv = self.csv_checkbox.isChecked()
        language = self.language_combo.currentText()
        individual_decks = self.individual_decks_checkbox.isChecked()  # Get individual decks setting
        
        # Start the worker thread
        self.worker_thread = FlashcardGeneratorThread(
            self.pdf_files, chunk_size, overlap, max_workers, include_csv, language, individual_decks
        )
        self.worker_thread.signals.progress.connect(self.update_progress)
        self.worker_thread.signals.status.connect(self.update_status)
        self.worker_thread.signals.finished.connect(self.generation_finished)
        self.worker_thread.signals.error.connect(self.show_error)
        self.worker_thread.start()
    
    def update_progress(self, value):
        self.progress_bar.setValue(int(value * 100))
    
    def update_status(self, status):
        self.status_label.setText(status)
    
    def show_error(self, error_msg):
        QMessageBox.critical(self, 'Error', error_msg)
        self.generate_btn.setEnabled(True)
    
    def generation_finished(self, files):
        success = False
        try:
            # Show save dialog for each file in the results
            for file_info in files:
                path = file_info['path']
                file_type = file_info['type']
                
                # Verify the file exists before attempting to save
                if not os.path.exists(path):
                    self.show_error(f"Generated file does not exist: {path}")
                    continue
                
                if file_type == 'apkg':
                    file_filter = 'Anki Package (*.apkg)'
                    default_name = os.path.basename(path)
                elif file_type == 'csv':
                    file_filter = 'CSV File (*.csv)'
                    default_name = os.path.basename(path)
                else:  # zip
                    file_filter = 'ZIP Archive (*.zip)'
                    default_name = os.path.basename(path)
                
                save_path, _ = QFileDialog.getSaveFileName(
                    self, 'Save Generated File', default_name, file_filter
                )
                
                if save_path:
                    try:
                        # Print debugging info
                        print(f"Copying from {path} to {save_path}")
                        print(f"Source exists: {os.path.exists(path)}")
                        
                        # Use copyfile for more reliable copying
                        shutil.copyfile(path, save_path)
                        success = True
                    except Exception as e:
                        self.show_error(f"Failed to save file: {str(e)}")
            
            # Re-enable UI
            self.generate_btn.setEnabled(True)
            self.status_label.setText('Flashcards generated successfully!')
            
            # Show success message only if at least one file was saved
            if success:
                QMessageBox.information(self, 'Success', 'Flashcards generated and saved successfully!')
        
        except Exception as e:
            self.show_error(f"Error saving files: {str(e)}")
            self.generate_btn.setEnabled(True)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create('Fusion'))  # Use Fusion style for a modern look
    
    window = FlashcardGenerator()
    window.show()
    sys.exit(app.exec_())