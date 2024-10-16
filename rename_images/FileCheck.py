import collections
import logging
import sys
import traceback

from gi.repository import GObject, Gio
from .Annotations import trace

logger = logging.getLogger('FileCheck')

# TODO: Split file by class into subpackage
class Check(GObject.GObject):
	# List of all file checks
	_checks = collections.OrderedDict()

	# Display nicely on print
	def __str__(self):
		return self.__name__

	# Add file check to list
	@classmethod
	def register(cls, check):
		cls._checks[check] = 1

	# Return list of all file checks
	@classmethod
	def get_file_checks(cls):
		return cls._checks.keys()

	# Get name of file check
	@classmethod
	def get_name(cls):
		pass
	
	# Get list of allowed actions
	@classmethod
	def get_possible_actions(cls):
		pass

	# Perform file check
	@classmethod
	@trace
	def do_check(cls, batch):
		return {}
	
	# Determine whether exception is fatal or further actions may be performed
	@classmethod
	@trace
	def is_exception_fatal(cls, action_type, exc_type, exc_value):
		return False

	# Execute selected action
	@classmethod
	@trace
	def execute_actions(cls, files, batch):
		batch._progresswindow.set_step('Executing actions for %s check ...' % cls.__name__, len(files))
		errors = 0
		for root in files:
			batch._progresswindow.increase_step(Gio.File.new_for_uri(root).get_path())
			for file in files[root]:
				try:
					logger.info("%s: action %s for %s", cls.__name__, file.get_property(cls).__name__, file.get_path())
					# TODO: Better use (supported from python 3.3): yield from ...
					generator = file.get_property(cls).execute(file, batch)
					message = None
					while True:
						try:
							item = generator.send(message)
							message = yield item
						except StopIteration:
							break
				except Exception:
					exc_type, exc_value, exc_traceback = sys.exc_info()
					traceback.print_exception(exc_type, exc_value, exc_traceback)
					if cls.is_exception_fatal(file.get_property(cls), exc_type, exc_value):
						raise exc_type(exc_value).with_traceback(exc_traceback)
					else:
						batch._progresswindow.output('\n%s\n\n' % exc_value)
						errors = errors + 1
		if errors:
			raise Exception('errors', errors)

class Unselected(Check):
	@classmethod
	def get_name(cls):
		return 'Unselected files'

	@classmethod
	def get_possible_actions(cls):
		return [FileAction.Include, FileAction.Ignore]

	# Check for files with same root not in collection
	@classmethod
	@trace
	def do_check(cls, batch):
		batch._progresswindow.set_step('Checking for unselected files ...', len(batch._files_by_root))
		seen = set()
		for root in batch._files_by_root.keys():
			path = batch._files_by_root[root][0].get_parent()
			batch._progresswindow.increase_step(path.get_path())
			yield
			pathuri = path.get_uri()
			if pathuri in seen: continue
			seen.add(pathuri)
			for child in path.enumerate_children():
				yield
				child.set_default_properties(False)
				if child.get_root() in batch._files_by_root and child.get_extension().lower() in File.EXTENSIONS:
					if child in batch._files_by_root[child.get_root()]: continue
					child.init()
					yield child
Check.register(Unselected)

class OnlyRaw(Check):
	@classmethod
	def get_name(cls):
		return 'Single RAW files'

	@classmethod
	def get_possible_actions(cls):
		return [FileAction.Trash, FileAction.Convert, FileAction.Ignore]

	# Check whether all raw files have a corresponding result file (including unselected files)
	@classmethod
	@trace
	def do_check(cls, batch):
		batch._progresswindow.set_step('Checking for single raw files ...', batch._file_count)
		for root in batch._files_by_root:
			for file in batch._files_by_root[root]:
				batch._progresswindow.increase_step(file.get_path())
				yield
				if file.get_property(File.STEP) != File.RAW: continue
				onlyraw = True
				for f in batch._files_by_root[root]:
					if f.get_property(File.STEP) != File.RESULT: continue
					if file.get_property(File.TYPE) != f.get_property(File.TYPE): continue
					onlyraw = False
				if root in batch._file_actions[Unselected]:
					for f in batch._file_actions[Unselected][root]:
						if f.get_property(File.STEP) != File.RESULT: continue
						if file.get_property(File.TYPE) != f.get_property(File.TYPE): continue
						onlyraw = False
				if onlyraw: yield file
Check.register(OnlyRaw)

class Rotate(Check):
	@classmethod
	def get_name(cls):
		return 'Rotate'

	@classmethod
	def get_possible_actions(cls):
		return [FileAction.Rotate, FileAction.Ignore]

	# Check which files have to be rotated
	@classmethod
	@trace
	def do_check(cls, batch):
		batch._progresswindow.set_step('Checking for rotated files ...', 1)
		for root in batch._files_by_root:
			for file in batch._files_by_root[root]:
				batch._progresswindow.increase_step(file.get_path())
				yield
				if not file.get_property(File.TAGS): continue
				orientation = file.get_orientation()
				if orientation == None or orientation == 0 or orientation == 1: continue
				if not file.get_property(File.ROTATE): continue
				yield file
Check.register(Rotate)

class NewFileGroup(Check):
	@classmethod
	def get_name(cls):
		return 'New file group'

	@classmethod
	def get_possible_actions(cls):
		return [FileAction.ConvertGroup, FileAction.Ignore]

	# Check whether all file groups have a corresponding result file (including unselected files)
	@classmethod
	@trace
	def do_check(cls, batch):
		if batch._command != 'postprocess': return
		batch._progresswindow.set_step('Checking for new file groups ...', batch._file_count)
		for group in batch._files_by_group:
			result_file = False
			group_files = []
			for file in batch._files_by_group[group]._files:
				batch._progresswindow.increase_step(file.get_path())
				yield
				if file.get_index() == file.get_extension(): result_file = True
				elif file.get_property(File.GROUPCONVERT): group_files.append(file)
			if len(group_files) >= 1 and not result_file and len(group) >= 1 and group[-1] != '/':
				file = File.File(batch, group + group_files[0].get_extension())
				file.set_default_properties(batch._command == 'postprocess')
				file.add_properties({File.GROUPCONVERT: group_files})
				yield file
			else: yield
Check.register(NewFileGroup)

class CreationTime(Check):
	@classmethod
	def get_name(cls):
		return 'Missing creation time'

	@classmethod
	def get_possible_actions(cls):
		return [FileAction.SetCreationTime, FileAction.Ignore]

	# Check which files have to be rotated
	@classmethod
	@trace
	def do_check(cls, batch):
		batch._progresswindow.set_step('Checking for creation time ...', 1)
		for group in batch._files_by_group:
			for file in batch._files_by_group[group]._files:
				batch._progresswindow.increase_step(file.get_path())
				yield
				if not file.get_property(File.TAGS): continue
				creation_times = {}
				for key in File.TIME_KEYS:
					if file._metadata.has_tag(key): continue
					times = list(filter(lambda x: x is not None, [f.get_creation_time(key, False) for f in batch._files_by_group[group]._files]))
					if len(times) == 0: continue
					creation_times[key] = min(times)
				if creation_times == {}: continue
				file.add_properties({File.CREATIONTIME: creation_times})
				yield file
Check.register(CreationTime)

from . import File
from . import FileAction
