# -*- coding: utf-8 -*-
"""Blender UI-language independent lookup helpers.

Use this module only for Blender-owned/default UI names. WoT/.visual semantic
names such as diffuseMap, normalMap or g_detailPower are addon/game data
identifiers and intentionally remain exact-name lookups.
"""
try:
    import bpy  # type: ignore
except Exception:  # allows static checks outside Blender
    bpy = None


def _norm(value):
    try:
        return str(value).casefold()
    except Exception:
        return ""


def translated_variants(name):
    """Source text plus translations for Blender's currently active locale."""
    values = [str(name)]
    if bpy is not None:
        tr_api = getattr(getattr(bpy, "app", None), "translations", None)
        if tr_api is not None:
            for fn_name in ("pgettext", "pgettext_iface", "pgettext_data", "pgettext_tip"):
                fn = getattr(tr_api, fn_name, None)
                if fn is None:
                    continue
                try:
                    value = fn(str(name))
                    if value and value not in values:
                        values.append(value)
                except Exception:
                    pass
    return values


def node_by_type(nodes, *node_types, fallback_names=()):
    """Resolve Blender-owned nodes by stable type/bl_idname first."""
    wanted = {_norm(v) for v in node_types if v}
    for node in nodes:
        if (_norm(getattr(node, "type", "")) in wanted or
                _norm(getattr(node, "bl_idname", "")) in wanted):
            return node

    # Compatibility fallback only. It accepts the active UI translation too.
    for raw in fallback_names:
        for name in translated_variants(raw):
            try:
                node = nodes.get(name)
                if node is not None:
                    return node
            except Exception:
                pass
    return None


def material_output_node(nodes):
    return node_by_type(nodes, "OUTPUT_MATERIAL", "ShaderNodeOutputMaterial",
                        fallback_names=("Material Output",))


def principled_bsdf_node(nodes):
    return node_by_type(nodes, "BSDF_PRINCIPLED", "ShaderNodeBsdfPrincipled",
                        fallback_names=("Principled BSDF",))


def socket_matches(sock, *names):
    """Match a socket by stable identifier, authored name, or current translation."""
    raw_names = [str(n) for n in names if n is not None]
    wanted_stable = {_norm(n) for n in raw_names}
    sid = _norm(getattr(sock, "identifier", ""))
    if sid and sid in wanted_stable:
        return True

    wanted_ui = set(wanted_stable)
    for raw in raw_names:
        wanted_ui.update(_norm(v) for v in translated_variants(raw))
    return _norm(getattr(sock, "name", "")) in wanted_ui


def socket_by_identifier(sockets, *names, index=None):
    """Resolve a socket without depending on an English display label."""
    raw_names = [str(n) for n in names if n is not None]
    wanted = {_norm(n) for n in raw_names}

    # Stable Blender/API identifier has highest priority.
    for sock in sockets:
        sid = _norm(getattr(sock, "identifier", ""))
        if sid and sid in wanted:
            return sock

    # Addon-authored node-group sockets keep their authored names.
    for name in raw_names:
        try:
            sock = sockets.get(name)
            if sock is not None:
                return sock
        except Exception:
            pass
        try:
            return sockets[name]
        except Exception:
            pass

    # Blender UI display names may be localized.
    for sock in sockets:
        if socket_matches(sock, *raw_names):
            return sock

    # Fixed-layout built-in nodes can safely provide an index fallback.
    if index is not None:
        try:
            return sockets[int(index)]
        except Exception:
            pass
    return None


def input_socket(node, *names, index=None):
    if node is None:
        return None
    return socket_by_identifier(node.inputs, *names, index=index)


def output_socket(node, *names, index=None):
    if node is None:
        return None
    return socket_by_identifier(node.outputs, *names, index=index)


def keymap_by_space_type(keymaps, space_type, fallback_name=None):
    """Resolve keymap by stable space_type, not a localized keymap display name."""
    if fallback_name:
        for candidate in translated_variants(fallback_name):
            try:
                km = keymaps.get(candidate)
                if km is not None:
                    return km
            except Exception:
                pass
    try:
        for km in keymaps:
            if getattr(km, "space_type", None) == space_type:
                return km
    except Exception:
        pass
    return None
