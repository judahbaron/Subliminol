import sys
import sublime
import sublime_plugin
import subprocess

CONSOLE_NAME = "Subliminol: Console"

class SubliminolCommand(sublime_plugin.TextCommand):

	def __init__(self, *args, **kwargs):
		sublime_plugin.TextCommand.__init__(self, *args, **kwargs)
		self.console = None
		self.edit = None
		self.running = False
		self.settings = None
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
		command_history = self.settings.get(history_key, None)
		# This may be the first time through, in which case the history array
		# will be None. Set it to [] instead, so we can add to it and 
		if command_history is None:
			command_history = []

		# Remove any other instances of this entry from the history array
		# so we don't get duplicates.
		while data in command_history:
			command_history.remove(data)
		
		# Insret at index 0 so the last used entry becomes the first item in the
		# history array.
		command_history.insert(0, data)

		if len(command_history) > self.history_length_setting:
			command_history = command_history[0:(self.history_length_setting-1)]
		
		self.settings.set(history_key, command_history)
		sublime.save_settings('Subliminol.sublime-settings')

	def run_history_panel(self):
		'''
		Open a panel displaying the history array, and allowing the user to make
		a selection. 
		'''
		history_data = self.settings.get(self.history_key, None)
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

	def run(self, edit, command_mode="system", history_panel_mode=False, command_string_data=None):
		'''
		Main entry point...
		'''
		self.running = True
		self.edit = edit
		self.command_mode = command_mode
		self.settings = sublime.load_settings('Subliminol.sublime-settings')
		
		if history_panel_mode:
			self.run_history_panel()
			return

		self.get_console(console_name=CONSOLE_NAME)
		# print("CONSOLE_NAME {0} call".format(command_mode))
		
		
		# print(self.settings.get("test_setting"))
		# print(self.settings.get("test_array_setting"))

		if self.console is None:
			print("NO CONSOLE! Exiting command.")
			self.running = False
			self.edit = None
			self.command_string_data = None
			self.running = False
			self.command_mode = None
			return

		self.command_string_data = []
		if command_string_data is None:
			# Gather command string data from the selections in the view	
			for region in self.view.sel():
				if (abs(region.b-region.a)) > 0:
					self.command_string_data.append(self.view.substr(region))
		else:
			self.command_string_data.extend(command_string_data)

		if len(self.command_string_data):
			the_call = None
			if self.command_mode == "system":
				the_call = self.system_run
			elif self.command_mode == "python":
				the_call = self.python_run
			
			if the_call is None:
				self.edit = None
				self.command_string_data = None
				self.running = False
				self.command_mode = None
				return

			if(self.view == self.console):
				# Add a carriage return if the CONSOLE is being used as the input terminal
				# so the printed text is not writen to an existing line containing text.
				last_char = self.view.substr(sublime.Region(self.view.size()-1,self.view.size()))
				if last_char != "\n":
					self.write("\n".format(last_char))

			for cmd_string in self.command_string_data:
				the_call(cmd_string)					
				# print("\t-"*10)
			print("-"*80)

		self.add_history(self.command_string_data)

		self.edit = None
		self.command_string_data = None
		self.running = False

	def write(self, data):
		'''
		This object has a write() method so it can be passed to stdout, redirecting
		output into the view specified by self.console.
		'''
		self.to_console( data )

	def python_run(self, cmd_string):
		'''
		Handles the setup of a "python" execute, rather than a system command.
		'''
		std_out_orig = sys.stdout
		try:
			sys.stdout = self
			
			result = exec(cmd_string, globals(), locals())
			
		except:
			print(sys.exc_info()[0])
			print(sys.exc_info()[1])
			print(sys.exc_info()[2])
		sys.stdout = std_out_orig

	def make_console(self, console_name):
		'''
		Create the output console used for writing results to. 
		'''
		window = sublime.active_window()
		console = window.new_file()
		# print(console)
		console.set_name(console_name)
		console.set_scratch(True)
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

	def to_console(self, output, name=CONSOLE_NAME):
		'''
		Write output to console.
		'''
		self.console.insert(self.edit, self.console.size(), output)

		# Scroll the view to the end of the buffer so we can see what was just written
		scroll_pos = (0, self.console.layout_extent()[1]-self.console.viewport_extent()[1])
		self.console.set_viewport_position(scroll_pos)
	
	def system_run(self, system_call, **kwargs):
		'''
		Method used to handle "system" calls
		'''
		blocking = True
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
							# print(output)
							
							if blocking is True:
								results += output
							else:
								# More needs to be done here. This is just stubbed out
								self.to_console(output)
		# This does not belong here, it's just a placeholder for actual code
		self.to_console("-"*80 + "\n")
		# This should probably be handled by a class call so all resultant output,
		# no matter the source, is handled in a standard manner.
		self.to_console(results)

