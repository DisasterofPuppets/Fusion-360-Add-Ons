# Fusion 360 Add-Ins

A collection of small Autodesk Fusion add-ins. Each one lives in its own
folder with its own README covering what it does and how to install it.

| Add-in | Description |
|--------|--------------|
| [ToggleFolderVisibility](ToggleFolderVisibility/) | Toggles the Bodies/Sketches folder light bulb for the active component, without disturbing individual body/sketch visibility. Can be bound to a keyboard shortcut. |

## Installing any add-in in this repo

1. Download or clone this repository.
2. Copy the add-in's whole folder (e.g. `ToggleFolderVisibility/`) into
   your Fusion **AddIns** folder — keep the `.py`, `.manifest`, and any
   `resources` subfolder together:

   | OS      | Path |
   |---------|------|
   | Windows | `%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns` |
   | macOS   | `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns` |

3. In Fusion: **Utilities** tab → **Add-Ins** panel → **Scripts and
   Add-Ins** → **Add-Ins** tab → select the add-in → **Run** (tick
   **Run on Startup** to load it automatically).

See each add-in's own README for what it does, where its buttons appear,
and any suggested keyboard shortcuts.

## License

MIT — see [LICENSE](LICENSE). Applies to every add-in in this repo unless
a folder says otherwise.
