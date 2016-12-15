import sys
import os
import time
import functools
import sublime
import sublime_plugin
import subprocess
from threading import Thread

CONSOLE_NAME = "Subliminol: Console"
SUBLIMINOL_VERSION = "0.3.1"
LINE_PREFIX = "[SBNL] "
SBNL_LOG_LEVEL = 2

class InvalidCallType(Exception):
	pass


def plugin_loaded():
	SubliminolCommand.set_status(Status.IDLE)#"LOADED::READY ({0})".format(time.asctime()))
	SubliminolCommand.report_status()



def sbnl_log( message, mode="LOG", level=1 ):
	"""
	General logging function to handle all output, errors included
	Lower level values print more frequently
	"""

	output = message
	do_print = True
	
	if level > SBNL_LOG_LEVEL:
		do_print = False

	if mode == "ERROR":
		do_print = True
		output = "- ERROR: {0}\n{1}\n{2}\n{3}".format(
						sys.exc_info()[0],
						sys.exc_info()[1],
						sys.exc_info()[2],
						message
			
		)

	if do_print:
		print( "{} {}".format( LINE_PREFIX, output ))

def print_err( message=None):
	if message is None:
		message = ""
	sbnl_log(message, level=0)

class Status:
	@staticmethod
	def NULL():pass
	@staticmethod
	def INITIALIZING():pass
	@staticmethod
	def RUNNING():pass
	@staticmethod
	def ERROR():pass
	@staticmethod
	def IDLE():pass
	@staticmethod
	def COMPLETE():pass

	def __init__(self, state=None, data=None):
		if state is None:
			state = Status.NULL
		self._state = state
		self._data = data
		self._info = []
		# self.append_info("Init: {0}".format(time.asctime()))

	def append_info(self, info):
		self._info.append(info)

	def last_info(self):
		index = len(self._info)-1
		return(self._info[index])

	@property
	def state(self):
	    return self._state

	@state.setter
	def state(self, i_state):
		self.append_info("State Change: {0} -> {1} @ {2}".format(self._state.__name__, i_state.__name__, time.asctime()))
		self._state = i_state

	@property
	def data(self):
	    return self._data
	
	@data.setter
	def data(self, i_data):
		self._data = i_data

	def __repr__(self):
		return "{0}: ({1})".format(str(self._state.__name__), self.last_info())

def update_task(execution_id):
	'''
	This is called, indirectly, by monitor as an asynchronous command is running.
	It calles the SublimeText plugin command and passes only the execution_id on
	the argument list. The execution_id is used to identify the correct command
	instance in SubliminolCommand._tasks[] 
	'''
	current_view = sublime.active_window().active_view()

	current_view.run_command(
		'subliminol',
		{			
			'execution_id': execution_id
		}
	)

################################################################################
################################################################################

def get_console(console_name):
	'''
	Return the view currently being used as the output console. 
	'''
	# self.console.set_syntax_file("Packages/Subliminol/data/Batch File.tmLanguage")
	console = find_console(console_name)
	if console is None:
		console = make_console(console_name)		
	return console

def make_console(console_name):
	'''
	Create the output console used for writing results to. 
	'''
	window = sublime.active_window()
	console = window.new_file()
	console.set_name(console_name)
	console.set_scratch(False)
	console.set_read_only(False)
	return console

def find_console(console_name):
	'''
	Search for a view by name that will be used to direct output to.
	'''
	console = None
	for window in sublime.windows():
		for view in window.views():
			v_name = view.name()
			if v_name == console_name:
				return view
	return None

################################################################################
################################################################################

def get_history_key(command_mode):
	return("{0}_history".format(command_mode))

class SubliminolCommand(sublime_plugin.TextCommand):

	__status = Status()

	_tasks = []

	last_execution_id = 0

	

	@classmethod
	def set_status(cls, status):
		cls.__status.state = status

	@classmethod
	def get_status(cls):
		return cls.__status.state

	@classmethod
	def report_status(cls, *args):
		sbnl_log("Status: {0}".format( cls.__status ), level=1)

	def __init__(self, *args, **kwargs):
		sublime_plugin.TextCommand.__init__(self, *args, **kwargs)
		self._read_only_state_orig = False
		self.settings = None
		self.history = None
		# self.command_string_data = None
		# A string indicating either "system" or "python"
		# self.command_mode = None

	# @property
	# def history_key(self):
	# 	'''
	# 	Generate key based on command_mode member var
	# 	'''
	# 	if command_mode:
	# 	    return "{0}_history".format(command_mode)
	# 	return None


	def history_length_setting(self, command_mode):
		'''
		Retrieve the maximum number of commands to save in the history array.
		'''
		history_length_key = "{0}_history_length".format(command_mode)
		return self.settings.get(history_length_key, 12)


	def add_history(self, data, command_mode):
		'''
		Adds data to history and ensures there are no duplicates.
		The last entry becomes entry [0], so it's at the beginning of the list.
		'''
		history_key = get_history_key(command_mode)
		command_history = self.history.get(history_key, None)
		# This may be the first time through, in which case the history array
		# will be None. Set it to [] instead, so we can add to it and 
		if command_history is None:
			sbnl_log("No history_key!")
			command_history = []

		# Remove any other instances of this entry from the history array
		# so we don't get duplicates.
		while data in command_history:
			command_history.remove(data)
		
		# Insert at index 0 so the last used entry becomes the first item in the
		# history array.
		command_history.insert(0, data)
		h_length = self.history_length_setting(command_mode)
		if len(command_history) > h_length:
			command_history = command_history[0:(h_length-1)]
		
		self.history.set(history_key, command_history)
		sublime.save_settings('Subliminol-history.sublime-settings')

	def run_history_panel(self, command_mode):
		'''
		Open a panel displaying the history array, and allowing the user to make
		a selection. 
		'''
		history_key = get_history_key(command_mode)
		history_data = self.history.get(history_key, None)
		if history_data is None:
			sbnl_log("NO HISTORY")
			return
		
		def history_panel_callback(index):
			if index == -1:
				return
			current_view = sublime.active_window().active_view()

			current_view.run_command(
				'subliminol',
				{
					'command_mode': '{0}'.format(command_mode),
					'history_panel_mode': False,
					'command_string_data': history_data[index][:]
				}
			)
		# self.view.show_popup_menu( history_data, panel_callback)
		history_display_data = [str(hi) for hi in history_data]
		self.view.window().show_quick_panel( history_display_data, history_panel_callback)

	def new_execution_id(self):
		self.last_execution_id += 1
		return self.last_execution_id 

	def get_command_regions(self, view=None):
		sbnl_log("get_command_regions", level=3)
		if view is None:
			view = sublime.active_window().active_view()
		regions = []
		for region in view.sel():
			if region.b-region.a == 0:
				# if region is zero length extend it to contain the selected line
				region = view.line(region)
			regions.append(region)
		return regions

	def _get_command_string_data(self, command_string_data, view=None):
		# When nothing is provided on the call to run(), command_string_data
		# is populated from the current selection.
		l_command_string_data = []
		if view is None:
			view = sublime.active_window().active_view()
		if command_string_data is None:
			# Gather command string data from the selections in the view
			for region in self.get_command_regions(view):
				l_command_string_data.append(view.substr(region))
		else:
			l_command_string_data.extend(command_string_data)
		
		return l_command_string_data



	def run(self, edit,
			command_mode="system",
			history_panel_mode=False,
			command_string_data=None,
			execution_id=None
		):
		'''
		Main entry point for command execution...
		'''
		self.settings = sublime.load_settings('Subliminol.sublime-settings')
		self.history = sublime.load_settings('Subliminol-history.sublime-settings')
		

		if history_panel_mode:
			self.run_history_panel(command_mode)
			return

		if execution_id is None:
			self.run_new(command_mode, command_string_data)
		else:
			self.run_update(edit, execution_id)

	def run_update(self, edit, execution_id):
		SubliminolCallBase.update_task(edit, execution_id)
	
	def get_call_type(self, key):
		"""
		Based on the privided (string) key, return a valid class to be used
		"""
		call_type_dict = {
							"system": SubliminolSystemCall,
							"python": SubliminolPythonCall
						}
		try:
			return(call_type_dict[key])
		except:
			return None

	def run_new(self, command_mode, command_string_data):
		"""
		Initializes a 'new' command.
		The term 'new' is used because there may be long running commands, so it
		distingueshes a call emited by a command already in progress, called with
		run_update() vs a brand new call.
		"""
		sbnl_log("command_string_data({})".format(command_string_data), level=3)

		view = sublime.active_window().active_view()

		console = get_console(console_name=CONSOLE_NAME)

		console_mode = False
		if view == console:
			console_mode = True
		execution_id = self.new_execution_id()
		
		command_string_data = self._get_command_string_data(command_string_data, view)
		command_regions = self.get_command_regions(view=view)

		if len(command_string_data):
			the_call = None
			call_type = self.get_call_type(command_mode)
			if command_mode is None:
				raise InvalidCallType(command_mode)

			the_call = call_type(execution_id, command_string_data, console, console_mode=console_mode, settings=self.settings)
			target_region_id = the_call.get_target_region_id()
			
			console.add_regions(target_region_id, command_regions, icon="Packages/Theme - Default/dot.png")

			try:
				the_call.start()
			except Exception:
				print_err()
				self.set_status(Status.ERROR)
			
			#########################################################
			#########################################################
		# 	if self.get_status() is not Status.ERROR:
		# 		# select output upon completion
		# 		if self.settings.get("subliminol_select_output_on_complete"):
		# 			selection = self.console.sel()
		# 			selection.clear()
		# 			region = sublime.Region(self._insertion_point, self._insertion_point+self._write_count)
		# 			c_regions = self.console.get_regions(self.command_mode)
		# 			c_regions.append(region)
		# 			# self.view.add_regions(self.command_mode, c_regions, scope="a", flags=(sublime.PERSISTENT | sublime.DRAW_NO_OUTLINE ) )
		# 			selection.add(region)
	

		do_write_history = True
		if self.settings.get("subliminol_write_history_on_success_only"):
			if self.get_status() is not Status.ERROR:
				do_write_history = False

		if do_write_history:
			self.add_history(command_string_data, command_mode)



################################################################################
################################################################################

class SubliminolCallBase(Thread):
	'''
	Base class for Subliminol calls.
	'''
	_tasks = []

	@classmethod
	def monitor( cls, execution_id ):
		'''
		Initially called when a process is first triggered, monitor is used to perform
		updates on running processes. It re-invokes itself using sublime.set_timeout().
		Once a process is complete re-invokation is not performed, leaving nothing
		consuming any performance. 
		'''

		removals = []
		for at in cls._tasks:
			if at.execution_id == execution_id:
				if at.has_data():
					update_task(execution_id)

				if at.status is Status.ERROR:
					# execution_id may not actually be related to an error here
					sbnl_log("ERROR: {0}".format(at.execution_id), level=0)
				elif at.status is Status.RUNNING:
					# Continue RUNNING until Status.COMPLETE is triggred
					_monitor = functools.partial(cls.monitor, execution_id)
					sublime.set_timeout(_monitor, 100)
				elif at.status is Status.COMPLETE:
					at.status.state = Status.IDLE
					# Could change how this works so removals is not used. Instead
					# monitor could be invoked one more time to do a removal pass.
					sbnl_log("Command Complete: {0}".format(at.command_string_data), level=2)
					removals.append(at)
				else:
					# Not sure yet how this may come to be, but it is triggered by
					# an unhandled status value
					sbnl_log("UNEXPECTED STATUS: {0}".format(at.status), level=1)
			
			for rm in removals:
				cls._tasks.remove(rm)

	def _register(self):
		self._tasks.append(self)

	def __init__(self, execution_id, command_string_data, console, console_mode=True, settings=None):
		Thread.__init__(self)
		self._status = Status(state=Status.INITIALIZING)
		self.command_string_data = command_string_data[:]
		self._data = []
		self.console = console
		self.console_mode = console_mode
		self._execution_id = execution_id

		self._write_count = 0
		self._lock = False
		self._has_data = False
		
		self.settings = settings

		if not self.console_mode:
			if self.console.substr(self.console.size()) != "\n":
				self.append("\n")

		self._register()
		self._status.state = Status.IDLE


	@property
	def status(self):
		return self._status.state

	@property
	def execution_id(self):
	    return self._execution_id

	@execution_id.setter
	def execution_id(self, value):
		self.execution_id = value

	@classmethod
	def get_active_task(cls, execution_id):
		for at in cls._tasks:
			if at.execution_id == execution_id:
				return at
		return None

	@classmethod
	def update_task(cls, edit, execution_id):
		at = cls.get_active_task(execution_id)

		if at is None:
			sbnl_log("update_task(): INVALID EXECTUTION_ID", level=1)
			return

		data = at.get_data()
		at.to_console(edit, data)

	def run(self):

		# Generate and trigger the monitoring callback here
		cb = functools.partial( self.__class__.monitor, self.execution_id )

		self._status.state = Status.RUNNING

		cb()


		for command_string in self.command_string_data:
			try:
				self.run_single(command_string)
			except:
				self._status.state = Status.ERROR
				self._status.append_info(command_string)
				return

		self._status.state = Status.COMPLETE

	def append(self, data):
		if len(data):
			self._data.append(data)
			self._has_data = True
	
	def has_data(self):
		return self._has_data
	
	def get_data(self):

		result = self._data[:]
		self._data = []
		self._has_data = False;
		return result

	def get_insertion_point(self):
		# print("get_insertion_point()")
		insertion_point = 0
		l_min = self.console.size()
		l_max = 0

		if self.console_mode:
			
			# If the console is the the current view, then the user is using the
			# console to perform input. In this case we want to handle insertion
			# in such a way that reflects standard terminal input behavior.

			for region in self.get_target_regions():
				if region.a < l_min:
					l_min = region.a
				if region.a > l_max:
					l_max = region.b
				if region.b < l_min:
					l_min = region.b
				if region.b > l_max:
					l_max = region.b

			message = "BEFORE"
			insert_before = self.settings.get("subliminol_insert_before_selection")
			if insert_before:
				insertion_point = l_min
			else:
				insertion_point = l_max
				message = "AFTER"
			sbnl_log("INSERT {0} {1}".format(message, l_max), level=3);
		else:
			"DELTA"
			insertion_point = self.console.size()

		return insertion_point

	def get_target_region_id(self):
		return "SBNL_{0}_[{1}]".format(self.__class__.__name__, self.execution_id)
	
	def make_target_region(self, edit, id=None):
		if id is None:
			id = self.get_target_region_id()

		ip = self.get_insertion_point()
		self.console.insert(edit, ip, "<[]>")
		target_region = sublime.Region(ip, ip+4)
		return target_region

	def get_target_regions(self):
		return self.console.get_regions(self.get_target_region_id())

	def to_console(self, edit, output):
		'''
		Write output to console.
		When status is RUNNING, the console is locked to prevent user input from
		colliding with the program's output.
		'''
		_output = "\n"
		if self.settings.get("subliminol_insert_before_selection"):
			_output = ""
		_output += "".join(output)

		insertion_point = self.get_insertion_point()
		
		self._write_count += len(_output)
		# self.console.set_read_only(False)
		
		self.console.insert(edit, insertion_point, _output)
		
		# self.console.add_regions(self.get_target_region_id(), self.console.get_regions(self.get_target_region_id()), icon="Packages/Theme - Default/dot.png")

		# self.console.set_read_only(True)
		# Scroll the view to the end of the buffer so we can see what was just written
		scroll_pos = (0, self.console.layout_extent()[1]-self.console.viewport_extent()[1])
		self.console.set_viewport_position(scroll_pos)

class SubliminolPythonCall(SubliminolCallBase):
	'''
	Subliminol class for Python calls.
	'''
	def __init__(self, execution_id, command_string_data, console, console_mode, settings=None):
		SubliminolCallBase.__init__(self, execution_id, command_string_data, console, console_mode, settings=settings)

	def run_single(self, command_string):
		'''
		Handles the setup and execution of a "python" call, rather than a system command.
		'''

		try:
			# result is not returned due to the nature of the execution environment 
			result = exec(command_string, globals(), locals())			
		except:
			print_err()


class SubliminolSystemCall(SubliminolCallBase):
	'''
	Subliminol class for System calls.
	'''

	def __init__(self, execution_id, command_string_data, console, console_mode, settings=None):
		SubliminolCallBase.__init__(self, execution_id, command_string_data, console, console_mode, settings=settings)

	def run_single(self, system_call):
		'''
		Method used to handle "system" calls
		'''
		blocking = False
		results = ""
		stdin = subprocess.PIPE
		proc = subprocess.Popen(
				system_call,
				# executable=executable,
				stdin=subprocess.PIPE,
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				shell=True,
				# cwd=working_dir,
				# startupinfo=startupinfo
				)

		if stdin is not None:
			return_code = None
			while return_code is None:
				return_code = proc.poll()
				if return_code is None or return_code == 0:
					output = True
					while output:
						output = proc.stdout.readline().decode().replace('\r\n', '\n')
						if output != "":
							self.append(output)
						# else:
						# This actually happens a lot, so don't do anything...
