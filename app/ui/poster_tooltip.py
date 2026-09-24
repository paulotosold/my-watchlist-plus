"""Use the same tooltip delay for every poster, including adjacent posters."""

from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle, QWidget


POSTER_TOOLTIP_DELAY_MS = 2000


class _PosterTooltipStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return POSTER_TOOLTIP_DELAY_MS
        if hint == QStyle.StyleHint.SH_ToolTip_FallAsleepDelay:
            # End Qt's fast-tooltip window immediately after showing a poster.
            return 0
        return super().styleHint(hint, option, widget, returnData)


def apply_poster_tooltip_timing(widget):
    app = QApplication.instance()
    style = getattr(app, "_poster_tooltip_style", None)
    if style is None:
        style = _PosterTooltipStyle(app.style().objectName())
        style.setParent(app)
        app._poster_tooltip_style = style
    # Qt asks the widget under the pointer, which may be an overlay or button.
    for surface in (widget, *widget.findChildren(QWidget)):
        surface.setStyle(style)
