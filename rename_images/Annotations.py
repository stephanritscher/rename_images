import datetime
import inspect
import logging
import sys
import traceback
import types

from gi.repository import GLib

logger = logging.getLogger('Annotations')
LOGTRACE = False

def get_function_name(func, func_name = None):
	if inspect.ismethod(func):
		return "%s.%s" % (func.im_class.__name, func_name or func.__name__)
	else:
		return func_name or func.__name__

def get_generator_line_str(generator):
	if generator.gi_frame is None:
		return "%s:%d" % (generator.gi_code.co_filename.split('/')[-1], generator.gi_code.co_firstlineno)
	else:
		return "%s:%d" % (generator.gi_frame.f_code.co_filename.split('/')[-1], generator.gi_frame.f_lineno)

# Print trace output
def trace(func, func_name = None):
	fn = get_function_name(func, func_name)
	def run(*args, **kwds):
		# Determine additional parameters for generators
		if func.__name__ == 'next' and type(func).__name__ == 'method-wrapper':
			line_from = " [%s]" % get_generator_line_str(func.__self__)
		else:
			line_from = ""
		start = datetime.datetime.now()
		# Trace start of function
		if LOGTRACE and logger.isEnabledFor(logging.DEBUG):
			level = len(traceback.format_stack())
			argstr = ", ".join([str(arg) for arg in args] + ["%s=%s" % (str(key), str(value)) for (key, value) in kwds.items()])
			logger.debug("%s %s(%s)%s", ">" * level, fn, argstr, line_from)
		# Execute function and catch exceptions
		ret = exc_type = exc_value = exc_traceback = None
		try:
			ret = func(*args, **kwds)
			# Enable tracing of generators
			if inspect.isgenerator(ret):
				ret = TracingGenerator(ret, fn)
			return ret
		except Exception:
			if LOGTRACE and logger.isEnabledFor(logging.DEBUG):
				exc_type, exc_value, exc_traceback = sys.exc_info()
			raise
		finally:
			# Determine additional parameters for generators
			end = datetime.datetime.now()
			if func.__name__ == 'next' and type(func).__name__ == 'method-wrapper':
				line_to = ' -> [%s]' % get_generator_line_str(func.__self__)
			else:
				line_to = ""
			# Trace end of function
			if LOGTRACE and logger.isEnabledFor(logging.DEBUG):
				if exc_type is None:
					logger.debug('%s %s = %s%s', '<' * level, fn, str(ret), line_to)
				else:
					logger.debug('%s %s: %s %s%s', '<' * level, fn, str(exc_type), str(exc_value), line_to)
			# Warn about long execution times
			if end - start > datetime.timedelta(milliseconds=200):
				logger.warn('%s%s%s took %.3fs', fn, line_from, line_to, (end - start).total_seconds())
	return run

class TracingGenerator:
	def __init__(self, gen, fn):
		self._generator = gen
		self._fn = fn

	def __iter__(self):
		return self

	def __next__(self):
		return trace(self._generator.__next__, "%s.next" % self._fn)()

	def send(self, value):
		return self._generator.send(value)

	def throw(self):
		return self._generator.throw()

# Execute a function pausing at yields
def yieldsleep(func):
	# Define function start which wraps func and initializes the execution
	def start(*args, **kwds):
		# Create generator
		generator = func(*args, **kwds)
		#  Define function step which executes func up to (one of the) next yields and schedules the next step
		def step(*args, **kwds):
			try:
				# Run func up to next yield
				start = end = datetime.datetime.now()
				while end - start < datetime.timedelta(milliseconds=50):
					time = next(generator)
					end = datetime.datetime.now()
				# Schedule next step of func
				if time is None: GLib.idle_add(step)
				else: GLib.timeout_add(time, step)
			except StopIteration:
				pass
		step.__name__ = "%s::step" % func.__name__
		# Schedule first step of func
		GLib.idle_add(step)
	start.__name__ = "%s::start" % func.__name__
	return start

