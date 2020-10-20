# Copyright 2020 Scott Maday
# Copyright 2020 Graham J. Norbury - gnorbury@bondcar.com
# Copyright 2011, 2012, 2013, 2014, 2015, 2016, 2017 Max H. Parke KA1RBI

# Specialized receiver built for working with plugin_op25

import os, sys, logging, threading, json, time
from math import pi

from gnuradio import gr

from plugin_op25 import *
from configuration import *

import osmosdr
import op25							# Python dist-packages
import op25_repeater				# Python dist-packages
import trunking						# apps
import p25_demodulator				# apps
import p25_decoder					# apps
import lfsr							# apps/tdma
from sockaudio import audio_thread	# apps

GR_IO_QUEUE_LIMIT	= 10
GR_RX_QUEUE_LIMIT	= 100

AUDIO_HOST	= "127.0.0.1"
AUDIO_PORT	= 23456


class Device_Configuration(Configuration):
	def __init__(self, log, *args):
		self.log_proxy = log
		super(Device_Configuration, self).__init__(*args)
		if not self.struct:
			self._log(logging.WARNING, "No structure for device configuration; cannot validate input")
			return None
		
		self.assigned = False
		
		try:
			self.src = osmosdr.source(self["osmosdr"])
		except:
			self._log(logging.ERROR, "Could not load device")
			return None
		# Sample rate
		sample_rates = self.struct["sample_rate"].get_options()
		if not self["sample_rate"] in sample_rates:
			self._log(logging.WARNING, "Sample rate is not in the list of recommended rates. Use one of the following: %s", str(sample_rates))
		# Gain
		for gain_name in self.src.get_gain_names():
			gain_range = self.src.get_gain_range(gain_name)
			self._log(logging.DEBUG, "Device supports gain: %s (%d-%d,%d)", gain_name, gain_range.start(), gain_range.stop(), gain_range.step())
			for key,value in self["gains"].items():
				if key.lower() == gain_name.lower():
					gain = int(value)
					self.src.set_gain(gain, gain_name)
					self._log(logging.DEBUG, "Set %s gain to %d", gain_name, gain)
					break
		# Frequency correction
		self.src.set_freq_corr(self["ppm"])
		self.log_proxy(logging.DEBUG, "Set frequency correction to: %d ppm", self.src.get_freq_corr())
		# Frequency
		adj_freq = self.get_adjusted_freq()
		if adj_freq > 0:
			self.src.set_center_freq(adj_freq)
	
	def _log(self, lvl, msg = None, *args, **kwargs):
		if msg:
			msg = ("[Device %s(%s)]: " % (str(self), self["osmosdr"])) + msg
		self.log_proxy(lvl, msg, *args, **kwargs)
	
	def get_adjusted_freq(self):
		freq = self["frequency"]
		ppm = self["ppm"]
		offset = self["offset"] if self["offset"] else 0
		if not freq:
			return 0
		return freq + offset + (int(round(ppm)) - ppm) * (frequency/1e6)
###


class Channel_Configuration(Configuration):
	def __init__(self, log, param, device, msgq_id, rx_q):
		self.log_proxy = log
		self.device = device
		self.msgq_id = msgq_id
		self.rx_q = rx_q
		super(Channel_Configuration, self).__init__(param)
		if not self.struct:
			self._log(logging.WARNING, "No structure for channel configuration; cannot validate input")
			return None
		
		
	
	def _log(self, lvl, msg = None, *args, **kwargs):
		if msg:
			msg = ("[Channel %s]: " % str(self)) + msg
		self.log_proxy(lvl, msg, *args, **kwargs)
###


# The P25 receiver based on multi_rx.py and adapted for plugin use
# 
# Many rx features such as source & save methods have been removed to reduce complexity. 
# The intent of this is to be used as a plugin and therefore
# features such as plot sinks and file sources/sinks have been removed
class op25_multi_rx_block(gr.top_block):
	def __init__(self, log, config):
		gr.top_block.__init__(self)
		self.config = config
		self.log_proxy = log
		
		self.devices = []
		self.channels = []
		
		self.in_q = gr.msg_queue(GR_IO_QUEUE_LIMIT)
		self.out_q = gr.msg_queue(GR_IO_QUEUE_LIMIT)
		self.rx_q = gr.msg_queue(GR_RX_QUEUE_LIMIT)
		
		self._log(logging.DEBUG, "Enabling trunking")
		"""self.trunk_rx = trunking.rx_ctl(frequency_set = self.change_freq,
										debug = to_op25_verbosity(), 
										slot_set = self.set_slot,
										nbfm_ctrl = self.nbfm_control,
										chans = self.to_op25_chans
										)
		self.du_watcher = DataUnit_Dispatcher(self.rx_q, self.trunk_rx.process_qmsg)"""
		self.__init_devices()
		self.__init_channels()
		# self.trunk_rx.post_init()
		# terminal
	
	def _log(self, lvl, msg = None, *args, **kwargs):
		self.log_proxy(lvl, msg, *args, **kwargs)
	
	def __init_devices(self):
		for i, config in self.config["devices"].items():
			self._log(logging.INFO, "Found device in configuration: %s", str(config))
			device = Device_Configuration(self._log, config)
			if device:
				self.devices.append(device)
				break # remove this!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
	
	def __init_channels(self):
		for i, config in self.config["channels"].items():
			device = None
			for dev in self.devices:
				if not dev.assigned and dev["dev_pref"] == config["name"]:
					device = dev
					device.assigned = True
					break
			if not device:
				for dev in self.devices:
					if not dev.assigned:
						device = dev
						device.assigned = True
						break
			if not device:
				self._log(logging.WARNING, "Could not assign any device to channel")
				return None
			self._log(logging.INFO, "Assigned device '%s' to channel '%s'", device, str(config))
	
	def to_op25_chans(self):
		pass
###