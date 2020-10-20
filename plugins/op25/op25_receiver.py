# Copyright 2020 Scott Maday
# Copyright 2018-2020 Graham J. Norbury
# Copyright 2008-2011 Steve Glass
# Copyright 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020 Max H. Parke KA1RBI
# Copyright 2003, 2004, 2005, 2006 Free Software Foundation, Inc.
#         (from radiorausch)

import os, sys, logging, threading, json, time
from math import pi

from gnuradio import gr

from plugin_op25 import *

import op25							# Python dist-packages
import op25_repeater				# Python dist-packages
import trunking						# apps
import p25_demodulator				# apps
import p25_decoder					# apps
import lfsr							# apps/tdma
from sockaudio import audio_thread	# apps

OP25_OSMOSDR_SOURCES		= ["rtl", "airspy", "hackrf", "uhd"]
OP25_DEMOD_TYPES			= ["cqpsk", "fsk4"]
OP25_SPEEDS					= [4800, 6000]
OP25_SYMBOL_RATE			= 4800
OP25_SYMBOL_DEVIATION		= 600.0
OP25_BASIC_RATE				= 24000
OP25_DEFAULT_SPEED			= 4800
OP25_DEFAULT_EXCESS_BW		= 0.2
OP25_DEFAULT_OFFSET			= 0.0
OP25_DEFAULT_FINE_TUNE		= 0.0
OP25_DEFAULT_GAIN_MU		= 0.025
OP25_DEFAULT_COSTAS_ALPHA	= 0.04
OP25_DEFAULT_AUDIO_GAIN		= 1.0
OP25_DEFAULT_PHASE2_ENABLED	= False
OP25_DEFAULT_AUDIO_OUTPUT	= "default"

GR_IO_QUEUE_LIMIT	= 10
GR_RX_QUEUE_LIMIT	= 100

AUDIO_HOST	= "127.0.0.1"
AUDIO_PORT	= 23456


# The P25 receiver based on rx.py
# 
# Many rx features such as source & save methods have been removed to reduce complexity. 
# The intent of this is to be used as a plugin and therefore
# features such as plot sinks and file sources/sinks have been removed
class gr_op25_rx_block(gr.top_block):
	xor_cache = {}
	
	
	def __init__(self, plugin_config, log):
		gr.top_block.__init__(self)
		self.plugin_config = plugin_config
		self.log_proxy = log
		
		self.input_queue = gr.msg_queue(GR_IO_QUEUE_LIMIT)
		self.output_queue = gr.msg_queue(GR_IO_QUEUE_LIMIT)
		self.meta_queue = gr.msg_queue(GR_IO_QUEUE_LIMIT)
		self.rx_queue = None
		
		self.demod = None
		self.trunk_rx = None
		self.lo_freq = 0
		self.tdma_state = False
		self.channels = []

		self.error_band = 0
		self.tuning_error = 0
		self.freq_correction = 0
		self.last_set_freq = 0
		self.last_set_freq_at = time.time()
		self.last_set_ppm = 0
		self.last_change_freq = 0
		self.last_change_freq_at = time.time()
		self.last_freq_params = {"freq" : 0.0, "tgid" : None, "tag" : "", "tdma" : None}

		self.sps = 0.0
		self.channel_rate = 0
		self.current_speed = OP25_SPEEDS[0]
		
		self.offset = self["offset"] if "offset" in self.plugin_config else OP25_DEFAULT_OFFSET
		self.fine_tune = self["fine_tune"] if "fine_tune" in self.plugin_config else OP25_DEFAULT_FINE_TUNE
		self.phase2_tdma = bool(self["phase2_tdma"]) if "phase2_tdma" in self.plugin_config else OP25_DEFAULT_PHASE2_ENABLED
		self.demod_type = self["demod_type"].lower() if "demod_type" in self.plugin_config and self["demod_type"].lower() in OP25_DEMOD_TYPES else OP25_DEMOD_TYPES[0]
		self.nocrypt = bool(self["nocrypt"]) if "nocrypt" in self.plugin_config else True
		self.audio_output = self["audio_output"] if "audio_output" in self.plugin_config else OP25_DEFAULT_AUDIO_OUTPUT
		self.audio_gain = self["audio_gain"] if "audio_gain" in self.plugin_config else OP25_DEFAULT_AUDIO_GAIN
		
		if "channels" in self.plugin_config:
			self.channels = self["channels"].as_obj()
			for chan in self.channels:
				print(chan)
				if not "nac" in chan:
					chan["nac"] = "0"
				if not "sysname" in chan:
					chan["sysname"] = "P25 SYSTEM"
		
		# SDR configuration
		# This version only configures as an sdr source method to reduce complexity
		osmosdr_args = str(self["osmosdr_args"])
		print(osmosdr_args)
		# Should be in a try-catch block, but we'll let the plugin handle the exception if there is one
		import osmosdr
		self.src = osmosdr.source(osmosdr_args)
		
		for gain_name in self.src.get_gain_names():
			gain_range = self.src.get_gain_range(gain_name)
			self.log_proxy(logging.DEBUG, "Device supports gain: %s (%d-%d,%d)", gain_name, gain_range.start(), gain_range.stop(), gain_range.step())
			for key,value in self.plugin_config["gains"].items():
				if key.lower() == gain_name.lower():
					gain = int(value)
					self.src.set_gain(gain, gain_name)
					self.log_proxy(logging.DEBUG, "Set %s gain to %d", gain_name, gain)
					break
		
		sample_rates = self.src.get_sample_rates()
		if len(sample_rates) > 0:
			self.log_proxy(logging.INFO, "Device supports sample rate range: %d-%d,%d", sample_rates.start(), sample_rates.stop(), sample_rates.step())
		
		for antenna in self.src.get_antennas():
			self.log_proxy(logging.INFO, "Device has antenna: '%s'", antenna)
		
		freq_corr = self["freq_corr"]
		if freq_corr:
			self.src.set_freq_corr(freq_corr)
			self.log_proxy(logging.DEBUG, "Set frequency correction to: %d ppm", freq_corr)
	
		if "gain_mode" in self.plugin_config:
			agc = self["gain_mode"] == True
			self.src.set_gain_mode(agc, 0)
			self.log_proxy(logging.DEBUG, "Automatic gain control is set to: %s", self.src.get_gain_mode())
			
		self.channel_rate = int(self["sample_rate"])
		self.set_sps(OP25_DEFAULT_SPEED)
		
		# Set rx
		self.set_rx_from_osmosdr()
		if "frequency" in self.plugin_config:
			self.last_freq_params["freq"] = self["frequency"]
			self.set_freq(self["frequency"])
		
		self.trunk_rx.post_init()
		
		# self.terminal = op25_terminal(self.input_queue, self.output_queue, "curses")
		self.audio = audio_thread(AUDIO_HOST, AUDIO_PORT, self.audio_output, False, self.audio_gain)
	
	def __getitem__(self, key):
		return self.plugin_config[key]
		
	# No clue what sps stands for. something per symbol??
	def set_sps(self, rate):
		self.sps = OP25_BASIC_RATE / rate
	
	# Setup to rx from sdr source
	def set_rx_from_osmosdr(self):
		if "antenna" in self.plugin_config and self["antenna"]:
			self.src.set_antenna(unicode(self["antenna"])) # swig error?
			self.log_proxy(logging.DEBUG, "Antenna is set to: %s", self.src.get_antenna())
		
		capture_rate = self.src.set_sample_rate(self["sample_rate"])
		self.src.set_bandwidth(capture_rate)
		self.log_proxy(logging.DEBUG, "Capture rate: %d", capture_rate)		
		# Finally
		self.__build_graph(self.src, capture_rate)
		
	# Setup common flow graph elements	
	def __build_graph(self, source, capture_rate):
		self.rx_queue = gr.msg_queue(GR_RX_QUEUE_LIMIT)
		
		# Set local oscillator frequency
		self.lo_freq = self.offset
		self.log_proxy(logging.DEBUG, "Local oscillator frequency: %d hz", self.lo_freq)
		self.demod = p25_demodulator.p25_demod_cb(	input_rate = capture_rate, 
													demod_type = self.demod_type,
													relative_freq = self.lo_freq,
													offset = self.offset,
													if_rate = self.sps * OP25_DEFAULT_SPEED,
													gain_mu = self["gain_mu"] if "gain_mu" in self.plugin_config else OP25_DEFAULT_GAIN_MU,
													costas_alpha = self["costas_alpha"] if "costas_alpha" in self.plugin_config else OP25_DEFAULT_COSTAS_ALPHA,
													excess_bw = self["excess_bw"] if "excess_bw" in self.plugin_config else OP25_DEFAULT_EXCESS_BW,
													symbol_rate = OP25_SYMBOL_RATE
												 )
		self.decoder = p25_decoder.p25_decoder_sink_b(	dest = "audio", 
														do_imbe = bool(self["vocoder"]) if "vocoder" in self.plugin_config else True, 
														num_ambe = 1 if self.phase2_tdma else 0, 
														wireshark_host = AUDIO_HOST, 
														udp_port = AUDIO_PORT, 
														do_msgq = True, 
														msgq = self.rx_queue, 
														audio_output = self.audio_output,
														debug = to_op25_verbosity(), 
														nocrypt = self.nocrypt
													 )
		# Connect the flowgraph to p25 dsp
		self.connect(source, self.demod, self.decoder)
		
		logfile_workers = []
		#TODO logfile workers?
		
		self.trunk_rx = trunking.rx_ctl(frequency_set = self.change_freq, 
										debug = to_op25_verbosity(), 
										# conf_file = "/home/pi/Programs/op25/op25/gr-op25_repeater/apps/trunk.tsv", 
										chans = self.channels,
										logfile_workers = logfile_workers, 
										crypt_behavior  = self.nocrypt
										)
		self.du_watcher = du_queue_watcher(self.rx_queue, self.trunk_rx.process_qmsg)
	
	
	### From rx.py ###
	
	def change_freq(self, params):
		last_freq = self.last_freq_params["freq"]
		self.last_freq_params = params
		freq = params["freq"]
		offset = params["offset"]
		center_freq = params["center_frequency"]
		self.last_change_freq = freq
		self.last_change_freq_at = time.time()
		
		# Ignore requests to tune to same freq
		if freq != last_freq:
			self.log_proxy(logging.DEBUG, "Changing frequency to: %d", freq)
			if params["center_frequency"]:
				relative_freq = center_freq - freq
				if abs(relative_freq + self.offset) > self.channel_rate / 2:
					self.lo_freq = self.offset							# relative tune not possible
					self.demod.set_relative_frequency(self.lo_freq)		# reset demod relative freq
					self.set_freq(freq + offset)						# direct tune instead
				else:	
					self.lo_freq = self.offset + relative_freq
					if self.demod.set_relative_frequency(self.lo_freq):	# relative tune successful
						self.demod.reset()								# reset gardner-costas loop
						self.set_freq(center_freq + offset)
					else:
						self.lo_freq = self.offset						# relative tune unsuccessful
						self.demod.set_relative_frequency(self.lo_freq)	# reset demod relative freq
						self.set_freq(freq + offset)					# direct tune instead
			else:
				self.set_freq(freq + offset)
			self.decoder.reset_timer()
		self.configure_tdma(params)
		self.freq_update()
	
	# Set the center frequency we're interested in.
	def set_freq(self, target_freq):
		# Tuning is a two step process.  First we ask the front-end to tune as close to the desired frequency as it can. 
		# Then we use the result of that operation and our target_frequency to determine the value for the digital down converter.
		if not self.src:
			return False
		self.target_freq = target_freq
		tune_freq = target_freq + self.offset + self.fine_tune
		r = self.src.set_center_freq(tune_freq)
		self.demod.reset()	# reset gardner-costas loop
		return r != 0
		
	def freq_update(self):
		params = self.last_freq_params
		params["json_type"] = "change_freq"
		params["fine_tune"] = self.fine_tune
		# params["stream_url"] = self.stream_url
		js = json.dumps(params)
		msg = gr.message().make_from_string(js, -4, 0, 0)
		self.input_queue.insert_tail(msg)
	
	def adj_tune(self, tune_incr):
		if self.target_freq == 0.0:
			return False
		self.fine_tune += tune_incr;
		self.set_freq(self.target_freq)
		return True
		
	def configure_tdma(self, params):
		if params["tdma"] is not None and not self.phase2_tdma:
			self.log_proxy(logging.ERROR, "TDMA request for frequency %d failed - phase2_tdma option not enabled", params["freq"])
			return
		set_tdma = False
		if params["tdma"] is not None:
			set_tdma = True
			self.decoder.set_slotid(params["tdma"])
		if set_tdma == self.tdma_state:
			return	# already in desired state
		self.tdma_state = set_tdma
		if set_tdma:
			hash = "%x%x%x" % (params["nac"], params["sysid"], params["wacn"])
			if hash not in self.xor_cache:
				self.xor_cache[hash] = lfsr.p25p2_lfsr(params["nac"], params["sysid"], params["wacn"]).xor_chars
			self.decoder.set_xormask(self.xor_cache[hash], hash)
			rate = 6000
		else:
			rate = 4800

		self.set_sps(rate)
		self.demod.set_omega(rate)
	
	def process_qmsg(self, msg):
		# return true = end top block
		RX_COMMANDS = "skip lockout hold whitelist reload"
		s = msg.to_string()
		if s == "quit":
			return True
		elif s == "update":
			self.freq_update()
			if self.trunk_rx is None:
				return False	## possible race cond - just ignore
			js = self.trunk_rx.to_json() # extract data from trunking module
			msg = gr.message().make_from_string(js, -4, 0, 0)
			self.input_queue.insert_tail(msg)
		elif s == "set_freq":
			freq = msg.arg1()
			self.last_freq_params["freq"] = freq
			self.set_freq(freq)
		elif s == "adj_tune":
			freq = msg.arg1()
			self.adj_tune(freq)
		elif s == "dump_tgids":
			self.trunk_rx.dump_tgids()
		elif s == "add_default_config":
			nac = msg.arg1()
			self.trunk_rx.add_default_config(int(nac))
		elif s in RX_COMMANDS:
			self.rx_q.insert_tail(msg)
		return False
###