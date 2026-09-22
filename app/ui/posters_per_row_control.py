from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QStyle, QWidget

from .poster_density import normalize_posters_per_row


class _DensityComboBox(QComboBox):
    """Keep real keyboard focus without painting a persistent selection halo."""

    def initStyleOption(self, option):
        super().initStyleOption(option)
        # QMacStyle paints the combo's focus ring from State_HasFocus directly,
        # ignoring WA_MacShowFocusRect. Change only the visual state, not focus.
        option.state &= ~(
            QStyle.StateFlag.State_HasFocus | QStyle.StateFlag.State_Selected
        )


class PostersPerRowControl(QWidget):
    """Status-bar dropdown for the supported numbers of posters per row."""

    value_changed = Signal(int)

    def __init__(self, parent=None, *, value, options):
        super().__init__(parent)
        self._options = tuple(int(option) for option in options)
        if (
            not self._options
            or self._options != tuple(sorted(set(self._options)))
            or self._options[0] < 1
        ):
            raise ValueError("options must be positive, unique and ascending")

        self.setObjectName("postersPerRowControl")
        self.title_label = QLabel("Posters per row:", self)
        self.title_label.setObjectName("postersPerRowLabel")
        self.combo_box = _DensityComboBox(self)
        self.combo_box.setObjectName("postersPerRowComboBox")
        self.combo_box.setEditable(False)
        self.combo_box.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.combo_box.setAccessibleName("Posters per row")
        self.combo_box.setToolTip("Choose the number of posters per row")
        self.combo_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for option in self._options:
            self.combo_box.addItem(str(option), option)
        self.set_value(value)
        self.title_label.setBuddy(self.combo_box)
        self.setFocusProxy(self.combo_box)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.title_label)
        layout.addWidget(self.combo_box)

        self.combo_box.currentIndexChanged.connect(self._on_selection_changed)
        self._update_accessible_value()

    def value(self):
        return self.combo_box.currentData()

    @property
    def posters_per_row(self):
        return self.value()

    @property
    def minimum(self):
        return self._options[0]

    @property
    def maximum(self):
        return self._options[-1]

    def set_value(self, value):
        normalized = normalize_posters_per_row(value, self._options)
        self.combo_box.setCurrentIndex(self._options.index(normalized))

    def _on_selection_changed(self, _index):
        self._update_accessible_value()
        self.value_changed.emit(self.value())

    def _update_accessible_value(self):
        self.setAccessibleName(f"Posters per row: {self.value()}")
