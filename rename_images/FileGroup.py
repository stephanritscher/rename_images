import logging

from gi.repository import GObject
from .Annotations import trace

logger = logging.getLogger('FileGroup')

# Class containing a group of image/video files (i.e. files with same group attribute)
class FileGroup(GObject.GObject):
	def __init__(self, file):
		GObject.GObject.__init__(self)
		self._files = []
		self._base = None
		self._number = None
		self._group = file.get_group()
		self.add_file(file)

	# Add new file to group
	def add_file(self, file):
		assert self._group == file.get_group()
		self._files.append(file)
		file.set_group(self)

	# Assign the basename and numbers to the files in the group
	@trace
	def assign_base_number(self, base, number):
		self._base = base if base != '' else self._files[0].get_actual_base()
		self._number = number

	# Get timestamp for file group based on DATEPRIO
	def get_creation_time(self):
		times = [(file.get_property(File.DATEPRIO), file.get_creation_time()) for file in self._files]
		times = filter(lambda x: x[1] is not None, times)
		times = sorted(times, key=lambda x: x[0])
		return min([y[1] for y in filter(lambda x: x[0] == times[0][0], times)])

from . import File
