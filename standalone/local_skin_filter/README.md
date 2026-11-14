# Local skin filter 1.0 (experimental)

An independent stdlib/Tk preparation tool plus a normally loaded in-game cosmetic
selector. Reads the chosen WG client's native packages, creates private model,
LOD, visual, primitive, material and texture resources, and chooses those paths
for selected enemy/allied appearances. Own vehicle and hangar stay unchanged.

The design follows UML's per-vehicle selection idea; it does not copy UML code or
claim compatibility with arbitrary UML/third-party attachments. Only stock-path
resource replacements are covered. No collision getter, spotting/visibility,
shooting/input, server communications, injection or anti-cheat bypass is used.

`filter_runtime.py.txt` is compiled in an isolated offline helper using the
selected client's Python 2.7 DLL. Runtime selection wraps the normal appearance
prerequisites/refresh context and the cosmetic `model_assembler` getter only.
No shared vehicle descriptor or fashion is changed. Settings use the original
[ModsSettings API](https://github.com/izeberg/modssettingsapi), separately
installed with ModsList API. Their code/binaries are not redistributed.

The parser/catalog/relocation/group-audit helpers are shared project code copied
from the independent self-skin converter, with their third-party license retained.
No workbench import or additional Python dependency is needed by the portable app.

All builds remain `whole_vehicle_loading.status = not_tested` until a final hash
has been tested in the actual client. No official approval or anti-cheat guarantee.
Reference: [WG prohibited mods](https://worldoftanks.eu/en/content/guide/fair-play/prohibited-mods/).
