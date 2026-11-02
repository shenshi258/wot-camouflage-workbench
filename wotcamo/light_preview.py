"""Offline light-band simulation. Never executes the game's shader or writes assets."""
import re
import numpy as np
from . import light_effects as engine, light_recipe as recipe, light_assets as mesh


def prepare(lights, global_recipe):
    """Use export band geometry/phase coordinates, with bounded display samples."""
    selected = [x for x in lights if x.get('selected') and x.get('supported')]
    emitted, aliases = engine.deduplicate_variant_lights(selected, global_recipe)
    models = engine.render_groups(emitted)
    result = []
    for mi, (((visual, anchor, kind, texture), _), faces) in enumerate(models):
        cfg = recipe.validate_config(engine.model_recipe(faces) or global_recipe)
        vertices = np.concatenate([x['_vertices'] for x in faces])
        indices = []; offset = 0
        for face in faces:
            indices.extend((face['_indices'] + offset).tolist()); offset += len(face['_vertices'])
        indices = np.asarray(indices, dtype=int)
        # The export retains every triangle. Interactive simulation may decimate
        # dense inputs before Python clipping; keep extrema for stable bounds.
        budget=max(96,min(512,8000//max(1,len(models))))
        sampled=len(indices)>budget
        if sampled:
            centers=vertices[indices,:3].mean(1)
            keep=np.unique(np.r_[np.linspace(0,len(indices)-1,budget,dtype=int),
                                  centers.argmin(0),centers.argmax(0)])
            indices=indices[keep]
        wheel = faces[0]['part'] == 'chassis' and re.fullmatch(r'(?:W|WD)_[LR]\d+', anchor)
        bands = mesh.split_for_direction(vertices,indices,cfg['direction'],faces[0]['_anchor_matrix'],wheel)
        related = np.concatenate([x['_preview'] for x in selected if x['visual'] == visual])
        center = (related.min(0) + related.max(0)) / 2
        matrix = faces[0]['_anchor_matrix']
        face_ids = {x['id'] for x in faces}
        visuals = {visual} | {x['source'] for x in aliases if x['representative'] in face_ids}
        for bi, (vs, ix, z) in enumerate(bands):
            point = mesh.flow_phase_point(vs,z,cfg['direction'],matrix,wheel)
            identifier = 'light_%03d_band_%02d' % (mi, bi)
            phase = recipe.spatial_offset(point, center, cfg, identifier)
            triangles = vs[np.asarray(ix).reshape(-1, 3), :3]
            samples = np.concatenate((triangles.reshape(-1, 3), triangles.mean(1)))
            samples = samples[::max(1, int(np.ceil(len(samples) / 40)))]
            samples = (np.c_[samples, np.ones(len(samples))] @ matrix)[:, :3]
            result.append(dict(points=samples, config=cfg, offset=phase, visual=visual, visuals=visuals,
                               identifier=identifier, sampled=sampled))
    # Keep the Canvas responsive even for exceptionally dense inputs.
    total = sum(len(band['points']) for band in result)
    stride = max(1, int(np.ceil(total / 1600)))
    for band in result: band['points'] = band['points'][::stride]
    return result


def colors(seconds, band):
    """Tone-map HDR to a dark screen; native Pulse is an approximate envelope."""
    rgb = np.maximum(recipe.animated_value(seconds, band['offset'], band['config'])[:3], 0)
    rgb = 1 - np.exp(-rgb)
    def hex_color(values):
        return '#' + ''.join('%02x' % int(np.clip(x, 0, 1) * 255) for x in values)
    return hex_color(rgb), hex_color(rgb * .24 + np.array([.035, .045, .065]))
