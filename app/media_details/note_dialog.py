from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .constants import (
    DETAIL_BUTTON_WIDTH,
    DETAILS_BACKGROUND_COLOR,
)
from app.media_notes import (
    EMPTY_NOTE_ERROR,
    normalize_note_text,
    validate_note_text,
)
from app.media_state_controls import ClickableEntryLabel


NOTE_DETAILS_INPUT_WIDTH = 500
NOTE_DETAILS_INPUT_HEIGHT = 100


class NotePreviewLabel(ClickableEntryLabel):
    def __init__(self, text, parent=None, callback=None):
        self.full_text = text or ""
        self.preview_text = " ".join(self.full_text.split())
        super().__init__("", parent, callback)

        self.setToolTip(self.full_text)
        self._refresh_elided_text()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_elided_text()

    def _refresh_elided_text(self):
        available_width = max(0, self.contentsRect().width())
        self.setText(
            self.fontMetrics().elidedText(
                self.preview_text,
                Qt.TextElideMode.ElideRight,
                available_width,
            )
        )


class NoteDetailsDialog(QDialog):
    def __init__(self, parent, note=None):
        super().__init__(parent)

        self.note = deepcopy(note) if note is not None else None
        self.result_payload = {"action": "cancel"}
        self.initial_note_text = normalize_note_text(
            (self.note or {}).get("note")
        )
        self._has_user_edited = False

        self.setWindowTitle("Note Details")
        self._apply_parent_styles(parent)
        self._build_ui()
        self._populate_initial_value()
        self.resize(self.sizeHint())
        self._refresh_state()

    def _apply_parent_styles(self, parent):
        parent_style = parent.styleSheet() if parent is not None else ""
        self.setStyleSheet(parent_style + f"""
            QLabel#errorLabel {{
                color: #b00020;
            }}

            QFrame#dialogButtonBar {{
                background-color: {DETAILS_BACKGROUND_COLOR};
                border: none;
            }}
        """)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(8)

        self.note_input = QPlainTextEdit(self)
        self.note_input.setFixedSize(
            NOTE_DETAILS_INPUT_WIDTH,
            NOTE_DETAILS_INPUT_HEIGHT,
        )
        self.note_input.textChanged.connect(self._on_text_changed)
        main_layout.addWidget(self.note_input)

        self.error_label = QLabel(self)
        self.error_label.setObjectName("errorLabel")
        self.error_label.setWordWrap(True)
        main_layout.addWidget(self.error_label)

        main_layout.addWidget(self._build_button_bar())

    def _build_button_bar(self):
        bar = QFrame(self)
        bar.setObjectName("dialogButtonBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)
        layout.addStretch()

        self.delete_note_button = QPushButton("DELETE", bar)
        self.delete_note_button.setObjectName("deleteButton")
        self.cancel_note_button = QPushButton("Cancel", bar)
        self.save_note_button = QPushButton("Save", bar)

        for button in (
            self.delete_note_button,
            self.cancel_note_button,
            self.save_note_button,
        ):
            button.setMinimumHeight(32)
            button.setFixedWidth(DETAIL_BUTTON_WIDTH)
            layout.addWidget(button)

        layout.addStretch()

        self.delete_note_button.clicked.connect(self._delete_note)
        self.cancel_note_button.clicked.connect(self.reject)
        self.save_note_button.clicked.connect(self._save_note)
        return bar

    def _populate_initial_value(self):
        self.note_input.blockSignals(True)
        self.note_input.setPlainText((self.note or {}).get("note") or "")
        self.note_input.blockSignals(False)

    def _on_text_changed(self):
        self._has_user_edited = True
        self._refresh_state()

    def _refresh_state(self):
        normalized_text = normalize_note_text(self.note_input.toPlainText())
        is_valid = bool(normalized_text)
        is_changed = normalized_text != self.initial_note_text
        can_save = is_valid and (self.note is None or is_changed)
        show_empty_error = self._has_user_edited and not is_valid

        self.error_label.setText(EMPTY_NOTE_ERROR if show_empty_error else "")
        self.error_label.setVisible(show_empty_error)
        self.save_note_button.setEnabled(can_save)
        self.delete_note_button.setEnabled(self.note is not None)

    def _save_note(self):
        try:
            note_text = validate_note_text(self.note_input.toPlainText())
        except ValueError:
            self._has_user_edited = True
            self._refresh_state()
            return

        self.result_payload = {
            "action": "save",
            "note": note_text,
        }
        self.accept()

    def _delete_note(self):
        if self.note is None:
            return

        self.result_payload = {"action": "delete"}
        self.accept()
