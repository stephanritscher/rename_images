from __future__ import with_statement

import datetime
import gi
import logging
import os
import re
import string

gi.require_version('GExiv2', '0.10')
from gi.repository import GObject, Gio, GLib, GExiv2
from .Annotations import trace

logger = logging.getLogger('File')

# Class containing a single image/video file in a batch
class File(GObject.GObject):
	def __init__(self, batch, uri):
		GObject.GObject.__init__(self)
		self._file = Gio.File.new_for_uri(uri)
		self._batch = batch
		self._group = None
		self.reset()

	# Overwrite equality - only uri matters
	def __eq__(self, other):
		if self is None or other is None:
			return self is None and other is None
		else:
			return self.get_uri() == other.get_uri()

	# Display nicely on print
	def __str__(self):
		return self.get_path()

	# Set default values since processing might be called several times
	def reset(self):
		self._file_type = None
		self._creation_time = None
		self._metadata = None
		self._properties = {}

	# Add default properties by extension
	def set_default_properties(self, postprocessing):
		ext = self.get_extension().lower()
		if ext in EXTENSIONS:
			for key, value in EXTENSIONS[ext].items():
				if 'is_postprocessing' in dir(value) and value.is_postprocessing() and not postprocessing:
					value = FileAction.Ignore
				self.add_properties({key: value})

	# Assign to file group
	def set_group(self, group):
		assert group._group == self.get_group()
		self._group = group

	# Initialize file
	def init(self):
		self.read_tags()
		self.get_creation_time()

	# Load exif/xmp tags
	@trace
	def read_tags(self):
		if self._metadata != None:
			return
		if self.get_property(TAGS):
			self._metadata = GExiv2.Metadata()
			self._metadata.open_path(self.get_path())

	# Return path
	def get_uri(self):
		return self._file.get_uri()

	# Return native path
	def get_path(self):
		return self._file.get_path()

	# Get the file extension
	def get_extension(self):
		root, ext = os.path.splitext(self._file.get_uri())
		return ext

	# Get the file root (without extension)
	def get_root(self):
		root, ext = os.path.splitext(self._file.get_uri())
		return root

	# Get the common part of the file name in the group
	def get_group(self):
		if self._batch._allow_subgroups: 
			match = self._batch._grouppattern.match(self._file.get_uri())
			if match: return match.group('group')
			else: return self._file.get_uri()
		else: return self.get_root()

	# Get the individual part of the file name in the group
	def get_index(self):
		if self._batch._allow_subgroups: 
			match = self._batch._grouppattern.match(self._file.get_uri())
			if match: return match.group('index')
			else: return ""
		else: return self.get_extension()

	# Determine the actual base from the file
	def get_actual_base(self):
		basename = Gio.File.new_for_uri(self.get_group()).get_basename()
		match = re.match(self._batch._basepattern, basename)
		return match.group('base')

	# Get the file type
	def get_file_type(self):
		if self._file_type is None:
			self._file_type = self._file.query_file_type(Gio.FileQueryInfoFlags.NONE, None)
		return self._file_type

	# Return uri of directory
	def get_parent(self):
		return File(self._batch, self._file.get_parent().get_uri())

	# Return list of all parents
	def get_parents(self):
		current = self
		parents = [current]
		while current._file.has_parent():
			current = current.get_parent()
			parents.append(current)
		return parents

	# Return the common root
	def get_common_root(self, file):
		if file is None:
			return self
		self_parents = self.get_parents()
		file_parents = file.get_parents()
		common = None
		while len(self_parents) > 0 and len(file_parents) > 0:
			self_parent = self_parents.pop()
			file_parent = file_parents.pop()
			if self_parent.get_uri() == file_parent.get_uri():
				common = self_parent
			else:
				break
		#print "Common root of %s and %s is %s" % (self.get_path(), file.get_path(), common.get_path())
		return common

	# Return the path of file relative to self
	def get_relative_path(self, file):
		relative = self._file.get_relative_path(file._file)
		if relative is None:
			#print "%s is not relative to %s" % (file.get_path(), self.get_path())
			return file.get_path()
		else:
			#print "Relative path of %s to %s is %s" % (file.get_path(), self.get_path(), relative)
			return relative

	# Return children of directory
	def enumerate_children(self):
		for fileinfo in self._file.enumerate_children(Gio.FILE_ATTRIBUTE_STANDARD_NAME, Gio.FileQueryInfoFlags.NONE, None):
			uri = self._file.get_child(fileinfo.get_name()).get_uri()
			yield File(self._batch, uri)

	# Get property by key
	def get_property(self, key):
		return self._properties.get(key, None)

	# Set property
	def add_properties(self, prop):
		self._properties.update(prop)

	@trace
	def check_rename(self):
		dest = self.get_destination_uri()
		return Gio.File.new_for_uri(dest).query_exists()

	# Rename file using the destination path
	def rename(self):
		src = self._file.get_uri()
		dest = self.get_destination_uri()
		if src == dest: return
		logger.info('Renaming %s to %s', src, dest)
		try:
			if not self._file.move(Gio.File.new_for_uri(dest), Gio.FileCopyFlags.NONE, None, None, None):
				raise Exception('Could not rename %s to %s.' % (src, dest))
		except Exception as e:
			logger.error('Could not rename %s to %s: %s.' % (src, dest, e))
			raise


	# Delete file
	def delete(self):
		logger.info('Deleting %s', self._file.get_uri())
		try:
			if not self._file.delete(None):
				raise Exception('Could not delete %s.' % (self._file.get_uri()))
		except Exception as e:
			logger.error('Could not trash %s: %s', self._file.get_uri(), e)
			raise

	# Move file to trash; optionally delete if trash is not supported
	def trash(self, delete_if_not_supported):
		logger.info('Trashing %s', self._file.get_uri())
		try:
			if not self._file.trash(None):
				raise Exception('Could not trash %s.' % (self._file.get_uri()))
		except GLib.Error as e:
			if e.code == Gio.IOErrorEnum.NOT_SUPPORTED and delete_if_not_supported:
				logger.warn('Trashing %s not supported', self._file.get_uri())
				return self.delete()
			logger.error('Could not trash %s: %s', self._file.get_uri(), e)
			raise
		except Exception as e:
			logger.error('Could not trash %s: %s', self._file.get_uri(), e)
			raise

	# Check whether file has a delete action
	def check_delete_action(self):
		for check in FileCheck.Check.get_file_checks():
			if not check in self._batch._file_actions: continue
			if not self.get_root() in self._batch._file_actions[check]: continue
			if not self in self._batch._file_actions[check][self.get_root()]: continue
			if self.get_property(check) is FileAction.Trash: return True
		return False

	# Get destination uri for renaming
	def get_destination_uri(self):
		return Gio.File.new_for_path(self.get_destination_path()).get_uri()

	# Get destination file for renaming
	def get_destination(self):
		return File(self._batch, self.get_destination_uri())

	# Get destination path for renaming
	def get_destination_path(self):
		return self._batch._format.format(
			datetime=self._group.get_creation_time().strftime('%Y.%m.%d %Hh%Mm%Ss'),
			directory=self.get_parent().get_path(),
			base=self._group._base,
			counter=self._group._number,
			alphacounter=number2alpha(self._group._number),
			extension=self.get_index().lower()
		)

	# Read the tags from the file's metadata
	def get_tags(self):
		tags = []
		for key in TAG_KEYS:
			tags += self._metadata.get_tag_multiple(key)
		return tags

	# Add a tag to the file's metadata
	@trace
	def assign_tag(self, tag):
		if not self.get_property(TAGS): return
		for key in TAG_KEYS:
			tags = self._metadata.get_tag_multiple(key)
			tags.append(tag)
			self._metadata.set_tag_multiple(key, tags)

	# Parse date/time string
	def parse_time_string(self, time):
		if not time: return None
		try:
		    return datetime.datetime.strptime(time, TIME_FORMAT)
		except ValueError:
		    return None

	# Get creation time
	@trace
	def get_creation_time(self, key = None, fallback = True):
		# From cache
		if self._creation_time is not None:
			return self._creation_time
		# Default exif key
		if key is None:
			key = TIME_KEYS[0]
		# From exif
		if self._metadata is not None:
			self._creation_time = self.parse_time_string(self._metadata.get_tag_string(key))
		if self._creation_time is not None or not fallback:
			return self._creation_time
		# Fallback: from file date
		fileinfo = self._file.query_info(Gio.FILE_ATTRIBUTE_TIME_MODIFIED + "," + Gio.FILE_ATTRIBUTE_TIME_CREATED, Gio.FileQueryInfoFlags.NONE, None)
		modified = fileinfo.get_attribute_uint64(Gio.FILE_ATTRIBUTE_TIME_MODIFIED)
		self._creation_time = datetime.datetime.fromtimestamp(modified)
		return self._creation_time

	# Set creation time in file metadata
	@trace
	def set_creation_time(self, key, time):
		self._metadata.set_tag_string(key, time.strftime(TIME_FORMAT))

	# Get file orientation
	@trace
	def get_orientation(self):
		return self._metadata.get_tag_long('Exif.Image.Orientation')

	# Save changes of metadata to file
	@trace
	def save(self):
		self._metadata.save_file(self.get_path())

# Convert a number to letter-count (0 -> a, 1 -> b, ..., 26 -> aa, 27 -> ab, ...)
def number2alpha(number):
	alpha = ''
	while True:
		alpha = alpha + chr(ord('a') + (number % 26))
		number = number // 26
		if number == 0: break
	return alpha[::-1]

from . import FileAction
from . import FileCheck

# Standard properties by extension
TYPE = 'type'
IMAGE = 'image'
VIDEO = 'video'
STEP = 'step'
RAW = 'raw'
INTERMEDIATE = 'intermediate'
RESULT = 'result'
TAGS = 'tags'
ROTATE = 'rotate'
DATEPRIO = 'dateprio'
GROUPCONVERT = 'groupconvert'
CREATIONTIME = 'creationtime'
RENAMEERROR = 'renameerror'
TAG_KEYS = ['Iptc.Application2.Keywords', 'Xmp.dc.subject']
TIME_KEYS = ['Exif.Photo.DateTimeOriginal', 'Exif.Photo.DateTimeDigitized', 'Exif.Image.DateTime']
TIME_FORMAT = '%Y:%m:%d %H:%M:%S'

EXTENSIONS = { # TODO: Separate configuration (default choice of file check action, dateprio) from actual code
	           # TODO: Possibly move support checks for ROTATE/GROUPCONVERT to file check plugins
	'.jpg': {TYPE: IMAGE, STEP: RESULT, TAGS: True, ROTATE: True, GROUPCONVERT: True, DATEPRIO: 1, FileCheck.Unselected: FileAction.Include, FileCheck.Rotate: FileAction.Rotate, FileCheck.NewFileGroup: FileAction.ConvertGroup, FileCheck.CreationTime: FileAction.SetCreationTime},
	'.cr2': {TYPE: IMAGE, STEP: RAW, TAGS: True, DATEPRIO: 2, FileCheck.OnlyRaw: FileAction.Trash, FileCheck.Unselected: FileAction.Include, FileCheck.CreationTime: FileAction.SetCreationTime},
	'.nef': {TYPE: IMAGE, STEP: RAW, TAGS: True, DATEPRIO: 2, FileCheck.OnlyRaw: FileAction.Trash, FileCheck.Unselected: FileAction.Include, FileCheck.CreationTime: FileAction.SetCreationTime},
	'.tif': {TYPE: IMAGE, STEP: INTERMEDIATE, TAGS: True, DATEPRIO: 3, FileCheck.Unselected: FileAction.Include, FileCheck.CreationTime: FileAction.SetCreationTime},
	'.mov': {TYPE: VIDEO, STEP: RAW, DATEPRIO: 5, FileCheck.OnlyRaw: FileAction.Convert, FileCheck.Unselected: FileAction.Include},
	'.mp4': {TYPE: VIDEO, STEP: RESULT, DATEPRIO: 4, FileCheck.Unselected: FileAction.Include},
	'.thm': {TYPE: VIDEO, STEP: INTERMEDIATE, TAGS: True, DATEPRIO: 6, FileCheck.Unselected: FileAction.Include},
}

