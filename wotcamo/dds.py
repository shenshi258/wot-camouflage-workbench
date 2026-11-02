"""Preserve reference DDS headers; encode every declared mip with edge padding.

DX10 is a container header, not a compression codec. Resolve its DXGI format
before reading payloads, and keep both headers byte-for-byte on export.
"""
from dataclasses import dataclass
from io import BytesIO
import math
import struct
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from .common import ROOT

# DDS_HEADER_DXT10 / DXGI_FORMAT values from Microsoft's DDS specification.
# Typeless BC data is read as UNORM; its original metadata is still preserved.
DXGI = {70:('DXT1',8),71:('DXT1',8),72:('DXT1',8),
        73:('DXT3',16),74:('DXT3',16),75:('DXT3',16),
        76:('DXT5',16),77:('DXT5',16),78:('DXT5',16),
        79:('BC4U',8),80:('BC4U',8),82:('BC5U',16),83:('BC5U',16),
        97:('BC7',16),98:('BC7',16),99:('BC7',16),
        28:('RGBA8',0),29:('RGBA8',0),87:('BGRA8',0),91:('BGRA8',0),
        88:('BGRX8',0),93:('BGRX8',0)}


@dataclass(frozen=True)
class Info:
    width: int
    height: int
    levels: int
    fourcc: str
    offset: int
    block: int
    dxgi_format: int | None = None

    @property
    def format_name(self):
        return f'DX10/{self.fourcc} (DXGI {self.dxgi_format})' if self.dxgi_format is not None else self.fourcc

    def sizes(self):
        w, h = self.width, self.height
        for _ in range(self.levels):
            yield w, h, max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * self.block if self.block else w*h*4
            w, h = max(1, w // 2), max(1, h // 2)


def inspect(data):
    if len(data) < 128 or data[:4] != b"DDS " or struct.unpack_from("<I", data, 4)[0] != 124:
        raise ValueError("DDS 文件头无效")
    h, w = struct.unpack_from("<II", data, 12)
    levels = max(1, struct.unpack_from("<I", data, 28)[0])
    fourcc = data[84:88].decode("ascii", errors="replace")
    blocks = {"DXT1": 8, "DXT3": 16, "DXT5": 16, "ATI1":8,"BC4U":8,"ATI2": 16, "BC5U": 16}
    offset=128;dxgi=None
    if fourcc=='DX10':
        if len(data)<148:raise ValueError('DDS DX10 扩展头不完整')
        dxgi,dimension,misc,array_size,alpha=struct.unpack_from('<5I',data,128)
        if dimension!=3 or array_size!=1 or misc&4:
            raise ValueError('仅支持二维单张 DDS；暂不支持数组、立方体或体积贴图')
        if alpha not in (0,1,3):raise ValueError('暂不支持预乘或自定义透明模式的 DX10 DDS；原资源未转换')
        if dxgi not in DXGI:
            raise ValueError(f'暂不支持 DDS DX10 的 DXGI 格式 {dxgi}；原资源未转换')
        fourcc,block=DXGI[dxgi];offset=148
    elif fourcc not in blocks:
        raise ValueError(f"暂不支持 DDS 格式 {fourcc!r}；保留原资源，未转换")
    else:block=blocks[fourcc]
    if not w or not h or levels > int(math.log2(max(w, h))) + 1:
        raise ValueError("DDS 尺寸或 mip 级数无效")
    depth = struct.unpack_from("<I", data, 24)[0]
    caps2 = struct.unpack_from("<I", data, 112)[0]
    if depth > 1 or caps2:
        raise ValueError("仅支持二维单张 DDS")
    info = Info(w, h, levels, fourcc, offset, block, dxgi)
    expected = info.offset + sum(n for _, _, n in info.sizes())
    if len(data) != expected:
        raise ValueError(f"DDS mip 链体积错误：实际 {len(data)}，应为 {expected}")
    return info


def decode(data):
    info=inspect(data)
    return _decode_level(data[:info.offset],data[info.offset:info.offset+next(info.sizes())[2]],info,info.width,info.height)


def _decode_level(header,payload,info,w,h):
    if not info.block:
        rawmode='RGBA' if info.fourcc=='RGBA8' else ('BGRA' if info.fourcc=='BGRA8' else 'BGRX')
        return Image.frombytes('RGBA' if rawmode!='BGRX' else 'RGB',(w,h),payload,'raw',rawmode).convert('RGBA')
    header=bytearray(header)
    struct.pack_into('<II',header,12,h,w);struct.pack_into('<I',header,20,len(payload));struct.pack_into('<I',header,28,1)
    # Pillow does not recognize the sRGB aliases for BC1/2/3. They have the
    # same block layout; normalize only this temporary decode header.
    if info.dxgi_format in (72,75,78):struct.pack_into('<I',header,128,info.dxgi_format-1)
    with Image.open(BytesIO(bytes(header)+payload)) as im:
        return im.convert("RGBA")


def _encode_bc7(image):
    tool=ROOT/'tools/wot_toolkit/texconv.exe'
    if not tool.is_file():raise ValueError('缺少 BC7 编码器，请使用完整的工作台程序。')
    cache=ROOT/'.cache/dds_codec';cache.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as folder:
        folder=Path(folder);source=folder/'image.png';image.save(source)
        try:
            process=subprocess.run([str(tool),'-nologo','-nogpu','-m','1','-f','BC7_UNORM','--ignore-srgb','-o',str(folder),str(source)],
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError,subprocess.TimeoutExpired) as error:
            raise ValueError('BC7 编码未完成：'+str(error)) from error
        output=folder/'image.dds'
        if process.returncode or not output.is_file():raise ValueError('BC7 编码失败，原资源未修改。')
        raw=output.read_bytes();info=inspect(raw)
        if info.fourcc!='BC7' or info.levels!=1 or (info.width,info.height)!=image.size:raise ValueError('BC7 编码器返回了错误的结构。')
        return raw[info.offset:]


def _encode_level(image, fourcc):
    # Explicit edge replication prevents transparent black at tiny mip edges.
    arr = np.asarray(image.convert("RGBA"))
    h, w = arr.shape[:2]
    arr = np.pad(arr, ((0, (-h) % 4), (0, (-w) % 4), (0, 0)), mode="edge")
    if fourcc=='BC7':return _encode_bc7(Image.fromarray(arr))
    if fourcc in ('BC4U','ATI1'):
        # BC4_UNORM has the exact layout of a BC3 alpha block.
        plane=arr.copy();plane[...,3]=arr[...,0];plane[...,:3]=0
        raw=_encode_level(Image.fromarray(plane),'DXT5')
        return b''.join(raw[i:i+8] for i in range(0,len(raw),16))
    mode = ("RGBA" if np.any(arr[..., 3] < 128) else "RGB") if fourcc == "DXT1" else ("RGB" if fourcc in ("ATI2", "BC5U") else "RGBA")
    im = Image.fromarray(arr).convert(mode)
    out = BytesIO()
    im.save(out, format="DDS", pixel_format="BC5" if fourcc in ("ATI2", "BC5U") else fourcc)
    raw = out.getvalue()
    return raw[148 if raw[84:88] == b"DX10" else 128:]


def encode_like(image, reference):
    info = inspect(reference)
    if image.size != (info.width, info.height):
        raise ValueError("输出尺寸必须与客户端原贴图一致")
    result = bytearray(reference[:info.offset])
    mip = image.convert("RGBA")
    for w, h, count in info.sizes():
        if mip.size != (w, h):
            # DDS alpha may contain material data, not opacity. Filter channels
            # independently so transparent texels do not erase RGB/mask data.
            mip = Image.merge('RGBA',tuple(c.resize((w,h),Image.Resampling.BOX) for c in mip.split()))
        if info.block:payload = _encode_level(mip, info.fourcc)
        else:
            arr=np.asarray(mip).copy()
            if info.fourcc in ('BGRA8','BGRX8'):arr=arr[...,[2,1,0,3]]
            if info.fourcc=='BGRX8':arr[...,3]=255
            payload=arr.tobytes()
        if len(payload) != count:
            raise ValueError("DDS 编码器返回了错误的块长度")
        result.extend(payload)
    result = bytes(result)
    verify_matches(result, reference)
    if info.fourcc == "DXT1":
        expected = np.asarray(image.convert("RGBA"))[..., 3] < 128
        actual = np.asarray(decode(result))[..., 3] < 128
        if not np.array_equal(expected, actual):
            raise ValueError("DXT1 透明通道编码不一致，已停止生成")
    return result


def verify_matches(data, reference):
    a, b = inspect(data), inspect(reference)
    if a != b or len(data) != len(reference) or data[:a.offset] != reference[:b.offset]:
        raise ValueError("生成的 DDS 结构与原版不符")
    return a


def decode_mips(data):
    info = inspect(data)
    offset = info.offset
    for w, h, n in info.sizes():
        yield _decode_level(data[:info.offset],data[offset:offset+n],info,w,h)
        offset += n
