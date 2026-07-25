import sys

from PySide6.QtWidgets import QApplication

from db.connection import initialize_database
from app.main_window import MainWindow

if __name__ == "__main__":
    initialize_database()

    app = QApplication(sys.argv)

    window = MainWindow()
    window.showMaximized()

    sys.exit(app.exec())
