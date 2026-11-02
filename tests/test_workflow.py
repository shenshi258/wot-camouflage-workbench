from pathlib import Path
from io import BytesIO
import struct
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from wotcamo import dds, modpack
from wotcamo.common import safe_join, write_json
from wotcamo.prompt import Recipe, parse
from wotcamo.compose import derive, compose_am


def reference(w, h, fmt, levels):
    # Independent constant-block fixture, including a deliberately non-square chain.
    buf = BytesIO()
    Image.new("RGBA", (4, 4), (64, 128, 192, 255)).save(buf, format="DDS", pixel_format=fmt)
    sample = buf.getvalue()
    header = bytearray(sample[:128])
    struct.pack_into("<II", header, 12, h, w)
    struct.pack_into("<I", header, 28, levels)
    payload = bytearray()
    block = sample[128:]
    for _ in range(levels):
        payload.extend(block * (((w+3)//4)*((h+3)//4)))
        w, h = max(1, w//2), max(1, h//2)
    return bytes(header+payload)


class DDSTests(unittest.TestCase):
    def test_rectangular_and_tiny_mips_opaque(self):
        for fmt in ("DXT1", "DXT3", "DXT5"):
            for w, h, levels in ((32, 8, 6), (8, 32, 6), (7, 3, 3), (1, 8, 4), (1, 1, 1), (16, 8, 1)):
                with self.subTest(fmt=fmt, dimensions=(w, h), levels=levels):
                    ref = reference(w, h, fmt, levels)
                    out = dds.encode_like(Image.new("RGBA", (w, h), (110, 160, 210, 255)), ref)
                    self.assertEqual(len(ref), len(out))
                    self.assertEqual(out[:128], ref[:128])
                    mips = list(dds.decode_mips(out))
                    self.assertEqual(len(mips), levels)
                    for im in mips:
                        self.assertEqual(np.asarray(im)[..., 3].min(), 255)
                        self.assertLess(np.abs(np.asarray(im)[..., :3].astype(int)-[110, 160, 210]).max(), 12)

    def test_corruption_rejected(self):
        good = reference(32, 8, "DXT5", 6)
        for bad in (good[:-1], good+b"extra", b"BAD!"+good[4:]):
            with self.assertRaises(ValueError):
                dds.inspect(bad)

    def test_reference_dimensions_required(self):
        with self.assertRaises(ValueError):
            dds.encode_like(Image.new("RGBA", (2, 2)), reference(4, 4, "DXT1", 1))


class RecipeTests(unittest.TestCase):
    def test_parser_and_part_default(self):
        r = parse("沙漠黄底色，白色虎纹，中度做旧，哑光，洗车，屏蔽官方涂装，number_07.png", [Path("number_07.png")])
        self.assertEqual(r.parts, ["all"])
        self.assertEqual(r.decals, ["number_07.png"])
        self.assertEqual((r.gmm_specular, r.gmm_brightness), (130, 40))

    def test_channel_preservation_and_bc1_alpha_rule(self):
        im = Image.new("RGBA", (8, 8), (15, 65, 125, 235))
        r = Recipe(ao_clean=True, block_official_camo=True)
        bc1 = np.asarray(derive(im, "AO", "DXT1", r))
        bc3 = np.asarray(derive(im, "AO", "DXT5", r))
        self.assertTrue(np.all(bc1[..., 0] == 15))
        self.assertTrue(np.all(bc1[..., 1:3] == 255))
        self.assertTrue(np.all(bc1[..., 3] == 235))
        self.assertTrue(np.all(bc3[..., 3] == 0))
        gmm = np.asarray(derive(im, "GMM", "DXT1", r))
        self.assertTrue(np.all(gmm[..., 0] == 15))
        self.assertTrue(np.all(gmm[..., 2] == 0))
        anm = np.asarray(derive(im, "ANM", "DXT5", Recipe(normal_strength=.5)))
        self.assertTrue(np.all(anm[..., 0] == 15))
        self.assertTrue(np.all(anm[..., 2] == 125))

    def test_deterministic_and_hd_layout(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            r = Recipe(wear=0)
            lo, _ = compose_am(Image.new("RGBA", (64, 64), "white"), None, r, folder, "tank_AM.dds")
            hi, _ = compose_am(Image.new("RGBA", (128, 128), "white"), None, r, folder, "tank_AM_hd.dds")
            same, _ = compose_am(Image.new("RGBA", (64, 64), "white"), None, r, folder, "tank_AM.dds")
            self.assertEqual(lo.tobytes(), same.tobytes())
            self.assertLess(np.abs(np.asarray(lo).astype(int)-np.asarray(hi.resize(lo.size)).astype(int)).mean(), 12)


class DeliveryTests(unittest.TestCase):
    def test_paths_reject_escape(self):
        for rel in ("../outside", "C:/file", "/etc/file", "a/../../out"):
            with self.assertRaises(ValueError):
                safe_join(Path.cwd(), rel)

    def test_install_backup_rollback_and_tamper(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            root = Path(folder)
            game, out = root / "game", root / "out"
            game.mkdir()
            (game / "paths.xml").write_text("<root><Paths><Path>./res_mods/2.4.1.0</Path></Paths></root>")
            old = game / "res_mods/2.4.1.0/vehicles/test/old.dds"
            old.parent.mkdir(parents=True)
            old.write_bytes(b"existing mod")
            files = {"vehicles/test/old.dds": b"new mod", "vehicles/test/new.dds": b"fresh mod"}
            for rel, data in files.items():
                dest = safe_join(out / "res", rel)
                dest.parent.mkdir(exist_ok=True, parents=True)
                dest.write_bytes(data)
            write_json(out / "report.json", {"complete": True, "game_version": "2.4.1.0", "files": [{"path": p, "sha256": modpack.digest(d)} for p, d in files.items()]})
            with patch.object(modpack, "ROOT", root):
                backup = modpack.install(out, game, lambda s: None)
                self.assertEqual(old.read_bytes(), b"new mod")
                old.write_bytes(b"another mod")
                with self.assertRaises(ValueError):
                    modpack.rollback(backup, lambda s: None, wot_root=game)
                self.assertEqual(old.read_bytes(), b"another mod")
                old.write_bytes(b"new mod")
                modpack.rollback(backup, lambda s: None, wot_root=game)
                self.assertEqual(old.read_bytes(), b"existing mod")
                self.assertFalse((old.parent / "new.dds").exists())
                (out / "res/vehicles/test/new.dds").write_bytes(b"tamper")
                with self.assertRaises(ValueError):
                    modpack.checked_files(out)


if __name__ == "__main__":
    unittest.main()
