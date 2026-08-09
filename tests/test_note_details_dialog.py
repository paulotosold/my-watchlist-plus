import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QDialog

from app.media_details.note_dialog import (
    NOTE_DETAILS_INPUT_HEIGHT,
    NOTE_DETAILS_INPUT_WIDTH,
    NoteDetailsDialog,
)


class NoteDetailsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.application.processEvents()

    def test_new_note_starts_empty_with_expected_size_and_button_states(self):
        dialog = self._dialog()

        self.assertEqual(dialog.windowTitle(), "Note Details")
        self.assertEqual(dialog.note_input.toPlainText(), "")
        self.assertEqual(
            dialog.note_input.size(),
            QSize(NOTE_DETAILS_INPUT_WIDTH, NOTE_DETAILS_INPUT_HEIGHT),
        )
        self.assertFalse(dialog.delete_note_button.isEnabled())
        self.assertFalse(dialog.save_note_button.isEnabled())
        self.assertTrue(dialog.cancel_note_button.isEnabled())
        self.assertTrue(dialog.error_label.isHidden())

    def test_whitespace_is_invalid_and_valid_multiline_text_is_trimmed(self):
        dialog = self._dialog()

        dialog.note_input.setPlainText(" \n\t ")
        self.assertFalse(dialog.save_note_button.isEnabled())
        self.assertEqual(dialog.error_label.text(), "Note cannot be empty.")
        self.assertFalse(dialog.error_label.isHidden())

        dialog.note_input.setPlainText("  First line\nSecond line  ")
        self.assertTrue(dialog.save_note_button.isEnabled())
        self.assertTrue(dialog.error_label.isHidden())
        dialog.save_note_button.click()

        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(
            dialog.result_payload,
            {"action": "save", "note": "First line\nSecond line"},
        )

    def test_edit_starts_unchanged_and_only_enables_save_for_valid_change(self):
        dialog = self._dialog({"id": 7, "note": "Original"})

        self.assertEqual(dialog.note_input.toPlainText(), "Original")
        self.assertTrue(dialog.delete_note_button.isEnabled())
        self.assertFalse(dialog.save_note_button.isEnabled())

        dialog.note_input.setPlainText("Changed")
        self.assertTrue(dialog.save_note_button.isEnabled())

        dialog.note_input.setPlainText("  Original  ")
        self.assertFalse(dialog.save_note_button.isEnabled())

        dialog.note_input.clear()
        self.assertFalse(dialog.save_note_button.isEnabled())
        self.assertEqual(dialog.error_label.text(), "Note cannot be empty.")

    def test_delete_is_available_only_for_existing_note(self):
        new_dialog = self._dialog()
        new_dialog.delete_note_button.click()
        self.assertEqual(new_dialog.result_payload, {"action": "cancel"})

        edit_dialog = self._dialog({"id": 7, "note": "Original"})
        edit_dialog.delete_note_button.click()
        self.assertEqual(edit_dialog.result(), QDialog.Accepted)
        self.assertEqual(edit_dialog.result_payload, {"action": "delete"})

    def test_cancel_rejects_without_changing_result_payload(self):
        dialog = self._dialog()
        dialog.note_input.setPlainText("Unsaved")

        dialog.cancel_note_button.click()

        self.assertEqual(dialog.result(), QDialog.Rejected)
        self.assertEqual(dialog.result_payload, {"action": "cancel"})

    def _dialog(self, note=None):
        dialog = NoteDetailsDialog(None, note)
        self.addCleanup(dialog.close)
        return dialog


if __name__ == "__main__":
    unittest.main()
