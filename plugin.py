from LSP.plugin import AbstractPlugin
from LSP.plugin import register_plugin
from LSP.plugin import unregister_plugin
from LSP.plugin import DottedDict
from LSP.plugin.core.typing import Any, Callable, List, Dict, Mapping, Optional, Tuple
from LSP.plugin.core.protocol import Notification, WorkspaceFolder, DocumentUri
from LSP.plugin.core.types import ClientConfig
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver
import threading
import sublime
import os
import urllib.request
import zipfile
import shutil
import tempfile
import json

def create_server(plugin):
    class ServerHandler(BaseHTTPRequestHandler):
        def _set_headers(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()

        def _write_json(self, data):
            self._set_headers()
            serialized = json.dumps(data)
            self.wfile.write(str.encode(serialized, "utf8"))

        def do_GET(self):
            self._write_json({ "test": True })

    return ServerHandler

class SublimeRbxLua(AbstractPlugin):
    VSC_PLUGIN = "https://github.com/NightrainsRbx/RobloxLsp/releases/download/v{0}/robloxlsp-{0}.vsix"

    http_server = None

    @classmethod
    def name(self) -> str:
        return "sublime-rbx-lsp"

    @classmethod
    def base_dir(self) -> str:
        return os.path.join(self.storage_path(), self.name())

    @classmethod
    def lsp_version_file(self) -> str:
        return os.path.join(self.base_dir(), "VERSION")

    @classmethod
    def lsp_zip_file(self) -> str:
        return os.path.join(self.base_dir(), "lsp.vsix")

    @classmethod
    def rbx_storage(self) -> str:
        return os.path.join(self.base_dir(), "rbx")

    @classmethod
    def rbx_version_file(self) -> str:
        return os.path.join(self.rbx_storage(), "version.txt")

    @classmethod
    def bin_platform(self) -> str:
        return {
            "linux": "Linux",
            "windows": "Windows",
            "osx": "macOS"
        }[sublime.platform()]

    @classmethod
    def bin_dir(cls) -> str:
        return os.path.join(cls.base_dir(), "bin", cls.bin_platform())

    @classmethod
    def get_latest_lsp_version(self) -> str:
        response = urllib.request.urlopen("https://api.github.com/repos/NightrainsRbx/RobloxLsp/releases/latest")
        response_data = json.loads(response.read().decode(response.info().get_param('charset') or 'utf-8'))
        return response_data["name"]

    @classmethod
    def get_current_lsp_version(self) -> str:
        with open(self.lsp_version_file(), "r") as fp:
            return fp.read().strip()

    @classmethod
    def needs_update_or_installation(self) -> bool:
        # This is handled by the next function, and been removed to
        # limit the amount of requests we make, so we don't get rate-limited.
        return True

    @classmethod
    def needs_lsp_update(self) -> Tuple[bool, str]:
        latest_version = None
        needs_update = True

        try:
            latest_version = self.get_latest_lsp_version()
            current_version = self.get_current_lsp_version()
            needs_update = current_version != latest_version

        except OSError:
            needs_update = True

        return (needs_update, latest_version)

    @classmethod
    def needs_rbx_update(self) -> Tuple[bool, str]:
        latest_version = None
        needs_update = True

        try:
            latest_version = urllib.request.urlopen("https://raw.githubusercontent.com/CloneTrooper1019/Roblox-Client-Tracker/roblox/version.txt").read().decode()
            rbx_version = self.rbx_version_file()
            if os.path.isfile(rbx_version):
                with open(rbx_version, 'r') as file:
                    current_version = file.read().strip()
                    needs_update = latest_version == current_version

        except Exception:
            needs_update = True

        return (needs_update, latest_version)

    @classmethod
    def install_rbx_files(self, version) -> None:
        auto_complete_metadata = os.path.join(self.rbx_storage(), "AutoCompleteMetadata.xml")
        api_dump = os.path.join(self.rbx_storage(), "API-Dump.json")
        urllib.request.urlretrieve("https://raw.githubusercontent.com/CloneTrooper1019/Roblox-Client-Tracker/roblox/AutocompleteMetadata.xml", auto_complete_metadata)
        urllib.request.urlretrieve("https://raw.githubusercontent.com/CloneTrooper1019/Roblox-Client-Tracker/roblox/API-Dump.json", api_dump)

        with open(self.rbx_version_file(), "w") as f:
            f.write(version)

    @classmethod
    def install_lsp_files(self, version) -> None:
        shutil.rmtree(self.base_dir(), ignore_errors=True)
        try:
            bin_platform = self.bin_platform()
            with tempfile.TemporaryDirectory() as tmp:
                downloaded_file = os.path.join(tmp, "lsp.vsix")
                urllib.request.urlretrieve(self.VSC_PLUGIN.format(version), downloaded_file)
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

            with open(self.lsp_version_file(), "w") as fp:
                fp.write(version)

        except Exception:
            shutil.rmtree(self.base_dir(), ignore_errors=True)
            raise

    @classmethod
    def install_or_update(self) -> None:
        has_lsp_update, lsp_version = self.needs_lsp_update()
        has_rbx_update, rbx_version = self.needs_rbx_update()

        if has_lsp_update and lsp_version != None:
            self.install_lsp_files(lsp_version)
        if has_rbx_update and rbx_version != None:
            self.install_rbx_files(rbx_version)

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
            "locale": str(settings.get("locale")),
            "develop": str(settings.get("develop")),
            "debuggerPort": str(settings.get("debug_port")),
            "debuggerWait": str(settings.get("debug_wait"))
        }

    @classmethod
    def on_pre_start(self, window: sublime.Window, initiating_view: sublime.View,
                     workspace_folders: List[WorkspaceFolder], configuration: ClientConfig) -> Optional[str]:

        # TODO: run server
        # settings, _ = self.configuration()
        # container = settings.get("settings")
        # port = container != None and container.get("robloxLsp.misc.serverPort", 0) or 0
        # if port > 0:
        #     print("got port", port)
        #     self.start_web_server(port)

        return None

    @classmethod
    def start_web_server(self, port: int):
        def start_server(self):
            print("running port on", port, self)
            server = HTTPServer(("localhost", port), create_server(self))
            server.serve_forever()
            server.shutdown
            self.http_server = server

        thread = threading.Thread(target=start_server, args=[self])
        thread.start()

    @classmethod
    def on_session_end_async(self) -> None:
        if self.http_server:
            self.http_server.shutdown()
        self.http_server = None

    def on_pre_server_command(self, command: Mapping[str, Any], done_callback: Callable[[], None]) -> bool:
        cmd = command["command"]
        if cmd == "robloxLsp.config":
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
            key = "settings.LSP.sublime-rbx-lsp.settings.{}".format(key)
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