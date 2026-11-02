"""Reusable BigWorld light geometry codecs. Conservative supported vertex layouts only."""

import io, struct

import xml.etree.ElementTree as ET

import numpy as np

from PIL import Image

def xml(root):
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

def sections(blob):
    """Decode a packed section table after checking its data and name bounds."""
    if len(blob)<8:
        raise ValueError('模型段容器头或段表尾部不完整')
    if struct.unpack_from('<I', blob)[0] != 0x42A14E65:
        raise ValueError('模型段容器魔数不正确')
    end = len(blob) - 4
    table_size=struct.unpack_from('<I', blob, end)[0]
    if table_size>end-4:
        raise ValueError('模型段表越过容器起始位置')
    at = end - table_size
    table_start=at
    offset = 4
    result = {}
    while at < end:
        if at+24>end:
            raise ValueError('模型段表记录不完整')
        length, = struct.unpack_from('<I', blob, at)
        size, = struct.unpack_from('<I', blob, at + 20)
        next_at=at+24+(size+3)//4*4
        if not size or next_at>end:
            raise ValueError('模型段名长度超出段表')
        try:name = blob[at + 24:at + 24 + size].decode('utf-8')
        except UnicodeDecodeError as error:raise ValueError('模型段名不是有效 UTF-8') from error
        if name in result:
            raise ValueError('模型段名重复：'+name)
        if offset+length>table_start or offset+(length+3)//4*4>table_start:
            raise ValueError('模型段数据长度超出数据区：'+name)
        result[name] = blob[offset:offset + length]
        offset += (length + 3) // 4 * 4
        at = next_at
    if at != end:
        raise ValueError('模型段表长度不匹配')
    return result

def primitives(vertices, indices):
    # Match the native spider barrel's processed static vertex declaration.
    vb = b'BPVTxyznuv'.ljust(64, b'\0') + struct.pack('<I', 0)
    vb += b'set3/xyznuvpc'.ljust(64, b'\0') + struct.pack('<I', len(vertices))
    for v in vertices:
        packed = 0
        for shift, component in enumerate(v[3:6]):
            value = min(1.0, max(-1.0, float(component)))
            encoded = (int(round(value * 127)) ^ 127) if value > 0 else (128 ^ int(round(-value * 127)))
            packed |= (encoded ^ 255) << (8 * shift)
        vb += struct.pack('<3fI2f', *v[:3], packed, *v[6:8])
    ib = b'list'.ljust(64, b'\0') + struct.pack('<II', len(indices), 1)
    ib += struct.pack('<' + 'H' * len(indices), *indices)
    ib += struct.pack('<IIII', 0, len(indices) // 3, 0, len(vertices))
    body, table = bytearray(struct.pack('<I', 0x42A14E65)), bytearray()
    for name, data in [('vertices', vb), ('indices', ib)]:
        body.extend(data + b'\0' * (-len(data) % 4))
        raw = name.encode()
        table.extend(struct.pack('<I4II', len(data), 0, 0, 0, 0, len(raw)))
        table.extend(raw + b'\0' * (-len(raw) % 4))
    return bytes(body + table + struct.pack('<I', len(table)))

class UnsupportedVertexFormat(ValueError):
    pass


def vertex_data(data):
    if len(data)<68:
        raise ValueError('顶点数据头不完整：至少需要 68 字节，实际 %d 字节'%len(data))
    fmt = data[:64].split(b'\0')[0]
    if fmt in (b'BPVTxyznuv', b'BPVTxyznuvtb', b'BPVTxyznuviiiwwtb'):
        if len(data)<136:raise ValueError('BPVT 顶点数据头不完整：至少需要 136 字节')
        target=data[68:132].split(b'\0')[0]
        expected={b'BPVTxyznuv':(b'set3/xyznuvpc',24),b'BPVTxyznuvtb':(b'set3/xyznuvtbpc',32),b'BPVTxyznuviiiwwtb':(b'set3/xyznuviiiwwtbpc',40)}
        target_name,stride=expected[fmt]
        if struct.unpack_from('<I', data, 64)[0]!=0 or target!=target_name:
            raise UnsupportedVertexFormat('暂不支持的处理后顶点布局：%s → %s'%(fmt.decode('ascii','replace'),target.decode('ascii','replace')))
        count, = struct.unpack_from('<I', data, 132)
        if len(data)!=136+count*stride:
            raise ValueError('BPVT 顶点长度不匹配：%d 个顶点应为 %d 字节，实际 %d 字节'%(count,136+count*stride,len(data)))
        values = []; skin = []
        for i in range(count):
            x, y, z, packed, u, v = struct.unpack_from('<3fI2f', data, 136 + i * stride)
            norm = []
            for shift in range(3):
                byte = ((packed >> (8 * shift)) & 255) ^ 255
                norm.append(-(byte & 127) / 127 if byte > 127 else (byte ^ 127) / 127)
            values.append((x, y, z, *norm, u, v))
            if stride == 40:
                at=136+i*stride+24
                skin.append(tuple(data[at:at+3])+tuple(data[at+6:at+8]))
        return np.array(values, dtype=np.float64).reshape(-1,8), skin
    # EU 2.4.1 shaders/formats/xyznuviiiwwtb.xml: position 12 + normal 4 +
    # UV 8 + indices 3 + weights 2 + tangent 4 + binormal 4 = 37 bytes.
    # TB stays in the original source buffer. The independent light export uses
    # its existing static declaration and only needs position, normal and UV.
    strides={b'xyznuv':32,b'xyznuviiiww':29,b'xyznuviiiwwtb':37,b'xyznuvtb':32}
    if fmt not in strides:
        raise UnsupportedVertexFormat('暂不支持的顶点格式：%s。已识别发光材质，但需要补充此布局的读取支持。'%fmt.decode('ascii','replace'))
    count, = struct.unpack_from('<I', data, 64)
    values, skin = [], []
    stride = strides[fmt]
    if len(data)!=68+count*stride:
        raise ValueError('%s 顶点长度不匹配：%d 个顶点、每顶点 %d 字节，应为 %d 字节，实际 %d 字节'%(fmt.decode('ascii'),count,stride,68+count*stride,len(data)))
    def signed(value, bits):
        return value - (1 << bits) if value & (1 << (bits - 1)) else value
    for i in range(count):
        at = 68 + i * stride
        if fmt == b'xyznuv':
            values.append(struct.unpack_from('<8f', data, at))
        else:
            x, y, z, normal, u, v = struct.unpack_from('<3fI2f', data, at)
            norm = np.array([signed(normal & 0x7ff, 11) / 1023,
                             signed((normal >> 22) & 0x3ff, 10) / 511,
                             signed((normal >> 11) & 0x7ff, 11) / 1023])
            length = np.linalg.norm(norm)
            norm = norm / length if length else np.array([0, 1, 0])
            values.append((x, y, z, *norm, u, v))
            if fmt in (b'xyznuviiiww',b'xyznuviiiwwtb'):
                skin.append(tuple(data[at + 24:at + 29]))
    return np.array(values, dtype=np.float64).reshape(-1,8), skin

def node_matrices(visual):
    matrices, parents = {}, {}
    def walk(node, parent, accumulated):
        matrix = np.eye(4)
        for row in range(4):
            matrix[row, :3] = list(map(float, node.findtext('transform/row' + str(row)).split()))
        global_matrix = matrix @ accumulated
        name = node.findtext('identifier').strip()
        matrices[name], parents[name] = global_matrix, parent
        for child in node.findall('node'):
            walk(child, name, global_matrix)
    walk(visual.find('node'), None, np.eye(4))
    return matrices, parents

def prop(material, name, kind, value):
    node = ET.SubElement(material, 'property')
    node.text = name
    ET.SubElement(node, kind).text = str(value)


def render_bounds(vertices):
    """Give planar independent models a conservative non-degenerate draw box.

    This only changes culling metadata. Never extrude the lamp or move its UVs.
    The 1 cm minimum applies only to axes thinner than 0.01 mm.
    """
    points=np.asarray(vertices,dtype=float)
    if points.ndim!=2 or points.shape[1]<3 or not len(points) or not np.isfinite(points[:,:3]).all():
        raise ValueError('灯面包围盒需要有效且有限的顶点坐标')
    low=points[:,:3].min(0);high=points[:,:3].max(0)
    thin=high-low<1e-5;center=(low+high)/2
    low=np.where(thin,center-.005,low);high=np.where(thin,center+.005,high)
    return low,high

def effect_visual(identifier, texture, vertices, ntri, prefix, tint=2.0):
    PREFIX, TINT = prefix, tint
    root = ET.Element('root')
    node = ET.SubElement(root, 'node')
    ET.SubElement(node, 'identifier').text = 'Scene Root'
    transform = ET.SubElement(node, 'transform')
    for row, value in enumerate(('1 0 0', '0 1 0', '0 0 1', '0 0 0')):
        ET.SubElement(transform, 'row' + str(row)).text = value
    rs = ET.SubElement(root, 'renderSet')
    ET.SubElement(rs, 'treatAsWorldSpaceObject').text = 'false'
    ET.SubElement(rs, 'node').text = 'Scene Root'
    geo = ET.SubElement(rs, 'geometry')
    ET.SubElement(geo, 'vertices').text = 'vertices'
    ET.SubElement(geo, 'primitive').text = 'indices'
    pg = ET.SubElement(geo, 'primitiveGroup'); pg.text = '0'
    mat = ET.SubElement(pg, 'material')
    ET.SubElement(mat, 'identifier').text = identifier
    ET.SubElement(mat, 'fx').text = 'shaders/custom/emissive_playground.fx'
    ET.SubElement(mat, 'materialKind').text = '0'
    ET.SubElement(mat, 'collisionFlags').text = '255'
    for name, kind, value in [
        ('emissionMap', 'Texture', texture), ('phaseMap', 'Texture', PREFIX + 'phase_white.dds'),
        ('doubleSided', 'Bool', 'true'), ('srcBlend', 'Int', 3), ('destBlend', 'Int', 6),
        ('animationMode', 'Int', 2), ('usePhaseMap', 'Bool', 'true'),
        ('useVersicolorMode', 'Bool', 'false'), ('angleFalloffParams', 'Vector4', '1 1 1 0'),
        # In the tested EU 2.4.1 Pulse+phaseMap branches, g_tint controls
        # brightness while g_forwardMult/g_deferredMult are compiled out.
        # Recheck other client versions and rendering branches independently.
        ('g_tint', 'Vector4', '%s %s %s %s' % (TINT, TINT, TINT, 1)), ('g_forwardMult', 'Float', 2), ('g_deferredMult', 'Float', 2),
        ('speed', 'Float', '1.3333333333333333'), ('waveLen', 'Float', 1), ('g_contrast', 'Float', 1),
        ('g_zeroPhaseLum', 'Float', 1), ('g_offsetBlack', 'Float', .4), ('g_offsetBlackFwd', 'Float', .4),
        ('g_chromaOffsetGreen', 'Float', 0), ('g_chromaOffsetBlue', 'Float', 0),
        ('g_enableVisTunnel', 'Bool', 'false'), ('g_enableEnvMultiplier', 'Bool', 'false')]:
        prop(mat, name, kind, value)
    bounds = ET.SubElement(root, 'boundingBox')
    for key, value in zip(('min','max'),render_bounds(vertices)):
        ET.SubElement(bounds, key).text = ' '.join(format(float(x), '.9g') for x in value)
    ET.SubElement(root, 'geometrySize').text = str(len(vertices) * 24 + ntri * 6)
    return xml(root)

def sequence(model_path):
    root = ET.Element('root')
    ET.SubElement(root, 'duration').text = '0.0'
    obj = ET.SubElement(root, 'sequenceObject')
    for name, value in [('name', 'Root'), ('type', 'model'), ('resource', '')]:
        ET.SubElement(obj, name).text = value
    obj = ET.SubElement(root, 'sequenceObject')
    for name, value in [('name', 'Light'), ('type', 'model'), ('resource', model_path), ('castsShadow', 'false')]:
        ET.SubElement(obj, name).text = value
    for name, value in [('position', '0 0 0'), ('rotationEuler', '0 0 0'), ('scale', '1 1 1')]:
        track = ET.SubElement(obj, 'track')
        ET.SubElement(track, 'name').text = name
        ET.SubElement(track, 'type').text = 'vector3'
        frame = ET.SubElement(track, 'frame')
        for key, val in [('startTime', '0.0'), ('value', value), ('inTangent', '0 0 0'),
                         ('outTangent', '0 0 0'), ('tangentMode', '0')]:
            ET.SubElement(frame, key).text = val
    ET.SubElement(root, 'events')
    return xml(root)

def dds(white):
    header = [124, 0x81007, 4, 4, 16, 0, 1] + [0] * 11
    header += [32, 4, struct.unpack('<I', b'DXT5')[0], 0, 0, 0, 0, 0, 0x1000, 0, 0, 0, 0]
    block = bytes([255 if white else 0, 255 if white else 0]) + b'\0' * 6
    block += struct.pack('<HHI', 65535 if white else 0, 65535 if white else 0, 0)
    result = b'DDS ' + struct.pack('<31I', *header) + block
    im = Image.open(io.BytesIO(result)).convert('RGBA')
    assert im.getpixel((0, 0)) == ((255, 255, 255, 255) if white else (0, 0, 0, 0))
    return result

def packed_sections(sections):
    body=bytearray(struct.pack('<I',0x42A14E65));table=bytearray()
    for name,data in sections.items():
        body.extend(data+b'\0'*(-len(data)%4));raw=name.encode()
        table.extend(struct.pack('<I4II',len(data),0,0,0,0,len(raw)));table.extend(raw+b'\0'*(-len(raw)%4))
    return bytes(body+table+struct.pack('<I',len(table)))

def make_ib(ids,nv):
    ids=np.asarray(ids,dtype=np.uint16).ravel()
    return b'list'.ljust(64,b'\0')+struct.pack('<II',len(ids),1)+ids.astype('<u2').tobytes()+struct.pack('<4I',0,len(ids)//3,0,nv)

def clip(poly,axis,bound,above):
    result=[]
    for a,c in zip(poly,poly[1:]+poly[:1]):
        ina=a[axis]>=bound if above else a[axis]<=bound;inc=c[axis]>=bound if above else c[axis]<=bound
        if ina:result.append(a)
        if ina!=inc:
            w=(bound-a[axis])/(c[axis]-a[axis]);result.append(a+(c-a)*w)
    return result

def split_bands(vertices,ids,wheel):
    if wheel:return [(vertices.copy(),ids.copy().ravel(),float(vertices[ids,2].mean()))]
    result=[]
    lo,hi=vertices[ids,2].min(),vertices[ids,2].max()
    if hi-lo<.1:return [(vertices.copy(),ids.copy().ravel(),float((lo+hi)/2))]
    # 0.5m bands, using exact triangle clipping to preserve source surface and UVs.
    edges=np.arange(np.floor(lo*2)/2,np.ceil(hi*2)/2+.001,.5)
    for low,high in zip(edges,edges[1:]):
        triangles=[]
        for tri in vertices[ids]:
            if tri[:,2].max()<low or tri[:,2].min()>high:continue
            poly=clip(list(tri),2,low,True);poly=clip(poly,2,high,False) if poly else []
            for k in range(1,len(poly)-1):
                v=np.array([poly[0],poly[k],poly[k+1]])
                if np.linalg.norm(np.cross(v[1,:3]-v[0,:3],v[2,:3]-v[0,:3]))>1e-11:triangles.extend(v)
        if triangles:
            v=np.array(triangles);v[:,3:6]/=np.maximum(np.linalg.norm(v[:,3:6],axis=1)[:,None],1e-12)
            result.append((v,np.arange(len(v)),float((low+high)/2)))
    return result

def area(vertices,ids):
    tri=vertices[np.asarray(ids).reshape(-1,3),:3]
    return float(np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1).sum()*.5)


def split_wheel(vertices, ids, sectors=12):
    """Clip a rigid wheel lamp into sectors in its own plane, keeping UVs.

    The attachment still belongs to the original wheel. Only the independent
    export is subdivided; no vehicle bone, skin weight or node is modified.
    """
    used = vertices[np.unique(ids), :3]
    low, high = used.min(0), used.max(0)
    axes = np.sort(np.argsort(high-low)[-2:])
    center = (low+high)/2

    def half_plane(poly, normal):
        result = []
        for a, b in zip(poly, poly[1:]+poly[:1]):
            da = float(np.dot(a[:3]-center, normal))
            db = float(np.dot(b[:3]-center, normal))
            ina, inb = da >= 0, db >= 0
            if ina:result.append(a)
            if ina != inb:result.append(a+(b-a)*(da/(da-db)))
        return result

    result = []
    for sector in range(sectors):
        a, b = np.array([sector, sector+1])*2*np.pi/sectors
        start, end = np.zeros(3), np.zeros(3)
        start[axes] = [-np.sin(a), np.cos(a)]
        end[axes] = [np.sin(b), -np.cos(b)]
        rows = []
        for tri in vertices[ids]:
            poly = half_plane(list(tri), start)
            poly = half_plane(poly, end) if poly else []
            for k in range(1, len(poly)-1):
                vs = np.array([poly[0], poly[k], poly[k+1]])
                if np.linalg.norm(np.cross(vs[1,:3]-vs[0,:3], vs[2,:3]-vs[0,:3])) > 1e-11:
                    rows.extend(vs)
        if rows:
            vs = np.array(rows)
            vs[:,3:6] /= np.maximum(np.linalg.norm(vs[:,3:6],axis=1)[:,None],1e-12)
            result.append((vs, np.arange(len(vs)), float(vs[:,2].mean())))
    return result


def split_radial(vertices, ids):
    """Exact X/Z grid clipping, preserving UVs; radial delay is sampled per cell."""
    cells = {}
    for tri in vertices[ids]:
        lower = np.floor(tri[:, [0, 2]].min(0) * 2).astype(int)
        upper = np.floor(tri[:, [0, 2]].max(0) * 2).astype(int)
        for x in range(lower[0], upper[0] + 1):
            for z in range(lower[1], upper[1] + 1):
                poly = list(tri)
                for axis, bound, above in [(0,x/2,True),(0,(x+1)/2,False),(2,z/2,True),(2,(z+1)/2,False)]:
                    poly = clip(poly,axis,bound,above) if poly else []
                for k in range(1,len(poly)-1):
                    vs = np.array([poly[0],poly[k],poly[k+1]])
                    if np.linalg.norm(np.cross(vs[1,:3]-vs[0,:3],vs[2,:3]-vs[0,:3])) > 1e-11:
                        cells.setdefault((x,z),[]).extend(vs)
    result = []
    for key, rows in sorted(cells.items()):
        vs = np.array(rows); vs[:,3:6] /= np.maximum(np.linalg.norm(vs[:,3:6],axis=1)[:,None],1e-12)
        result.append((vs,np.arange(len(vs)),float(vs[:,2].mean())))
    return result


def split_for_direction(vertices,ids,direction,anchor_matrix,wheel=False):
    """One geometry splitter for export, Canvas preview and 3D preview.

    Legacy forward/wheel/radial layouts are preserved. Vertical and diagonal
    flow is clipped against its actual direction in the part's bind space;
    splitting only along Z would make a flat side lamp change all at once.
    The projection column is temporary; original UVs and pick IDs survive.
    """
    from .light_recipe import FLOW_VECTORS
    if direction not in FLOW_VECTORS:
        return split_wheel(vertices,ids) if wheel else split_radial(vertices,ids) if direction=='四周扩散' else split_bands(vertices,ids,False)
    vector=np.asarray(FLOW_VECTORS[direction]);matrix=np.asarray(anchor_matrix)
    coordinate=(np.c_[vertices[:,:3],np.ones(len(vertices))]@matrix)[:,:3]@vector
    augmented=np.c_[vertices,coordinate];axis=vertices.shape[1];triangles=np.asarray(ids,dtype=int).reshape(-1,3)
    lo,hi=coordinate[np.unique(triangles)].min(),coordinate[np.unique(triangles)].max()
    if hi-lo<.01:return [(vertices.copy(),triangles.ravel().copy(),float((lo+hi)/2))]
    edges=np.arange(np.floor(lo*5)/5,np.ceil(hi*5)/5+.00001,.2)
    if len(edges)>512:raise ValueError('方向分段过多，请缩小选中的灯面范围。')
    result=[]
    for low,high in zip(edges,edges[1:]):
        rows=[]
        for tri in augmented[triangles]:
            if tri[:,axis].max()<low or tri[:,axis].min()>high:continue
            poly=clip(list(tri),axis,low,True);poly=clip(poly,axis,high,False) if poly else []
            for i in range(1,len(poly)-1):
                vs=np.array([poly[0],poly[i],poly[i+1]])
                if np.linalg.norm(np.cross(vs[1,:3]-vs[0,:3],vs[2,:3]-vs[0,:3]))>1e-11:rows.extend(vs[:,:axis])
        if rows:
            vs=np.asarray(rows);vs[:,3:6]/=np.maximum(np.linalg.norm(vs[:,3:6],axis=1)[:,None],1e-12)
            result.append((vs,np.arange(len(vs)),float((low+high)/2)))
    return result


def flow_phase_point(vertices,coordinate,direction,anchor_matrix,wheel=False):
    from .light_recipe import FLOW_VECTORS
    point=vertices[:,:3].mean(0)
    if direction in FLOW_VECTORS or wheel or direction=='四周扩散':point=(np.r_[point,1.]@anchor_matrix)[:3]
    if direction in FLOW_VECTORS:
        vector=np.asarray(FLOW_VECTORS[direction]);point+=vector*(coordinate-float(point@vector))
    if direction not in FLOW_VECTORS and direction!='四周扩散':point[2]=float(point[2]) if wheel else coordinate
    return point
