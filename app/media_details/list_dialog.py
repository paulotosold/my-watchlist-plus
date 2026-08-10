from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .constants import (
    DETAIL_BUTTON_WIDTH,
    DETAILS_BACKGROUND_COLOR,
)
from app.media_user_data.lists import (
    DUPLICATE_LIST_NAME_ERROR,
    EMPTY_LIST_NAME_ERROR,
    is_duplicate_list_name,
    normalize_list_description,
    normalize_list_name,
    validate_list_name,
)


LIST_DETAILS_INPUT_WIDTH = 500
LIST_DETAILS_DESCRIPTION_INPUT_HEIGHT = 100


class ListDetailsDialog(QDialog):
    def __init__(self, parent, list_item=None, existing_lists=None):
        super().__init__(parent)

        self.list_item = deepcopy(list_item) if list_item is not None else None
        self.existing_lists = deepcopy(existing_lists or [])
        self.result_payload = {"action": "cancel"}
        self.initial_signature = (
            normalize_list_name((self.list_item or {}).get("name")),
            normalize_list_description(
                (self.list_item or {}).get("description")
            ),
        )
        self._has_user_edited = False

        self.setWindowTitle("List Details")
        self._apply_parent_styles(parent)
        self._build_ui()
        self._populate_initial_values()
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

        form_layout = QGridLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(16)
        form_layout.setVerticalSpacing(12)

        name_label = QLabel("List Name:", self)
        name_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        description_label = QLabel("Description:", self)
        description_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )

        self.list_name_input = QLineEdit(self)
        self.list_name_input.setFixedSize(LIST_DETAILS_INPUT_WIDTH, 32)
        self.description_input = QPlainTextEdit(self)
        self.description_input.setFixedSize(
            LIST_DETAILS_INPUT_WIDTH,
            LIST_DETAILS_DESCRIPTION_INPUT_HEIGHT,
        )

        self.list_name_input.textChanged.connect(self._on_text_changed)
        self.description_input.textChanged.connect(self._on_text_changed)

        form_layout.addWidget(name_label, 0, 0)
        form_layout.addWidget(self.list_name_input, 0, 1)
        form_layout.addWidget(description_label, 1, 0)
        form_layout.addWidget(self.description_input, 1, 1)
        main_layout.addLayout(form_layout)

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

        self.delete_list_button = QPushButton("DELETE", bar)
        self.delete_list_button.setObjectName("deleteButton")
        self.cancel_list_button = QPushButton("Cancel", bar)
        self.save_list_button = QPushButton("Save", bar)

        for button in (
            self.delete_list_button,
            self.cancel_list_button,
            self.save_list_button,
        ):
            button.setMinimumHeight(32)
            button.setFixedWidth(DETAIL_BUTTON_WIDTH)
            layout.addWidget(button)

        layout.addStretch()

        self.delete_list_button.clicked.connect(self._delete_list)
        self.cancel_list_button.clicked.connect(self.reject)
        self.save_list_button.clicked.connect(self._save_list)
        return bar

    def _populate_initial_values(self):
        self.list_name_input.blockSignals(True)
        self.description_input.blockSignals(True)
        self.list_name_input.setText((self.list_item or {}).get("name") or "")
        self.description_input.setPlainText(
            (self.list_item or {}).get("description") or ""
        )
        self.list_name_input.blockSignals(False)
        self.description_input.blockSignals(False)

    def _on_text_changed(self):
        self._has_user_edited = True
        self._refresh_state()

    def _refresh_state(self):
        name = normalize_list_name(self.list_name_input.text())
        description = normalize_list_description(
            self.description_input.toPlainText()
        )
        is_duplicate = is_duplicate_list_name(
            name,
            self.existing_lists,
            current_list_id=(self.list_item or {}).get("id"),
        )
        is_valid = bool(name) and not is_duplicate
        is_changed = (name, description) != self.initial_signature
        can_save = is_valid and (self.list_item is None or is_changed)

        error = ""

        if self._has_user_edited and not name:
            error = EMPTY_LIST_NAME_ERROR
        elif is_duplicate:
            error = DUPLICATE_LIST_NAME_ERROR

        self.error_label.setText(error)
        self.error_label.setVisible(bool(error))
        self.save_list_button.setEnabled(can_save)
        self.delete_list_button.setEnabled(self.list_item is not None)

    def _save_list(self):
        try:
            name = validate_list_name(self.list_name_input.text())
        except ValueError:
            self._has_user_edited = True
            self._refresh_state()
            return

        if is_duplicate_list_name(
            name,
            self.existing_lists,
            current_list_id=(self.list_item or {}).get("id"),
        ):
            self._has_user_edited = True
            self._refresh_state()
            return

        self.result_payload = {
            "action": "save",
            "name": name,
            "description": normalize_list_description(
                self.description_input.toPlainText()
            ),
        }
        self.accept()

    def _delete_list(self):
        if self.list_item is None:
            return

        name = self.list_item.get("name") or "this list"
        result = QMessageBox.warning(
            self,
            "Delete List",
            f"Delete {name} and remove it from every media item?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if result != QMessageBox.Yes:
            return

        self.result_payload = {"action": "delete"}
        self.accept()
