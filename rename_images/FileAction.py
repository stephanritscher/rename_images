import logging

from gi.repository import GObject, Gio
from .Annotations import trace

logger = logging.getLogger('FileAction')

# TODO: Split file by class into subpackage
class Action(GObject.GObject):
	# Display nicely on print
	def __str__(self):
		return self.__name__

	# Return display text for file action
	@classmethod
	def get_text(cls, file = None):
		pass

	# Return whether action shall be postponed to postprocessing
	@classmethod
	def is_postprocessing(cls):
		pass

	# Execute action for a file in a batch
	@classmethod
	@trace
	def execute(cls, file, batch):
		yield

class Convert(Action):
	@classmethod
	def get_text(self, file = None):
		return "Convert file"

	# Return whether action shall be postponed to postprocessing
	@classmethod
	def is_postprocessing(cls):
		return True

	# Convert file (RAW -> result)
	@classmethod
	@trace
	def execute(cls, file, batch):
		ext = file.get_extension().lower()
		command = Command.Command(batch._progresswindow.get_output_buffer())
		if ext == ".mov":
			generator = command.execute('/usr/bin/recodevideos', file.get_path())
		elif ext == ".cr2":
			generator = command.execute('/usr/bin/convert-raw', file.get_path())
		else:
			raise Exception('Converting %s not implemented yet' % s)
		# Better use (supported from python 3.3): yield from ...
		message = None
		while True:
			try:
				item = generator.send(message)
				message = yield item
			except StopIteration:
				break

class Trash(Action):
	@classmethod
	def get_text(self, file = None):
		return "Trash file"

	# Return whether action shall be postponed to postprocessing
	@classmethod
	def is_postprocessing(cls):
		return False

	# Trash file
	@classmethod
	@trace
	def execute(cls, file, batch):
		file.trash(True)
		yield

class Rotate(Action):
	@classmethod
	def get_text(self, file = None):
		return "Rotate file"

	# Return whether action shall be postponed to postprocessing
	@classmethod
	def is_postprocessing(cls):
		return True

	# Include file into batch
	@classmethod
	@trace
	def execute(cls, file, batch):
		command = Command.Command(batch._progresswindow.get_output_buffer())
		generator = command.execute('/usr/bin/jhead', '-autorot', file.get_path())
		# TODO: Better use (supported from python 3.3): yield from ...
		message = None
		while True:
			try:
				item = generator.send(message)
				message = yield item
				if message: logger.info('Received %s, passing to subgenerator', message)
			except StopIteration:
				break

class ConvertGroup(Action):
	@classmethod
	def get_text(self, file = None):
		return "Convert file group"

	# Return whether action shall be postponed to postprocessing
	@classmethod
	def is_postprocessing(cls):
		return True

	# Convert file group (panorama, HDR)
	@classmethod
	@trace
	def execute(cls, file, batch):
		group = file.get_property(File.GROUPCONVERT)
		tags = {'Panorama':0, 'HDR':0}
		paths = []
		for f in group:
			yield
			paths.append(f.get_path())
			for tag in tags:
				if tag in f.get_tags(): tags[tag] += 1
		command = Command.Command(batch._progresswindow.get_output_buffer())
		if tags['Panorama'] == len(group) and tags['HDR'] == 0:
			generator = command.execute('/usr/bin/postprocess-photo', '-p', '-o', file.get_path(), *paths)
		elif tags['HDR'] == len(group) and tags['Panorama'] == 0:
			generator = command.execute('/usr/bin/postprocess-photo', '-h', '-o', file.get_path(), *paths)
		else: raise Exception('File group %s group has inconsistent tags' % file.get_group())
		# Better use (supported from python 3.3): yield from ...
		message = None
		while True:
			try:
				item = generator.send(message)
				message = yield item
				if message: logger.info('Received %s, passing to subgenerator', message)
			except StopIteration:
				break

class Ignore(Action):
	@classmethod
	def get_text(self, file = None):
		return "Ignore file"

	# Return whether action shall be postponed to postprocessing
	@classmethod
	def is_postprocessing(cls):
		return False

	# Do nothing
	@classmethod
	@trace
	def execute(cls, file, batch):
		yield

class Include(Action):
	@classmethod
	def get_text(self, file = None):
		return "Include file"

	# Return whether action shall be postponed to postprocessing
	@classmethod
	def is_postprocessing(cls):
		return False

	# Include file into batch
	@classmethod
	@trace
	def execute(cls, file, batch):
		batch.add_file(file)
		yield

class SetCreationTime(Action):
	@classmethod
	def get_text(self, file = None):
		creation_times = file.get_property(File.CREATIONTIME) if file else {}
		details = []
		for key, date in creation_times.items():
			key = key.split(".")[-1]
			details.append("%s = %s" % (key, date))
		details = ", ".join(details)
		if len(details) > 0: details = ": " + details
		return "Set by file group" + details

	# Return whether action shall be postponed to postprocessing
	@classmethod
	def is_postprocessing(cls):
		return True

	# Set exif creation time
	@classmethod
	@trace
	def execute(cls, file, batch):
		creation_times = file.get_property(File.CREATIONTIME)
		for key, creation_time in creation_times.items():
			file.set_creation_time(key, creation_time)
			yield
		if len(creation_times) > 0: file.save()

from . import Command
from . import File
