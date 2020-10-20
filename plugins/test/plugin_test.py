# Copyright (C) 2020 Scott Maday

import os, logging, time

import pluginlib
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from plugin import *
from gui import *


class Plugin_Test(Plugin):
	_alias_ = "test"
	
	def __init__(self, *args):
		super(Plugin_Test, self).__init__(*args)
		self._gui_class = GUI_Plugin_Test
	
	def on_loaded(self):
		self._log(logging.INFO, "on_loaded called")
		self._log(logging.INFO, "Reading plugin configuration: %s", str(self.plugin_config))
		time.sleep(5)
		self._log(logging.INFO, "Slept for 5 seconds")
		

class GUI_Plugin_Test(GUI_MainWindow):
	_file_name = os.path.join(PLUGIN_DIR_NAME, os.path.join("test", "plugin_test_gui.ui"))
	
	def __init__(self, config, *args, **kwargs):
		super(GUI_Plugin_Test, self).__init__(config, *args, **kwargs)
		
		self.worker = GUI_Plugin_Test_Worker(self)
		self.worker.sig_value_updated.connect(self.updateProgressBar)
		self.worker.sig_finished.connect(self.test_finish)
		
		self.close_button = self.findChild(QtWidgets.QPushButton, "close_button")
		self.close_button.clicked.connect(self.close)
		
		self.test_button = self.findChild(QtWidgets.QPushButton, "test_button")
		self.test_button.clicked.connect(self.test_start)
		
		self.progressbar = self.findChild(QtWidgets.QProgressBar, "progressbar")
		
	def test_start(self):
		if not self.worker.isRunning():
			self.worker.start()
		else:
			QMessageBox.warning(self, "Hold on!", self["hold_on_msg"], QMessageBox.Ok)
		
	def test_finish(self):
		QMessageBox.information(self, "Test Complete", self["test_complete_msg"], QMessageBox.Ok)
		
	def updateProgressBar(self, val):
		self.progressbar.setValue(val)


class GUI_Plugin_Test_Worker(QThread):
	sig_value_updated = pyqtSignal(int)
	sig_finished = pyqtSignal()

	def __init__(self, parent = None):
		super(GUI_Plugin_Test_Worker, self).__init__(parent)
	
	def run(self):
		sleep_time = self.parent()["wait_time"] / 100.0
		for i in range(101):
			time.sleep(sleep_time)
			self.sig_value_updated.emit(i)
		self.sig_finished.emit()
		self.sig_value_updated.emit(0)