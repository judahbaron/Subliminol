import sys
import os
import time
import sublime
import sublime_plugin
import subprocess

class InvalidCallType(Exception):
	pass

# Add the subliminol_core subdirectory so we can import the following modules.
# sys.path.insert(0, os.path.split(__file__)[0] + "\\subliminol_core")

# from subliminol_exc import InvalidCallType
# from subliminol_system_call import SubliminolSystemCall
# from subliminol_python_call import SubliminolPythonCall

CONSOLE_NAME = "Subliminol: Console"
SUBLIMINOL_VERSION = "0.3.0"

def plugin_loaded():
	SubliminolCommand.set_status(Status.IDLE)#"LOADED::READY ({0})".format(time.asctime()))
	SubliminolCommand.report_status()

class Status:
	@staticmethod
	def NULL():pass
	@staticmethod
	def RUNNING():pass
	@staticmethod
	def ERROR():pass
	@staticmethod
	def IDLE():pass

	def __init__(self, state=None, data=None):
		if state is None:
			state = Status.NULL
		self._state = state
		self._data = data
		self._info = []
		self.append_info("Init: {0}".format(time.asctime()))

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
		self._state = i_state

	@property
	def data(self):
	    return self._data
	
	@data.setter
	def data(self, i_data):
		self._data = i_data

	def __repr__(self):
		return "{0}: ({1})".format(str(self._state.__name__), self.last_info())

class SubliminolCommand(sublime_plugin.TextCommand):

	__status = Status()

	@classmethod
	def set_status(cls, status):
		cls.__status.state = status


	@classmethod
	def report_status(cls, *args):
		print("Subliminol Status: {0}".format(cls.__status))

	def __init__(self, *args, **kwargs):
		sublime_plugin.TextCommand.__init__(self, *args, **kwargs)
		self._read_only_state_orig = False
		self._insertion_point = None
		self._write_count = 0
		self.console = None
		self.edit = None
		self.settings = None
		self.history = None
		self.command_string_data = None
		# A string indicating either "system" or "python"
		self.command_mode = None

	@property
	def history_key(self):
		'''
		Generate key based on command_mode member var
		'''
		if self.command_mode:
		    return "{0}_history".format(self.command_mode)
		return None

	@property
	def history_length_setting(self):
		'''
		Retrieve the maximum number of commands to save in the history array.
		'''
		history_length_key = "{0}_history_length".format(self.command_mode)
		return self.settings.get(history_length_key, 12)
	
	def add_history(self, data):
		'''
		Adds data to history and ensures there are no duplicates.
		The last entry becomes entry [0], so it's at the beginning of the list.
		'''
		history_key = self.history_key
		if history_key is None:
			print("No history_key!")
			return
		command_history = self.history.get(history_key, None)
		# This may be the first time through, in which case the history array
		# will be None. Set it to [] instead, so we can add to it and 
		if command_history is None:
			command_history = []

		# Remove any other instances of this entry from the history array
		# so we don't get duplicates.
		while data in command_history:
			command_history.remove(data)
		
		# Insert at index 0 so the last used entry becomes the first item in the
		# history array.
		command_history.insert(0, data)

		if len(command_history) > self.history_length_setting:
			command_history = command_history[0:(self.history_length_setting-1)]
		
		self.history.set(history_key, command_history)
		sublime.save_settings('Subliminol-history.sublime-settings')

	def run_history_panel(self):
		'''
		Open a panel displaying the history array, and allowing the user to make
		a selection. 
		'''
		history_data = self.history.get(self.history_key, None)
		if history_data is None:
			print("NO HISTORY")
			return
		
		def panel_callback(index):
			if index == -1:
				return
			# print("RUNNING FROM HISTORY: {0}".format(history_data[index]))
			current_view = sublime.active_window().active_view()

			current_view.run_command(
				'subliminol',
				{
					'command_mode': '{0}'.format(self.command_mode),
					'history_panel_mode': False,
					'command_string_data': history_data[index][:]
				}
			)
		# self.view.show_popup_menu( history_data, panel_callback)
		history_display_data = [str(hi) for hi in history_data]
		self.view.window().show_quick_panel( history_display_data, panel_callback)

	def _init_run(self, edit, command_string_data, command_mode):
		self._read_only_state_orig = False#self.view.is_read_only()
		self.edit=edit
		self._insertion_point = self.get_insertion_point()
		self._write_count = 0
		self.command_string_data = command_string_data
		self.command_mode = command_mode
		self.set_status(Status.RUNNING)
		self.console.set_read_only(True)

	def _clean_exit_run(self):
		self.edit = None
		self.command_string_data = None
		# self.running = False
		self.command_mode = None
		self.set_status(Status.IDLE)
		self.console.set_read_only(self._read_only_state_orig)

	def run(self, edit, command_mode="system", history_panel_mode=False, command_string_data=None):
		'''
		Main entry point for command execution...
		'''

		self.settings = sublime.load_settings('Subliminol.sublime-settings')
		self.history = sublime.load_settings('Subliminol-history.sublime-settings')
		
		if history_panel_mode:
			self.run_history_panel()
			return

		self.get_console(console_name=CONSOLE_NAME)

		self.console.set_syntax_file("Packages/Subliminol/data/Batch File.tmLanguage")
		# self.console.set_syntax_file("Packages/Subliminol/data/Neon.tmTheme")

		self._init_run( edit, command_string_data, command_mode)

		if self.console is None:
			print("NO CONSOLE! Exiting command.")
			self._clean_exit_run()
			return

		# This is reset with each execution.
		self.command_string_data = []

		# When nothing is provided on the call to run(), command_string_data
		# is populated from the current selection.
		if command_string_data is None:
			# Gather command string data from te selections in the view	

			for region in self.view.sel():
				if (abs(region.b-region.a)) == 0:
					region = self.view.line(region)
				self.command_string_data.append(self.view.substr(region))
		else:
			self.command_string_data.extend(command_string_data)
		
		if len(self.command_string_data):
			the_call = None
			if self.command_mode == "system":
				# the_call = self.system_run
				the_call = SubliminolSystemCall(self.command_string_data)
			elif self.command_mode == "python":
				# the_call = self.python_run
				the_call = SubliminolPythonCall(self.command_string_data)
			else:
				self._clean_exit_run()
				raise InvalidCallType(self.command_mode)


			if(self.view == self.console):
				# Add a carriage return if the CONSOLE is being used as the input terminal
				# so the printed text is not writen to an existing line containing text.
				last_char = self.view.substr(sublime.Region(self.view.size()-1,self.view.size()))
				if last_char != "\n":
					self.write("\n".format(last_char))

			# remap stdout to the console so we don't lose any feedback, including
			# python returns, stack traces and errors, etc.
			orig_stdout = sys.stdout
			sys.stdout = self
			failure = False
			try:
				the_call.run()
			except Exception:
				print(sys.exc_info()[0])
				print(sys.exc_info()[1])
				print(sys.exc_info()[2])
				failure = True
			if self.settings.get("select_output_on_complete"):
				selection = self.view.sel()
				selection.clear()
				region = sublime.Region(self._insertion_point, self._insertion_point+self._write_count)
				c_regions = self.view.get_regions(self.command_mode)
				c_regions.append(region)
				# self.view.add_regions(self.command_mode, c_regions, scope="a", flags=(sublime.PERSISTENT | sublime.DRAW_NO_OUTLINE ) )
				selection.add(region)

			sys.stdout = orig_stdout

		do_write_history = True
		if self.settings.get("write_history_on_success_only"):
			if failure:
				do_write_history = False

		if do_write_history:
			self.add_history(self.command_string_data)

		self._clean_exit_run()


	def write(self, data):
		'''
		This object has a write() method so it can be passed to stdout, redirecting
		output into the view specified by self.console.
		'''
		self.to_console( data )


	def make_console(self, console_name):
		'''
		Create the output console used for writing results to. 
		'''
		window = sublime.active_window()
		console = window.new_file()
		# print(console)
		console.set_name(console_name)
		console.set_scratch(False)
		console.set_read_only(False)
		return console

	def get_console(self, console_name):
		'''
		Return the view currently being used as the output console. 
		'''
		console = self.find_console(console_name)
		if console is None:
			console = self.make_console(console_name)		
		self.console = console

	def find_console(self, console_name):
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

	def get_insertion_point(self):
		insertion_point = self.console.size()
		if self.settings.get("insert_before_selection"):
			# If the console is the the current view, then the user is using the
			# console to perform input. In this case we want to handle insertion
			# in such a way that reflects standard terminal input behavior.
			if self.console == self.view:
				for region in self.view.sel():
					selected_region = region
					if selected_region.b - selected_region.a == 0:
						selected_region = self.view.line(selected_region)
					insertion_point = selected_region.a
					if selected_region.b < insertion_point:
						insertion_point = selected_region.b
		return insertion_point

	def to_console(self, output, name=CONSOLE_NAME):
		'''
		Write output to console.
		When status is RUNNING, the console is locked to prevent user input from
		colliding with the program's output.
		'''
		insertion_point = self._insertion_point + self._write_count
		self._write_count += len(output)
		self.console.set_read_only(False)
		self.console.insert(self.edit, insertion_point, output)
		self.console.set_read_only(True)
		# Scroll the view to the end of the buffer so we can see what was just written
		scroll_pos = (0, self.console.layout_extent()[1]-self.console.viewport_extent()[1])
		self.console.set_viewport_position(scroll_pos)

class SubliminolCallBase(object):
	'''
	Base class for Subliminol calls.
	'''

	def __init__(self, command_string_data):
		self.command_string_data = command_string_data[:]

	def run(self):

		for command_string in self.command_string_data:
			self.run_single(command_string)

class SubliminolPythonCall(SubliminolCallBase):
	'''
	Subliminol class for Python calls.
	'''
	def __init__(self, command_string_data, **kwargs):
		SubliminolCallBase.__init__(self, command_string_data)



	def run_single(self, command_string):
		'''
		Handles the setup of a "python" execute, rather than a system command.
		'''

		try:
			# result is not returned due to the nature of the execution environment 
			result = exec(command_string, globals(), locals())
			
		except:
			print(sys.exc_info()[0])
			print(sys.exc_info()[1])
			print(sys.exc_info()[2])


class SubliminolSystemCall(SubliminolCallBase):
	'''
	Subliminol class for System calls.
	'''

	def __init__(self, command_string_data):
		SubliminolCallBase.__init__(self, command_string_data)

	def run_single(self, system_call):
		'''
		Method used to handle "system" calls
		'''
		blocking = False
		# print("system_run: {0}".format(system_call))
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
							results += output
							if not blocking:
								if len(results) >= 500:
									sys.stdout.write(results)									
									results = ""
		
		sys.stdout.write(results)
		sys.stdout.write("-"*80 + "\n")

