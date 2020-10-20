# Copyright (C) 2020 Scott Maday

import sys, os.path, logging, threading, time, platform, re
if sys.version_info.major >= 3:
	from queue import Queue
else:
	from Queue import Queue

import pluginlib
from PyQt5 import QtWidgets
from PyQt5.QtCore import QThread, pyqtSignal

from configuration import *
from gui import *


PLUGIN_ROOT					= "plugin"			# used in pluginlib
PLUGIN_DIR_NAME				= "plugins"			# directory containing plugins
PLUGIN_ENTRY_FILE_PREFIX	= "plugin_"			# used to reduce module name conflicts
PLUGIN_CONFIG_FILE_NAME		= "config.json"		# file name for configuration
PLUGIN_SCHEMA_FILE_NAME		= "schema.xml"		# file name of plugin schema
PLUGIN_LOG_INACTIVE_PLUGINS	= False

ANSI_PLUGIN_ENABLED		= "\033[92m"
ANSI_PLUGIN_DISABLED	= "\033[91m"
ANSI_PLUGIN_EXCEPTION	= "\033[1m"
ANSI_ENDC				= "\033[0m"


# Basic interpreter
# Might make more robust (and complex) if requirements begin to add up
def interpret_requirements(first_line):
	m1 = re.search(r"PLATFORM\((\w+\|?)+\)", first_line)
	if m1:
		return platform.system() in m1.group(0)
	return True

def get_plugin_modules():
	modules = []
	for dir_name in os.listdir(PLUGIN_DIR_NAME):
		dir = os.path.join(PLUGIN_DIR_NAME, dir_name)
		if os.path.isdir(dir):
			for file_name in os.listdir(dir):
				file = os.path.join(dir, file_name)
				file_root, file_ext = os.path.splitext(file_name)
				# check if the file is {PLUGIN_ENTRY_FILE_PREFIX}{dir_name}.py for further analysis
				if file_root.startswith(PLUGIN_ENTRY_FILE_PREFIX) and file_root[len(PLUGIN_ENTRY_FILE_PREFIX):] == dir_name and file_ext.lower() == ".py":
					can_import = True
					with open(file, "r") as f:
						first_line = f.readline()
						can_import = interpret_requirements(first_line)
					if can_import:
						modules.append(file)
					break
	return modules
	
def plugin_from_class(module_dir, plugin_class, main_config):
	assert os.path.isdir(module_dir)
	assert isinstance(plugin_class, Plugin.__class__)
	assert isinstance(main_config, Root_Configuration)
	return plugin_class(main_config, configuration_from_file(os.path.join(module_dir, PLUGIN_CONFIG_FILE_NAME), os.path.join(module_dir, PLUGIN_SCHEMA_FILE_NAME), True))
	

# Abstract base class https://pluginlib.readthedocs.io/en/stable/api.html
@pluginlib.Parent(PLUGIN_ROOT)
class Plugin(object):
	__logger = logging.getLogger(__name__)
	
	_full_name = None
	_description = None
	_enabled = True		# the static "out of the box" status of whether of not the plugin is enabled
	_auto_run = False
	
	def __init__(self, main_config, plugin_config):
		self._main_config = main_config
		assert isinstance(main_config, Root_Configuration)
		self.plugin_config = plugin_config
		assert isinstance(plugin_config, Root_Configuration)
		self.active = self.enabled	# the dynamic status of if the plugin is enabled
		self._worker = None
		self._gui = None
		self._gui_class = GUI_MainWindow
	
	def get_property_from_configuration(self, property, type_name = None):
		if not self.plugin_config or not self.plugin_config.struct:
			return None
		if property in self.plugin_config:						# try get from config first
			return self.plugin_config[property]
		if property in self.plugin_config.struct.attributes:	# then try get from config schema attributes
			prop = self.plugin_config.struct.attributes[property]
			if type_name:
				prop = get_structural_type(type_name).func_cast(prop)
			return prop
		return None
	
	@property
	def alias(self):
		return self.name if isinstance(self.name, str) else self.__class__.__name__
	
	@property
	def full_name(self):
		return (self._full_name if isinstance(self._full_name, str) else self.alias) if not self.plugin_config.struct and not self.plugin_config.struct.label else self.plugin_config.struct.label
		
	@property
	def description(self):
		return self._description if not self.get_property_from_configuration("description") else self.get_property_from_configuration("description", "string")
		
	@property
	def enabled(self):
		return self._enabled == True if not self.get_property_from_configuration("enabled") else self.get_property_from_configuration("enabled", "bool")
	
	@property
	def auto_run(self):
		return self._auto_run == True if not self.get_property_from_configuration("auto_run") else self.get_property_from_configuration("auto_run", "bool")
		
	
	def __getitem__(self, key):
		if not self.plugin_config or not key in self.plugin_config:
			return None
		return self.plugin_config[key]
	
	def get_ansi(self):
		return ANSI_PLUGIN_ENABLED if self.active else ANSI_PLUGIN_DISABLED
	
	def _log(self, lvl, msg = None, *args, **kwargs):
		if isinstance(lvl, str) and lvl.upper() == "EXCEPTION":
			msg = msg if msg != None else ANSI_PLUGIN_EXCEPTION + "Exception raised" + ANSI_ENDC
			self.__logger.exception("[" + self.get_ansi() + self.full_name + ANSI_ENDC + "]: " + msg, *args, **kwargs)
		else:
			self.__logger.log(lvl, "[" + self.get_ansi() + self.full_name + ANSI_ENDC + "]: " + msg, *args, **kwargs)
	
	def _deactivate(self, msg = None, *args, **kwargs):
		self.active = False
		if msg:
			self.__logger.error("[DEACTIVATED " + ANSI_PLUGIN_DISABLED + self.full_name + ANSI_ENDC + "]: " + msg, *args, **kwargs)
		if self._worker and self._worker.isRunning():
			self._worker.quit()
	
	# Starts the plugin and shows the GUI
	def start(self):
		if not self.active:
			self._log(logging.WARNING, "Plugin is deactivated and cannot start. Check the enabled property in the configuration.")
			return None
		self._worker = Plugin_Qt_Worker(None, lambda: self.invoke("on_loaded"))
		if self.plugin_config and self._gui_class and (issubclass(self._gui_class, GUI_MainWindow) or issubclass(self._gui_class, GUI_DialogWindow)):
			self._gui = self._gui_class(self.plugin_config)
			self._gui.setWindowTitle(self.full_name)
			self._gui.show()
		else:
			self._log(logging.WARNING, "Could not start gui. No configuration or the gui class cannot accept configuration")
		self._worker.start()
		
	
	# Invokes a plugin's method with error handling.
	def invoke(self, method_name, *args, **kwargs):
		if not hasattr(self, method_name):
			self._log(logging.WARNING, "Plugin does not implement method '%s'", method_name)
			return None
		if not self.active:
			if PLUGIN_LOG_INACTIVE_PLUGINS:
				self._log(logging.DEBUG, "NOT invoking %s because the plugin is not active", method_name)
			return None
		try:
			return getattr(self,  method_name)(*args, **kwargs)
		except Exception:
			self._log("EXCEPTION")
		return None
	
	# Called unconditionally when starting the plugin, after get_gui
	# This method is called inside a QThread and is asynchronous
	@pluginlib.abstractmethod
	def on_loaded(self):
		pass

#####


class Plugin_Qt_Worker(QThread):
	invoke_proxy = None

	def __init__(self, parent = None, work = None):
		super(Plugin_Qt_Worker, self).__init__(parent)
		self.work = work
	
	def run(self):
		if self.work:
			self.work()