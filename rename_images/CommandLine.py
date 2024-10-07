import getopt
import logging
import sys

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk 

# Display syntax and quit
def syntax():
	print('Syntax: %s -p|-h|-g|-d|-x <files>' % sys.argv[0])
	sys.exit(1)

# Initialize application GUI
def on_activate(app):
	# Check commandline arguments
	mode = None
	opts, args = getopt.getopt(sys.argv[1::], 'dhpgx')
	for opt, arg in opts:
		if opt in ['-d', '-h', '-p', '-g', '-x']:
			if mode != None: syntax()
			mode = opt
			properties = {
				'-p': Mode.PANORAMA,
				'-h': Mode.HDR,
				'-g': Mode.GROUP,
				'-d': Mode.DATE,
				'-x': Mode.POSTPROCESS,
			}[mode]
	if mode == None: syntax()
	# Initalize main window
	logger.info('Starting mode %s with properties %s for files [%s]', mode, properties, ",".join(args))
	FileActionWindow.FileActionWindow(app, None, properties, args).present()

# Entry point
def main():
	# Initialize logger
	global logger
	ch = logging.StreamHandler()
	ch.setLevel(logging.DEBUG)
	ch.setFormatter(logging.Formatter('"%(asctime)-12s [%(levelname)s] %(name)s %(message)s"'))
	logging.getLogger().addHandler(ch)
	logging.getLogger().setLevel(logging.DEBUG)
	logger = logging.getLogger('renameimages')

	# Define and start application
	app = Gtk.Application(application_id = 'de.ritscher.rename_images')
	app.connect('activate', on_activate)
	app.run(None)

from . import FileActionWindow
from . import Mode

