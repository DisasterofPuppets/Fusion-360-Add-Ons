"""
=================================================================================================
 HotkeyAssignment.py  -  Fusion 360 Add-In
=================================================================================================
PURPOSE
    Adds two controls (UTILITIES tab > Add-Ins panel, Design workspace):

    "Hotkey Assignment" - a direct single-click button - opens a window listing every command
    Fusion currently has a keyboard shortcut recorded for:

        Function Name | Hotkey | [Change]

    - grouped by workspace (Design/General, Animation, Manufacture, Drawing, Electronics,
      Simulation - a best-effort grouping, see classify_workspace()), with a Workspace dropdown
      to filter down to just one group
    - a Search box filters by name or internal command ID, on top of any workspace filter
    - the Hotkey column is suffixed "· Custom" for anything you've changed from Fusion's own
      default, blank suffix if it's still at the factory key
    - Change opens Fusion's own native "assign new hotkey" popup for that command

    "Hotkey Tools" - a dropdown/flyout next to it - nests three single-click commands (see NOTES
    item 6 for why these aren't buttons inside the window itself):
        - Export Current Hotkeys saves the current full hotkey set to a .json file you choose
        - Import Hotkeys loads a previously exported .json file (validated before anything is
          touched)
        - Reset to Default: first click builds a default_hotkeys.json baseline automatically
          from the bindings Fusion itself currently flags as isDefault:true (see NOTES, item 4);
          click again any time afterwards to restore that baseline

PREREQUISITES
    - Fusion 360 desktop, Windows only (see NOTES, item 5)
    - No third-party Python packages required. Only standard library modules are used
      (json, os, glob, shutil, traceback, datetime) - all already available inside Fusion's
      bundled Python interpreter.

INSTALL
    1. Copy this whole "HotkeyAssignment" folder (keep the folder name, the .py file inside it,
       and the Resources subfolder together) into your Fusion 360 Add-Ins folder:
           %APPDATA%\\Autodesk\\Autodesk Fusion 360\\API\\AddIns\\
    2. In Fusion: UTILITIES tab > Add-Ins > Scripts and Add-Ins > ADD-INS tab > "+" (Add) >
       select the HotkeyAssignment folder > Run.
    3. Tick "Run on Startup" there if you want it to load automatically every time.

*** NOTHING IN THIS FILE NEEDS TO BE EDITED TO GET STARTED ***
    Reset to Default builds its own baseline file the first time you click it - see NOTES item 4.

NOTES / KNOWN LIMITATIONS - please read before relying on this
    1. Fusion has NO public API to programmatically assign a hotkey to a command. Confirmed
       against the Fusion API forums and existing community add-ins. The only reliable
       mechanism found is Fusion's own text command "HotKey.Dialog <command_id>", which opens
       Fusion's built-in assign-shortcut popup (key capture + conflict/override prompt are all
       handled by Fusion itself). The Change button uses this.
    2. Fusion stores your live hotkey bindings in a per-install JSON file at:
           %LOCALAPPDATA%\\Autodesk\\Autodesk Fusion 360\\<install-id>\\hotkey.json
       Confirmed by diffing that folder before/after changing a shortcut through Fusion's own
       UI. This is an UNDOCUMENTED, UNSUPPORTED file - Autodesk can change its location or
       format in a future release without notice. Every write this add-in makes is preceded by
       an automatic timestamped backup (see BACKUPS below).
    3. Restart Fusion 360 after using Import or Reset to Default. Whether Fusion live-reloads
       hotkey.json while running has not been proven, so this add-in always treats a restart
       as required and tells you so.
    4. Reset to Default: Autodesk does not publish a factory-default hotkeys file, so rather than
       guess, the first time you click Reset to Default (and no default_hotkeys.json exists yet
       in this folder) the add-in offers to build one from your CURRENT hotkey.json, keeping only
       the bindings Fusion itself already flags "isDefault": true - i.e. keys you have never
       changed. Anything you had already customised before that first click keeps no record of
       its original key (Fusion's file doesn't retain it once a binding moves), so those specific
       commands can't be reset this way - only fixed by hand or by re-importing an old export/
       backup. Every click after the baseline exists just restores it, backing up the live file
       first as always.
    5. Windows only. The hotkey.json path above is a Windows AppData path and has not been
       tested or adapted for macOS - on a Mac this add-in will report that it can't find the
       file rather than silently doing nothing.
    6. Import/Export/Reset are separate ribbon buttons, not widgets inside the Hotkey Assignment
       window. They started out as buttons inside that window, but Fusion's native file-picker
       (ui.createFileDialog, used by Import/Export) opened from inside an already-running
       command's event handler leaves that command unresponsive to further input afterwards - a
       second click did nothing until the whole window was closed and reopened. Reset's plain
       confirm box didn't have this problem, only the file dialog did. Making all three separate,
       single-purpose commands (each using Command.doExecute(False) to run with no visible
       dialog) sidesteps the nesting entirely.
    7. Workspace grouping (classify_workspace()) is a pattern match against command_id prefixes
       actually seen in a real hotkey.json, not an official Autodesk mapping - Autodesk doesn't
       publish one. Render has no distinct prefix found in practice, so it's not a selectable
       group; anything Render-specific lands in Design/General along with genuinely shared core
       commands (Copy/Undo/Save/...). If a command looks misclassified, that's this heuristic
       being wrong, not the underlying data - worth a look if it happens often.

BACKUPS
    Before every write to hotkey.json, the existing file is copied to:
        <same folder>\\hotkey_backup_<YYYYMMDD_HHMMSS>.json
    Old backups are never deleted automatically - clean them up by hand if the folder gets busy.

ERROR LOG
    Unhandled errors are appended to "error_log.txt" next to this script (full traceback) as
    well as shown in a Fusion message box.
=================================================================================================
"""

import adsk.core
import traceback
import json
import os
import glob
import shutil
from datetime import datetime

# -------------------------------------------------------------------------------------------
# Constants / paths
# -------------------------------------------------------------------------------------------
_CMD_ID = 'HotkeyAssignmentCmd'
_CMD_NAME = 'Hotkey Assignment'
_CMD_TOOLTIP = 'View, search, and edit Fusion 360 keyboard shortcuts'
_PANEL_ID = 'SolidScriptsAddinsPanel'
_WORKSPACE_ID = 'FusionSolidEnvironment'
_MAX_TABLE_ROWS = 400  # safety cap for an unfiltered list - narrow with search to see more

# Import/Export/Reset used to be buttons inside the Hotkey Assignment table window, but Fusion's
# native file-picker (ui.createFileDialog) opened from inside an already-running command's event
# handler leaves that command's input events unresponsive afterwards - a second click on Import
# or Export did nothing until the whole window was closed and reopened. Plain message boxes
# (Reset's confirm prompt) don't have this problem, only the file dialog does. Splitting these
# three into their own single-purpose ribbon buttons avoids the nesting entirely - each one is a
# fresh command every click, not a widget living inside another still-open dialog.
_CMD_ID_IMPORT = 'HotkeyAssignmentImportCmd'
_CMD_ID_EXPORT = 'HotkeyAssignmentExportCmd'
_CMD_ID_RESET = 'HotkeyAssignmentResetCmd'

_WORKSPACE_GROUPS = ('Design / General', 'Animation', 'Manufacture', 'Drawing', 'Electronics', 'Simulation')

_ADDIN_FOLDER = os.path.dirname(os.path.realpath(__file__))
_ERROR_LOG_PATH = os.path.join(_ADDIN_FOLDER, 'error_log.txt')
_DEFAULT_HOTKEYS_PATH = os.path.join(_ADDIN_FOLDER, 'default_hotkeys.json')

# ButtonRowCommandInput items require a real icon resource folder (an empty string throws
# "Invalid argument icon") - these are shared across every button of each kind, including
# every row's Change button, which all point at the same ChangeIcon folder.
_ICON_IMPORT = os.path.join(_ADDIN_FOLDER, 'Resources', 'ImportIcon')
_ICON_EXPORT = os.path.join(_ADDIN_FOLDER, 'Resources', 'ExportIcon')
_ICON_RESET = os.path.join(_ADDIN_FOLDER, 'Resources', 'ResetIcon')
_ICON_CHANGE = os.path.join(_ADDIN_FOLDER, 'Resources', 'ChangeIcon')
_ICON_TOOLS = os.path.join(_ADDIN_FOLDER, 'Resources', 'HotkeyToolsIcon')

# Import/Export/Reset are nested inside this dropdown/flyout rather than sitting as their own
# flat buttons on the panel - "Hotkey Assignment" itself stays a direct single-click button.
_DROPDOWN_ID = 'HotkeyToolsDropdown'
_DROPDOWN_NAME = 'Hotkey Tools'

# -------------------------------------------------------------------------------------------
# Module state (Fusion add-in convention: keep event handler references alive, and keep the
# small amount of state the UI needs between callbacks)
# -------------------------------------------------------------------------------------------
_app = None
_ui = None
_handlers = []
_current_rows = []      # list of {'command_id', 'name', 'keys'} built from hotkey.json
_row_command_map = {}   # maps a "Change" button's input id -> command_id, rebuilt on every render
_render_generation = 0  # guarantees unique command-input ids across re-renders (search filtering)


# =============================================================================================
# Error handling
# =============================================================================================
def log_error(context_msg):
    """Writes a timestamped traceback to error_log.txt and shows it in a message box.
    Called from every top-level except block so nothing fails silently."""
    tb = traceback.format_exc()
    try:
        with open(_ERROR_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write('\n' + '=' * 80 + '\n')
            f.write('{}  -  {}\n'.format(datetime.now().isoformat(timespec='seconds'), context_msg))
            f.write(tb)
    except Exception:
        pass  # if we can't even write the log, still fall through to the message box
    if _ui:
        _ui.messageBox(
            '{}\n\n{}\n\n(Full details appended to error_log.txt next to this add-in.)'.format(context_msg, tb)
        )


# =============================================================================================
# hotkey.json handling
# =============================================================================================
def find_hotkey_file():
    """Locates Fusion's live hotkey.json. See NOTES item 2/5 in the header for why this path
    and why Windows-only. Raises FileNotFoundError with a clear message if it can't be found."""
    local_appdata = os.environ.get('LOCALAPPDATA')
    if not local_appdata:
        raise FileNotFoundError(
            'LOCALAPPDATA environment variable was not found - this add-in only supports Windows.'
        )
    pattern = os.path.join(local_appdata, 'Autodesk', 'Autodesk Fusion 360', '*', 'hotkey.json')
    matches = glob.glob(pattern)
    if not matches:
        raise FileNotFoundError(
            'Could not find hotkey.json under:\n{}\n\n'
            'Fusion may use a different path on your system/version. Search for "hotkey.json" '
            'under %LOCALAPPDATA%\\Autodesk manually and update find_hotkey_file() with the '
            'confirmed path.'.format(pattern)
        )
    # if more than one install exists, use whichever was written to most recently
    matches.sort(key=os.path.getmtime, reverse=True)
    return matches[0]


def load_hotkeys():
    """Returns (parsed_json_dict, path_to_file)."""
    path = find_hotkey_file()
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data, path


def validate_hotkey_data(data):
    """Structural check against the schema Fusion's own hotkey.json uses, run on every Import
    and on default_hotkeys.json before either is written over the live file.
    Returns (is_valid: bool, error_message: str)."""
    if not isinstance(data, dict):
        return False, 'Top level of the file must be a JSON object.'
    if 'hotkeys' not in data:
        return False, 'Missing required "hotkeys" key at the top level.'
    entries = data['hotkeys']
    if not isinstance(entries, list) or len(entries) == 0:
        return False, '"hotkeys" must be a non-empty list.'

    first = entries[0]
    if not isinstance(first, dict) or 'file_version' not in first:
        return False, 'First entry in "hotkeys" must contain "file_version" (Fusion currently uses "2").'

    seen_sequences = set()
    for i, entry in enumerate(entries[1:], start=1):
        if not isinstance(entry, dict):
            return False, 'Entry #{} is not a JSON object.'.format(i)
        seq = entry.get('hotkey_sequence')
        if not isinstance(seq, str) or not seq:
            return False, 'Entry #{} is missing a valid "hotkey_sequence" string.'.format(i)
        if seq in seen_sequences:
            return False, 'Duplicate "hotkey_sequence" entry for "{}" (entry #{}).'.format(seq, i)
        seen_sequences.add(seq)

        commands = entry.get('commands')
        if not isinstance(commands, list) or len(commands) == 0:
            return False, 'Entry #{} ("{}") has no "commands" list.'.format(i, seq)
        for j, cmd in enumerate(commands):
            if not isinstance(cmd, dict) or not cmd.get('command_id'):
                return False, 'Entry #{} ("{}"), command #{} is missing a valid "command_id".'.format(i, seq, j)

    return True, ''


def backup_hotkey_file(path):
    """Copies the live hotkey.json to a timestamped backup in the same folder before any write.
    Returns the backup path."""
    backup_name = 'hotkey_backup_{}.json'.format(datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup_path = os.path.join(os.path.dirname(path), backup_name)
    shutil.copyfile(path, backup_path)
    return backup_path


def get_display_name(command_id):
    """Looks up the human-readable command name from the running Fusion session. Falls back to
    the raw command_id when the owning workspace/extension (Simulation, Electronics, CAM, ...)
    isn't currently loaded, so its CommandDefinition doesn't exist yet."""
    try:
        cmd_def = _ui.commandDefinitions.itemById(command_id)
        if cmd_def and cmd_def.name:
            return cmd_def.name
    except Exception:
        pass
    return command_id


def classify_workspace(command_id):
    """Best-effort grouping by workspace, based on naming patterns seen in Fusion's own command
    IDs - NOT an official Autodesk mapping (Autodesk doesn't publish one). Render has no
    distinct prefix found in practice, so anything Render-specific ends up in Design/General
    along with the core commands (Copy/Undo/Save/...) that are genuinely shared everywhere. If
    something lands in the wrong group, that's this heuristic being wrong, not a data problem -
    worth flagging so the pattern list can be tightened."""
    if command_id.startswith('Electron::'):
        return 'Electronics'
    if command_id.startswith('Sim'):
        return 'Simulation'
    if command_id.startswith('Iron') or command_id.startswith('CAM'):
        return 'Manufacture'
    if command_id.startswith('FusionDrawing') or command_id.startswith('FDWG') or command_id.startswith('Drawing'):
        return 'Drawing'
    if command_id.startswith('Publisher'):
        return 'Animation'
    return 'Design / General'


def build_rows(data):
    """Turns the parsed hotkey.json into one row per command_id (a command can have more than
    one hotkey_sequence bound to it, e.g. Delete on both Backspace and Delete - those are
    joined with a comma), sorted by workspace group then alphabetically by display name.

    Fusion often reuses one generic label across several distinct, context-specific command
    IDs - e.g. "Copy" is the display name for 8 different command_ids (ctrl+c doing different
    things depending on what's selected: sketch geometry, MText, a custom table, ...). Left
    alone that shows up as several identical-looking rows with no way to tell which is which,
    so any name that isn't unique gets its command_id appended in brackets.

    Each row also gets a 'workspace' group (see classify_workspace) and an 'is_default' flag -
    True only if every binding for that command_id is still one Fusion itself flags
    isDefault:true; False (shown as "Custom") if any of them was user-assigned."""
    cmd_to_bindings = {}
    for entry in data.get('hotkeys', []):
        seq = entry.get('hotkey_sequence')
        if seq is None:
            continue
        for cmd in entry.get('commands', []):
            cid = cmd.get('command_id')
            if not cid:
                continue
            cmd_to_bindings.setdefault(cid, []).append((seq, cmd.get('isDefault') is True))

    rows = []
    for cid, bindings in cmd_to_bindings.items():
        seqs = [b[0] for b in bindings]
        is_default = all(b[1] for b in bindings)
        rows.append({
            'command_id': cid,
            'name': get_display_name(cid),
            'keys': ', '.join(sorted(set(seqs))),
            'workspace': classify_workspace(cid),
            'is_default': is_default,
        })

    name_counts = {}
    for r in rows:
        name_counts[r['name']] = name_counts.get(r['name'], 0) + 1
    for r in rows:
        if name_counts[r['name']] > 1:
            r['name'] = '{} ({})'.format(r['name'], r['command_id'])

    workspace_order = {name: i for i, name in enumerate(_WORKSPACE_GROUPS)}
    rows.sort(key=lambda r: (workspace_order.get(r['workspace'], len(_WORKSPACE_GROUPS)), r['name'].lower()))
    return rows


# =============================================================================================
# Actions - Change / Export / Import / Reset
# =============================================================================================
def action_change(command_id):
    """Opens Fusion's own native assign-hotkey popup for one command. This is the only proven
    write path - see NOTES item 1."""
    try:
        _app.executeTextCommand('HotKey.Dialog {}'.format(command_id))
    except Exception:
        log_error('Could not open the hotkey dialog for "{}"'.format(command_id))


def action_export():
    try:
        _, path = load_hotkeys()
        file_dlg = _ui.createFileDialog()
        file_dlg.isMultiSelectEnabled = False
        file_dlg.title = 'Export Current Hotkeys'
        file_dlg.filter = 'JSON files (*.json)'
        file_dlg.initialFilename = 'fusion_hotkeys_{}.json'.format(datetime.now().strftime('%Y%m%d_%H%M%S'))
        if file_dlg.showSave() != adsk.core.DialogResults.DialogOK:
            return
        shutil.copyfile(path, file_dlg.filename)
        _ui.messageBox('Exported to:\n{}'.format(file_dlg.filename))
    except Exception:
        log_error('Export Current Hotkeys failed')


def action_import():
    try:
        file_dlg = _ui.createFileDialog()
        file_dlg.isMultiSelectEnabled = False
        file_dlg.title = 'Import Hotkeys'
        file_dlg.filter = 'JSON files (*.json)'
        if file_dlg.showOpen() != adsk.core.DialogResults.DialogOK:
            return

        with open(file_dlg.filename, 'r', encoding='utf-8') as f:
            try:
                imported = json.load(f)
            except ValueError as e:
                _ui.messageBox('That file is not valid JSON and was not imported.\n\nDetail: {}'.format(e))
                return

        is_valid, err = validate_hotkey_data(imported)
        if not is_valid:
            _ui.messageBox(
                'That file does not match Fusion\'s hotkey format and was not imported.\n\n'
                'Problem: {}'.format(err)
            )
            return

        current_path = find_hotkey_file()
        confirm = _ui.messageBox(
            'This will replace your current hotkey mappings with the ones in:\n{}\n\n'
            'Your current mappings will be backed up first. Restart Fusion 360 afterwards to '
            'apply the change.\n\nContinue?'.format(file_dlg.filename),
            'Confirm Import', adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType
        )
        if confirm != adsk.core.DialogResults.DialogYes:
            return

        backup_path = backup_hotkey_file(current_path)
        with open(current_path, 'w', encoding='utf-8') as f:
            json.dump(imported, f)

        _ui.messageBox(
            'Import complete.\nYour previous hotkeys were backed up to:\n{}\n\n'
            'Restart Fusion 360 now to apply the imported hotkeys.'.format(backup_path)
        )
    except Exception:
        log_error('Import Hotkeys failed')


def build_default_baseline(data):
    """Filters a parsed hotkey.json down to only the bindings Fusion itself marks as
    isDefault:true - i.e. bindings that are still sitting at Fusion's own factory-set key.
    Anything the user has already changed (isDefault:false) is left out rather than guessed at,
    because once a binding is moved, Fusion's file no longer records what its original key was.
    This is how default_hotkeys.json gets built automatically - see action_reset()."""
    source_entries = data.get('hotkeys', [])
    file_version = source_entries[0].get('file_version', '2') if source_entries else '2'
    filtered = [{'file_version': file_version}]
    for entry in source_entries[1:]:
        seq = entry.get('hotkey_sequence')
        default_cmds = [c for c in entry.get('commands', []) if c.get('isDefault') is True]
        if seq and default_cmds:
            filtered.append({'hotkey_sequence': seq, 'commands': default_cmds})
    return {'hotkeys': filtered}


def action_reset():
    try:
        if not os.path.isfile(_DEFAULT_HOTKEYS_PATH):
            offer = _ui.messageBox(
                'No default baseline saved yet.\n\n'
                'Autodesk doesn\'t publish factory-default hotkeys, but Fusion tags every '
                'binding in your current hotkey file with isDefault true/false. I can build a '
                'baseline from just the isDefault:true ones - those are still sitting at '
                'Fusion\'s factory key.\n\n'
                'Anything you\'ve already customised (isDefault:false) can\'t be recovered to '
                'its original key this way, since Fusion stops recording that once you move it '
                '- those would need fixing by hand.\n\n'
                'Build this baseline now? Nothing changes yet - use Reset to Default again '
                'afterwards to actually apply it.',
                'No Default Baseline Yet', adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                adsk.core.MessageBoxIconTypes.QuestionIconType
            )
            if offer != adsk.core.DialogResults.DialogYes:
                return

            data, _ = load_hotkeys()
            baseline = build_default_baseline(data)
            is_valid, err = validate_hotkey_data(baseline)
            if not is_valid:
                _ui.messageBox('Could not build a valid baseline from your current file.\n\nProblem: {}'.format(err))
                return
            with open(_DEFAULT_HOTKEYS_PATH, 'w', encoding='utf-8') as f:
                json.dump(baseline, f)
            _ui.messageBox(
                'Baseline saved to:\n{}\n\n'
                'Click Reset to Default again whenever you want to apply it.'.format(_DEFAULT_HOTKEYS_PATH)
            )
            return

        confirm = _ui.messageBox(
            'This will reset all hotkeys to your saved default baseline, are you sure?',
            'Reset to Default', adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.WarningIconType
        )
        if confirm != adsk.core.DialogResults.DialogYes:
            return

        with open(_DEFAULT_HOTKEYS_PATH, 'r', encoding='utf-8') as f:
            defaults = json.load(f)
        is_valid, err = validate_hotkey_data(defaults)
        if not is_valid:
            _ui.messageBox('default_hotkeys.json is not valid and was not applied.\n\nProblem: {}'.format(err))
            return

        current_path = find_hotkey_file()
        backup_path = backup_hotkey_file(current_path)
        with open(current_path, 'w', encoding='utf-8') as f:
            json.dump(defaults, f)

        _ui.messageBox(
            'Reset complete.\nYour previous hotkeys were backed up to:\n{}\n\n'
            'Restart Fusion 360 now to apply the defaults.'.format(backup_path)
        )
    except Exception:
        log_error('Reset to Default failed')


# =============================================================================================
# Table rendering
# =============================================================================================
def render_table(table, top_inputs, filter_text, workspace_filter):
    """Clears and repopulates the table (header + data rows) from _current_rows, applying the
    search text and workspace filters. When showing every workspace, a bold divider row is
    inserted ahead of each group so the list still reads as grouped rather than one flat blob.
    Uses a fresh generation number in every child input id so re-rendering never collides with
    inputs from the previous render."""
    global _row_command_map, _render_generation
    _row_command_map = {}
    _render_generation += 1
    gen = _render_generation

    table.clear()

    h_name = top_inputs.addTextBoxCommandInput('h_name_g{}'.format(gen), '', '<b>Function Name</b>', 1, True)
    h_key = top_inputs.addTextBoxCommandInput('h_key_g{}'.format(gen), '', '<b>Hotkey</b>', 1, True)
    h_change = top_inputs.addTextBoxCommandInput('h_change_g{}'.format(gen), '', '<b>Change</b>', 1, True)
    table.addCommandInput(h_name, 0, 0)
    table.addCommandInput(h_key, 0, 1)
    table.addCommandInput(h_change, 0, 2)

    filter_lower = (filter_text or '').strip().lower()
    rows = _current_rows
    if filter_lower:
        rows = [r for r in rows if filter_lower in r['name'].lower() or filter_lower in r['command_id'].lower()]
    if workspace_filter and workspace_filter != 'All':
        rows = [r for r in rows if r['workspace'] == workspace_filter]

    truncated = len(rows) > _MAX_TABLE_ROWS
    rows = rows[:_MAX_TABLE_ROWS]

    row_index = 1  # row 0 is the header
    last_workspace = None
    show_groups = not workspace_filter or workspace_filter == 'All'
    for i, row in enumerate(rows):
        if show_groups and row['workspace'] != last_workspace:
            last_workspace = row['workspace']
            # Column-spanning a single cell across all 3 columns threw "overlap with existing
            # table cells" (Fusion's span semantics didn't match what was tried). Simpler and
            # proven: three separate cells per row like every data row, just with the group name
            # only in the first one.
            grp_name = top_inputs.addTextBoxCommandInput(
                'grp_name_g{}_{}'.format(gen, i), '', '<b>{}</b>'.format(row['workspace']), 1, True
            )
            grp_key = top_inputs.addTextBoxCommandInput('grp_key_g{}_{}'.format(gen, i), '', '', 1, True)
            grp_change = top_inputs.addTextBoxCommandInput('grp_change_g{}_{}'.format(gen, i), '', '', 1, True)
            table.addCommandInput(grp_name, row_index, 0)
            table.addCommandInput(grp_key, row_index, 1)
            table.addCommandInput(grp_change, row_index, 2)
            row_index += 1

        keys_text = row['keys'] or '(none)'
        if not row['is_default']:
            keys_text += '  ·  Custom'
        name_in = top_inputs.addTextBoxCommandInput('r_name_g{}_{}'.format(gen, i), '', row['name'], 1, True)
        name_in.tooltip = row['command_id']  # power-user reference without a 4th column
        key_in = top_inputs.addTextBoxCommandInput('r_key_g{}_{}'.format(gen, i), '', keys_text, 1, True)
        # TableCommandInput does not support ButtonRowCommandInput as a cell (throws
        # "unsupported command input type"). A BoolValueCommandInput with isCheckBox=False and
        # a real icon folder IS a supported cell type and renders as an actual clickable button
        # rather than a checkbox - that's the combination that works inside a table.
        change_in = top_inputs.addBoolValueInput('change_g{}_{}'.format(gen, i), 'Change', False, _ICON_CHANGE, False)
        table.addCommandInput(name_in, row_index, 0)
        table.addCommandInput(key_in, row_index, 1)
        table.addCommandInput(change_in, row_index, 2)
        _row_command_map[change_in.id] = row['command_id']
        row_index += 1

    if truncated:
        _ui.messageBox('Showing the first {} matches - narrow your search to see the rest.'.format(_MAX_TABLE_ROWS))


# =============================================================================================
# Command event handlers
# =============================================================================================
class HotkeyCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            global _current_rows

            try:
                data, _ = load_hotkeys()
            except FileNotFoundError as e:
                _ui.messageBox(str(e))
                return  # leave the (empty) dialog rather than build a table with nothing to show

            _current_rows = build_rows(data)

            cmd = args.command
            cmd.isRepeatable = False
            cmd.setDialogInitialSize(760, 640)
            cmd.setDialogMinimumSize(520, 420)

            inputs = cmd.commandInputs

            inputs.addStringValueInput('searchBox', 'Search', '')

            ws_dropdown = inputs.addDropDownCommandInput(
                'workspaceFilter', 'Workspace', adsk.core.DropDownStyles.TextListDropDownStyle
            )
            ws_dropdown.listItems.add('All', True)
            for name in _WORKSPACE_GROUPS:
                ws_dropdown.listItems.add(name, False)

            table = inputs.addTableCommandInput(
                'hotkeyTable', 'Hotkeys ({} found)'.format(len(_current_rows)), 3, '3:2:1'
            )
            table.isFullWidth = True
            table.maximumVisibleRows = 18

            render_table(table, inputs, '', 'All')

            on_execute = HotkeyExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)

            on_input_changed = HotkeyInputChangedHandler()
            cmd.inputChanged.add(on_input_changed)
            _handlers.append(on_input_changed)

            on_destroy = HotkeyDestroyHandler()
            cmd.destroy.add(on_destroy)
            _handlers.append(on_destroy)

        except Exception:
            log_error('Failed to open the Hotkey Assignment window')


class HotkeyInputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        global _current_rows
        try:
            changed = args.input
            inputs = args.inputs
            table = inputs.itemById('hotkeyTable')
            search = inputs.itemById('searchBox')
            ws_dropdown = inputs.itemById('workspaceFilter')
            current_search = search.value if search else ''
            current_ws = ws_dropdown.selectedItem.name if ws_dropdown and ws_dropdown.selectedItem else 'All'

            if changed.id in ('searchBox', 'workspaceFilter'):
                render_table(table, inputs, current_search, current_ws)
                return

            if changed.id in _row_command_map:
                changed.value = False  # momentary press, not a persistent checkbox
                command_id = _row_command_map[changed.id]
                action_change(command_id)
                # HotKey.Dialog is Fusion's own popup - refresh once the user is back here
                try:
                    data, _ = load_hotkeys()
                    _current_rows = build_rows(data)
                except FileNotFoundError:
                    pass
                render_table(table, inputs, current_search, current_ws)
                return

        except Exception:
            log_error('Error handling a Hotkey Assignment window action')


class HotkeyExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        pass  # nothing to commit - every action already happens live via inputChanged


class HotkeyDestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        pass


class ImportCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Import/Export/Reset are single-purpose, no-dialog commands (see the note by _CMD_ID_IMPORT
    for why they're separate from the table window). doExecute(False) fires the command
    immediately without ever showing an empty OK/Cancel dialog."""
    def notify(self, args):
        try:
            action_import()
            args.command.doExecute(False)
        except Exception:
            log_error('Import Hotkeys failed')


class ExportCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            action_export()
            args.command.doExecute(False)
        except Exception:
            log_error('Export Current Hotkeys failed')


class ResetCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            action_reset()
            args.command.doExecute(False)
        except Exception:
            log_error('Reset to Default failed')


# =============================================================================================
# Add-in entry points
# =============================================================================================
def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        cmd_defs = _ui.commandDefinitions
        workspace = _ui.workspaces.itemById(_WORKSPACE_ID)
        panel = workspace.toolbarPanels.itemById(_PANEL_ID)

        # "Hotkey Assignment" - direct single-click button, straight on the panel.
        existing = cmd_defs.itemById(_CMD_ID)
        if existing:
            existing.deleteMe()
        main_resource_folder = os.path.join(_ADDIN_FOLDER, 'Resources', 'HotkeyAssignmentCmd')
        main_cmd_def = cmd_defs.addButtonDefinition(_CMD_ID, _CMD_NAME, _CMD_TOOLTIP, main_resource_folder)
        on_created = HotkeyCommandCreatedHandler()
        main_cmd_def.commandCreated.add(on_created)
        _handlers.append(on_created)
        if panel and not panel.controls.itemById(_CMD_ID):
            panel.controls.addCommand(main_cmd_def)

        # "Hotkey Tools" - dropdown/flyout on the same panel, holding Import/Export/Reset.
        dropdown = panel.controls.itemById(_DROPDOWN_ID) if panel else None
        if panel and not dropdown:
            dropdown = panel.controls.addDropDown(_DROPDOWN_NAME, _ICON_TOOLS, _DROPDOWN_ID)

        tool_specs = (
            (_CMD_ID_IMPORT, 'Import Hotkeys', 'Import a previously exported hotkey mapping', _ICON_IMPORT,
             ImportCommandCreatedHandler),
            (_CMD_ID_EXPORT, 'Export Current Hotkeys', 'Save the current hotkey mapping to a file', _ICON_EXPORT,
             ExportCommandCreatedHandler),
            (_CMD_ID_RESET, 'Reset to Default', 'Restore the saved default hotkey baseline', _ICON_RESET,
             ResetCommandCreatedHandler),
        )

        for cmd_id, name, tooltip, resource_folder, handler_class in tool_specs:
            existing = cmd_defs.itemById(cmd_id)
            if existing:
                existing.deleteMe()

            cmd_def = cmd_defs.addButtonDefinition(cmd_id, name, tooltip, resource_folder)
            on_created = handler_class()
            cmd_def.commandCreated.add(on_created)
            _handlers.append(on_created)

            if dropdown and not dropdown.controls.itemById(cmd_id):
                dropdown.controls.addCommand(cmd_def)

        # Only added to the Design workspace by default. To surface it in other workspaces
        # (Manufacture, Simulation, Drawing...) find their workspace IDs - e.g. run
        # "for ws in ui.workspaces: print(ws.id)" from a script - then repeat this function's
        # panel/dropdown-lookup and addCommand calls with each additional workspace id.

    except Exception:
        log_error('HotkeyAssignment add-in failed to start')


def stop(context):
    try:
        workspace = _ui.workspaces.itemById(_WORKSPACE_ID)
        panel = workspace.toolbarPanels.itemById(_PANEL_ID) if workspace else None
        dropdown = panel.controls.itemById(_DROPDOWN_ID) if panel else None

        main_control = panel.controls.itemById(_CMD_ID) if panel else None
        if main_control:
            main_control.deleteMe()
        main_cmd_def = _ui.commandDefinitions.itemById(_CMD_ID) if _ui else None
        if main_cmd_def:
            main_cmd_def.deleteMe()

        for cmd_id in (_CMD_ID_IMPORT, _CMD_ID_EXPORT, _CMD_ID_RESET):
            control = dropdown.controls.itemById(cmd_id) if dropdown else None
            if control:
                control.deleteMe()

            cmd_def = _ui.commandDefinitions.itemById(cmd_id) if _ui else None
            if cmd_def:
                cmd_def.deleteMe()

        if dropdown:
            dropdown.deleteMe()
    except Exception:
        log_error('HotkeyAssignment add-in failed to stop cleanly')
