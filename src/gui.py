# Copyright 2020 Scott Maday

import os, logging
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QTreeWidgetItem, QTableWidgetItem

GUI_DIRECTORY_NAME = "gui"

FLAG_ITEM_ISSELECTABLE	= Qt.ItemIsSelectable
FLAG_ITEM_ISEDITABLE	= Qt.ItemIsEditable
FLAG_ITEM_ISENABLED		= Qt.ItemIsEnabled

FLAG_TABLE_CELL_PARTIAL_ENABLED		= FLAG_ITEM_ISEDITABLE
FLAG_TABLE_CELL_FULL_ENABLED		= FLAG_ITEM_ISEDITABLE | FLAG_ITEM_ISENABLED


################################ [ HELPER FUNCTIONS & CLASSES ]	################################

def enable_flags(current_flags, flags, enable):
	flags = int(flags)
	if enable:
		return current_flags | flags
	else:
		return current_flags & ~flags
		

class Data_Defined_QTreeWidgetItem(QTreeWidgetItem):
	def __init__(self, data = None, *args, **kwargs):
		super(Data_Defined_QTreeWidgetItem, self).__init__(*args, **kwargs)
		self.data = data
	
	def expand_recusive(self, expand):
		self.setExpanded(expand)
		for i in range(self.childCount()):
			child = self.child(i)
			if isinstance(child, Data_Defined_QTreeWidgetItem):
				child.expand_recusive(expand)
###


class Data_Defined_QTableWidgetItem(QTableWidgetItem):
	def __init__(self, data = None, *args, **kwargs):
		super(Data_Defined_QTableWidgetItem, self).__init__(*args, **kwargs)
		self.data = data
	
	def enable_flags(self, flags, enable):
		self.setFlags(enable_flags(self.flags(), flags, enable))
		return self
	
	def setToolTip(self, toolTip):
		if toolTip:
			super(Data_Defined_QTableWidgetItem, self).setToolTip(toolTip)
		return self
###


################################ [ ABSTRACT BASE CLASSES ]	################################

# Abstract base class for the main window
class GUI_MainWindow(QtWidgets.QMainWindow):
	_logger = logging.getLogger(__name__)
	_file_name = None
	
	def __init__(self, config = None, *args, **kwargs):
		super(GUI_MainWindow, self).__init__(*args, **kwargs)
		if self._file_name:
			uic.loadUi(self._file_name, self)
		self.statusBar().setSizeGripEnabled(False)
		self.config = config
	
	def __getitem__(self, key):
		if not self.config or not key in self.config:
			return None
		return self.config[key]

# Abstract base class for dialog 
class GUI_DialogWindow(QtWidgets.QDialog):
	_logger = logging.getLogger(__name__)
	_file_name = None
	
	def __init__(self, config = None, *args, **kwargs):
		super(GUI_DialogWindow, self).__init__(*args, **kwargs)
		self.setWindowModality(Qt.ApplicationModal)
		if self._file_name:
			uic.loadUi(self._file_name, self)
		self.config = config
	
	def __getitem__(self, key):
		if not self.config or not key in self.config:
			return None
		return self.config[key]

#############