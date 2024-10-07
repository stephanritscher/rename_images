from __future__ import with_statement

import fcntl
import logging
import os
import re
import signal
import string
import subprocess
import time

from gi.repository import GObject, Gio, Gtk
from .Annotations import trace

logger = logging.getLogger('Command')

# Class executing a shell command redirecting input and output
class Command(GObject.GObject):
	@trace
	def __init__(self, output_buffer = None):
		self._output_buffer = output_buffer

	@trace
	def output(self, text):
		self._output_buffer.insert(self._output_buffer.get_end_iter(), text)

	@trace
	def execute(self, *args):
		self.output('\n# %s\n' % " ".join(args))
		# Create process
		args = ('/usr/bin/nice', '-n', '10', '/usr/bin/ionice', '-c', '3', '/usr/bin/setsid', '--wait') + args
		self._process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		# Make pipe nonblocking
		flags = fcntl.fcntl(self._process.stdout.fileno(), fcntl.F_GETFL)
		fcntl.fcntl(self._process.stdout.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)
		self._paused = None
		# Wait for process termination
		while self._process.poll() is None:
			# Look for pipe output and display it
			try:
				self.output(self._process.stdout.read())
			except Exception: pass
			pause = yield 100
			# Pause/resume process
			if pause != self._paused:
				logger.info('Process is %s, but should be %s. Singalling process ...', 'paused' if self._paused else 'running', 'paused' if pause else 'running')
				os.killpg(self._process.pid, signal.SIGSTOP if pause else signal.SIGCONT)
				self.output('\n +++ Process %s +++\n' % ('paused' if pause else 'resumed'))
				self._paused = pause
		try:
			self.output(self._process.stdout.read())
		except Exception: pass
		if self._process.returncode != 0: raise Exception('command terminated with return code %d' % self._process.returncode)

