import logging
import os
import sys
import traceback
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Nautilus, GObject, Gtk
from .Annotations import trace, yieldsleep

# Class providing a Nautilus menu
class RenameImagesMenuProvider(Nautilus.MenuProvider, GObject.GObject):
	@trace
	def __init__(self):
		ch = logging.StreamHandler()
		ch.setLevel(logging.DEBUG)
		ch.setFormatter(logging.Formatter('"%(asctime)-12s [%(levelname)s] %(name)s %(message)s"'))
		logging.getLogger().addHandler(ch)
		logging.getLogger().setLevel(logging.INFO)
		self._logger = logging.getLogger('renameimages')
		self._app = Gtk.Application(application_id = 'de.ritscher.rename_images')

		self._disabled = False
		pass

	@trace
	def get_file_items_full(self, window, items):
		try:
			if self._disabled: return []
			return self.get_context_menu(window, items)
		except Exception:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_exception(exc_type, exc_value, exc_traceback)
			self._disabled = True
			self.display_error(window, exc_value)

	def get_background_items_full(self, window, items):
		pass

	# Callback for activation of our menu items
	@trace
	def menu_activate_cb(self, menu, window, properties, uris):
		if self._disabled: return
		self._logger.info('User activated menu with properties %s for files [%s]', properties, ",".join(map(str, uris)))
		FileActionWindow.FileActionWindow(self._app, window, properties, uris).present()

	# Show error dialog
	@trace
	def display_error(self, window, msg):
		self._logger.error(msg)
		dialog = Gtk.MessageDialog(window, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, msg)
		dialog.run()
		dialog.destroy()

	# Check whether we should append the rename menu items
	@trace
	def get_context_menu(self, window, files):
		# Check for file types
		directories = 0
		media_files = 0
		all_files = 0
		for file in files:
			if file.get_uri_scheme() == 'admin': file.set_uri_scheme('file')
			if file.get_uri_scheme() != 'file': continue
			if file.is_directory():
				directories += 1
			else:
				all_files += 1
				root, ext = os.path.splitext(file.get_name())
				if ext.lower() in File.EXTENSIONS: media_files += 1
		# Nothing to do?
		if directories == 0 and media_files == 0: return []
		# Prepare menus
		uris = list(map(lambda x : x.get_uri(), files))
		items = []
		if directories == 0 and all_files == media_files:
			item = Nautilus.MenuItem.new('rename_panorama', 'Rename panorama',
				'Rename and tag panorama images using increasing letters while pairing by extension', ''
			)
			item.connect('activate', self.menu_activate_cb, window, Mode.PANORAMA, uris)
			items.append(item)
			item = Nautilus.MenuItem.new('rename_hdr', 'Rename HDR',
				'Rename and tag HDR images using increasing letters while pairing by extension', ''
			)
			item.connect('activate', self.menu_activate_cb, window, Mode.HDR, uris)
			items.append(item)
			item = Nautilus.MenuItem.new('rename_group', 'Rename image group',
				'Rename image group using increasing letters while pairing by extension and subgroups (e.g. panorama, HDR)', ''
			)
			item.connect('activate', self.menu_activate_cb, window, Mode.GROUP, uris)
			items.append(item)
			item = Nautilus.MenuItem.new('rename_date', 'Rename images by date',
				'Rename images using their digitalization date and time', ''
			)
			item.connect('activate', self.menu_activate_cb, window, Mode.DATE, uris)
			items.append(item)
		if directories > 0 or media_files > 0:
			item = Nautilus.MenuItem.new('postprocess', 'Postprocess images',
				'Rotate and create panorama/HDR', ''
			)
			item.connect('activate', self.menu_activate_cb, window, Mode.POSTPROCESS, uris)
			items.append(item)
		return items

from . import File
from . import FileActionWindow
from . import Mode
