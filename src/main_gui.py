# Copyright 2020 Scott Maday

import os

from gui import *


class GUI_Main(GUI_MainWindow):
	def __init__(self, config, *args, **kwargs):
		self._file_name = os.path.join(GUI_DIRECTORY_NAME, "main.ui")
		super(GUI_Main, self).__init__(config, *args, **kwargs)