import datetime
import logging
import os
import re
import sys
import traceback

from gi.repository import GObject, Gtk, Gio
from .Annotations import trace

logger = logging.getLogger('Batch')

# Class containing a batch of image/video files (e.g. a panorama or HDR set)
class Batch(GObject.GObject):
	# allow_subgroups: If True, panorama/HDR files will be treated as one file
	# format: destination file format; $datetime = digitalization date and time, $base = basefile, $counter = fileindex, $alphacounter = fileindex as number, $extension = file extension (including ".", may include something before "." for HDR/panorama files)
	@trace
	def __init__(self, uris):
		GObject.GObject.__init__(self)
		self._initial_files = []
		self._common_path = None
		self.reset()
		self._uris = uris

	# Convert paths to uris
	def prepare_uri(self, uri):
		if uri.startswith('/'):
			return Gio.File.new_for_path(uri).get_uri()
		return uri

	# Check which file uris we can/want to handle
	def valid_uri(self, uri):
		if not uri.startswith('file://'):
			logger.info('Ignoring URI %s' % uri)
			return False
		return True

	# Set default values since processing might be called several times
	@trace
	def reset(self):
		self._group_key = GROUP_KEY['by date']
		self._file_count = 0
		self._files_by_group = {}
		self._files_by_root = {}
		self._file_actions = {}
		for file in self._initial_files: file.reset()

	# Test whether files with type IMAGE or VIDEO were added (lazy: check for directories always is True)
	# May be invoked before init()
	#def has_files(self, recursive):
	#	for file in self._initial_files:
	#		if file.get_property(File.TYPE) in [File.IMAGE, File.VIDEO]: return True
	#		if recursive and file.get_file_type() == Gio.FileType.DIRECTORY: return True
	#	return False

	# Show error dialog
	#@trace
	#def display_error(self, window, msg):
	#	dialog = Gtk.MessageDialog(window, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, msg)
	#	dialog.run()
	#	dialog.destroy()

	# Set properties for command to be executed
	@trace
	def init(self, properties, progresswindow):
		self.reset()
		self._allow_subgroups = properties.get('allow_subgroups', True)
		self._tag = properties.get('tag', None)
		self._counter = properties.get('counter', 0)
		self._format = properties.get('format', '{directory:s}/{base:s}{alphacounter:s}{extension:s}')
		self._basepattern = re.compile(properties.get('basepattern', r'^(?P<base>.*?)\s*[0-9]*$'))
		self._grouppattern = re.compile(r'^(?P<group>.*?)(?P<index>((?<=[0-9])|\([a-z]*\)?)?\.[^.]*)$')
		self._recursive = properties.get('recursive', False)
		self._command = properties.get('command', 'postprocess')
		self._progresswindow = progresswindow

	# Calculate common root of file with the rest of the batch
	def get_common_root(self, file):
		common_root = file.get_common_root(self._common_path)
		if common_root.get_file_type() != Gio.FileType.DIRECTORY:
			common_root = common_root.get_parent()
		return common_root

	# Calculate relative path to commmon part of the batch
	@trace
	def get_relative_path(self, file):
		return self._common_path.get_relative_path(file)

	# Determine the basename for the batch
	@trace
	def get_default_base(self):
		if len(self._files_by_group.keys()) == 0: return "/"
		base = Gio.File.new_for_uri(sorted(self._files_by_group.keys())[0]).get_basename()
		match = self._basepattern.match(base)
		return match.group('base')

	# Prepare rename or postrocessing (autorotation, panorama/HDR creation) command of files in batch
	@trace
	def prepare(self):
		self._progresswindow.set_title('Image batch loading')
		self._progresswindow.set_visible(True)
		self._progresswindow.set_step('Searching selected directories ...', len(self._uris))
		for uri in self._uris:
			uri = self.prepare_uri(uri)
			if not self.valid_uri(uri): continue
			file = File.File(self, uri)
			self._common_path = self.get_common_root(file)
			for item in self.add_files_recursively(file, self._command == 'postprocess'): yield item
		for item in self.init_files(): yield item
		for check in FileCheck.Check.get_file_checks():
			self._file_actions[check] = {}
			for file in check.do_check(self):
				if file is not None:
					if file.get_root() not in self._file_actions[check]:
						self._file_actions[check][file.get_root()] = []
					self._file_actions[check][file.get_root()].append(file)
				yield
		self._base = self.get_default_base()
		self._progresswindow.set_visible(False)

	# Execute rename or postrocessing (autorotation, panorama/HDR creation) command of files in batch
	@trace
	def execute(self):
		rename = self._command == 'rename'
		if rename: title = "Image batch rename in " + self._common_path.get_path()
		else: title = "Image batch process in " + self._common_path.get_path()
		self._progresswindow.set_title(title)
		self._progresswindow.set_visible(True)
		errors = 0
		for check in FileCheck.Check.get_file_checks():
			# TODO: Better use (supported from python 3.3): yield from ...
			generator = check.execute_actions(self._file_actions[check], self)
			message = None
			while True:
				try:
					item = generator.send(message)
					message = yield item
				except StopIteration:
					break
				except Exception as e:
					if e.args[0] == 'errors': errors += e.args[1]
					else: raise
		if errors > 0:
			raise Exception('Encountered %d errors' % errors)
		if self._command == 'rename':
			for item in self.assign_base_numbers(): yield item
			rename_order = []
			try:
				for file in self.calculate_rename_order():
					if file is not None: rename_order.append(file)
					yield
			except Exception:
				for group in self._files_by_group:
					for file in self._files_by_group[group]._files:
						if file.get_property(File.RENAMEERROR) is not None:
							self._progresswindow.output('%s: %s\n' % (file.get_path(), file.get_property(File.RENAMEERROR)))
							yield
							errors += 1
				raise Exception('Encountered %d problems. See output above.' % errors)
			for item in self.assign_tag(): yield item
			for item in self.rename_files(rename_order): yield item
		self._progresswindow.set_visible(False)

	# Add files recursively to batch
	@trace
	def add_files_recursively(self, file, postprocessing):
		yield
		file.set_default_properties(postprocessing)
		type = file.get_file_type()
		# Scan directory recursively
		if type == Gio.FileType.DIRECTORY and self._recursive:
			self._progresswindow.increase_step(file.get_path())
			try:
				for idx, child in enumerate(file.enumerate_children()):
					for item in self.add_files_recursively(child, postprocessing): yield item
			except:
				pass
		# Filter non-media files
		if type != Gio.FileType.REGULAR: return
		# Add file to batch
		self.add_file(file)

	# Add file to batch if it is a supported image/video
	@trace
	def add_file(self, file):
		# Filter non-media files
		if not file.get_property(File.TYPE) in [File.IMAGE, File.VIDEO]: return
		# Add file to batch
		self._file_count = self._file_count + 1
		if file.get_root() in self._files_by_root:
			self._files_by_root[file.get_root()].append(file)
		else:
			self._files_by_root[file.get_root()] = [file]
		if file.get_group() in self._files_by_group:
			self._files_by_group[file.get_group()].add_file(file)
		else:
			self._files_by_group[file.get_group()] = FileGroup.FileGroup(file)

	# Initialize files by reading tags
	@trace
	def init_files(self):
		self._progresswindow.set_step('Reading image tags ...', self._file_count)
		for group in self._files_by_group:
			for file in self._files_by_group[group]._files:
				self._progresswindow.increase_step(file.get_path())
				yield
				file.init()

	# Assign the basename and numbers to the files in the batch
	@trace
	def assign_base_numbers(self):
		if self._progresswindow:
			self._progresswindow.set_step('Calculating file names ...', self._file_count)
		counter = self._counter
		for group, files in sorted(self._files_by_group.items(), key=self._group_key):
			yield
			if self._progresswindow:
				self._progresswindow.increase_step(files._group)
			empty = len([file for file in files._files if not file.check_delete_action()]) == 0
			files.assign_base_number(self._base, counter)
			if not empty: counter = counter + 1

	# Determine the order for renaming the files
	@trace
	def calculate_rename_order(self):
		# Build rename graph
		destination_uris = {}
		source_uris = {}
		source_counts = {}
		for group in self._files_by_group:
			for file in self._files_by_group[group]._files:
				yield
				# Skip files that are deleted
				if file.check_delete_action(): continue
				# Determine uris
				src_uri = file.get_uri()
				dest_uri = file.get_destination_uri()
				# Reset old errors
				file.add_properties({File.RENAMEERROR: None})
				# Nodes
				source_uris[src_uri] = file
				# Backward edges
				if dest_uri in destination_uris:
					destination_uris[dest_uri].append(file)
				else:
					destination_uris[dest_uri] = [file]
				# Out degree
				source_counts[src_uri] = source_counts.get(src_uri, 0) + 1
				source_counts[dest_uri] = source_counts.get(dest_uri, 0)
		# Get nodes with zero out degree
		next_uris = []
		for uri in source_counts:
			if source_counts[uri] == 0: next_uris.append(uri)
		# Calculate rename order
		order = []
		error = False
		while len(next_uris) > 0:
			uri = next_uris.pop()
			for src in destination_uris.get(uri, []):
				src_uri = src.get_uri()
				# Check in degree > 1
				if len(destination_uris[uri]) > 1:
					src.add_properties({File.RENAMEERROR: 'Destination not unique'})
					logger.info('%s: %s' % (src.get_path(), 'Destination not unique'))
					error = True
				# Check rename to existing file not part of renaming
				elif uri not in source_uris and src.check_rename():
					src.add_properties({File.RENAMEERROR: 'Destination exists'})
					logger.info('%s: %s %s' % (src.get_path(), 'Destination exists', uri))
					error = True
				source_counts[src_uri] = source_counts[src_uri] - 1
				if source_counts[src_uri] == 0: next_uris.append(src_uri)
			if uri in source_uris: yield source_uris[uri]
			else: yield
		# The remaining files are in one or more circles
		for uri in source_uris:
			yield
			file = source_uris[uri]
			# Allow one edge circles
			dest_uri = file.get_destination_uri()
			if uri == dest_uri: continue
			if source_counts[uri] != 0:
				file.add_properties({File.RENAMEERROR: 'Circular rename'})
				logger.info('%s: %s %d' % (file.get_path(), 'Circular rename', source_counts[uri]))
				error = True
		if error: raise Exception('Could not calculate rename order')

	# Add the tag of the batch to its files metadata
	@trace
	def assign_tag(self):
		if not self._tag: return
		self._progresswindow.set_step('Assigning tag %s ...' % self._tag, self._file_count)
		for group in self._files_by_group:
			for file in self._files_by_group[group]._files:
				self._progresswindow.increase_step(file.get_path())
				yield
				if file.check_delete_action(): continue
				file.assign_tag(self._tag)
				file.save()

	# Rename the files in batch
	@trace
	def rename_files(self, rename_order):
		self._progresswindow.set_step('Renaming files ...', len(rename_order))
		for file in rename_order:
			self._progresswindow.increase_step(file.get_path())
			yield
			if file.check_delete_action(): continue
			file.rename()

GROUP_KEY = {
	'by name': lambda item: item[0],
	'by date': lambda item: item[1].get_creation_time(),
}

from . import File
from . import FileAction
from . import FileCheck
from . import FileGroup
