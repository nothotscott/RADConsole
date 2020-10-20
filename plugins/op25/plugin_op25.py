# PLATFORM(Linux)
 
# Copyright 2020 Scott Maday
# Copyright 2018-2020 Graham J. Norbury
# Copyright 2008-2011 Steve Glass
# Copyright 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020 Max H. Parke KA1RBI
# Copyright 2003, 2004, 2005, 2006 Free Software Foundation, Inc.
#         (from radiorausch)

# This plugin is a simplified version of rx.py included in op25

import os, sys, logging, threading, json, time

import pluginlib

from plugin import Plugin

PLUGIN_UPDATE_INTERVAL	= 0.5


def to_op25_verbosity():
	return 6 - logging.getLogger().getEffectiveLevel() // 10

def num_to_freq(num):
	s = str(num)
	if len(s) < 9:
		s = s + ("0" * (9 - len(s)))
	return "%s.%s.%s" % (s[0:3], s[3:6], s[6:9])

def tgid_list_tostring(tgids):
	tgids = list(filter(None, tgids))
	tgids = map(str, tgids)
	return ", ".join(tgids)


from plugin_op25_gui import GUI_Plugin_OP25

	
class Plugin_OP25(Plugin):
	_alias_ = "op25"
	_version_ = "0.1.0.0"
	
	def __init__(self, *args):
		super(Plugin_OP25, self).__init__(*args)
		# self._gui_class = GUI_Plugin_OP25
		self.queue_watcher = None
		self.top_block = None
		self.keep_running = False
	
	def on_loaded(self):
		apps_dir = self["gr_op25_repeater_apps_dir"]
		if not apps_dir or not os.path.isdir(os.path.expanduser(apps_dir)):
			self._deactivate("'%s' was not found or not a directory, but is needed for op25/gr-op25_repeater/apps modules", apps_dir)
			return None
		apps_dir = os.path.expanduser(apps_dir)
		apps_subdirs = next(os.walk(apps_dir))[1]
		for apps_subdir_name in apps_subdirs:
			apps_subdir = os.path.join(apps_dir, apps_subdir_name)
			sys.path.append(apps_subdir)
		sys.path.append(apps_dir)
		from op25_multi_receiver import op25_multi_rx_block
		global op25_multi_rx_block
		
		self.top_block = op25_multi_rx_block(self.log, self.plugin_config)
		
		"""try:
			self.top_block = op25_multi_rx_block(self.plugin_config, self.log)
			self._gui.set_queues(self.top_block.input_queue, self.top_block.output_queue)
			self._gui.start()
			self.top_block.start()
		except:
			self._deactivate()
			self._log("EXCEPTION", "gr_op25_rx_block raised an exception")
			return None"""
		
		"""try:
			self.top_block = gr_op25_rx_block(self.plugin_config, self.log)
			self._gui.set_queues(self.top_block.input_queue, self.top_block.output_queue)
			self._gui.start()
			self.top_block.start()
		except:
			self._deactivate()
			self._log("EXCEPTION", "gr_op25_rx_block raised an exception")
			return None
		
		self.keep_running = True
		self.queue_watcher = du_queue_watcher(self.top_block.output_queue, self.process_qmsg)
		self._log(logging.DEBUG, "OP25 plugin initalized")
		
		while self.keep_running:
			time.sleep(PLUGIN_UPDATE_INTERVAL)
		if hasattr(self.top_block, "terminal") and self.top_block.terminal:
			self.top_block.terminal.end_terminal()
		if hasattr(self.top_block, "audio") and self.top_block.audio:
			self.top_block.audio.stop()"""
		
	def log(self, lvl, msg = None, *args, **kwargs):
		self._log(lvl, msg, *args, **kwargs)
	
	def process_qmsg(self, msg):
		if self.top_block.process_qmsg(msg):
			self.keep_running = False

# Data unit receive queue
class DataUnit_Dispatcher(threading.Thread):

	def __init__(self, msgq,  callback, **kwds):
		threading.Thread.__init__ (self, **kwds)
		self.setDaemon(1)
		self.msgq = msgq
		self.callback = callback
		self.keep_running = True
		self.start()

	def run(self):
		while(self.keep_running):
			msg = self.msgq.delete_head()
			# sys.stderr.write(msg.to_string())
			self.callback(msg)

