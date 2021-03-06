import os
import shutil
import sublime
import sublime_plugin

STVER = int(sublime.version())
ST3 = STVER >= 3000


def plugin_loaded():
    settings.load_settings()


class GitGutterOpenFileCommand(sublime_plugin.ApplicationCommand):
    """This is a wrapper class for SublimeText's `open_file` command.

    The task is to hide the command in menu if `edit_settings` is available.
    """

    @staticmethod
    def run(file):
        """Expand variables and open the resulting file.

        NOTE: For some unknown reason the `open_file` command doesn't expand
              ${platform} when called by `run_command`, so it is expanded here.
        """
        platform_name = {
            'osx': 'OSX',
            'windows': 'Windows',
            'linux': 'Linux',
        }[sublime.platform()]
        file = file.replace('${platform}', platform_name)
        sublime.run_command('open_file', {'file': file})

    @staticmethod
    def is_visible():
        """Return True to to show the command in command pallet and menu."""
        return STVER < 3124


class GitGutterEditSettingsCommand(sublime_plugin.ApplicationCommand):
    """This is a wrapper class for SublimeText's `open_file` command.

    Hides the command in menu if `edit_settings` is not available.
    """

    @staticmethod
    def run(**kwargs):
        """Expand variables and open the resulting file."""
        sublime.run_command('edit_settings', kwargs)

    @staticmethod
    def is_visible():
        """Return True to to show the command in command pallet and menu."""
        return STVER >= 3124


class GitGutterSettings:

    def __init__(self):
        self._settings = None
        self._user_settings = None
        self._git_binary_path_fallback = None
        self._git_binary_path_error_shown = False
        # A mapping from git dir to a string indicating what to compare against.
        self._compare_against_mapping = {}
        # These settings have public getters as they go through more
        # complex initialization than just getting the value from settings.
        self.git_binary_path = None
        self.ignore_whitespace = False
        self.patience_switch = ''
        # Name of this package (GitGutter or GitGutter-Edge)
        # stored in settings as kind of environment variable
        path = os.path.realpath(__file__)
        root = os.path.split(os.path.dirname(path))[1]
        self.package_name = os.path.splitext(root)[0]
        # built-in themes location
        self._builtin_theme_path = '%s/%s/themes' % (
            'Packages' if ST3 else '..', self.package_name)
        # cached theme path to reduce calls of find_resources
        self._theme_path = ''

    def get(self, key, default=None):
        if self._settings is None or not self._settings.has(key):
            self.load_settings()
        return self._settings.get(key, default)

    def set(self, key, value):
        if self._settings is None:
            self.load_settings()
        return self._settings.set(key, value)

    def load_settings(self):
        self._settings = sublime.load_settings('GitGutter.sublime-settings')
        self._user_settings = sublime.load_settings(
            'Preferences.sublime-settings')

        # Git Binary Setting
        git_binary_setting = (
            self._user_settings.get("git_binary") or
            self._settings.get("git_binary"))
        if isinstance(git_binary_setting, dict):
            self.git_binary_path = git_binary_setting.get(sublime.platform())
            if not self.git_binary_path:
                self.git_binary_path = git_binary_setting.get('default')
        else:
            self.git_binary_path = git_binary_setting

        if self.git_binary_path:
            self.git_binary_path = os.path.expandvars(self.git_binary_path)
        elif self._git_binary_path_fallback:
            self.git_binary_path = self._git_binary_path_fallback
        elif ST3:
            self.git_binary_path = shutil.which("git")
            self._git_binary_path_fallback = self.git_binary_path
        else:
            git_exe = "git.exe" if sublime.platform() == "windows" else "git"
            for folder in os.environ["PATH"].split(os.pathsep):
                path = os.path.join(folder.strip('"'), git_exe)
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    self.git_binary_path = path
                    self._git_binary_path_fallback = path
                    break

        if not self.git_binary_path:
            if not self._git_binary_path_error_shown:
                self._git_binary_path_error_shown = True
                msg = ("Your Git binary cannot be found. If it is installed, "
                       "add it to your PATH environment variable, or add "
                       "a `git_binary` setting in the "
                       "`User/GitGutter.sublime-settings` file.")
                sublime.error_message(msg)
                raise ValueError("Git binary not found.")

        # Ignore White Space Setting
        self.ignore_whitespace = self._settings.get('ignore_whitespace')
        if self.ignore_whitespace == 'all':
            self.ignore_whitespace = '-w'
        elif self.ignore_whitespace == 'eol':
            self.ignore_whitespace = '--ignore-space-at-eol'
        else:
            self.ignore_whitespace = ''

        # Patience Setting
        self.patience_switch = ''
        if self._settings.get('patience'):
            self.patience_switch = '--patience'

    def get_compare_against(self, git_tree, view):
        """Return the compare target for a view.

        If interactivly specified a compare target for the view's repository,
        use it first, then try view's settings, which includes project
        settings and preferences. Finally try GitGutter.sublime-settings or
        fall back to HEAD if everything goes wrong to avoid exceptions.

        Arguments:
            git_tree    - real root path of the current work-tree
            view        - the view whose settings to query first
        """
        # Interactively specified compare target overrides settings.
        if git_tree in self._compare_against_mapping:
            return self._compare_against_mapping[git_tree]
        # Project settings and Preferences override plugin settings if set.
        compare = view.settings().get('git_gutter_compare_against')
        if not compare:
            compare = self.get('compare_against', 'HEAD')
        return compare

    def set_compare_against(self, git_tree, new_compare_against):
        """Assign a new compare target for current repository.

        Arguments:
            git_tree            - real root path of the current work-tree
            new_compare_against - new branch/tag/commit to cmpare against
        """
        self._compare_against_mapping[git_tree] = new_compare_against

    def get_show_in_minimap(self, view):
        """Read 'show_in_minimap' setting and apply appropiate limits."""
        if not ST3:
            return 0
        width = view.settings().get('git_gutter_show_in_minimap')
        if width is None:
            width = self.get('show_in_minimap', 1)
        return width if 0 <= width else 100000

    @property
    def default_theme_path(self):
        """Return the default theme path."""
        return self._builtin_theme_path + '/Default'

    @property
    def theme_path(self):
        """Read 'theme' setting and return path to gutter icons."""
        theme = self.get('theme', 'Default.gitgutter-theme')
        # rebuilt path if setting changed
        if theme != os.path.basename(self._theme_path):
            if ST3:
                themes = sublime.find_resources(theme)
                self._theme_path = os.path.dirname(themes[-1]) \
                    if themes else self.default_theme_path
            else:
                # ST2 doesn't support find_resource so use built-in themes only
                theme, _ = os.path.splitext(theme)
                self._theme_path = '/'.join((self._builtin_theme_path, theme))
        return self._theme_path


if 'settings' not in globals():
    settings = GitGutterSettings()
    if not ST3:
        plugin_loaded()
