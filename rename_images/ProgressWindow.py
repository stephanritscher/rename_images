import logging
import sys
import traceback

from gi.repository import GObject, Gtk, GdkPixbuf, Gio
from .Annotations import trace

logger = logging.getLogger('ProgressWindow')

# Dialog for displaying processing progress
class ProgressWindow(Gtk.Window):
	@trace
	def __init__(self, parent):
		self._count = 1
		self._index = 0
		self._cancel = False
		self._pause = False
		self._is_paused = False
		self._parent = parent
		Gtk.Window.__init__(self)
		self.set_modal(True)
		self.set_transient_for(parent)
		self._window_close_handler = self.connect('close-request', self.button_cancel_clicked)
		# GUI layout
		self.set_default_size(700, 350)
		box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
		# Create label for process step
		self._label_step = Gtk.Label(valign=Gtk.Align.FILL)
		box.append(self._label_step)
		# Create progress bar
		self._progressbar = Gtk.ProgressBar(valign=Gtk.Align.FILL)
		box.append(self._progressbar)
		# Create entry for command line output
		self._textview_output = Gtk.TextView(editable=False)
		#self._textview_output.connect("size-allocate", self.autoscroll)
		self._scrolledtextview_output = Gtk.ScrolledWindow(min_content_height=200, min_content_width=700, child=self._textview_output, valign=Gtk.Align.FILL, vexpand=True)
		box.append(self._scrolledtextview_output)
		# Buttons
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5, valign=Gtk.Align.FILL)
		self._button_cancel = Gtk.Button(label="Cancel", halign=Gtk.Align.FILL)
		self._button_cancel_handler = self._button_cancel.connect('clicked', self.button_cancel_clicked)
		hbox.append(self._button_cancel)
		self._button_pause = Gtk.Button(label="Pause", halign=Gtk.Align.FILL)
		self._button_pause.connect('clicked', self.button_pause_clicked)
		hbox.append(self._button_pause)
		box.append(hbox)
		self.set_child(box)
		self.present()
		self.set_property('visible', True)

	# Scroll to end of text output
	def autoscroll(self, *args):
		vadj = self._scrolledtextview_output.get_vadjustment()
		vadj.set_value(vadj.get_upper() - vadj.get_page_size())

	# Empty progress window
	def reset(self):
		#self.check_cancel()
		self._textview_output.set_text('')

	# Set progress text and progress bar
	def set_step(self, text, count=1, progress_text=None):
		#self.check_cancel()
		self._count = count if count > 0 else 1
		self._index = 0
		self._label_step.set_text(text)
		self._progressbar.set_fraction(float(self._index) / self._count)
		self._progressbar.set_show_text(progress_text != None)
		if progress_text: self._progressbar.set_text(progress_text)

	# Step progress bar
	def increase_step(self, progress_text=None):
		#self.check_cancel()
		self._index = self._index + 1
		self._progressbar.set_fraction(float(self._index) / self._count)
		self._progressbar.set_show_text(progress_text != None)
		if progress_text: self._progressbar.set_text(progress_text)

	# Get buffer of output textview
	def get_output_buffer(self):
		return self._textview_output.get_buffer()

	# Append text to output textview
	def output(self, text):
		self.get_output_buffer().insert(self.get_output_buffer().get_end_iter(), text)

	# Increase number of total steps
	def increase_count(self, count):
		#self.check_cancel()
		self._count = self._count + count
		self._progressbar.set_fraction(float(self._index) / self._count)

	# Operation was finished, so hide pause and replace cancel by close
	def set_finished(self):
		self._button_pause.set_visible(False)
		self._button_cancel.set_label('Close')
		self._button_cancel.disconnect(self._button_cancel_handler)
		self._button_cancel_handler = self._button_cancel.connect('clicked', self.button_close_clicked)
		self.disconnect(self._window_close_handler)
		self._window_close_handler = self.connect('close-request', self.button_close_clicked)

	# Cancel button action
	@trace
	def button_cancel_clicked(self, widget):
		logger.info('User clicked cancel button / closed window')
		self._cancel = True

	# Close button action
	def button_close_clicked(self, widget):
		logger.info('User clicked close button / closed window')
		self.destroy()
		self._parent.destroy()

	# Pause button action
	@trace
	def button_pause_clicked(self, widget):
		logger.info('User clicked %s button' % ('resume' if self._is_paused else 'pause'))
		self._pause = not self._is_paused

	# Determine whether cancel button was clicked meanwhile
	#@trace
	#def check_cancel(self):
	#	if self._cancel: raise Exception('Aborted by user')

	# Determine whether pause or cancel button was clicked meanwhile
	def check_pause_cancel(self):
		if self._cancel: raise Exception('Aborted by user')
		if self._pause != self._is_paused:
			self._button_pause.set_label('Resume' if self._pause else 'Pause')
			self._is_paused = self._pause
		return self._is_paused
