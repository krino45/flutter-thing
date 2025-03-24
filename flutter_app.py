import os
import sys
import json
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PyQt5.QtWidgets import (QApplication, QMainWindow, QScrollArea, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QFileDialog, QLabel, QMenu, QMenuBar,
                             QStatusBar, QMessageBox, QSizePolicy, QSplitter, QAction)
from PyQt5.QtCore import QDir, Qt, QFileSystemWatcher, QTimer
from PyQt5 import QtCore, QtGui, QtWidgets

# Import the analysis module
import flutter_analyzer as analyzer


CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".flutter_analyzer_config.json")


class FlutterCanvas(FigureCanvas):
    """Matplotlib canvas for flutter analysis plots"""
    def __init__(self, parent=None, width=10, height=12, dpi=100):
        # Create the figure first
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.subplots(nrows=2, ncols=1, gridspec_kw={'height_ratios': [1, 1]})
        
        # Initialize the canvas with the figure
        FigureCanvas.__init__(self, self.fig)
        self.setParent(parent)
        
        # Set the canvas to expand with the layout
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.updateGeometry()
        
    def plot_vg(self, flow, freqs, deltas, modes=[], name="V-g диаграмма"):
        """Plot V-g diagram on the canvas"""
        self.fig.clf()
        # Create subplots with equal height
        self.axes = self.fig.subplots(nrows=2, ncols=1, gridspec_kw={'height_ratios': [1, 1]})
        num_modes = freqs.shape[1]
        
        if not modes:
            modes = range(0, num_modes)

        # Plot damping with increased figure size
        for j in modes:
            self.axes[0].plot(flow, deltas[:, j], label=f"{j+1}", marker=".")
        self.axes[0].set_title(name, fontsize=12)
        self.axes[0].set_ylabel("Лог. декремент", fontsize=10)
        self.axes[0].grid(True)
        self.axes[0].tick_params(labelsize=9)

        # Plot frequencies
        for j in modes:
            self.axes[1].plot(flow, freqs[:, j], label=f"{j+1}", marker=".")
        self.axes[1].set_xlabel("Скорость потока, м/c", fontsize=10)
        self.axes[1].set_ylabel("Частота, Гц", fontsize=10)
        self.axes[1].grid(True)
        self.axes[1].tick_params(labelsize=9)

        # Add legend with appropriate size and position
        lines, labels = self.axes[0].get_legend_handles_labels()
        self.fig.legend(lines, labels, loc="upper right", fontsize=9)
        
        # Better spacing for the plots
        self.fig.tight_layout(rect=[0, 0, 0.85, 1], pad=2.0)
        self.draw()


class ResultsLabel(QLabel):
    """Custom label for results with a minimum height"""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setMinimumHeight(100)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setStyleSheet("""
            background-color: white;
            border: 1px solid #dddddd;
            border-radius: 4px;
            padding: 8px;
            font-family: Consolas, monospace;
            font-size: 10pt;
            color: #333333;
        """)

class ScrollableResults(QWidget):
    """Widget that contains a scrollable ResultsLabel"""
    def __init__(self, text="", parent=None):
        super().__init__(parent)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.results_label = ResultsLabel(text)
        self.results_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.results_label.setWordWrap(True)
        
        self.scroll_area.setWidget(self.results_label)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        layout.addWidget(self.scroll_area)
        self.setLayout(layout)

    def setText(self, text): 
        """Set the text of the ResultsLabel"""
        self.results_label.setText(text)
        # Force update of the labels size hint
        self.results_label.adjustSize()


class FileTab(QWidget):
    """Tab for a single analysis file"""
    def __init__(self, parent, file_path, dir_path):
        super().__init__(parent)
        self.file_path = file_path
        self.dir_path = dir_path
        self.file_name = os.path.basename(file_path)
        self.result_cache = None
        self.modes = []
        
        # Set up the layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(8, 8, 8, 8)
        control_layout.setSpacing(10)

        self.mode_label = QLabel("Показаны все моды")
        self.mode_label.setStyleSheet("font-weight: bold; color: #555555;")
        control_layout.addWidget(self.mode_label)

        control_layout.addStretch(1)  # Push buttons to the right

        self.recalculate_btn = QPushButton("Пересчитать")
        self.recalculate_btn.setIcon(self.parent().style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
        self.recalculate_btn.clicked.connect(self.analyze_file)
        control_layout.addWidget(self.recalculate_btn)
        
        main_layout.addLayout(control_layout)
        
        # Create a splitter to divide the space between plots and results
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        
        # Plot area widget (top part of splitter)
        plot_widget = QWidget()
        plot_layout = QVBoxLayout(plot_widget)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        
        # Add navigation toolbar and canvas to plot widget
        self.canvas = FlutterCanvas(parent=plot_widget)
        self.toolbar = NavigationToolbar(self.canvas, plot_widget)
        
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas)
        
        # Results area widget (bottom part of splitter)
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        results_layout.setContentsMargins(4, 4, 4, 4)
        
        # Use custom label class with minimum height
        self.results_label = ScrollableResults("Flutter Roots:")
        results_layout.addWidget(self.results_label)
        
        # Add widgets to splitter
        splitter.addWidget(plot_widget)
        splitter.addWidget(results_widget)
        
        # Set initial sizes - give most space to the plot
        splitter.setSizes([700, 150])
        
        # Add splitter to main layout
        main_layout.addWidget(splitter)
        
        # Analyze the file
        self.analyze_file()
        
    def analyze_file(self):
        """Run flutter analysis on the file"""
        try:
            velocities, frequencies, dampings, roots = analyzer.get_flutter(self.file_name, self.dir_path)
            self.result_cache = (velocities, frequencies, dampings, roots)
            
            # Update the plot
            self.canvas.plot_vg(velocities, frequencies, dampings, self.modes, self.file_name)
            
            # Update the results text
            results_text = "Flutter Roots:\n"
            for mode, values in roots.items():
                if len(values) > 0:
                    values_str = ", ".join([f"{x:.3f}" for x in values])
                    results_text += f"Mode {mode+1}: {values_str}\n"
            
            self.results_label.setText(results_text)
            
        except Exception as e:
            QMessageBox.critical(self, "Analysis Error", f"Error analyzing file: {str(e)}")
            
    def set_modes(self, modes):
        """Set which modes to display"""
        self.modes = modes
        if self.result_cache:
            velocities, frequencies, dampings, _ = self.result_cache
            self.canvas.plot_vg(velocities, frequencies, dampings, self.modes, self.file_name)
            if modes:
                self.mode_label.setText(f"Показаны моды: {', '.join(str(m+1) for m in modes)}")
            else:
                self.mode_label.setText("Показаны все моды")


class FlutterAnalyzer(QMainWindow):
    """Main application window"""
    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
        QMainWindow {
            background-color: #f5f5f5;
        }
        QTabWidget {
            background-color: #f5f5f5;
            border: none;
        }
        QTabWidget::pane {
            border: 1px solid #cccccc;
            border-radius: 4px;
            background-color: white;
        }
        QPushButton {
            background-color: #4a86e8;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #3a76d8;
        }
        QPushButton:pressed {
            background-color: #2a66c8;
        }
        QSplitter::handle {
            background-color: #dddddd;
        }
        QLabel {
            color: #333333;
            font-size: 9pt;
        }
        QStatusBar {
            background-color: #f0f0f0;
            color: #555555;
        }
        QMenuBar {
            background-color: #f5f5f5;
            border-bottom: 1px solid #dddddd;
        }
        QMenuBar::item {
            padding: 6px 12px;
            background: transparent;
        }
        QMenuBar::item:selected {
            background-color: #4a86e8;
            color: white;
        }
        QMenu {
            background-color: white;
            border: 1px solid #cccccc;
        }
        QMenu::item {
            padding: 6px 20px 6px 20px;
        }
        QMenu::item:selected {
            background-color: #4a86e8;
            color: white;
        }
        """)
        self.current_dir = ""
        self.file_tabs = {}  # Dictionary to track open tabs
        self.watcher = QFileSystemWatcher()
        self.watcher.directoryChanged.connect(self.handle_directory_changed)
        
        self.init_ui()
        self.load_config()
    
    def keyPressEvent(self, event):
        """Handle ESC key to close current tab"""
        if event.key() == QtCore.Qt.Key_Escape:
            current_index = self.tab_widget.currentIndex()
            if current_index >= 0:
                self.close_tab(current_index)
        super().keyPressEvent(event)

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Flutter Analysis Tool")
        self.setGeometry(100, 100, 1200, 900)  # Larger default window size
        
        # Create central widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)
        
        # Create tab widget
        self.tab_widget = TabWidget()
        #self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        
        # Add directory selection if no directory is set
        self.dir_label = QLabel("Папка не выбрана")
        self.dir_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: white; border: 1px solid #dddddd; border-radius: 4px;")
        self.select_dir_btn = QPushButton("Выбрать папку")
        self.select_dir_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon))
        self.select_dir_btn.clicked.connect(self.select_directory)

        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Папка:"))
        dir_layout.addWidget(self.dir_label, 1)  # Give it a stretch factor
        dir_layout.addWidget(self.select_dir_btn)
        
        main_layout.addLayout(dir_layout)
        main_layout.addWidget(self.tab_widget)
        
        # Make tab widget take most of the space
        main_layout.setStretchFactor(self.tab_widget, 10)
        
        self.central_widget.setLayout(main_layout)
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Готов")
        
    def create_menu_bar(self):
        """Create the application menu bar"""
        menu_bar = QMenuBar()
        
        # File menu
        file_menu = QMenu("&Файл", self)
        menu_bar.addMenu(file_menu)
        
        select_dir_action = file_menu.addAction(self.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon), "Выбрать папку с файлами")
        select_dir_action.triggered.connect(self.select_directory)

        open_all_tabs = file_menu.addAction(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogContentsView), "Открыть все вкладки")
        open_all_tabs.triggered.connect(self.open_all_tabs)
        
        refresh_tabs_action = file_menu.addAction(self.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload), "Обновить открытые вкладки")
        refresh_tabs_action.triggered.connect(self.refresh_all_tabs)
        
        file_menu.addSeparator()
        
        exit_action = file_menu.addAction(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCloseButton), "Выход")
        exit_action.triggered.connect(self.close)
        
        # View menu
        view_menu = QMenu("&Вид", self)
        menu_bar.addMenu(view_menu)
        
        # Add options to show/hide specific modes
        mode_menu = QMenu("Показать моды", self)
        view_menu.addMenu(mode_menu)
        
        all_modes_action = mode_menu.addAction("Все моды")
        all_modes_action.triggered.connect(lambda: self.set_modes_for_current_tab([]))
        
        # Add actions for selecting first 10 modes
        mode_menu.addSeparator()
        for i in range(10):
            action = QAction(f"Мода {i+1}", mode_menu, checkable=True)
            view_menu.addAction(action)
            action.triggered.connect(lambda checked, m=i: self.set_all_modes(m, checked))
        
        self.setMenuBar(menu_bar)

    
    checked_modes = [False] * 10

    def set_all_modes(self, mode, checked):
        self.checked_modes[mode] = checked
        curr_modes = []
        for i in range(10):
            if self.checked_modes[i]:
                curr_modes.append(i)
        self.set_modes_for_current_tab(curr_modes) 

        
    def set_modes_for_current_tab(self, modes):
        """Set modes for the current tab"""
        current_tab = self.tab_widget.currentWidget()
        if current_tab and hasattr(current_tab, 'set_modes'):
            current_tab.set_modes(modes)
        
    def select_directory(self):
        """Open a dialog to select the input directory"""
        dir_path = QFileDialog.getExistingDirectory(self, "Выберите папку", 
                                                   self.current_dir or QDir.homePath())
        
        if dir_path:
            # Clear existing tabs and set up new directory
            self.clear_tabs()
            
            self.current_dir = dir_path
            self.dir_label.setText(f"{dir_path}")
            
            # Save directory to config
            self.save_config()
            
            # Set up file watcher
            if self.watcher.directories():
                self.watcher.removePaths(self.watcher.directories())
            self.watcher.addPath(dir_path)
            
            # Load files from directory
            self.load_files_from_directory()
            
    def load_files_from_directory(self):
        """Load all F06 files from the current directory"""
        if not self.current_dir:
            return
            
        try:
            # Find all F06 files
            files = [f for f in os.listdir(self.current_dir) if f.lower().endswith('.f06')]
            
            if not files:
                self.statusBar.showMessage("Не найдено файлов с расширением f06")
                return
                
            # Add a tab for each file
            for file_name in files:
                self.add_file_tab(file_name)
                
            self.statusBar.showMessage(f"Загружено файлов: {len(files)}")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не получилось загрузить файл: {str(e)}")
            
    def add_file_tab(self, file_name):
        """Add a new tab for the specified file"""
        if file_name in self.file_tabs:
            # File already open, just switch to its tab
            tab_index = self.tab_widget.indexOf(self.file_tabs[file_name])
            self.tab_widget.setCurrentIndex(tab_index)
            return
            
        file_path = os.path.join(self.current_dir, file_name)
        
        # Only add if it's an F06 file
        if not file_name.lower().endswith('.f06'):
            return
            
        try:
            # Create new tab
            tab = FileTab(self, file_path, self.current_dir)
            tab_index = self.tab_widget.addTab(tab, file_name)
            self.file_tabs[file_name] = tab
            
            # Switch to the new tab
            self.tab_widget.setCurrentIndex(tab_index)
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не получилось загрузить файл {file_name}: {str(e)}")
            
    def close_tab(self, index):
        """Close the tab at the specified index"""
        widget = self.tab_widget.widget(index)
        
        # Find and remove from our file_tabs dictionary
        for file_name, tab in list(self.file_tabs.items()):
            if tab == widget:
                del self.file_tabs[file_name]
                break
                
        # Remove the tab
        self.tab_widget.removeTab(index)
        
    def clear_tabs(self):
        """Clear all open tabs"""
        self.tab_widget.clear()
        self.file_tabs = {}
        
    def handle_directory_changed(self, path):
        """Handle changes in the watched directory"""
        # Use a timer to debounce multiple rapid changes
        QTimer.singleShot(500, self.refresh_directory)
        
    def refresh_directory(self):
        """Refresh the file list after directory changes"""
        if not self.current_dir:
            return
            
        try:
            current_files = set(f for f in os.listdir(self.current_dir) 
                               if f.lower().endswith('.f06'))
            open_files = set(self.file_tabs.keys())
            
            # Add tabs for new files
            for file_name in current_files - open_files:
                self.add_file_tab(file_name)
                
            # Update status
            self.statusBar.showMessage("Папка открыта")
            
        except Exception as e:
            self.statusBar.showMessage(f"Ошибка обновления папки: {str(e)}")
            
    def refresh_all_tabs(self):
        """Refresh all open tabs"""
        for tab in self.file_tabs.values():
            tab.analyze_file()
            
        self.statusBar.showMessage("Все вкладки обновлены")

    def open_all_tabs(self):
        """Open all closed tabs"""
        self.refresh_directory()
        for tab in self.file_tabs.values():
            tab.analyze_file()
            
        self.statusBar.showMessage("Все вкладки вновь открыты.")
        
    def load_config(self):
        """Load saved configuration"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    
                if 'directory' in config and os.path.isdir(config['directory']):
                    self.current_dir = config['directory']
                    self.dir_label.setText(f"Directory: {self.current_dir}")
                    
                    # Set up watcher
                    self.watcher.addPath(self.current_dir)
                    
                    # Load files
                    self.load_files_from_directory()
        except Exception as e:
            print(f"Ошибка загрузки когфигурции: {str(e)}")
            
    def save_config(self):
        """Save configuration"""
        try:
            config = {
                'directory': self.current_dir
            }
            
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f)
                
        except Exception as e:
            print(f"Ошибка сохранения конфигурации: {str(e)}")
            
    def closeEvent(self, event):
        """Handle window close event"""
        self.save_config()
        event.accept()

class TabBar(QtWidgets.QTabBar):
    def __init__(self, parent=None):
        super(TabBar, self).__init__(parent)
        self.setFont(QtGui.QFont("Arial", 12))
        
        self.setStyleSheet("""
            QTabBar::tab {
                background: #f0f0f0;
                color: #333333;
                border: 1px solid #cccccc;
                border-bottom: none;
                min-width: 80px;
                max-height: 480px;
            }
            QTabBar::tab:selected {
                background: #4a86e8;
                color: white;
            }
        """)

    def tabSizeHint(self, index):
        fm = QtGui.QFontMetrics(self.font())
        text = self.tabText(index)
        text_width = fm.width(text) + 40 
        text_height = fm.height() + 20

        s = QtWidgets.QTabBar.tabSizeHint(self, index)
        s.transpose()
        return QtCore.QSize(
            min(max(s.width(), text_width), 500),
            min(max(s.height(), text_height), 500)   
        )

    def paintEvent(self, event):
        painter = QtWidgets.QStylePainter(self)
        opt = QtWidgets.QStyleOptionTab()

        for i in range(self.count()):
            self.initStyleOption(opt, i)
            painter.drawControl(QtWidgets.QStyle.CE_TabBarTabShape, opt)
            painter.save()

            # Rotate the text for vertical tabs
            s = opt.rect.size()
            s.transpose()
            r = QtCore.QRect(QtCore.QPoint(), s)
            r.moveCenter(opt.rect.center())
            opt.rect = r

            c = self.tabRect(i).center()
            painter.translate(c)
            painter.rotate(90)
            painter.translate(-c)
            
            # Draw the text
            painter.drawControl(QtWidgets.QStyle.CE_TabBarTabLabel, opt)
            painter.restore()


class TabWidget(QtWidgets.QTabWidget):
    def __init__(self, *args, **kwargs):
        QtWidgets.QTabWidget.__init__(self, *args, **kwargs)
        self.setTabBar(TabBar())
        self.setTabPosition(QtWidgets.QTabWidget.West)

class ProxyStyle(QtWidgets.QProxyStyle):
    def drawControl(self, element, opt, painter, widget):
        if element == QtWidgets.QStyle.CE_TabBarTabLabel:
            ic = self.pixelMetric(QtWidgets.QStyle.PM_TabBarIconSize)
            r = QtCore.QRect(opt.rect)
            w = opt.rect.width() if opt.icon.isNull() else opt.rect.width() + ic
            r.setHeight(opt.fontMetrics.width(opt.text) + w)
            r.moveBottom(opt.rect.bottom())
            opt.rect = r
        QtWidgets.QProxyStyle.drawControl(self, element, opt, painter, widget)

def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    window = FlutterAnalyzer()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()