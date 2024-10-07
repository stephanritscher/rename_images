import datetime
import logging
import sys
import traceback

from gi.repository import GObject, Gtk, GdkPixbuf, Gio

from . import Batch, ProgressWindow
from .Annotations import trace, yieldsleep

logger = logging.getLogger('FileActionWindow')

# Dialog for selecting unselected files and handling single raw files
class FileActionWindow(Gtk.ApplicationWindow):
	@trace
	def __init__(self, app, parent, properties, uris):
		# Create window
		Gtk.ApplicationWindow.__init__(self, application=app)
		self._update_counter = 0
		self._parent = parent
		self._rename = properties.get('command') == 'rename'
		self.create_widgets()

		# Prepare data loading
		self._batch = Batch.Batch(uris)
		self._progresswindow = ProgressWindow.ProgressWindow(self)
		self._batch.init(properties, self._progresswindow)
		self.connect('map', self.load_data)

		# Show window
		self.present()
		self.set_property('visible', True)

	# Create GUI widgets without data
	def create_widgets(self):
		self._button_ok = Gtk.Button(label="Ok")
		self.connect('close-request', self.button_cancel_clicked)
		# GUI layout
		box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
		if self._rename:
			# Create entry for base name
			hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5, valign=Gtk.Align.FILL)
			hbox.append(Gtk.Label(label="Base name:", halign=Gtk.Align.FILL))
			self._entry_base = Gtk.Entry(halign=Gtk.Align.FILL)
			self._entry_base.connect('changed', self.action_base_changed)
			hbox.append(self._entry_base)
			# Create spin button for counter
			hbox.append(Gtk.Label(label="Counter:", halign=Gtk.Align.FILL))
			self._spinbutton_counter = Gtk.SpinButton(halign=Gtk.Align.FILL)
			self._spinbutton_counter.set_increments(1, 10)
			self._spinbutton_counter.set_range(0, sys.maxsize)
			self._spinbutton_counter.connect('value-changed', self.action_counter_changed)
			hbox.append(self._spinbutton_counter)
			# Create combobox for sorting
			hbox.append(Gtk.Label(label="Sorting:", halign=Gtk.Align.FILL))
			self._combobox_sorting = Gtk.ComboBoxText(halign=Gtk.Align.FILL)
			self._combobox_sorting.append_text("by name")
			self._combobox_sorting.append_text("by date")
			self._combobox_sorting.set_active(1)
			self._combobox_sorting.connect('changed', self.action_sorting_changed)
			hbox.append(self._combobox_sorting)
			box.append(hbox)
		label = Gtk.Label(label="The following actions are suggested for the selected files. Please review and correct them:", valign=Gtk.Align.FILL)
		#label.set_line_wrap(True)
		box.append(label)
		# Prepare comboboxes for changing actions
		self._COMBO_COLUMN = {}
		for check in FileCheck.Check.get_file_checks():
			self._COMBO_COLUMN[check] = len(self._COMBO_COLUMN) + 2
		self._combostore_fileactions = {}
		for check in self._COMBO_COLUMN:
			self._combostore_fileactions[check] = Gtk.ListStore(str, str, str)
			for action in check.get_possible_actions():
				self._combostore_fileactions[check].append([action.__module__, action.__name__, action.get_text()])
		# Create treeview containing files
		self._treestore_fileactions = Gtk.TreeStore(File.File, str, *([str] * len(self._COMBO_COLUMN)))
		self._treeview_fileactions = Gtk.TreeView(model=self._treestore_fileactions)
		self._treeview_fileactions.append_column(Gtk.TreeViewColumn('File', Gtk.CellRendererText(editable=False), text=1))
		column = Gtk.TreeViewColumn('Action')
		for check in self._COMBO_COLUMN:
			cellrender = Gtk.CellRendererCombo(model=self._combostore_fileactions[check], text_column=2, has_entry=False, editable=True)
			cellrender.connect('changed', self.action_fileaction_changed, check)
			column.pack_start(cellrender, True)
			column.add_attribute(cellrender, 'text', self._COMBO_COLUMN[check])
			column.set_cell_data_func(cellrender, self.cell_data_func, self._COMBO_COLUMN[check])
		self._treeview_fileactions.append_column(column)
		self._scrolledtreeview_fileactions = Gtk.ScrolledWindow(min_content_height=200, min_content_width=700, child=self._treeview_fileactions, valign=Gtk.Align.FILL, vexpand=True)
		box.append(self._scrolledtreeview_fileactions)
		if self._rename:
			# Create listview for preview
			box.append(Gtk.Label(label='Preview', valign=Gtk.Align.FILL))
			self._liststore_preview = Gtk.ListStore(File.File, str, str, str, str)
			self._treeview_preview = Gtk.TreeView(model=self._liststore_preview)
			self._treeview_preview.append_column(Gtk.TreeViewColumn('Source', Gtk.CellRendererText(editable=False), text=1))
			column = Gtk.TreeViewColumn('Destination')
			cellrenderer = Gtk.CellRendererPixbuf()
			column.pack_start(cellrenderer, True)
			column.add_attribute(cellrenderer, "icon-name", 3)
			cellrenderer = Gtk.CellRendererText(editable=False)
			column.pack_start(cellrenderer, True)
			column.add_attribute(cellrenderer, 'text', 2)
			self._treeview_preview.append_column(column)
			self._treeview_preview.append_column(Gtk.TreeViewColumn('Date', Gtk.CellRendererText(editable=False), text=4))
			self._scrolledtreeview_preview = Gtk.ScrolledWindow(min_content_height=200, min_content_width=700, child=self._treeview_preview, valign=Gtk.Align.FILL, vexpand=True)
			box.append(self._scrolledtreeview_preview)
		# Buttons
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5, valign=Gtk.Align.FILL)
		self._button_ok.connect('clicked', self.button_ok_clicked)
		hbox.append(self._button_ok)
		self._button_cancel = Gtk.Button(label="Cancel", halign=Gtk.Align.FILL)
		self._button_cancel.connect('clicked', self.button_cancel_clicked)
		hbox.append(self._button_cancel)
		box.append(hbox)
		self.set_child(box)

	# Load image metadata
	@yieldsleep
	def load_data(self, widget):
		try:
			# Prepare the batch
			for item in self._batch.prepare():
				yield item
			while self._progresswindow.check_pause_cancel(): yield 200
			self.update_data()
		except Exception:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_exception(exc_type, exc_value, exc_traceback)
			self._progresswindow.output('\n%s\n\n' % exc_value)
			self._progresswindow.set_finished()

	# Update data shown in GUI widgets
	def update_data(self):
		# Update title
		if self._rename: title = "Image batch rename in " + self._batch._common_path.get_path()
		else: title = "Image batch process in " + self._batch._common_path.get_path()
		self.set_title(title)
		# Fill treeviews
		for check in self._COMBO_COLUMN:
			values = [None, check.get_name()] + ([None] * len(self._COMBO_COLUMN))
			parent = self._treestore_fileactions.append(None, values)
			for root in self._batch._file_actions[check]:
				for file in self._batch._file_actions[check][root]:
					values = [file, self._batch.get_relative_path(file)] + ([None] * len(self._COMBO_COLUMN))
					values[self._COMBO_COLUMN[check]] = file.get_property(check).get_text(file)
					self._treestore_fileactions.append(parent, values)
		self._treeview_fileactions.expand_all()
		if self._rename:
			for group in sorted(self._batch._files_by_group):
				for file in sorted(self._batch._files_by_group[group]._files):
					self._liststore_preview.append([file, self._batch.get_relative_path(file), self._batch.get_relative_path(file), '', file.get_creation_time().strftime("%x %X")]) #"%Y-%m-%d %H:%M:%S"
			self._entry_base.set_text(self._batch._base)
			self._spinbutton_counter.set_value(self._batch._counter)

	# Button ok was clicked, execute batch actions
	@trace
	@yieldsleep
	def button_ok_clicked(self, button):
		logger.info('User clicked ok button')
		try:
			# Execute a batch command displaying a progress window
			generator = self._batch.execute()
			for item in generator:
				yield item
				if self._progresswindow.check_pause_cancel():
					# Pause command and wait for next user action
					logger.info('Sending pause to generators')
					generator.send(True)
					while self._progresswindow.check_pause_cancel(): yield 100
			self._progresswindow.destroy()
			self.destroy()
		except Exception:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_exception(exc_type, exc_value, exc_traceback)
			self._progresswindow.output('\n%s\n\n' % exc_value)
			self._progresswindow.set_finished()

	# Button cancel was clicked or window was closed otherwise
	@trace
	def button_cancel_clicked(self, button):
		logger.info('User clicked cancel button/closed window')
		self._progresswindow.destroy()
		self.destroy()

	# Custom data retrieval; make cellrenderers with value None invisible
	def cell_data_func(self, tree_column, cell, model, tree_iter, column):
		value = model.get_value(tree_iter, column)
		if value == None:
			cell.set_visible(False)
			cell.set_property('editable', False)
		else:
			cell.set_visible(True)
			cell.set_property('editable', True)
		return value

	# Base was changed by entry - reflect it into batch
	@trace
	@yieldsleep
	def action_base_changed(self, widget):
		try:
			self._batch._base = widget.get_text()
			logger.info('User changed base entry to "%s"', self._batch._base)
			for item in self.update_preview(): yield item
		except Exception:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_exception(exc_type, exc_value, exc_traceback)
			self.display_error(self, exc_value)

	# Counter was changed by spinbutton - reflect it into batch
	@trace
	@yieldsleep
	def action_counter_changed(self, widget):
		try:
			self._batch._counter = widget.get_value_as_int()
			logger.info('User changed counter spinbutton to "%d"', self._batch._counter)
			for item in self.update_preview(): yield item
		except Exception:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_exception(exc_type, exc_value, exc_traceback)
			self.display_error(self, exc_value)

	# Sorting was changed by combobox - reflect it into batch
	@trace
	@yieldsleep
	def action_sorting_changed(self, widget):
		try:
			sorting = widget.get_active_text()
			logger.info('User changed sorting combobox to "%s"', sorting)
			self._batch._group_key = Batch.GROUP_KEY[sorting]
			for item in self.update_preview(): yield item
		except Exception:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_exception(exc_type, exc_value, exc_traceback)
			self.display_error(self, exc_value)

	# Action was changed by combo - reflect it into file
	@trace
	def action_fileaction_changed(self, cellrenderercombo, treepath, comboiter, actiontype):
		try:
			treeiter = self._treestore_fileactions.get_iter(treepath)
			file = self._treestore_fileactions.get_value(treeiter, 0)
			if file == None: return
			action_module = self._combostore_fileactions[actiontype].get_value(comboiter, 0)
			action_name = self._combostore_fileactions[actiontype].get_value(comboiter, 1)
			action_text = self._combostore_fileactions[actiontype].get_value(comboiter, 2)
			logger.info('User changed action combobox of "%s" to "%s"', file.get_path(), action_text)
			self._treestore_fileactions.set_value(treeiter, self._COMBO_COLUMN[actiontype], action_text)
			file.add_properties({actiontype: getattr(sys.modules[action_module], action_name)})
		except Exception:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_exception(exc_type, exc_value, exc_traceback)
			self.display_error(self, exc_value)

	# Update preview of file names
	@trace
	def update_preview(self):
		this_counter = self._update_counter = self._update_counter + 1
		for item in self.inner_update_preview():
			yield item
			if this_counter != self._update_counter:
				self._button_ok.set_sensitive(False)
				return
	
	def inner_update_preview(self):
		self._button_ok.set_sensitive(False)
		yield
		for item in self._batch.assign_base_numbers(): yield item
		try:
			for file in self._batch.calculate_rename_order(): yield
			self._button_ok.set_sensitive(True)
		except Exception as e:
			logger.debug(e)
			pass
		iter = self._liststore_preview.get_iter_first()
		while iter:
			file = self._liststore_preview.get_value(iter, 0)
			if file.check_delete_action():
				dest = '<File will be deleted>'
				icon = 'edit-delete'
			else:
				dest = self._batch.get_relative_path(file.get_destination())
				if file.get_property(File.RENAMEERROR) is not None:
					icon = 'process-stop'
				elif file.get_uri() == file.get_destination_uri():
					icon = 'change-prevent'
				else:
					icon = ''
			self._liststore_preview.set_value(iter, 2, dest)
			self._liststore_preview.set_value(iter, 3, icon)
			iter = self._liststore_preview.iter_next(iter)
			yield

	# Show error dialog
	@trace
	def display_error(self, window, msg):
		logger.error(msg)
		dialog = Gtk.MessageDialog(window, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, msg)
		dialog.run()
		dialog.destroy()

from . import Batch
from . import File
from . import FileAction
from . import FileCheck
