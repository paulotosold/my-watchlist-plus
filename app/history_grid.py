from __future__ import annotations

from collections import defaultdict, deque
from math import ceil

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetrics, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QWidget,
)

from app.history_entry_widget import POSTER_DIR


MIN_POSTERS_PER_ROW = 6
DEFAULT_POSTERS_PER_ROW = 18
MAX_POSTERS_PER_ROW = 24

GRID_SPACING = 6
GRID_TOP_MARGIN = 12
GRID_BOTTOM_MARGIN = 12
POSTER_ASPECT_WIDTH = 2
POSTER_ASPECT_HEIGHT = 3

# Explicit aliases keep imports unambiguous beside the Watchlist constants.
HISTORY_GRID_MIN_POSTERS_PER_ROW = MIN_POSTERS_PER_ROW
HISTORY_GRID_DEFAULT_POSTERS_PER_ROW = DEFAULT_POSTERS_PER_ROW
HISTORY_GRID_MAX_POSTERS_PER_ROW = MAX_POSTERS_PER_ROW
HISTORY_GRID_SPACING = GRID_SPACING
HISTORY_GRID_TOP_MARGIN = GRID_TOP_MARGIN
HISTORY_GRID_BOTTOM_MARGIN = GRID_BOTTOM_MARGIN


class HistoryPosterTile(QLabel):
    """A lightweight, focusable poster for one History entry."""

    details_requested = Signal(int)

    def __init__(self, entry, parent=None):
        super().__init__(parent)

        self.entry = None
        self._poster_filename = None
        self._poster_path = None
        self._poster_fingerprint = None
        self._rendered_fingerprint = None
        self._rendered_size = QSize()

        self.setObjectName("historyGridPosterTile")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.setFixedSize(1, 1)
        self._placeholder_font = QFont(self.font())

        self.set_entry(entry)

    @property
    def entry_key(self):
        return self.entry.key

    def set_entry(self, entry):
        self.entry = entry
        self._poster_filename = _poster_filename(entry)
        (
            self._poster_path,
            poster_fingerprint,
        ) = _poster_file_state(self._poster_filename)
        self.setToolTip(entry.formatted_date)
        self.setAccessibleName(
            f"{entry.title} — {entry.formatted_date}"
        )

        if poster_fingerprint != self._poster_fingerprint:
            self._rendered_fingerprint = None
            self._rendered_size = QSize()

        self._poster_fingerprint = poster_fingerprint
        self._render_poster()

    def request_details(self):
        self.details_requested.emit(self.entry.details_media_id)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.request_details()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self.request_details()
            event.accept()
            return

        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_poster()

    def _render_poster(self):
        target_size = self.size()

        if target_size.width() <= 1 or target_size.height() <= 1:
            self.setPixmap(QPixmap())
            self.setText("")
            return

        if (
            self._rendered_fingerprint == self._poster_fingerprint
            and self._rendered_size == target_size
        ):
            return

        if (
            self._poster_fingerprint is None
            or target_size.isEmpty()
        ):
            self._show_placeholder()
            self._remember_render(target_size)
            return

        scaled = _read_scaled_poster(
            self._poster_path,
            target_size,
        )

        if scaled.isNull():
            self._show_placeholder()
            self._remember_render(target_size)
            return

        self.setText("")
        self.setStyleSheet(
            "QLabel#historyGridPosterTile {"
            "background-color: #dedede;"
            "border: none;"
            "}"
            "QLabel#historyGridPosterTile:focus {"
            "border: 2px solid #4f93cc;"
            "}"
        )
        crop_x = max(0, (scaled.width() - target_size.width()) // 2)
        crop_y = max(0, (scaled.height() - target_size.height()) // 2)
        self.setPixmap(
            scaled.copy(
                crop_x,
                crop_y,
                target_size.width(),
                target_size.height(),
            )
        )
        self._remember_render(target_size)

    def _show_placeholder(self):
        self.setPixmap(QPixmap())
        self.setText("No\nposter")
        self.setFont(
            _fit_placeholder_font(
                self._placeholder_font,
                max(1, self.width() - 4),
            )
        )
        self.setStyleSheet(
            "QLabel#historyGridPosterTile {"
            "background-color: #dedede;"
            "border: 1px solid #c6c6c6;"
            "color: #777777;"
            "}"
            "QLabel#historyGridPosterTile:focus {"
            "border: 2px solid #4f93cc;"
            "}"
        )

    def _remember_render(self, target_size):
        self._rendered_fingerprint = self._poster_fingerprint
        self._rendered_size = QSize(target_size)


class HistoryGridBoard(QWidget):
    """Row-major poster grid for the already loaded History collection."""

    details_requested = Signal(int)

    def __init__(
        self,
        posters_per_row=DEFAULT_POSTERS_PER_ROW,
        parent=None,
    ):
        super().__init__(parent)

        self.posters_per_row = self._clamp_posters_per_row(
            posters_per_row
        )
        self.entries = []
        self.tiles = []
        self.tile_by_entry_key = {}
        self.tiles_by_entry_key = {}
        self.entry_index_by_key = {}
        self.tile_width = 0
        self.tile_height = 0
        self.row_count = 0
        self._content_height = 0
        self._layout_width = None
        self._last_reflow_width = None

        self.setObjectName("historyGridBoard")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSizeConstraint(
            QLayout.SizeConstraint.SetNoConstraint
        )
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setHorizontalSpacing(GRID_SPACING)
        self.grid_layout.setVerticalSpacing(GRID_SPACING)
        self.grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        self._reflow_timer = QTimer(self)
        self._reflow_timer.setSingleShot(True)
        self._reflow_timer.timeout.connect(self.reflow_tiles)

    # Short aliases make the lookup convenient to callers without duplicating it.
    @property
    def tile_by_key(self):
        return self.tile_by_entry_key

    @property
    def tiles_by_key(self):
        return self.tiles_by_entry_key

    @property
    def content_height(self):
        return self._content_height

    def set_entries(self, entries):
        self.entries = list(entries or ())
        previous_tiles = list(self.tiles)
        reusable_tiles = defaultdict(deque)

        for tile in previous_tiles:
            reusable_tiles[tile.entry_key].append(tile)

        next_tiles = []

        for entry in self.entries:
            matching_tiles = reusable_tiles.get(entry.key)

            if matching_tiles:
                tile = matching_tiles.popleft()
                tile.set_entry(entry)
            else:
                tile = self._create_tile(entry)

            next_tiles.append(tile)

        for remaining_tiles in reusable_tiles.values():
            for tile in remaining_tiles:
                self._dispose_tile(tile)

        self.tiles = next_tiles
        self._rebuild_entry_key_mappings()

        if self.tiles != previous_tiles:
            self.reflow_tiles()

        return self.tiles

    def set_posters_per_row(self, posters_per_row):
        clamped_value = self._clamp_posters_per_row(posters_per_row)

        if clamped_value == self.posters_per_row:
            return False

        self.posters_per_row = clamped_value
        self.reflow_tiles()
        return True

    def set_layout_width(self, layout_width):
        normalized_width = (
            None
            if layout_width is None
            else max(1, int(layout_width))
        )

        if normalized_width == self._layout_width:
            return False

        self._layout_width = normalized_width
        self.reflow_tiles()
        return True

    def reflow_tiles(self):
        if self._reflow_timer.isActive():
            self._reflow_timer.stop()

        self._last_reflow_width = self.width()

        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        layout_width = min(
            max(1, self.width()),
            self._layout_width
            if self._layout_width is not None
            else max(1, self.width()),
        )
        spacing_width = (
            GRID_SPACING * max(0, self.posters_per_row - 1)
        )
        available_width = max(1, layout_width - spacing_width)
        self.tile_width = max(
            1,
            available_width // self.posters_per_row,
        )
        self.tile_height = max(
            1,
            round(
                self.tile_width
                * POSTER_ASPECT_HEIGHT
                / POSTER_ASPECT_WIDTH
            ),
        )

        used_width = (
            self.tile_width * self.posters_per_row + spacing_width
        )
        unused_width = max(0, layout_width - used_width)
        left_margin = unused_width // 2
        right_margin = unused_width - left_margin
        self.grid_layout.setContentsMargins(
            left_margin,
            GRID_TOP_MARGIN,
            right_margin,
            GRID_BOTTOM_MARGIN,
        )

        for index, tile in enumerate(self.tiles):
            row, column = divmod(index, self.posters_per_row)
            tile.setFixedSize(self.tile_width, self.tile_height)
            self.grid_layout.addWidget(tile, row, column)
            tile.show()

        self.row_count = (
            ceil(len(self.tiles) / self.posters_per_row)
            if self.tiles
            else 0
        )
        self._content_height = (
            GRID_TOP_MARGIN
            + self.row_count * self.tile_height
            + max(0, self.row_count - 1) * GRID_SPACING
            + GRID_BOTTOM_MARGIN
            if self.row_count
            else 0
        )

        self.setMinimumHeight(self._content_height)
        self.grid_layout.invalidate()
        self.grid_layout.activate()
        self.updateGeometry()

    def schedule_reflow(self):
        self._reflow_timer.start(0)

    def minimumSizeHint(self):
        return QSize(0, self._content_height)

    def sizeHint(self):
        return QSize(max(0, self.width()), self._content_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if event.size().width() != self._last_reflow_width:
            self.schedule_reflow()

    def _create_tile(self, entry):
        tile = HistoryPosterTile(entry, self)
        tile.details_requested.connect(self.details_requested.emit)
        return tile

    def _dispose_tile(self, tile):
        self.grid_layout.removeWidget(tile)
        tile.hide()
        tile.setParent(None)
        tile.deleteLater()

    def _rebuild_entry_key_mappings(self):
        grouped_tiles = defaultdict(list)
        entry_index_by_key = {}

        for index, tile in enumerate(self.tiles):
            grouped_tiles[tile.entry_key].append(tile)
            entry_index_by_key.setdefault(tile.entry_key, index)

        self.tiles_by_entry_key = dict(grouped_tiles)
        self.tile_by_entry_key = {
            key: matching_tiles[0]
            for key, matching_tiles in grouped_tiles.items()
        }
        self.entry_index_by_key = entry_index_by_key

    @staticmethod
    def _clamp_posters_per_row(posters_per_row):
        return max(
            MIN_POSTERS_PER_ROW,
            min(MAX_POSTERS_PER_ROW, int(posters_per_row)),
        )


def _poster_filename(entry):
    poster = entry.poster or {}
    return str(poster.get("filename") or "").lstrip("/") or None


def _poster_file_state(filename):
    if not filename:
        return None, None

    poster_path = POSTER_DIR / filename

    try:
        stat_result = poster_path.stat()
    except OSError:
        return poster_path, None

    fingerprint = (
        str(poster_path),
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
        stat_result.st_size,
    )
    return poster_path, fingerprint


def _read_scaled_poster(poster_path, target_size):
    reader = QImageReader(str(poster_path))
    reader.setAutoTransform(True)
    source_size = reader.size()

    if (
        not source_size.isValid()
        or source_size.width() <= 0
        or source_size.height() <= 0
    ):
        return QPixmap()

    scale_factor = max(
        target_size.width() / source_size.width(),
        target_size.height() / source_size.height(),
    )
    reader.setScaledSize(
        QSize(
            max(1, ceil(source_size.width() * scale_factor)),
            max(1, ceil(source_size.height() * scale_factor)),
        )
    )
    image = reader.read()

    if image.isNull():
        return QPixmap()

    return QPixmap.fromImage(image)


def _fit_placeholder_font(base_font, available_width):
    font = QFont(base_font)
    metrics = QFontMetrics(font)
    required_width = metrics.horizontalAdvance("poster")

    if required_width <= available_width:
        return font

    scale_factor = available_width / max(1, required_width)

    if font.pixelSize() > 0:
        font.setPixelSize(
            max(5, int(font.pixelSize() * scale_factor))
        )

        while (
            font.pixelSize() > 5
            and QFontMetrics(font).horizontalAdvance("poster")
            > available_width
        ):
            font.setPixelSize(font.pixelSize() - 1)
    else:
        font.setPointSizeF(
            max(5.0, font.pointSizeF() * scale_factor)
        )

        while (
            font.pointSizeF() > 5.0
            and QFontMetrics(font).horizontalAdvance("poster")
            > available_width
        ):
            font.setPointSizeF(
                max(5.0, font.pointSizeF() - 0.5)
            )

    return font


# Compatibility names for callers that prefer the grid-specific class wording.
HistoryGridPosterTile = HistoryPosterTile
HistoryGridTile = HistoryPosterTile
