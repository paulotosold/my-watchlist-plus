import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from app.media_details.list_dialog import (
    LIST_DETAILS_DESCRIPTION_INPUT_HEIGHT,
    LIST_DETAILS_INPUT_WIDTH,
    ListDetailsDialog,
)


class ListDetailsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.application.processEvents()

    def test_new_list_starts_empty_with_expected_size_and_button_states(self):
        dialog = self._dialog()

        self.assertEqual(dialog.windowTitle(), "List Details")
        self.assertEqual(dialog.list_name_input.text(), "")
        self.assertEqual(dialog.description_input.toPlainText(), "")
        self.assertEqual(
            dialog.list_name_input.size(),
            QSize(LIST_DETAILS_INPUT_WIDTH, 32),
        )
        self.assertEqual(
            dialog.description_input.size(),
            QSize(
                LIST_DETAILS_INPUT_WIDTH,
                LIST_DETAILS_DESCRIPTION_INPUT_HEIGHT,
            ),
        )
        self.assertFalse(dialog.delete_list_button.isEnabled())
        self.assertFalse(dialog.save_list_button.isEnabled())
        self.assertTrue(dialog.cancel_list_button.isEnabled())
        self.assertTrue(dialog.error_label.isHidden())

    def test_valid_name_enables_save_and_fields_are_trimmed(self):
        dialog = self._dialog()

        dialog.list_name_input.setText("  Kinotag  ")
        dialog.description_input.setPlainText("  Weekly movies\nwith family  ")
        self.assertTrue(dialog.save_list_button.isEnabled())
        dialog.save_list_button.click()

        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(
            dialog.result_payload,
            {
                "action": "save",
                "name": "Kinotag",
                "description": "Weekly movies\nwith family",
            },
        )

    def test_empty_and_duplicate_names_disable_save(self):
        existing_lists = [{"id": 1, "name": "Kinotag"}]
        dialog = self._dialog(existing_lists=existing_lists)

        dialog.list_name_input.setText(" \n\t ")
        self.assertFalse(dialog.save_list_button.isEnabled())
        self.assertEqual(dialog.error_label.text(), "List name cannot be empty.")

        dialog.list_name_input.setText("Kinotag")
        self.assertFalse(dialog.save_list_button.isEnabled())
        self.assertEqual(
            dialog.error_label.text(),
            "A list with this name already exists.",
        )

    def test_edit_enables_save_only_after_a_valid_change(self):
        list_item = {"id": 1, "name": "Kinotag", "description": "Original"}
        dialog = self._dialog(list_item, existing_lists=[list_item])

        self.assertTrue(dialog.delete_list_button.isEnabled())
        self.assertFalse(dialog.save_list_button.isEnabled())

        dialog.description_input.setPlainText("Changed")
        self.assertTrue(dialog.save_list_button.isEnabled())

        dialog.description_input.setPlainText("  Original  ")
        self.assertFalse(dialog.save_list_button.isEnabled())

    def test_delete_requires_confirmation(self):
        list_item = {"id": 1, "name": "Kinotag", "description": None}
        dialog = self._dialog(list_item, existing_lists=[list_item])

        with patch.object(
            QMessageBox,
            "warning",
            return_value=QMessageBox.No,
        ):
            dialog.delete_list_button.click()

        self.assertEqual(dialog.result_payload, {"action": "cancel"})

        with patch.object(
            QMessageBox,
            "warning",
            return_value=QMessageBox.Yes,
        ) as warning:
            dialog.delete_list_button.click()

        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(dialog.result_payload, {"action": "delete"})
        self.assertIn("every media item", warning.call_args.args[2])

    def _dialog(self, list_item=None, existing_lists=None):
        dialog = ListDetailsDialog(None, list_item, existing_lists)
        self.addCleanup(dialog.close)
        return dialog


if __name__ == "__main__":
    unittest.main()
