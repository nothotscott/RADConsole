#!/usr/bin/env python
# cd /home/pi/Desktop/Python/RADConsole && python2 -B src/main.py -v 10

# Copyright 2020 Scott Maday

import sys, os, logging
from optparse import OptionParser

import pluginlib
from PyQt5 import QtWidgets

from configuration import *
from plugin import *
from gui import *
from configuration_gui import *
from main_gui import GUI_Main


DEFAULT_VERBOSITY 	= logging.WARNING
DEFAULT_SCHEMA_FILE	= "schema.xml"
DEFAULT_CONFIG_FILE	= "config.json"

logger = logging.getLogger()
main_config = None
plugins = []
qt_app = None

def cli_options():
	global main_config
	parser = OptionParser()
	parser.add_option("-v", "--verbose", type="int", default=DEFAULT_VERBOSITY, help="Verbosity of logging. The number is based off of python's logging library")
	parser.add_option("-c", "--config", type="string", default=DEFAULT_CONFIG_FILE, help="Location of configuration json file")
	parser.add_option("-s", "--schema", type="string", default=DEFAULT_SCHEMA_FILE, help="Location of schema xml file")
	options, args = parser.parse_args()
	if len(args) != 0:
		parser.print_help()
		sys.exit(1)
	logging.basicConfig(level=options.verbose)
	
	if os.path.isfile(options.config):
		logger.info("Main configuration file set to: %s", options.config)
	main_config = configuration_from_file(options.config, options.schema, True)
	
def run_gui():
	global qt_app, main_config
	qt_app = QtWidgets.QApplication(sys.argv[:1])
	main = GUI_Main(main_config)
	# main.show()
	for plugin_obj in plugins:
		if plugin_obj.auto_run:
			plugin_obj.start()
	# c = GUI_Configuration_Advanced(None)
	# c.show()
	sys.exit(qt_app.exec_())

def load_plugins():
	global plugins, main_config
	plugin_modules = get_plugin_modules()
	for module in plugin_modules:
		module_name = os.path.splitext(os.path.basename(module))[0]
		module_dir = os.path.dirname(module)
		sys.path.append(module_dir)
		# Each module gets its own loader to isolate themselves if an import fails
		loader = pluginlib.PluginLoader(modules=[module_name])
		try:
			plugin_list = getattr(loader.plugins, PLUGIN_ROOT)
			plugin_class = getattr(plugin_list, next(iter(plugin_list))) # better than loader.get_plugin(PLUGIN_ROOT, ...) ??
			plugin_obj = plugin_from_class(module_dir, plugin_class, main_config)
			plugins.append(plugin_obj)
		except:
			logger.exception("Exception raised while loading plugin module: %s", module)

def invoke_plugins(method_name, *args, **kwargs):
	global plugins
	for plugin_obj in plugins:
		plugin_obj.invoke(method_name, *args, **kwargs)


def main():
	os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # root structure independent of where i'm being called from
	cli_options()
	load_plugins()
	run_gui()

if __name__ == "__main__":
	main()