import glob
import inspect
import logging
import os
import sys


# do the logging at the script location (most likely .local/share/nautilus/scripts)
nautilus_scripts_dir = os.path.dirname(os.path.realpath(__file__))
logging.basicConfig(
    filename=os.path.join(nautilus_scripts_dir, 'nautilus_scripts.log'),
    level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')


try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    from gi.repository import Gdk
except Exception as err:
    logging.error(str(err))


PATH_PARAMETERS = ['file_path', 'file_paths', 'directory_path', 'directory_paths']


class ColorButton(Gtk.ColorButton):
    """
    Gtk.ColorButton has methods like 'to_string', but I could not find one that returns a tuple of integers.
    'get_rgb_int_tuple' is made to return the color in such way that it is compatible with Pillow
    """
    def get_rgb_int_tuple(self):
        return tuple([int(value * 255) for value in self.get_rgba()])


class EntryWindow(Gtk.Window):
    def __init__(self, method):
        """
        Loop through the parameters of the 'method', determine the name, type and default value.
        Add every parameter to a GUI window, with the default value filled in,
        except for the 'path' parameter. The path or paths are selected by the user in Nautilus, and will be handled
        by an environment variable set by Nautilus (in on_submit method).

        This 'path' parameter has to be one of the 'PATH_PARAMETERS' and will be saved as self.method_file_parameter
        The list of input entry attributes (with the parameter name and type) will be saved as self.entries
        """
        Gtk.Window.__init__(self, title=method.__name__)

        self.method = method
        self.color_parameters = getattr(method, 'color_parameters', [])
        self.combo_choices = getattr(method, 'combo_choices', {})
        self.check_combo_choices()

        grid = Gtk.Grid(column_homogeneous=True, column_spacing=10, row_spacing=10)
        self.add(grid)

        self.entries = []  # collect for every parameter the name, type and how the user input can be retrieved
        file_parameters = []  # collect which parameter defines the selected files, later check if there is exactly one
        row_index = 0
        for parameter in inspect.signature(method).parameters.values():
            if parameter.name in PATH_PARAMETERS:
                file_parameters.append(parameter.name)
            else:
                parameter_type = parameter.annotation
                if parameter_type is inspect._empty:
                    if parameter.default is inspect._empty:
                        self._quit_with_error_dialog(
                            error_message="Could not retrieve a type for parameter {}".format(parameter.name)
                        )
                        sys.exit()
                    else:
                        parameter_type = type(parameter.default)

                # prevent that the parameter name equals an existing class variable, prepend them with 'entry_'
                param_entry_name = 'entry_{}'.format(parameter.name)

                # Determine how the parameter should show up. If it is a boolean, a checkbox will be rendered.
                # If it is a color, render a ColorButton (parameter name has to be added to method.color_parameter)
                # If a list of multiple choices is defined in method.combo_choices, render a ComboBox
                # For all other values, render a 'normal' text Entry
                if parameter_type is bool:
                    entry = Gtk.CheckButton()
                    entry.set_active(is_active=parameter.default is True)  # False for any value other then exactly True
                    user_input_getter = 'get_active'
                elif parameter.name in self.color_parameters:
                    if isinstance(parameter.default, tuple) and len(parameter.default) in (3, 4):
                        default_color = parameter.default
                        if len(default_color) == 3:
                            default_color += (1, )  # add the alpha channel just in case
                    else:
                        default_color = (255, 255, 255, 1)

                    entry = ColorButton()
                    color = Gdk.RGBA(*default_color)  # default_color is a 4 tuple of rgba values
                    entry.set_rgba(color)
                    user_input_getter = 'get_rgb_int_tuple'
                elif parameter.name in self.combo_choices:
                    entry = Gtk.ComboBoxText()
                    default_index = 0
                    for choice_index, choice in enumerate(self.combo_choices[parameter.name]):
                        # only a string can be added here. If the parameter is not a string, it will be converted to
                        # the correct type later, with the 'parameter_type' that has been determined above
                        entry.append_text(str(choice))
                        if choice == parameter.default:
                            default_index = choice_index

                    entry.set_active(default_index)
                    user_input_getter = 'get_active_text'
                else:
                    # for all other types, show a text entry
                    entry = Gtk.Entry(text=str(parameter.default))
                    user_input_getter = 'get_text'
                setattr(self, param_entry_name, entry)

                self.entries.append((parameter.name, param_entry_name, parameter_type, user_input_getter))

                label = Gtk.Label(label=parameter.name, halign=Gtk.Align.END)
                grid.attach(label, left=0, top=row_index, width=2, height=1)
                grid.attach_next_to(getattr(self, param_entry_name), sibling=label, side=Gtk.PositionType.RIGHT,
                                    width=2, height=1)

                row_index += 1

        if len(file_parameters) != 1:
            self._quit_with_error_dialog(error_title="The method should have exactly one of the following paramters:",
                                         error_message=str(PATH_PARAMETERS))
            sys.exit()

        self.method_file_parameter = file_parameters[0]

        self.cancel_button = Gtk.Button.new_with_mnemonic('cancel')
        self.cancel_button.connect("clicked", self._quit)
        self.submit_button = Gtk.Button.new_with_mnemonic(self.method.__name__)
        self.submit_button.connect("clicked", self.on_submit)

        grid.attach(self.cancel_button, 0, row_index, 2, 1)
        grid.attach(self.submit_button, 2, row_index, 2, 1)

        self.progressbar = Gtk.ProgressBar(show_text=True)
        grid.attach(self.progressbar, 0, row_index + 1, 4, 1)

    def check_combo_choices(self):
        if not isinstance(self.combo_choices, dict) or \
                any(not isinstance(value, (list, tuple)) for value in self.combo_choices.values()):
            self._quit_with_error_dialog(error_title='method.combo_choices is not correct',
                                         error_message="It should be a dict like {'param_name': ['val1', 'val2']}")
            sys.exit()

    def update_progress_bar(self, fraction, text):
        self.progressbar.set_fraction(fraction)
        self.progressbar.set_text(text)

        while Gtk.events_pending():
            Gtk.main_iteration()

    def _call_method(self, kwargs, process_number=0, total_processes=1):
        try:
            logging.debug('Running method {} with {}'.format(self.method.__name__, kwargs))
            self.cancel_button.set_sensitive(False)
            self.submit_button.set_sensitive(False)

            self.method(**kwargs)
            if total_processes > 0:
                self.update_progress_bar(
                    fraction=(process_number + 1) / total_processes,
                    text='{} / {} done'.format(process_number + 1, total_processes))
        except Exception as e:
            self._quit_with_error_dialog(error_message=str(e))

    def _quit(self, *args, **kwargs):
        Gtk.main_quit()

    def _quit_with_error_dialog(self, error_message, error_title=None):
        """
        Show a dialog with the error message. After the user clicks on ok, the application quits.
        """
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=error_title or 'ERROR',
        )
        dialog.format_secondary_text(error_message)
        dialog.connect("response", self._quit)
        dialog.run()
        dialog.destroy()
        logging.error('{} {}'.format(error_title or '', error_message))

    def on_submit(self, button):
        """
        Collect the values that the user submitted in the input fields (Entry), which could be the default values.
        Convert them to the parameter type that was retrieved earlier by inspecting the method.

        NAUTILUS added a list of the selected file paths to the environment. This list is based on the user input
        and can contain one or more items which can be file_paths and / or directories.
        When file path(s) is/are expected, all  file paths are passed to the method (even if they contain both files
        and directories)
        When directory path(s) is/are expected, (silently) ignore all items that are not a directory.

        The user can always select on ore more paths, but the method could expect either a single path or
        a list of several paths. Determine how to pass the file paths to the the method.

        When the method_file_parameter is
            - a single 'file_path': call the method for every path in the list
            - several 'file_paths': call the method once with the list of file paths
                If exactly one path was provided which is a directory, assume that the user means to apply
                the action on all files in this directory (this rule applies to the two options above, a file_path(s)
                was expected, not a directory_path)

            - a single 'directory_path': call the method for every path directory path in the list.
            - several 'directory_paths': call the method once for the list of directory paths.
        """
        user_inputs = {}
        for param_name, param_entry_name, param_type, user_input_getter in self.entries:
            try:
                user_input = getattr(getattr(self, param_entry_name), user_input_getter)()
                user_inputs[param_name] = param_type(user_input)
            except Exception as e:
                self._quit_with_error_dialog(
                    error_title="Wrong user input for the field '{}'".format(param_name),
                    error_message=str(e))
                return

        # If the file_paths variable is not in the environment, quit and log the error.
        # In case the code is not run via a nautilus menu, it will fail on the line below it, and the user
        # will see the error in his command line
        if 'NAUTILUS_SCRIPT_SELECTED_FILE_PATHS' not in os.environ:
            self._quit_with_error_dialog(
                error_title="NAUTILUS_SCRIPT_SELECTED_FILE_PATHS is not in os.environ.",
                error_message="Did you run this code via a nautilus menu?")

        # the list of file paths that the user selected in Nautilus
        nautilus_file_paths = os.environ['NAUTILUS_SCRIPT_SELECTED_FILE_PATHS'].splitlines()

        if self.method_file_parameter in ['file_path', 'file_paths']:
            # if one or more file_paths are expected by the method, but the user selected a single directory,
            # assume that the user wants the method to be called for every file in this directory
            if len(nautilus_file_paths) == 1 and os.path.isdir(nautilus_file_paths[0]):
                # '*' could be changed to '*.jpeg' to filter on file format
                nautilus_file_paths = [path for path in glob.glob(os.path.join(nautilus_file_paths[0], '*')) if
                                       os.path.isfile(path)]
        elif self.method_file_parameter in ['directory_path', 'directory_paths']:
            # Only perform the method on directories, silently ignore all paths that are not directories
            nautilus_file_paths = [dir_path for dir_path in nautilus_file_paths if os.path.isdir(dir_path)]

        # When the method expects one single path, but the user selected multiple paths, call the method for every path
        if self.method_file_parameter in ['file_path', 'directory_path']:
            total_processes = len(nautilus_file_paths)
            for process_index, file_path in enumerate(nautilus_file_paths):
                user_inputs[self.method_file_parameter] = file_path
                self._call_method(kwargs=user_inputs, process_number=process_index, total_processes=total_processes)

        # When the method expects several paths, call the method once with the list of paths
        elif self.method_file_parameter in ['file_paths', 'directory_paths']:
            user_inputs[self.method_file_parameter] = nautilus_file_paths
            self._call_method(kwargs=user_inputs)

        else:
            self._quit_with_error_dialog(
                error_message='Method parameter {} was not recognised'.format(self.method_file_parameter))

        self._quit()


def launch_entry_window(method):
    win = EntryWindow(method=method)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
