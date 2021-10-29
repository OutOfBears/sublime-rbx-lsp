from LSP.plugin import AbstractPlugin
from LSP.plugin import register_plugin
from LSP.plugin import unregister_plugin
from LSP.plugin import DottedDict
from LSP.plugin.core.typing import Any, Callable, List, Dict, Mapping, Optional, Tuple
from LSP.plugin.core.protocol import Notification, WorkspaceFolder, DocumentUri
from LSP.plugin.core.types import ClientConfig
import sublime
import os
import urllib.request
import zipfile
import shutil
import tempfile

class SublimeRbxLua(AbstractPlugin):
    VSC_PLUGIN = "https://github.com/NightrainsRbx/RobloxLsp/releases/download/v{0}/robloxlsp-{0}.vsix"

    @classmethod
    def name(self) -> str:
        return "sublime-rbx-lsp"

    @classmethod
    def base_dir(self) -> str:
        return os.path.join(self.storage_path(), self.name())

    @classmethod
    def version_file(self) -> str:
        return os.path.join(self.base_dir(), "VERSION")

    @classmethod
    def rbx_storage(self) -> str:
        return os.path.join(self.base_dir(), "rbx")

    @classmethod
    def rbx_version_file(self) -> str:
        return os.path.join(self.rbx_storage(), "version.txt")

    @classmethod
    def zip_file(self) -> str:
        return os.path.join(self.base_dir(), "lsp.vsix")

    @classmethod
    def bin_platform(self) -> str:
        return {
            "linux": "Linux",
            "windows": "Windows",
            "osx": "macOS"
        }[sublime.platform()]

    @classmethod
    def bindir(cls) -> str:
        return os.path.join(cls.base_dir(), "bin", cls.bin_platform())

    @classmethod
    def needs_update_or_installation(self) -> bool:
        settings, _ = self.configuration()
        server_version = str(settings.get("server_version"))
        print(self.bindir())
        try:
            with open(self.version_file(), "r") as fp:
                needs_update = server_version != fp.read().strip()
                return needs_update

        except OSError:
            return True

    @classmethod
    def needs_rbx_update(self) -> Tuple[bool, str]:
        latest_version = urllib.request.urlopen("https://raw.githubusercontent.com/CloneTrooper1019/Roblox-Client-Tracker/roblox/version.txt")
        rbx_version = self.rbx_version_file()
        if os.path.isfile(rbx_version):
            with open(rbx_version, 'r') as file:
                current_version = file.read().strip()
                return latest_version == current_version, latest_version

        return False, latest_version


    @classmethod
    def install_rbx_files(self, version) -> None:
        auto_complete_metadata = os.path.join(self.rbx_storage(), "AutoCompleteMetadata.xml")
        api_dump = os.path.join(self.rbx_storage(), "API-Dump.json")
        urllib.request.urlretrieve("https://raw.githubusercontent.com/CloneTrooper1019/Roblox-Client-Tracker/roblox/AutocompleteMetadata.xml", auto_complete_metadata)
        urllib.request.urlretrieve("https://raw.githubusercontent.com/CloneTrooper1019/Roblox-Client-Tracker/roblox/API-Dump.json", api_dump)
        with open(self.rbx_version_file(), "w") as f:
            f.write(version)

    @classmethod
    def install_or_update(self) -> None:
        shutil.rmtree(self.base_dir(), ignore_errors=True)
        try:
            settings, _ = self.configuration()
            server_version = str(settings.get("server_version"))
            bin_platform = self.bin_platform()
            with tempfile.TemporaryDirectory() as tmp:
                downloaded_file = os.path.join(tmp, "lsp.vsix")
                urllib.request.urlretrieve(self.VSC_PLUGIN.format(server_version), downloaded_file)
                with zipfile.ZipFile(downloaded_file, "r") as z:
                    z.extractall(tmp)
                for root, dirs, files in os.walk(os.path.join(tmp, "extension", "server", "bin")):
                        for d in dirs:
                            if d != bin_platform:
                                shutil.rmtree(os.path.join(root, d))
                for root, dirs, files in os.walk(os.path.join(tmp, "extension", "server", "bin", bin_platform)):
                    for file in files:
                        os.chmod(os.path.join(root, file), 0o744)
                os.makedirs(self.storage_path(), exist_ok=True)
                shutil.move(os.path.join(tmp, "extension", "server"), self.base_dir())
            with open(self.version_file(), "w") as fp:
                fp.write(server_version)
        except Exception:
            shutil.rmtree(self.base_dir(), ignore_errors=True)
            raise

    @classmethod
    def configuration(self) -> Tuple[sublime.Settings, str]:
        base_name = "{}.sublime-settings".format(self.name())
        file_path = "Packages/{}/{}".format(self.name(), base_name)
        return sublime.load_settings(base_name), file_path

    @classmethod
    def additional_variables(self) -> Optional[Dict[str, str]]:
        settings, _ = self.configuration()
        return {
            "bin_platform": self.bin_platform(),
            "develop": str(settings.get("develop")),
            "debuggerPort": str(settings.get("debug_port")),
            "debuggerWait": str(settings.get("debug_wait"))
        }

    @classmethod
    def on_pre_start(self, window: sublime.Window, initiating_view: sublime.View,
                     workspace_folders: List[WorkspaceFolder], configuration: ClientConfig) -> Optional[str]:

        needs_update, version = self.needs_rbx_update()
        if needs_update:
            print("updating roblox...")
            self.install_rbx_files(version)
        else:
            print("roblox is up to date")

        return None

    @classmethod
    def on_open_uri_async(self, uri: DocumentUri, callback: Callable[[str, str, str], None]) -> bool:
        return False

    def on_pre_server_command(self, command: Mapping[str, Any], done_callback: Callable[[], None]) -> bool:
        cmd = command["command"]
        if cmd == "lua.config":
            return self._handle_lua_config_command(command["arguments"], done_callback)
        return super().on_pre_server_command(command, done_callback)

    def _handle_lua_config_command(self, args: List[Dict[str, Any]], done_callback: Callable[[], None]) -> bool:
        action = args[0]["action"]
        if action == "add" or action == "set":
            key = args[0]["key"]
            value = args[0]["value"]
            session = self.weaksession()
            if not session:
                return False
            window = session.window
            data = window.project_data()
            if not isinstance(data, dict):
                return False
            dd = DottedDict(data)
            key = "settings.LSP.LSP-lua.settings.{}".format(key)
            thelist = dd.get(key)
            if isinstance(thelist, list):
                if value not in thelist:
                    thelist.append(value)
            else:
                thelist = [value]
            dd.set(key, thelist)
            data = dd.get()
            window.set_project_data(data)
            done_callback()
            return True
        return False

def plugin_loaded() -> None:
    register_plugin(SublimeRbxLua)


def plugin_unloaded() -> None:
    unregister_plugin(SublimeRbxLua)