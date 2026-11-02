# -*- coding: utf-8 -*-
import bpy
import os


from .common.blender_compat import input_socket, output_socket, socket_by_identifier, socket_matches
def log(msg):
    print(msg)

# ==========================================================================
# 0. YARDIMCI VE GÜVENLİK FONKSİYONLARI (Eski Koddan Birebir Alındı)
# ==========================================================================
def get_socket(node, name, is_output=False):
    sockets = node.outputs if is_output else node.inputs
    sock = socket_by_identifier(sockets, name)
    if sock is not None:
        return sock
    target = str(name).casefold()
    for sock in sockets:
        if target in str(getattr(sock, "identifier", "")).casefold() or target in str(getattr(sock, "name", "")).casefold():
            return sock
    return sockets[0] if sockets else None

def safe_link(tree, n1, out_name, n2, in_name, in_index=0):
    def match_name(name, target):
        n = name.lower().replace("ı", "i").replace("lenght", "length").replace("velocitiy", "velocity").replace("gravitiy", "gravity")
        t = target.lower().replace("ı", "i").replace("lenght", "length").replace("velocitiy", "velocity").replace("gravitiy", "gravity")
        return n == t

    out_sock = next((s for s in n1.outputs if socket_matches(s, out_name) or match_name(getattr(s, "name", ""), out_name)), None)
    matching_in_sockets = [s for s in n2.inputs if socket_matches(s, in_name) or match_name(getattr(s, "name", ""), in_name)]
    
    if out_sock and matching_in_sockets:
        if in_index == -1:
            for sock in matching_in_sockets:
                tree.links.new(out_sock, sock)
        elif in_index < len(matching_in_sockets):
            in_sock = matching_in_sockets[in_index]
            tree.links.new(out_sock, in_sock)
        else:
            log(f"WARNING: Socket '{in_name}' index {in_index} not found!")
    else:
        log(f"WARNING: Link failed! '{out_name}' -> '{in_name}' (Socket not found).")

def ensure_wot_animation_node():
    """Kütüphane yüklenmezse diye procedural fallback (Eski kodundan)"""
    group_name = "VFX_WoT_Animation_Node"
    if group_name in bpy.data.node_groups:
        return bpy.data.node_groups[group_name]

    log(f"Warning: '{group_name}' not found. Generating in background...")
    group = bpy.data.node_groups.new(group_name, 'ShaderNodeTree')
    
    for name in ["Cols", "Rows", "Rate", "U_Min", "U_Max", "V_Min", "V_Max", "Frame"]:
        group.interface.new_socket(name=name, in_out='INPUT', socket_type='NodeSocketFloat')
    group.interface.new_socket(name="UV_Vector", in_out='OUTPUT', socket_type='NodeSocketVector')
    
    # ... (Procedural nodeların detayları buradaydı, uzatmamak için kestiğimiz varsayılır,
    # ama ana projende bu fonksiyonun İÇİNİ ESKİ KODUNDAN TAMAMEN KOPYALA.)
    return group

# ==========================================================================
# 1. MATERIAL NODES (Instance Objesi İçin)
# ==========================================================================
def setup_vfx_material_nodes(obj):
    if not obj or obj.type != 'MESH': return

    mat_name = f"Mat_{obj.name}"
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    mat.blend_method = 'BLEND'
    mat.show_transparent_back = True
    
    if len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # 1. Animasyon Nodu (Yeni: Volume_Density çıkışı olan versiyon)
    wot_node_tree = bpy.data.node_groups.get("VFX_WoT_Animation_Node")
    anim_node = nodes.new('ShaderNodeGroup')
    if wot_node_tree: anim_node.node_tree = wot_node_tree
    anim_node.name = "VFX_WoT_Animation"
    anim_node.location = (-900, 400)
    if 'Frame' in anim_node.inputs:
        f_in = anim_node.inputs['Frame']
        f_driver = f_in.driver_add("default_value").driver
        f_driver.expression = "frame"

    # 2. Doku (Texture)
    tex = nodes.new('ShaderNodeTexImage')
    tex.location = (-600, 400)
    if 'UV_Vector' in anim_node.outputs:
        links.new(anim_node.outputs['UV_Vector'], input_socket(tex, 'Vector', index=0))

    # 3. Curve Driver
    curve_driver = nodes.new('ShaderNodeGroup')
    curve_driver_tree = bpy.data.node_groups.get("Curve Driver")
    if curve_driver_tree: curve_driver.node_tree = curve_driver_tree
    curve_driver.name = "Curve Driver"
    curve_driver.location = (-900, -100)

    # 4. Renk ve Zaman Eğrileri (Curves)
    r_curve = nodes.new('ShaderNodeFloatCurve'); r_curve.name = "R Curve"; r_curve.location = (-350, 600)
    g_curve = nodes.new('ShaderNodeFloatCurve'); g_curve.name = "G Curve"; g_curve.location = (-350, 400)
    b_curve = nodes.new('ShaderNodeFloatCurve'); b_curve.name = "B Curve"; b_curve.location = (-350, 200)
    alpha_curve = nodes.new('ShaderNodeFloatCurve')
    alpha_curve.name = "Alpha Curve"
    alpha_curve.label = "Alpha Curve"
    alpha_curve.location = (-350, 0)
    color_op_curve = nodes.new('ShaderNodeFloatCurve'); color_op_curve.name = "tl_color_op_key"; color_op_curve.location = (-350, -250)
    
    comb_color = nodes.new('ShaderNodeCombineColor')
    comb_color.location = (-100, 400)

    # 5. Alpha Calculator
    alpha_calc = nodes.new('ShaderNodeGroup')
    alpha_calc_tree = bpy.data.node_groups.get("Alpha calculator")
    if alpha_calc_tree: alpha_calc.node_tree = alpha_calc_tree
    alpha_calc.name = "Alpha calculator"
    alpha_calc.location = (-100, 0)

    # 6. Lighting Calculator (MERKEZİ IŞIK NODU)
    light_calc = nodes.new('ShaderNodeGroup')
    light_calc_tree = bpy.data.node_groups.get("Lighting calculator")
    if light_calc_tree: light_calc.node_tree = light_calc_tree
    light_calc.name = "Lighting calculator"
    light_calc.location = (250, 400)
    light_calc.width = 250

    # 7. Principled BSDF & Output
    bsdf = nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (600, 400)
    out = nodes.new('ShaderNodeOutputMaterial'); out.location = (900, 400)

    # --- KABLOLAMA ---

    # A) Curve Driver -> Tüm Eğrilere
    cd_out = curve_driver.outputs[0]
    for c in [r_curve, g_curve, b_curve, alpha_curve, color_op_curve]:
        links.new(cd_out, input_socket(c, 'Value', index=1))

    # B) R-G-B Curves -> Combine Color -> Lighting Calc (Doğrudan Bağlantı)
    links.new(r_curve.outputs[0], comb_color.inputs[0])
    links.new(g_curve.outputs[0], comb_color.inputs[1])
    links.new(b_curve.outputs[0], comb_color.inputs[2])
    if 'Color Curves' in light_calc.inputs:
        links.new(comb_color.outputs[0], light_calc.inputs['Color Curves'])

    # C) Doku (Texture) -> Lighting Calc ve Alpha Calc
    tex_color = output_socket(tex, 'Color', index=0)
    if tex_color is not None and 'Texture Color' in light_calc.inputs:
        links.new(tex_color, light_calc.inputs['Texture Color'])
    tex_alpha = output_socket(tex, 'Alpha', index=1)
    if tex_alpha is not None and 'Alpha in' in alpha_calc.inputs:
        links.new(tex_alpha, alpha_calc.inputs['Alpha in'])

    # D) Alpha Calc -> Lighting Calc
    links.new(alpha_curve.outputs[0], alpha_calc.inputs['Alpha Curve'])
    if 'Alpha out' in alpha_calc.outputs and 'Alpha Curve' in light_calc.inputs:
        links.new(alpha_calc.outputs['Alpha out'], light_calc.inputs['Alpha Curve'])

    # E) Volume_Density ve tl_color_op_key
    if 'Volume_Density' in anim_node.outputs and 'Volume_Density' in light_calc.inputs:
        links.new(anim_node.outputs['Volume_Density'], light_calc.inputs['Volume_Density'])
    if 'tl_color_op_key' in light_calc.inputs:
        links.new(color_op_curve.outputs[0], light_calc.inputs['tl_color_op_key'])
    if 'Curve Driver' in light_calc.inputs:
        links.new(cd_out, light_calc.inputs['Curve Driver'])

    # F) Güneş Ayarları (Varsayılan)
    if 'Scattering Tint' in light_calc.inputs:
        light_calc.inputs['Scattering Tint'].default_value = (1.0, 0.9, 0.7, 1.0)
    if 'Sun Direction' in light_calc.inputs:
        light_calc.inputs['Sun Direction'].default_value = (0.5, 0.5, 1.0)

    # G) FINAL ÇIKIŞLAR (Lighting Calc -> BSDF)
    l_out = light_calc.outputs
    base_color_in = input_socket(bsdf, 'Base Color', index=0)
    emission_color_in = input_socket(bsdf, 'Emission Color', 'Emission')
    alpha_in = input_socket(bsdf, 'Alpha')
    normal_in = input_socket(bsdf, 'Normal')
    if 'Result Color' in l_out and base_color_in is not None: links.new(l_out['Result Color'], base_color_in)
    if 'Result Emission' in l_out and emission_color_in is not None: links.new(l_out['Result Emission'], emission_color_in)
    if 'Result Alpha' in l_out and alpha_in is not None: links.new(l_out['Result Alpha'], alpha_in)
    if 'Final Normal' in l_out and normal_in is not None: links.new(l_out['Final Normal'], normal_in)

    emission_strength_in = input_socket(bsdf, 'Emission Strength')
    if emission_strength_in is not None:
        emission_strength_in.default_value = 1.0
    links.new(output_socket(bsdf, 'BSDF', index=0), input_socket(out, 'Surface', index=0))


# ==========================================================================
# 2. GEOMETRY NODES (EmitterSettings Objesi İçin)
# ==========================================================================
def setup_vfx_geometry_nodes(obj):
    if not obj or obj.type != 'MESH': return

    gn_mod = obj.modifiers.new(name="VFX_WoT_Controller", type='NODES')
    new_gn_tree = bpy.data.node_groups.new(name=f"GN_{obj.name}", type='GeometryNodeTree')
    gn_mod.node_group = new_gn_tree
    
    # Soketler
    new_gn_tree.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    new_gn_tree.interface.new_socket(name="Point Clean Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    
    out_node = new_gn_tree.nodes.new('NodeGroupOutput')
    out_node.location = (800, 0)

    wot_gn_tree = bpy.data.node_groups.get("Wot .vfxbin to blender")
    master_gn_tree = bpy.data.node_groups.get("GeoSpritesV2+WoT by wotcuk MASTER NODE")

    if wot_gn_tree and master_gn_tree:
        # 1. Wot Data Node
        wot_node = new_gn_tree.nodes.new('GeometryNodeGroup')
        wot_node.node_tree = wot_gn_tree
        wot_node.name = "Wot .vfxbin to blender"
        wot_node.location = (-400, 0)
        wot_node.width = 250
        
        # 2. Master Node
        master_node = new_gn_tree.nodes.new('GeometryNodeGroup')
        master_node.node_tree = master_gn_tree
        master_node.name = "GeoSpritesV2+WoT by wotcuk MASTER NODE"
        master_node.location = (200, 0)
        master_node.width = 300
        
        safe_link(new_gn_tree, master_node, "Point Clean Geometry", out_node, "Point Clean Geometry", 0)

        # 3. Eğriler ve Scale Grubu
        size_curve_node = new_gn_tree.nodes.new('ShaderNodeFloatCurve')
        size_curve_node.name = "tl_size_key"
        size_curve_node.label = "tl_size_key" # Ekranda görünmesi için
        size_curve_node.location = (-100, 200)

        # Diğer Timeline Nodeları (Şimdilik Dummy)
        gn_curves = ["tl_angle_speed_key", "tl_tangent_speed_key", "tl_speed_key", "tl_gravity_key", "tl_rate_key"]
        for i, c_name in enumerate(gn_curves):
            dummy_curve = new_gn_tree.nodes.new('ShaderNodeFloatCurve')
            dummy_curve.name = c_name
            dummy_curve.label = c_name # Ekranda görünmesi için
            dummy_curve.location = (-100, 0 - (i * 250))
        
        scale_node = new_gn_tree.nodes.new('GeometryNodeGroup')
        scale_tree = bpy.data.node_groups.get("Scale From Curve")
        if scale_tree: scale_node.node_tree = scale_tree
        scale_node.name = "Scale From Curve"
        scale_node.location = (550, 0)

        # Scale Kabloları (Tek Size Curve hem X'e hem Y'ye gidiyor!)
        safe_link(new_gn_tree, wot_node, "Curve Driver", size_curve_node, "Value", 0)
        safe_link(new_gn_tree, master_node, "Geometry", scale_node, "Geometry", 0)
        safe_link(new_gn_tree, size_curve_node, "Value", scale_node, "X Scale Curve", 0)
        safe_link(new_gn_tree, size_curve_node, "Value", scale_node, "Y Scale Curve", 0)
        safe_link(new_gn_tree, scale_node, "Geometry", out_node, "Geometry", 0)

        # ESKİ KODDAKİ DEVASA BAĞLANTI DİZİSİ (HATA YAPILMAYACAK YER)
        link_pairs = [
            ("Emitter Object", "EMITTER OBJECT", 0),
            ("Count", "Count", 0),
            ("Lifetime Max", "Lifetime Max", 0),
            ("Lifetime Min", "Lifetime Min", 0),
            ("Normal Velocity Max", "Normal Velocity Max", 0),
            ("Normal Velocity Min", "Normal Velocity Min", 0),
            ("Distribution ratio (cone)", "Distribution ratio (cone)", 0),
            ("Global Gravitiy Max", "Global Gravitiy Max", 0),
            ("Global Gravitiy Min", "Global Gravitiy Min", 0),
            ("Object to Instance", "Object to Instance", 0),
            ("Base X Scale Max", "Max", 0),
            ("Base X Scale Min", "Min", 0),
            ("Base Y Scale Max", "Max", 1),
            ("Base Y Scale Min", "Min", 1),
            ("Camera", "Select Camera", 0),
            ("Camera Track Mode", "Cam Tracking Mode info from other group (negative)", 0),
            ("Inital Angle Max", "Max", 2),
            ("Inital Angle Min", "Min", 2),
            ("Rotation Speed Max", "Max", 3),
            ("Rotation Speed Min", "Min", 3),
            ("x first rotation value", "x first rotation value", 0),
            ("y first rotation value", "y first rotation value", 0),
            ("z first rotation value", "z first rotation value", 0),
            ("x rotation speed max", "x rotation speed max", 0),
            ("x rotation speed min", "x rotation speed min", 0),
            ("y rotation speed max", "y rotation speed max", 0),
            ("y rotation speed min", "y rotation speed min", 0),
            ("z rotation speed max", "z rotation speed max", 0),
            ("z rotation speed min", "z rotation speed min", 0),
            ("Seed", "Seed", -1), 
            ("Wind Collection", "Wind Collection", 0),
            ("Wind Max", "Wind Max", 0),
            ("Wind Min", "Wind Min", 0),
            ("Loop Lenght", "Loop Lenght", 0) # Normal Loop Lenght
        ]
        
        for wot_out, master_in, in_idx in link_pairs:
            safe_link(new_gn_tree, wot_node, wot_out, master_node, master_in, in_index=in_idx)

    else:
        log("WARNING: Master GeoNodes not found. Tree created but left empty.")
# ==========================================================================
# --- YARDIMCI FONKSİYONLAR: EĞRİ ÇİZDİRİCİ ---
# ==========================================================================
def apply_curve_points(curve_node, points_data):
    if not curve_node or not hasattr(curve_node, 'mapping'): return
    
    # Kırpmayı AKTİF ediyoruz. Bu, Blender'ın yazdığımız 
    # Max Y değerine (örneğin 10.4) otomatik zoom yapmasını sağlar.
    curve_node.mapping.use_clip = True
    
    # Veri Sınırlarını Hesapla
    if not points_data:
        points_data = [(0.0, 1.0), (1.0, 1.0)]
    elif len(points_data) == 1:
        points_data.append((1.0, points_data[0][1]))

    times = [p[0] for p in points_data]
    values = [p[1] for p in points_data]
    
    min_x, max_x = min(times), max(times)
    min_y, max_y = min(values), max(values)
    
    # Görsel rahatlık için dikeyde %10'luk bir pay bırak
    margin_y = (max_y - min_y) * 0.1 if max_y != min_y else 0.5
    
    # SINIRLARI YAZ: Bu sayede grafik kutusu tam bu aralığı gösterecek
    curve_node.mapping.clip_min_x = min_x
    curve_node.mapping.clip_max_x = max_x
    curve_node.mapping.clip_min_y = min_y - margin_y
    curve_node.mapping.clip_max_y = max_y + margin_y
    
    curve_map = curve_node.mapping.curves[0]
    
    # Noktaları Temizle ve Yeni Verileri Yaz
    while len(curve_map.points) > 2:
        curve_map.points.remove(curve_map.points[-1])
        
    curve_map.points[0].location = (points_data[0][0], points_data[0][1])
    curve_map.points[1].location = (points_data[1][0], points_data[1][1])
    
    for i in range(2, len(points_data)):
        curve_map.points.new(points_data[i][0], points_data[i][1])
        
    curve_node.mapping.update()

def parse_timeline(xml_block, is_color=False):
    # Boş bloksa (Örn: <tl_angle_speed_key/>) Düz 1.0 çizgisi çek
    if len(xml_block) == 0:
        if is_color: return [(0.0, (1.0, 1.0, 1.0, 1.0)), (1.0, (1.0, 1.0, 1.0, 1.0))]
        return [(0.0, 1.0), (1.0, 1.0)]

    times = []
    values = []
    for child in xml_block:
        if child.tag == 'time':
            times.append(float(child.text.strip()))
        elif child.tag == 'value':
            values.append(float(child.text.strip()))
        elif child.tag == 'value_RGBA':
            parts = child.text.split()
            # BigWorld Renkleri: RGB(0-255), Alpha(0.0-1.0)
            r = float(parts[0]) / 255.0
            g = float(parts[1]) / 255.0
            b = float(parts[2]) / 255.0
            a = float(parts[3])
            values.append((r, g, b, a))
    return list(zip(times, values))
def fill_emitter_nodes_from_xml(emitter_node, instance_obj, settings_obj, emitter_obj, finder, dir_path):
    """
    XML Emitter bloğundaki verileri okur, veri tiplerini otomatik algılar ve 
    eğer Node Gruplarında aynı isimde bir soket varsa değerini doldurur.
    Eşleşmeyen veya atlanan alt blokları konsola Debug Log olarak yazar.
    """
    # 1. Hedef Node Gruplarını Objelerin İçinden Çek
    anim_node = None
    light_node = None
    mat = None
    if instance_obj and instance_obj.data.materials:
        mat = instance_obj.data.materials[0]
        mat_tree = instance_obj.data.materials[0].node_tree
        anim_node = mat_tree.nodes.get("VFX_WoT_Animation")
        light_node = mat_tree.nodes.get("Lighting calculator")

    wot_data_node = None
    if settings_obj and settings_obj.modifiers:
        gn_mod = settings_obj.modifiers.get("VFX_WoT_Controller")
        if gn_mod and gn_mod.node_group:
            wot_data_node = gn_mod.node_group.nodes.get("Wot .vfxbin to blender")
    
    # =====================================================================
    # 0.5 OBJELERİ GEOMETRY NODE GİRİŞLERİNE BAĞLA
    # =====================================================================
    if wot_data_node:
        if "Emitter Object" in wot_data_node.inputs and emitter_obj:
            wot_data_node.inputs["Emitter Object"].default_value = emitter_obj
        if "Object to Instance" in wot_data_node.inputs and instance_obj:
            wot_data_node.inputs["Object to Instance"].default_value = instance_obj
    
    # =====================================================================
    # 1. TEXTURE (DOKU) YÜKLEME VE KAYDETME
    # =====================================================================
    tex_path_raw = emitter_node.findtext("particle.ch_fn_texture")
    
    # SADECE Doku yolunu materyalin Custom Prop'larına yazıyoruz (Shader YOK)
    if mat and tex_path_raw and tex_path_raw.strip():
        mat["particle.ch_fn_texture"] = tex_path_raw.strip()

    if tex_path_raw and tex_path_raw.strip() and finder:
        tex_path_clean = tex_path_raw.strip().replace("\\", "/")
        tex_filename = os.path.basename(tex_path_clean)
        
        found_tex_path = finder.find(target_file=tex_filename, base_dir=dir_path, internal_path=tex_path_clean)
        
        if found_tex_path and mat_tree:
            try:
                img = bpy.data.images.load(found_tex_path, check_existing=True)
                tex_node = next((n for n in mat_tree.nodes if n.type == 'TEX_IMAGE'), None)
                if tex_node:
                    tex_node.image = img
            except Exception as e:
                print(f"[TEXTURE ERROR] Doku yüklenemedi: {found_tex_path} -> {e}")

    # =====================================================================
    # 2. TEXTURE ATLAS (UV) AYARLARI (Sıfır Çökme Garantili)
    # =====================================================================
    def get_safe_uv(tag, default_val):
        raw = emitter_node.findtext(tag)
        if raw and raw.strip():
            try: return float(raw.strip())
            except ValueError: return default_val
        return default_val

    uv_left = get_safe_uv("particle.UV_set.left", 0.0)
    uv_right = get_safe_uv("particle.UV_set.right", 1.0)
    uv_up = get_safe_uv("particle.UV_set.up", 1.0)
    uv_down = get_safe_uv("particle.UV_set.down", 0.0)

    if instance_obj and instance_obj.type == 'MESH':
        mesh = instance_obj.data
        if mesh.uv_layers.active:
            uv_layer = mesh.uv_layers.active.data
            if len(uv_layer) >= 4:
                uv_layer[0].uv = (uv_left, uv_down)  # Bottom-Left
                uv_layer[1].uv = (uv_right, uv_down) # Bottom-Right
                uv_layer[2].uv = (uv_right, uv_up)   # Top-Right
                uv_layer[3].uv = (uv_left, uv_up)    # Top-Left

    # =====================================================================
    # 3. ÖZEL PARAMETRELER VE KONUM AYARLARI (Custom Props & Transforms)
    # =====================================================================
    
    # vt.ui_volume_type -> Emitter (Custom Prop)
    vol_type_raw = emitter_node.findtext("vt.ui_volume_type")
    if vol_type_raw and vol_type_raw.strip() and emitter_obj:
        emitter_obj["vt.ui_volume_type"] = int(vol_type_raw.strip())

    # reserved -> EmitterSettings (Custom Prop) - Örn: #Hard_small yazısını korur
    reserved_raw = emitter_node.findtext("reserved")
    if reserved_raw and reserved_raw.strip() and settings_obj:
        settings_obj["reserved"] = reserved_raw.strip()
    else:
        if settings_obj: settings_obj["reserved"] = ""

    # reserved_buffer -> EmitterSettings (Custom Prop)
    reserved_buf_raw = emitter_node.findtext("reserved_buffer")
    if reserved_buf_raw and reserved_buf_raw.strip() and settings_obj:
        settings_obj["reserved_buffer"] = reserved_buf_raw.strip()
    else:
        if settings_obj: settings_obj["reserved_buffer"] = ""

    # particle.ui_particle_Type -> Instance (Custom Prop)
    part_type_raw = emitter_node.findtext("particle.ui_particle_Type")
    if part_type_raw and part_type_raw.strip() and instance_obj:
        instance_obj["particle.ui_particle_Type"] = int(part_type_raw.strip())

    # emitter.fa_start_pos -> Emitter (Local Location)
    start_pos_raw = emitter_node.findtext("emitter.fa_start_pos")
    if start_pos_raw and start_pos_raw.strip() and emitter_obj:
        parts = start_pos_raw.split()
        if len(parts) == 3:
            try:
                emitter_obj.location = (float(parts[0]), float(parts[2]), float(parts[1]))
            except ValueError:
                pass
    
    # =====================================================================
    # 3.5 VOLUME DIMENSIONS
    # =====================================================================
    dim_x = emitter_node.findtext("f_X_dim_volume")
    dim_y = emitter_node.findtext("f_Z_dim_volume")
    dim_z = emitter_node.findtext("f_Y_dim_volume")

    if all([dim_x, dim_y, dim_z]) and emitter_obj:
        try:
            emitter_obj.dimensions = (float(dim_x), float(dim_y), float(dim_z))
            
            print(f"[SIZE SUCCESS] {emitter_obj.name} boyutları (Blender XZY): {dim_x} x {dim_z} x {dim_y}")
        except ValueError:
            print(f"[SIZE ERROR] Boyut değerleri sayıya çevrilemedi!")
  
    # =====================================================================
    # 4. STANDART NODE DOLDURMA İŞLEMİ
    # =====================================================================
    unmapped_tags = []
    
    # İşlenmiş, gereksiz veya boş olan etiketleri Node taramasından muaf tut
    ignored_tags = [
        "s_emitter_name", "buffer", "Seed", "Frame",
        "particle.ch_fn_texture", "i_RT_shader_num",
        "vt.ui_volume_type", "particle.ui_particle_Type", "emitter.fa_start_pos",
        "f_X_dim_volume", "f_Y_dim_volume", "f_Z_dim_volume",
        "coordinate_system", "fa_epicenter_pos", "fa_epicenter_box", "reserved", "reserved_buffer"
    ]
    #Buffer ve type kısmını araştır.
    
    # 2. XML İçindeki Her Bir Veriyi Tara
    for child in emitter_node:
        tag = child.tag
        
        # --- YENİ: ÖZEL PARAMETRELERİ EMITTER SETTINGS'E YAZ ---
        if tag in ["coordinate_system", "fa_epicenter_pos", "fa_epicenter_box", "type"] and settings_obj:
            val_text = child.text.strip() if child.text else ""
            parts = val_text.split()
            
            # Eğer 3'lü bir sayı dizisiyse (Vektör) tuple olarak yaz
            if len(parts) == 3:
                try:
                    if "pos" in tag.lower() or "box" in tag.lower():
                        settings_obj[tag] = (float(parts[0]), float(parts[2]), float(parts[1]))
                    else:
                        settings_obj[tag] = (float(parts[0]), float(parts[1]), float(parts[2]))
                except ValueError:
                    settings_obj[tag] = val_text
            else:
                settings_obj[tag] = val_text
            
            continue# 3.5 VOLUME DIMENSIONS (KÜP BOYUTLANDIRMA)
        if tag in ignored_tags:
            continue

        # --- TIMELINE (CURVE) İŞLEYİCİ ---
        if tag.startswith("tl_"):
            if len(child) == 0:
                # 1. DOSYADA CURVE BOŞSA: Gereksiz oluşturulmuş Node'ları Blender'dan tamamen sil!
                target_curve = None
                if settings_obj and settings_obj.modifiers.get("VFX_WoT_Controller"):
                    gn_tree = settings_obj.modifiers["VFX_WoT_Controller"].node_group
                    target_curve = gn_tree.nodes.get(tag)
                
                if not target_curve and mat_tree:
                    target_curve = mat_tree.nodes.get(tag)

                if target_curve:
                    if tag == "tl_Color_key":
                        for c_name in ["R Curve", "G Curve", "B Curve", "Alpha Curve"]:
                            c_node = mat_tree.nodes.get(c_name)
                            if c_node: mat_tree.nodes.remove(c_node)
                    else:
                        target_curve.id_data.nodes.remove(target_curve)
                continue # İşlemi bitir ve bir sonraki etikete geç

            if tag == "tl_Color_key":
                color_data = parse_timeline(child, is_color=True)
                if mat_tree:
                    apply_curve_points(mat_tree.nodes.get("R Curve"), [(t, v[0]) for t, v in color_data])
                    apply_curve_points(mat_tree.nodes.get("G Curve"), [(t, v[1]) for t, v in color_data])
                    apply_curve_points(mat_tree.nodes.get("B Curve"), [(t, v[2]) for t, v in color_data])
                    apply_curve_points(mat_tree.nodes.get("Alpha Curve"), [(t, v[3]) for t, v in color_data])
            else:
                curve_data = parse_timeline(child, is_color=False)
                # Önce GeoNodes içinde ara (Size, Speed, Gravity vb.)
                target_curve = None
                if settings_obj and settings_obj.modifiers.get("VFX_WoT_Controller"):
                    gn_tree = settings_obj.modifiers["VFX_WoT_Controller"].node_group
                    target_curve = gn_tree.nodes.get(tag)
                
                # Bulamazsa Material Nodes içinde ara (Color_op_key vb.)
                if not target_curve and mat_tree:
                    target_curve = mat_tree.nodes.get(tag)

                if target_curve:
                    apply_curve_points(target_curve, curve_data)
                else:
                    unmapped_tags.append(f"{tag} (Node Bulunamadı)")
            
            # Curve işlemi bittiği için alttaki standart işleme geçmesini engelle
            continue

        # --- YENİ: ALT BLOKLARI (dw_mode, dw_ext_mode vb.) TARAYAN KISIM ---
        if len(child) > 0:
            # Bu blok bir 'konteyner' (Örn: particle.dw_mode)
            # İçindeki her bir flag etiketini (ps_...) tek tek dönüyoruz.
            for flag in child:
                flag_tag = flag.tag
                flag_val_raw = flag.text.strip() if flag.text else "0"
                
                # 0/1 değerini Boolean'a (True/False) çevir
                flag_bool = True if flag_val_raw == "1" else False
                
                # Bu bayrağı Node soketlerine göndermeyi dene
                flag_assigned = False
                
                # 1. Geometry Node (Wot Data Node) kontrolü
                if wot_data_node and flag_tag in wot_data_node.inputs:
                    try:
                        wot_data_node.inputs[flag_tag].default_value = flag_bool
                        flag_assigned = True
                    except: pass
                
                # 2. Işık veya Animasyon nodunda da olabilir mi? (Opsiyonel)
                if not flag_assigned:
                    for n in [light_node, anim_node]:
                        if n and flag_tag in n.inputs:
                            try:
                                n.inputs[flag_tag].default_value = flag_bool
                                flag_assigned = True
                                break
                            except: pass
                
                # Eğer hiçbir yerde yoksa log listesine ekle (To-Do gibi kalır)
                if not flag_assigned:
                    unmapped_tags.append(f"{tag} -> {flag_tag}")
            
            continue # Alt blok tamamen işlendi, ana döngüde bir sonraki etikete geç.
            
        text_val = child.text.strip() if child.text else ""
        if not text_val:
            continue
            
        # 3. Veri Tipini Otomatik Algıla (Float, Int, Vektör, Bool, String)
        parsed_val = None
        parts = text_val.split()
        
        if len(parts) == 3: # 3'lü sayı dizisi (Vektör / Float Array)
            try: 
                if "pos" in tag.lower() or "box" in tag.lower():
                    parsed_val = (float(parts[0]), float(parts[2]), float(parts[1]))
                else:
                    parsed_val = (float(parts[0]), float(parts[1]), float(parts[2]))
            except ValueError: 
                parsed_val = text_val
        elif text_val.lower() == 'true': 
            parsed_val = True
        elif text_val.lower() == 'false': 
            parsed_val = False
        # YENİ: Eğer metin sadece rakamlardan oluşuyorsa (veya negatif bir tam sayıysa) Integer yap!
        elif text_val.isdigit() or (text_val.startswith('-') and text_val[1:].isdigit()):
            raw_int = int(text_val)
            
            # --- DEVASA DEĞER (OVERFLOW) KORUMASI VE GİZLEME ---
            # Blender soketleri 32-bit (max 2147483647) sınırına takılır.
            if raw_int > 2147483647 or raw_int < -2147483648:
                # Orijinal değeri export için RAW_ önekiyle güvenli bir string olarak sakla
                if settings_obj:
                    settings_obj[f"RAW_{tag}"] = text_val
                # Node'un çökmemesi için sahte bir 0 veriyoruz
                parsed_val = 0
            else:
                parsed_val = raw_int
        else:
            try: 
                parsed_val = float(text_val) # Normal Ondalıklı Sayı
            except ValueError: 
                parsed_val = text_val # String (Örn: texture_path.dds)

        # 4. Node'lara Atama İşlemi
        assigned = False
        
        # A)Işık Nodunda Otomatik Arama
        if light_node and tag in light_node.inputs:
            try:
                light_node.inputs[tag].default_value = parsed_val
                assigned = True
            except: pass
        # B) Geometry Node'da (Wot Data Node) bu isimde bir giriş var mı?
        if wot_data_node and tag in wot_data_node.inputs:
            try:
                wot_data_node.inputs[tag].default_value = parsed_val
                assigned = True
            except Exception as e:
                print(f"[GN HATA] '{tag}' değeri Node'a yazılamadı: {e}")

        # C) Material Node'da (Animation Node) bu isimde bir giriş var mı?
        if anim_node and tag in anim_node.inputs:
            try:
                anim_node.inputs[tag].default_value = parsed_val
                assigned = True
            except Exception as e:
                print(f"[MAT HATA] '{tag}' değeri Node'a yazılamadı: {e}")

        # Eğer Node'ların ikisinde de bu isimde bir giriş bulunamadıysa listeye ekle
        if not assigned:
            unmapped_tags.append(tag)

    # 5. Debug Log (Konsola Eksikleri Yazdır)
    if unmapped_tags:
        em_name = emitter_node.findtext('s_emitter_name', 'Bilinmeyen_Emitter').strip()
        print(f"\n[DEBUG] --- '{em_name}' İÇİN EŞLEŞMEYEN / ATLANAN VERİLER ---")
        for t in unmapped_tags:
            print(f" -> {t}")
        print(f"----------------------------------------------------------\n")