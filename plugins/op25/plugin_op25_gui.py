# Copyright 2020 Scott Maday

import os, sys, logging, threading, json, time

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem
from PyQt5.QtGui import QColor
from gnuradio import gr

from plugin import PLUGIN_DIR_NAME
from gui import *

GUI_FREQUENCY_DATA_HEADERS		= ["Frequency", "Talkgroup ID", "Last seen", "Count"]
GUI_COLOR_COL_HIGHLIGHT_TGID	= QColor(46, 204, 113)
GUI_COLOR_ROW_HIGHLIGHT			= QColor(46, 204, 113)
GUI_COLOR_ROW_HIGHLIGHT_ENCRYPT	= QColor(192, 57, 43)
GUI_UPDATE_INTERVAL				= 0.5


class GUI_Plugin_OP25(GUI_MainWindow):
	_file_name = os.path.join(PLUGIN_DIR_NAME, os.path.join("test", "plugin_op25_gui.ui"))
	
	def __init__(self, config, *args, **kwargs):
		super(GUI_Plugin_OP25, self).__init__(config, *args, **kwargs)
		
		self.current_nac = None
		self.current_sysname = None
		self.current_freq = 0
		self.current_tgid = 0
		self.encrypted = False
		self.freq_data = []
		
		self.worker = GUI_Plugin_OP25_Worker(self)
		self.worker.sig_trunk_update.connect(self.on_trunk_update)
		self.worker.sig_change_freq.connect(self.on_change_freq)
		
		self.label_sysname = self.findChild(QtWidgets.QLabel, "label_sysname")
		self.label_sysname.setText("")
		self.label_info = self.findChild(QtWidgets.QLabel, "label_info")
		self.label_info.setText("")
		self.label_tsbks = self.findChild(QtWidgets.QLabel, "label_tsbks")
		self.label_tsbks.setText("")
		self.label_frequency = self.findChild(QtWidgets.QLabel, "label_frequency")
		self.label_fine_tune = self.findChild(QtWidgets.QLabel, "label_fine_tune")
		
		self.table_frequency_data = self.findChild(QtWidgets.QTableWidget, "table_frequency_data")
		self.table_frequency_data.setColumnCount(len(GUI_FREQUENCY_DATA_HEADERS))
		self.table_frequency_data.setHorizontalHeaderLabels(GUI_FREQUENCY_DATA_HEADERS)
		header = self.table_frequency_data.horizontalHeader()
		header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
		for i in range(len(GUI_FREQUENCY_DATA_HEADERS) - 1):
			header.setSectionResizeMode(i + 1, QtWidgets.QHeaderView.ResizeToContents)
	
	def set_queues(self, input_queue, output_queue):
		self.worker.input_queue = input_queue
		self.worker.output_queue = output_queue
		
	def start(self):
		self.worker.start()
	
	def on_trunk_update(self, msg):
		# print(json.dumps(msg))
		nacs = [x for x in list(msg.keys()) if x.isnumeric() ]
		if not nacs:
			return
		sysnames = {}
		for nac in nacs:
			if "system" in msg[nac] and msg[nac]["system"] is not None:
				print("found system " + msg[nac]["system"])
				sysnames[msg[nac]["system"]] = nac
		
		if self.current_sysname in sysnames:
			current_nac = str(sysnames[self.current_sysname])
		elif msg.get("nac"):
			current_nac = str(msg["nac"])
		else:
			times = {msg[nac]["last_tsbk"]:nac for nac in nacs}
			current_nac = times[ sorted(list(times.keys()), reverse=True)[0] ]
		self.current_nac = current_nac
		current_data = msg[current_nac]
		
		info = "NAC 0x%x WACN 0x%x SYSID 0x%x" % (int(self.current_nac), current_data["wacn"], current_data["sysid"])
		self.label_info.setText(info)
		if "tsbks" in current_data: # my commit :)
			tsbks_str = " Received TS-blocks %d" % (current_data["tsbks"]) # Trunking Signaling blocks is what TS stands for btw
			self.label_tsbks.setText(tsbks_str)
		if "encrypted" in current_data and current_data["encrypted"]:
			self.encrypted = True
			print("ENCRYPTED!")
		else:
			self.encrypted = False
		
		# format frequency_data into a more standardized and comparable format
		self.freq_data = [None] * len(current_data["frequency_data"])
		for i, (freq, data) in enumerate(current_data["frequency_data"].items()):
			tgids = data["tgids"] if len(data["tgids"]) > 0 else [0, None]
			self.freq_data[i] = [int(freq), data["tgids"], data["last_activity"], data["counter"]]
		self.table_frequency_data.setRowCount(len(self.freq_data))
		for row, data in enumerate(self.freq_data):
			self.table_frequency_data.setItem(row, 0, QTableWidgetItem(num_to_freq(data[0])))
			self.table_frequency_data.setItem(row, 1, QTableWidgetItem(tgid_list_tostring(data[1])))
			self.table_frequency_data.setItem(row, 2, QTableWidgetItem(str(data[2]) + "s"))
			self.table_frequency_data.setItem(row, 3, QTableWidgetItem(str(data[3])))
			if self.current_freq == data[0]:
				for col in range(self.table_frequency_data.columnCount()): self.table_frequency_data.item(row, col).setBackground(GUI_COLOR_ROW_HIGHLIGHT_ENCRYPT if self.encrypted else GUI_COLOR_ROW_HIGHLIGHT)
			elif self.current_tgid == data[1][0]:
				self.table_frequency_data.item(row, 1).setBackground(GUI_COLOR_COL_HIGHLIGHT_TGID)
	
	def on_change_freq(self, msg):
		self.current_freq = 0
		self.current_tgid = 0
		
		if msg["fine_tune"]:	self.label_fine_tune.setText(str(msg["fine_tune"]))
		if msg["system"]:		self.label_sysname.setText(msg["system"])
		if msg["freq"]:
			self.current_freq = msg["freq"]
			self.label_frequency.setText(num_to_freq(self.current_freq))
		if "tgid" in msg and msg["tgid"]:
			self.current_tgid = msg["tgid"]
###

# From the curses terminal in op25 apps adapted to dispatch signals on a QThread
class GUI_Plugin_OP25_Worker(QThread):	
	sig_trunk_update = pyqtSignal(dict)
	sig_change_freq = pyqtSignal(dict)
	
	def __init__(self, parent = None):
		super(GUI_Plugin_OP25_Worker, self).__init__(parent)
		self.input_queue = None
		self.output_queue = None
		self.last_update = 0
		self.current_msgqid = "0"
		
	def do_auto_update(self):
		if self.last_update + GUI_UPDATE_INTERVAL > time.time():
			return False
		self.last_update = time.time()
		return True
	
	def process_json(self, js):
		msg = json.loads(js)
		if msg["json_type"] == "trunk_update":	self.sig_trunk_update.emit(msg)
		elif msg["json_type"] == "change_freq":	self.sig_change_freq.emit(msg)
		
	def send_command(self, command, arg1 = 0, arg2 = None):
		if arg2 == None:
			arg2 = int(self.current_msgqid)
		msg = gr.message().make_from_string(command, -2, arg1, arg2)
		self.output_queue.insert_tail(msg)
	
	def run(self):
		self.keep_running = True
		while self.keep_running:
			# Send updates
			if self.do_auto_update():
				self.send_command("update")
			# Check input queue
			while not self.input_queue.empty_p():
				msg = self.input_queue.delete_head() # delete_head_nowait()
				if msg.type() == -4:
					self.process_json(msg.to_string())
		keep_running = False


from plugin_op25 import *