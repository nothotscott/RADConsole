# Copyright 2020 Scott Maday
# Contains GUIs for a configuration

import os.path, logging

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QMessageBox, QFileDialog

from main import DEFAULT_CONFIG_FILE
from configuration import *
from gui import *


GUI_CONFIG_TREE_COLUMNS	= ["Label", "Object"]
GUI_CONFIG_DATA_HEADERS	= ["Key", "Type", "Value"]


def configuration_to_configurable_qtreewidgetitem(config):
	assert issubclass(type(config), Configuration)
	item = Data_Defined_QTreeWidgetItem(config)
	item.setText(0, str(config))
	if config.struct and config.struct.name:
		item.setText(1, config.struct.name)
	for key, value in config.items():
		if not issubclass(type(value), Configuration):
			continue
		child_text = str(key) if not config.is_list() or not value.struct or not value.struct.name else value.struct.name
		child_item = configuration_to_configurable_qtreewidgetitem(value)
		if child_item:
			item.addChild(child_item)
	return item

def configuration_to_qtablewidgetitem_matrix(config):
	items = []
	for key, child in config.items():
		if issubclass(type(child), Configuration) or (SCHEMA_STRUCTURE_OBJECT_CONTEXT_ATTRIBUTES and key == SCHEMA_STRUCTURE_OBJECT_CONTEXT_NAME):
			continue
		child_struct = config.struct[key] if config.struct and key in config.struct else None
		disabled_flags = FLAG_TABLE_CELL_PARTIAL_ENABLED if child_struct else FLAG_TABLE_CELL_FULL_ENABLED
		items.append([
			Data_Defined_QTableWidgetItem(key, key).enable_flags(disabled_flags, False).setToolTip(child_struct.label if child_struct and child_struct.label else None),
			Data_Defined_QTableWidgetItem(key, child_struct.struct_type.type_name if child_struct else type(child).__name__).enable_flags(disabled_flags, False),
			Data_Defined_QTableWidgetItem(key, str(child)).enable_flags(0 if child_struct else disabled_flags, False).setToolTip(str(child_struct.default) if child_struct and hasattr(child_struct, "default") and child_struct.default else None)
		])
	return items

def create_file_dialog(parent, title, format, save_mode = False, existing_file = None):
	if format == "config":
		format = "Configuration (*.json)"
	elif format == "schema":
		format = "Schemas (*.xml)"
	dialog = QFileDialog(parent, title, existing_file)
	dialog.setFileMode(QFileDialog.AnyFile)
	dialog.setNameFilters([format, "All Files (*)"])
	if save_mode:
		dialog.setAcceptMode(QFileDialog.AcceptSave)
	return dialog

class GUI_Configuration_Advanced(GUI_MainWindow):
	__logger = logging.getLogger(__name__)
	_file_name = os.path.join(GUI_DIRECTORY_NAME, "configuration_advanced.ui")
	
	def __init__(self, config = None, *args, **kwargs):
		super(GUI_Configuration_Advanced, self).__init__(config, *args, **kwargs)
		self.working_config = None
		self.loading_table = False
		self.changes = False
		self.__init_gui()
		self.load_config()
		
	def __init_gui(self):
		self.actionSave.triggered.connect(lambda: self.save_config())
		self.actionSave_As.triggered.connect(lambda: self.save_config(self.config, True))
		self.actionSave_Object.triggered.connect(lambda: self.save_config(self.get_selected_config(), True))
		self.actionOpen.triggered.connect(self.open_dialog)
		self.actionClose.triggered.connect(self.clear_config)
		self.actionAdd_Object.triggered.connect(self.add_object)
		self.actionRemove_Object.triggered.connect(self.remove_object)
		self.actionExpand.triggered.connect(lambda: self.expand_config_tree(True))
		self.actionCollapse.triggered.connect(lambda: self.expand_config_tree(False))
		self.actionReset.triggered.connect(self.reset_clicked)
		self.actionGenerate.triggered.connect(self.generate_clicked)
		
		self.dialog_buttons = self.findChild(QtWidgets.QDialogButtonBox, "dialog_buttons")
		self.dialog_buttons.button(QtWidgets.QDialogButtonBox.Cancel).clicked.connect(lambda: self.safe_close(False))
		self.dialog_buttons.button(QtWidgets.QDialogButtonBox.Ok).clicked.connect(lambda: self.safe_close(True))
		
		self.config_tree = self.findChild(QtWidgets.QTreeWidget, "config_tree")
		self.config_tree.itemClicked.connect(self.config_tree_item_clicked)
		self.config_tree.setColumnCount(len(GUI_CONFIG_TREE_COLUMNS))
		self.config_tree.setHeaderLabels(GUI_CONFIG_TREE_COLUMNS)
		tree_header = self.config_tree.header()
		tree_header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
		# tree_header.resizeSection(0, 400)
		tree_header.setSectionResizeMode(len(GUI_CONFIG_TREE_COLUMNS) - 1, QtWidgets.QHeaderView.Stretch)
		for i in range(len(GUI_CONFIG_TREE_COLUMNS) - 1):
			tree_header.setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeToContents)
		
		self.config_table = self.findChild(QtWidgets.QTableWidget, "config_table")
		self.config_table.itemChanged.connect(self.config_table_cell_changed)
		self.config_table.setColumnCount(len(GUI_CONFIG_DATA_HEADERS))
		self.config_table.setHorizontalHeaderLabels(GUI_CONFIG_DATA_HEADERS)
		table_header = self.config_table.horizontalHeader()
		table_header.setSectionResizeMode(len(GUI_CONFIG_DATA_HEADERS) - 1, QtWidgets.QHeaderView.Stretch)
		for i in range(len(GUI_CONFIG_DATA_HEADERS) - 1):
			table_header.setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeToContents)
	
	def refresh_action_buttons(self):
		selection = self.get_selection()
		has_config = self.config != None
		has_selection = selection != None
		selection_is_structural_array = has_selection and len(selection.data.get_structural_array_configurations(False)) > 0
		parent_selection_is_structural_array = has_selection and selection.parent() != None and len(selection.parent().data.get_structural_array_configurations(False)) > 0 
		self.actionSave.setEnabled(has_config)
		self.actionSave_As.setEnabled(has_config)
		self.actionSave_Object.setEnabled(has_selection)
		self.actionAdd_Object.setEnabled(selection_is_structural_array)
		self.actionRemove_Object.setEnabled(parent_selection_is_structural_array)
		self.actionExpand.setEnabled(has_config)
		self.actionCollapse.setEnabled(has_config)
		self.actionReset.setEnabled(has_config)
		
	def get_selection(self):
		if len(self.config_tree.selectedItems()) == 0:
			return None
		return self.config_tree.selectedItems()[0]
	
	def get_selected_config(self):
		selection = self.get_selection()
		if not selection:
			return None
		return selection.data
	
	def prompt_unsaved_changes(self, cancelable = False):
		if not self.changes:
			return None
		answer = QMessageBox.warning(self, "Save changes", "There are unsaved changes. Save this configuration?", QMessageBox.No | QMessageBox.Save | (QMessageBox.Cancel if cancelable else QMessageBox.NoButton))
		if answer == QMessageBox.No:
			return None
		elif answer == QMessageBox.Cancel:
			self.__logger.debug("User selected cancel. The next operation should be cancelled")
			return True
		self.save_config()
	
	def safe_close(self, definite_save):
		if definite_save:
			self.save_config()
		elif self.prompt_unsaved_changes(True):
			return None
		self.close()
	
	def load_config(self):
		assert self.config == None or issubclass(type(self.config), Configuration)
		self.working_config = None
		self.changes = False
		self.config_tree.clear()
		self.config_table.clearContents()
		self.config_table.setRowCount(0)
		if self.config:
			top_item = configuration_to_configurable_qtreewidgetitem(self.config)
			self.config_tree.addTopLevelItem(top_item)
		self.refresh_action_buttons()
	
	def save_config(self, config = None, prompt_dialog = False):
		if not config:
			config = self.config
		if not config:
			QMessageBox.critical(self, "No configuration", "There is no configuration to save", QMessageBox.Ok)
			return None
		file_name = config.file_name if isinstance(config, Root_Configuration) else DEFAULT_CONFIG_FILE
		if prompt_dialog or not isinstance(config, Root_Configuration):
			dialog_config = create_file_dialog(self, "Save configuration", "config", False, file_name)
			if not dialog_config.exec_():
				return None
			file_name = dialog_config.selectedFiles()[0]
			config = Root_Configuration(file_name, config)
		assert isinstance(config, Root_Configuration)
		config.save()
		self.changes = False
		self.__logger.info("Saved configuration %s", file_name)
	
	def open_dialog(self, checked = False):
		dialog_config = create_file_dialog(self, "Open configuration", "config")
		if not dialog_config.exec_():
			return None
		dialog_schema = create_file_dialog(self, "Open schema corresponding to the configuration", "schema")
		dialog_schema_file = None
		if dialog_schema.exec_():
			dialog_schema_file = dialog_schema.selectedFiles()[0]
		if self.prompt_unsaved_changes(True):
			return None
		self.config = configuration_from_file(dialog_config.selectedFiles()[0], dialog_schema_file)
		self.load_config()
	
	def clear_config(self):
		if self.prompt_unsaved_changes(True):
			return None
		self.config = None
		self.load_config()
	
	def reset_clicked(self, checked = False):
		if not self.config:
			return None
		if not self.config.struct:
			QMessageBox.critical(self, "Cannot reset", "Cannot perform a reset without a schema. Reload this configuration with a schema to perform a reset.", QMessageBox.Ok)
			return
		if QMessageBox.warning(self, "Reset this configuration?", "Resetting this configuration will set all values to those defined by the schema. The reset will not write any data to the configuration file. Continue?", QMessageBox.Cancel | QMessageBox.Ok) != QMessageBox.Ok:
			return None
		if self.prompt_unsaved_changes(True):
			return None
		self.config = Root_Configuration(self.config.file_name, self.config.struct) if isinstance(self.config, Root_Configuration) else Configuration(self.config.struct)
		self.load_config()
	
	def generate_clicked(self, checked = False):
		dialog_schema = create_file_dialog(self, "Schema to generate from", "schema", False, self.config.struct.attributes["file_name"] if self.config and self.config.struct and "file_name" in self.config.struct.attributes else None)
		if not dialog_schema.exec_():
			return None
		dialog_config = create_file_dialog(self, "Save generated configuration as...", "config", True)
		if not dialog_config.exec_():
			return None
		struct = schema_from_file(dialog_schema.selectedFiles()[0])
		if not struct:
			QMessageBox.critical(self, "Failed to generate", "Failed to generate because no structure was found.", QMessageBox.Ok)
			return None
		config = Root_Configuration(dialog_config.selectedFiles()[0], struct)
		config.save()
		if QMessageBox.information(self, "Open generated configuration?", "Open the generated configuration in this editor?", QMessageBox.No | QMessageBox.Yes) != QMessageBox.Yes:
			return None
		if self.prompt_unsaved_changes(True):
			return None
		self.config = config
		self.load_config()
	
	def config_tree_item_clicked(self, item):
		self.refresh_config_table(item)
		self.refresh_action_buttons()
	
	def refresh_config_table(self, item):
		self.working_config = item.data
		self.loading_table = True
		qtablewidgetitems_matrix = configuration_to_qtablewidgetitem_matrix(self.working_config)
		self.config_table.setRowCount(len(qtablewidgetitems_matrix))
		for row, qtablewidgetitems in enumerate(qtablewidgetitems_matrix):
			for col, qtablewidgetitem in enumerate(qtablewidgetitems):
				self.config_table.setItem(row, col, qtablewidgetitem)
		self.loading_table = False
	
	def config_table_cell_changed(self, item):
		if self.loading_table or not self.working_config or not item.data in self.working_config:
			return None
		key = item.data
		if not self.working_config.struct or not key in self.working_config.struct:
			QMessageBox.critical(self, "Cannot modify value", "This value cannot be modified because no structure for this key could be found. Either reload with the schema file or directly modify the JSON.", QMessageBox.Ok)
			return None
		new_value = item.text()
		if not self.working_config.struct[key].validate_value(new_value):
			QMessageBox.critical(self, "Cannot modify value", "The value entered is not valid", QMessageBox.Ok)
			return None
		self.working_config[key] = self.working_config.struct[key].cast_value(new_value)
		self.changes = True
	
	def add_object(self, checked = False):
		item = self.get_selection()
		if not item:
			return None
		config = item.data
		configs = config.get_structural_array_configurations()
		if len(configs) == 0:
			return None
		
		config_append = configs[0]
		if len(configs) > 1:
			prompt = GUI_Configuration_Object_Dialog(configs)
			if not prompt.exec_():
				return None
			config_append = prompt.get_selected()
		config.append(config_append)
		item.addChild(configuration_to_configurable_qtreewidgetitem(config_append))
		self.changes = True
	
	def remove_object(self, checked = False):
		item = self.get_selection()
		if not item:
			return None
		item_config = item.data
		parent = item.parent()
		if not parent:
			return None
		parent_config = parent.data
		if len(parent_config.get_structural_array_configurations()) == 0:
			return None
		parent_config.remove(item_config)
		parent.removeChild(item)
		self.changes = True
		
		
	def expand_config_tree(self, expand, item = None):
		if not item and len(self.config_tree.selectedItems()) > 0:
			item = self.config_tree.selectedItems()[0]
		elif self.config_tree.topLevelItemCount() > 0:
			item = self.config_tree.topLevelItem(0)
		else:
			return None
		item.expand_recusive(expand)
###


class GUI_Configuration_Object_Dialog(GUI_DialogWindow):
	__logger = logging.getLogger(__name__)
	_file_name = os.path.join(GUI_DIRECTORY_NAME, "configuration_object_dialog.ui")
	
	def __init__(self, configs = None, *args, **kwargs):
		super(GUI_Configuration_Object_Dialog, self).__init__(configs, *args, **kwargs)
		self.objects_combobox = self.findChild(QtWidgets.QComboBox, "object_comboBox")
		for config in configs:
			self.objects_combobox.addItem(config.struct.label, config)
	
	def get_selected(self):
		return self.objects_combobox.currentData()
###